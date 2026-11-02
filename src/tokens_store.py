"""Generation with stored token IDs and log-probabilities (migration 001). Used for the smoke run and the held-out run; the dev outputs
keep their v2 scoring (their token IDs were not stored).

Flow:  generate_tokens()  ->  clean_output()  ->  store_tokens()  ->  load_tokens()  ->  C2 / D4a / D4b read only from the table.

The sampling scores of generate() are computed after temperature 0.3 and top-p. D4a is defined on a plain softmax at temperature 1, so the
log-probabilities here come from a second, teacher-forced pass over the exact generated IDs (the same quantity as pilot.token_probs, but on
IDs that are stored instead of text that is re-tokenized).
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import platform
import re
import subprocess
import time
from pathlib import Path

import torch
import yaml

from pilot import CFG, PREAMBLE, ROOT
from prompt_pin import DATE_STRING, build_prompt_ids, uses_date

LOGP_FLOOR = math.log(1e-12)   # v2 clamps probabilities at 1e-12 before taking logs; kept so D4a means are comparable


@torch.no_grad()
def generate_tokens(tok, model, body: str, seed: int) -> dict:
    """One generation for the whole text. Returns IDs, plain-softmax log-probabilities and character offsets into the raw decoded text."""
    prompt = build_prompt_ids(tok, body).to(CFG["device"])
    torch.manual_seed(seed)
    t0 = time.perf_counter()
    out = model.generate(prompt, do_sample=True, temperature=CFG["temperature"], top_p=CFG["top_p"],
                         max_new_tokens=CFG["max_new_tokens"], pad_token_id=tok.eos_token_id, return_dict_in_generate=True)
    gen_s = time.perf_counter() - t0
    n_prompt = prompt.shape[1]
    ids = [i for i in out.sequences[0, n_prompt:].tolist() if i not in tok.all_special_ids]   # same filter as v2: the stored IDs are what is scored
    t0 = time.perf_counter()
    full = torch.cat([prompt, torch.tensor([ids], device=prompt.device)], dim=1)
    logits = model(full).logits[0, n_prompt - 1:-1].float()
    logp = torch.log_softmax(logits, dim=-1).gather(1, torch.tensor(ids, device=logits.device)[:, None])[:, 0].tolist()
    score_s = time.perf_counter() - t0
    raw, offsets = token_offsets(tok, ids)
    return dict(ids=ids, logp=logp, raw=raw, offsets=offsets, gen_s=gen_s, score_s=score_s,
                hit_limit=len(ids) >= CFG["max_new_tokens"], n_prompt=n_prompt)


def token_offsets(tok, ids: list[int]) -> tuple[str, list[tuple[int, int]]]:
    """Decode the prefix once per token and record the character range each token adds to the raw text.
    A prefix that ends in a replacement character (a multi-byte character split across tokens) adds nothing yet; the next token takes it."""
    offsets, prev = [], 0
    for i in range(len(ids)):
        cur = tok.decode(ids[: i + 1])
        if cur.endswith("�") and i < len(ids) - 1:
            offsets.append((prev, prev))
            continue
        offsets.append((prev, len(cur)))
        prev = len(cur)
    return tok.decode(ids), offsets


def clean_output(raw: str) -> tuple[str, int, dict]:
    """Cleaning is a logged step: drop a lead-in line ("Here is the rewritten text:"). Returns cleaned text, the number of characters cut at
    the start, and a log entry. The cleaned text is raw[cut:], so every cleaned-text offset maps back to a token by adding the cut."""
    m = PREAMBLE.match(raw)
    cut = m.end() if m else 0
    return raw[cut:], cut, {"removed_lead_in": raw[:cut] if cut else None}


def store_tokens(conn, base_output_id: int, gen: dict, cut: int, source: str = "generation") -> None:
    conn.execute("UPDATE base_outputs SET raw_output=%s, clean_cut=%s, token_source=%s WHERE id=%s",
                 (gen["raw"], cut, source, base_output_id))
    conn.execute("DELETE FROM output_tokens WHERE base_output_id=%s", (base_output_id,))
    with conn.cursor() as cur:
        cur.executemany("INSERT INTO output_tokens VALUES (%s,%s,%s,%s,%s,%s)",
                        [(base_output_id, k, t, lp, a, z) for k, (t, lp, (a, z)) in enumerate(zip(gen["ids"], gen["logp"], gen["offsets"]))])


def load_tokens(conn, base_output_id: int) -> list[tuple[int, int, float]]:
    """(start, end, log-probability) per token in the coordinates of the CLEANED output; tokens inside the cut lead-in are dropped."""
    cut = conn.execute("SELECT clean_cut FROM base_outputs WHERE id=%s", (base_output_id,)).fetchone()[0]
    if cut is None:
        raise ValueError(f"base_output {base_output_id} has no stored tokens")
    rows = conn.execute("SELECT char_start, char_end, logprob FROM output_tokens WHERE base_output_id=%s ORDER BY position",
                        (base_output_id,)).fetchall()
    return [(a - cut, z - cut, lp) for a, z, lp in rows if z > cut]


def prob_spans(tokens):
    """Same shape as pilot.token_probs() returns, so pilot.span_prob() and run_conditions() (C2, D4b) read the table unchanged."""
    return [(a, z, math.exp(max(lp, LOGP_FLOOR))) for a, z, lp in tokens]


def sentence_logprob(tokens, start: int, end: int) -> float:
    """D4a: mean token log-probability of the tokens overlapping [start, end) in the cleaned output (0.0 if none, as in v2)."""
    lps = [max(lp, LOGP_FLOOR) for a, z, lp in tokens if a < end and z > start]
    return sum(lps) / len(lps) if lps else 0.0


PINS = yaml.safe_load(open(ROOT / "config/model_pins.yaml"))["generator"]


def sha256_stream(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(1 << 24):
            h.update(chunk)
    return h.hexdigest()


def load_model_pinned():
    """Load the generator at the revision in config/model_pins.yaml, offline, and check the weight file's SHA-256 against the pin
    (the cache's blob names are not content hashes, so the file is hashed: a few seconds, once per process, outside every per-output timer)."""
    from huggingface_hub import try_to_load_from_cache
    from transformers import AutoModelForCausalLM, AutoTokenizer
    repo, rev = PINS["repo"], PINS["revision"]
    if repo != CFG["model"]:
        raise SystemExit(f"config model {CFG['model']} is not the pinned generator {repo}")
    w = try_to_load_from_cache(repo, PINS["weights"], revision=rev)
    if not isinstance(w, str):
        raise SystemExit(f"{repo}@{rev[:10]} is not in the local cache")
    if sha256_stream(w) != PINS["weights_sha256"]:
        raise SystemExit(f"weights of {repo}@{rev[:10]} differ from the pinned SHA-256")
    tok = AutoTokenizer.from_pretrained(repo, revision=rev, local_files_only=True)
    model = AutoModelForCausalLM.from_pretrained(repo, revision=rev, local_files_only=True, dtype=getattr(torch, CFG["dtype"]))
    model.to(CFG["device"]).eval()
    return tok, model


def _sh(*args, timeout=5) -> str:
    try:
        return subprocess.run(list(args), capture_output=True, text=True, timeout=timeout).stdout
    except Exception:
        return ""


def machine_state() -> dict:
    """Is the machine in the state a timing needs? On mains, no low-power mode, no thermal limit, nothing else busy. Cheap enough to call per output."""
    batt, pm, therm = _sh("pmset", "-g", "batt"), _sh("pmset", "-g"), _sh("pmset", "-g", "therm")
    num = lambda pat, txt: (lambda m: int(m.group(1)) if m else None)(re.search(pat, txt))
    busy = []
    for line in _sh("ps", "-Ao", "pid,pcpu,comm", "-r").splitlines()[1:8]:
        pid, cpu, comm = line.split(None, 2)
        if int(pid) != os.getpid() and float(cpu) >= 10:
            busy.append(f"{Path(comm).name} {cpu}%")
    return dict(on_ac="AC Power" in batt, battery=(re.search(r"(\d+)%", batt) or [None, None])[1],
                low_power_mode=num(r"lowpowermode\s+(\d)", pm), power_mode=num(r"\bpowermode\s+(\d)", pm),
                cpu_speed_limit=num(r"CPU_Speed_Limit\s*=\s*(\d+)", therm), load1=round(os.getloadavg()[0], 2), cpus=os.cpu_count(),
                other_busy=busy)


def git_state() -> dict:
    git = lambda *a: subprocess.run(["git", *a], cwd=ROOT, capture_output=True, text=True).stdout
    dirty = [l for l in git("status", "--porcelain").splitlines() if l.strip()]
    return dict(commit=git("rev-parse", "HEAD").strip(), dirty=bool(dirty), dirty_files=[l[3:] for l in dirty][:60])


def code_sha256() -> str:
    """Hash of the code and config that produced a run, so a dirty-tree run (smoke, dev only) can still be told apart from another."""
    h = hashlib.sha256()
    for pat in ("src/*.py", "config/*.yaml", "db/migrations/*.sql", "wordlists/*.txt", "wordlists/*.tsv"):
        for f in sorted(ROOT.glob(pat)):
            h.update(f.name.encode()); h.update(f.read_bytes())
    return h.hexdigest()


def run_manifest(tok, model, seed: int, prompt_text: str) -> dict:
    """Everything needed to judge whether two runs are comparable; stored in runs.manifest."""
    import sentence_transformers, spacy, transformers   # noqa: E401
    cfg_json = json.dumps(CFG, sort_keys=True, default=str)
    g = git_state()
    return dict(model=CFG["model"], model_revision=PINS["revision"], weights_sha256=PINS["weights_sha256"],
                chat_template_sha256=hashlib.sha256((tok.chat_template or "").encode()).hexdigest(),
                torch=torch.__version__, transformers=transformers.__version__, tokenizers=__import__("tokenizers").__version__,
                sentence_transformers=sentence_transformers.__version__, spacy=spacy.__version__, python=platform.python_version(),
                platform=platform.platform(), threads=torch.get_num_threads(), seed=seed, dtype=CFG["dtype"], temperature=CFG["temperature"],
                top_p=CFG["top_p"], max_new_tokens=CFG["max_new_tokens"], prompt_sha256=hashlib.sha256(prompt_text.encode()).hexdigest(),
                chat_template_uses_date=uses_date(tok), chat_template_date_string=DATE_STRING if uses_date(tok) else None,
                config_sha256=hashlib.sha256(cfg_json.encode()).hexdigest(), code_sha256=code_sha256(), git_commit=g["commit"],
                git_dirty=g["dirty"], git_dirty_files=g["dirty_files"], machine_at_start=machine_state())


LEAD_IN_ONLY = re.compile(PREAMBLE.pattern + r"$", re.I)   # the removed text must be one lead-in line plus whitespace, nothing else


def check_round_trip(conn, tok, base_output_id: int, in_memory: dict) -> dict:
    """Per-output integrity checks on what is in the database, not on what is in memory."""
    raw, cut, out = conn.execute("SELECT raw_output, clean_cut, output FROM base_outputs WHERE id=%s", (base_output_id,)).fetchone()
    rows = conn.execute("SELECT token_id, char_start, char_end FROM output_tokens WHERE base_output_id=%s ORDER BY position", (base_output_id,)).fetchall()
    ids = [r[0] for r in rows]
    tiles = bool(rows) and rows[0][1] == 0 and rows[-1][2] == len(raw) and all(rows[k][2] == rows[k + 1][1] for k in range(len(rows) - 1))
    return dict(decode=tok.decode(ids) == raw, tiles=tiles, cleaned=raw[cut:] == out, ids_match_memory=ids == in_memory["ids"],
                lead_in_only=(cut == 0) or bool(LEAD_IN_ONLY.match(raw[:cut])) and bool(raw[cut:].strip()))
