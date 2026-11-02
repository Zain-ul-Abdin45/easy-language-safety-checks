"""Why do 51 of 64 stored Llama dev outputs not regenerate (v2: 8)?  Hypothesis: the Llama 3.2 chat template writes today's date into the system
prompt (strftime_now), the dev outputs were generated on 2026-10-31, and the reproduction ran on 2026-11-02.

  diverge  Regenerate every dev C1 output with (a) today's date and (b) the generation-day date. For each: rendered-prompt SHA-256, whether the stored
           text is contained in the regeneration (the v2 test), and the first divergent token position when it is not.
  retok    Score D4 on all dev C1 outputs without regenerating: the stored text is re-tokenized and teacher-forced after the generation-day prompt.

Run:  PILOT_CONFIG=config/second_model.yaml DB_SCHEMA=p3_second .venv/bin/python src/llama_d4_diagnosis.py diverge|retok
Writes results/v3/llama_d4_diagnosis.md / results/v3/llama_d4_retok.md (+ llama_d4_retok_scores.json)."""
import hashlib
import json
import sys
from pathlib import Path

import numpy as np
import torch

import pilot
from db import connect

ROOT = Path(__file__).resolve().parents[1]
GEN_DATE = "31 Oct 2026"   # runs.created_at of every p3_second run is 2026-10-31


def prompt_ids(tok, body, date=None):
    msgs = [{"role": "system", "content": pilot.SYSTEM}, {"role": "user", "content": pilot.INSTRUCTION.format(text=body)}]
    kw = {"date_string": date} if date else {}
    return tok.apply_chat_template(msgs, add_generation_prompt=True, return_tensors="pt", return_dict=True, **kw)["input_ids"]


def rendered_sha(tok, body, date=None):
    msgs = [{"role": "system", "content": pilot.SYSTEM}, {"role": "user", "content": pilot.INSTRUCTION.format(text=body)}]
    kw = {"date_string": date} if date else {}
    return hashlib.sha256(tok.apply_chat_template(msgs, add_generation_prompt=True, tokenize=False, **kw).encode()).hexdigest()[:12]


@torch.no_grad()
def regen(tok, model, body, seed, date):
    p = prompt_ids(tok, body, date).to(pilot.CFG["device"])
    torch.manual_seed(seed)
    out = model.generate(p, do_sample=True, temperature=pilot.CFG["temperature"], top_p=pilot.CFG["top_p"],
                         max_new_tokens=pilot.CFG["max_new_tokens"], pad_token_id=tok.eos_token_id)
    return [i for i in out[0, p.shape[1]:].tolist() if i not in tok.all_special_ids]


def rows(conn):
    return conn.execute("""SELECT b.id, b.text_id, r.seed, t.body, co.output FROM condition_outputs co JOIN base_outputs b ON b.id=co.base_output_id
                           JOIN runs r ON r.id=b.run_id JOIN texts t ON t.id=b.text_id WHERE co.condition='C1' AND t.split='dev'
                           ORDER BY b.text_id, r.seed""").fetchall()


def first_divergence(tok, ids, out):
    """Character and token position where the regeneration first differs from the stored text (both lead-in-stripped)."""
    from tokens_store import clean_output, token_offsets
    raw, offs = token_offsets(tok, ids)
    cleaned, cut, _ = clean_output(raw)
    a, b = cleaned.strip(), out.strip()
    lead = len(cleaned) - len(cleaned.lstrip())
    n = next((i for i, (x, y) in enumerate(zip(a, b)) if x != y), min(len(a), len(b)))
    char = cut + lead + n
    tokpos = next((k for k, (s, e) in enumerate(offs) if s <= char < e), len(ids))
    return n, tokpos, len(ids)


def diverge():
    tok, model = pilot.load_model()
    L = ["# Llama D4 mismatch: diagnosis", "", f"Dev C1 outputs of `{pilot.CFG['model']}` (seeds 1, 2), generated 2026-10-31. Regenerated now (2026-11-02) with (a) the template's own date (today) and (b) date_string = `{GEN_DATE}`.", "",
         "| text | seed | prompt hash today | prompt hash generation day | stored text found: today | stored text found: generation day | first divergent token (today): char / token of N | first divergent token (generation day) |", "|---|---|---|---|---|---|---|---|"]
    ok = {"today": 0, "gen": 0}; n = 0
    with connect() as conn:
        for b_id, text_id, seed, body, out in rows(conn):
            res = {}
            for k, d in (("today", None), ("gen", GEN_DATE)):
                ids = regen(tok, model, body, seed, d)
                found = out.strip() in tok.decode(ids)
                ok[k] += found
                res[k] = ("yes" if found else "no", "" if found else "%d / %d of %d" % first_divergence(tok, ids, out))
            n += 1
            L.append(f"| {text_id} | {seed} | {rendered_sha(tok, body)} | {rendered_sha(tok, body, GEN_DATE)} | {res['today'][0]} | {res['gen'][0]} | {res['today'][1]} | {res['gen'][1]} |")
            print(n, text_id, seed, res, flush=True)
    L += ["", f"Stored text found in the regeneration: today's date {ok['today']} / {n}; generation-day date {ok['gen']} / {n}."]
    (ROOT / "results/v3/llama_d4_diagnosis.md").write_text("\n".join(L) + "\n")


def retok():
    import d4_screen as D
    tok, model = pilot.load_model()

    def scorer(body, seed, out):
        p = prompt_ids(tok, body, GEN_DATE).to(pilot.CFG["device"])
        ids = tok(out.strip(), add_special_tokens=False)["input_ids"]
        return pilot.token_probs(tok, model, p, ids)
    with connect() as conn:
        sents, mismatch = D.collect(conn, tok, model, scorer=scorer)
    (ROOT / "results/v3/llama_d4_retok_scores.json").write_text(json.dumps(dict(sents=sents, mismatch=mismatch)))
    v2 = json.loads((ROOT / "results/llama_dev24/d4_scores.json").read_text())["sents"]
    rng = np.random.default_rng(0)   # one stream in table order, as d4_screen.main does, so the v2 rows reproduce the published ones
    L = ["# Llama 3.2 1B, D4 on all dev outputs by re-tokenizing the stored text (sensitivity; v2 regenerated and lost outputs that did not regenerate)", "",
         f"Stored C1 text re-tokenized and teacher-forced after the generation-day prompt (`date_string = {GEN_DATE}`), plain softmax, no regeneration. "
         f"{len(sents)} sentences ({sum(s['harmful'] for s in sents)} harmful) in all 64 outputs, against {len(v2)} ({sum(s['harmful'] for s in v2)} harmful) in the v2 table. "
         "The lead-in line (\"Here's the rewritten text:\") was cut before storage, so the model is not conditioned on it here: a small difference from the generation-time scoring.", "",
         "| scoring | score | flagged / sentences | recall | random recall | difference [95%] | AUC [95%] | Gate A |", "|---|---|---|---|---|---|---|---|"]
    for label, S in (("v2 (regenerated, 56 of 64 outputs)", [dict(x, unit=tuple(x["unit"])) for x in v2]), ("re-tokenized, 64 of 64 outputs", sents)):
        for key, name in (("a", "D4a"), ("b", "D4b")):
            r = D.evaluate(S, key, 5000, rng)
            ok = r["lo"] > 0 and r["alo"] > 0.5 and r["rate"] <= 0.30 + 1e-9
            L.append(f"| {label} | {name} | {r['F']} / {r['n']} | {100*r['rec']:.0f}% | {100*r['rnd']:.0f}% | {100*r['diff']:+.0f} points [{100*r['lo']:+.0f}, {100*r['hi']:+.0f}] | "
                     f"{r['auc']:.3f} [{r['alo']:.3f}, {r['ahi']:.3f}] | {'passes' if ok else 'does not pass'} |")
    # same sentences in both: how much does re-tokenizing move D4a?
    k = lambda s: (s["unit"], round(s["b"], 12), s["harmful"])
    by = {}
    for s in sents:
        by.setdefault(tuple(s["unit"]), []).append(s)
    by2 = {}
    for s in v2:
        by2.setdefault(tuple(s["unit"]), []).append(s)
    d = [abs(x["a"] - y["a"]) for u in by2 if u in by and len(by[u]) == len(by2[u]) for x, y in zip(by2[u], by[u])]
    if d:
        L += ["", f"Outputs present in both with the same number of sentences: {len(d)} sentences; D4a difference between the two scorings: median {np.median(d):.3f}, max {max(d):.3f} (mean log-probability units)."]
    (ROOT / "results/v3/llama_d4_retok.md").write_text("\n".join(L) + "\n")
    print("\n".join(L))


if __name__ == "__main__":
    {"diverge": diverge, "retok": retok}[sys.argv[1]]()
