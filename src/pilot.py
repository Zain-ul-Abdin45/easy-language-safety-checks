"""Pilot run: generate once per text and seed, apply C1-C5 to the same output, store everything.

Run:  .venv/bin/python src/pilot.py [--limit N] [--seeds 1 2]
Settings: config/pilot.yaml (or the file in PILOT_CONFIG). Writes to database easylang_p3, schema p3
(or DB_SCHEMA).
"""
from __future__ import annotations

import argparse
import os
import difflib
import json
import math
import re
import resource
import time
from dataclasses import dataclass, field
from pathlib import Path

import spacy
import textstat
from sentence_transformers import SentenceTransformer
import torch
import yaml
from transformers import AutoModelForCausalLM, AutoTokenizer

from db import connect

ROOT = Path(__file__).resolve().parents[1]
CFG = yaml.safe_load(open(ROOT / os.environ.get("PILOT_CONFIG", "config/pilot.yaml")))
NLP = spacy.load("en_core_web_sm")
EMB = SentenceTransformer(CFG["align_model"], device="cpu")
PREAMBLE = re.compile(r"^\s*(here('s| is)[^\n]*?:|sure[^\n]*?:)\s*", re.I)

EASY = {w.strip().lower() for w in open(ROOT / "wordlists/dale_chall_easy_words.txt") if w.strip()}
REPL = {}
for line in open(ROOT / "wordlists/replacements.tsv"):
    if line.strip() and not line.startswith("#"):
        hard, easy = line.rstrip("\n").split("\t")
        REPL[hard.lower()] = easy

SYSTEM = "You rewrite workplace onboarding texts in Easy-to-Read English for new staff."
INSTRUCTION = """Rewrite the text below in Easy-to-Read English.
Rules:
- Use short sentences. One idea per sentence.
- Use common, everyday words.
- Use active voice. Speak to the reader as "you".
- Keep every name, date, time, number, place and condition.
- Do not add information that is not in the text.
Write only the rewritten text.

Text:
{text}"""


# ---------------------------------------------------------------- model
def load_model():
    path = str(ROOT / CFG["model_path"]) if CFG.get("model_path") else CFG["model"]   # local copy of a gated model; CFG["model"] stays the recorded name
    tok = AutoTokenizer.from_pretrained(path)
    model = AutoModelForCausalLM.from_pretrained(path, dtype=getattr(torch, CFG["dtype"]))
    model.to(CFG["device"]).eval()
    return tok, model


def build_prompt_ids(tok, text: str) -> torch.Tensor:
    msgs = [{"role": "system", "content": SYSTEM},
            {"role": "user", "content": INSTRUCTION.format(text=text)}]
    ids = tok.apply_chat_template(msgs, add_generation_prompt=True, return_tensors="pt", return_dict=True)
    return ids["input_ids"]


@torch.no_grad()
def generate(tok, model, text: str, seed: int):
    prompt_ids = build_prompt_ids(tok, text).to(CFG["device"])
    torch.manual_seed(seed)
    t0 = time.perf_counter()
    out = model.generate(prompt_ids, do_sample=True, temperature=CFG["temperature"], top_p=CFG["top_p"],
                         max_new_tokens=CFG["max_new_tokens"], pad_token_id=tok.eos_token_id)
    gen_s = time.perf_counter() - t0
    gen_ids = [i for i in out[0, prompt_ids.shape[1]:].tolist() if i not in tok.all_special_ids]
    return prompt_ids, gen_ids, gen_s


@torch.no_grad()
def token_probs(tok, model, prompt_ids, gen_ids):
    """Model probability of each generated token given prompt and earlier output (one forward pass).
    Plain softmax (temperature 1), not the sampling temperature; keep the same scoring for the AUC and for tau.
    Returns output text and a list of (char_start, char_end, prob)."""
    full = torch.cat([prompt_ids, torch.tensor([gen_ids], device=prompt_ids.device)], dim=1)
    logits = model(full).logits[0, prompt_ids.shape[1] - 1:-1].float()
    probs = torch.softmax(logits, dim=-1).gather(1, torch.tensor(gen_ids, device=logits.device)[:, None])[:, 0]
    spans, prev = [], ""
    for i in range(len(gen_ids)):
        cur = tok.decode(gen_ids[: i + 1])
        spans.append((len(prev), len(cur), probs[i].item()))
        prev = cur
    return prev, spans


def span_prob(tok_spans, start: int, end: int) -> float | None:
    """Geometric mean probability of the tokens that overlap [start, end)."""
    ps = [p for s, e, p in tok_spans if s < end and e > start]
    if not ps:
        return None
    return math.exp(sum(math.log(max(p, 1e-12)) for p in ps) / len(ps))


# ---------------------------------------------------------------- alignment
@dataclass
class Span:
    sent_idx: int
    src: str | None
    out: str
    out_start: int
    out_end: int
    reachable: bool
    prob: float | None = None
    on_wordlist: bool | None = None
    actions: dict = field(default_factory=dict)   # condition -> (action, final_text)
    db_id: int | None = None


def content_lemmas(sent):
    return {t.lemma_.lower() for t in sent if t.is_alpha and not t.is_stop} | {t.text for t in sent if t.like_num}


def align(source: str, output: str) -> list[Span]:
    """Match each output sentence to its most similar source sentence (sentence embeddings),
    then diff words inside the pair. Output sentences below the similarity threshold have no source."""
    src_doc, out_doc = NLP(source), NLP(output)
    src_sents, out_sents = list(src_doc.sents), list(out_doc.sents)
    sim = EMB.similarity(EMB.encode([x.text for x in out_sents]), EMB.encode([x.text for x in src_sents]))
    spans: list[Span] = []
    for k, osent in enumerate(out_sents):
        j = int(sim[k].argmax())
        best, best_score = src_sents[j], float(sim[k, j])
        o_toks = [t for t in osent if not t.is_punct and not t.is_space]
        if best_score < CFG["min_sentence_similarity"]:
            if o_toks:   # whole sentence has no source: insertion / possible hallucination
                spans.append(Span(k, None, osent.text, osent.start_char, osent.end_char, False))
            continue
        s_toks = [t for t in best if not t.is_punct and not t.is_space]
        sm = difflib.SequenceMatcher(a=[t.lower_ for t in s_toks], b=[t.lower_ for t in o_toks], autojunk=False)
        for op, i1, i2, j1, j2 in sm.get_opcodes():
            if op in ("equal", "delete"):
                continue   # deletions are source-side; omissions are caught by annotation and preservation
            o_part = o_toks[j1:j2]
            start, end = o_part[0].idx, o_part[-1].idx + len(o_part[-1].text)
            src_txt = source[s_toks[i1].idx: s_toks[i2 - 1].idx + len(s_toks[i2 - 1].text)] if i2 > i1 else None
            small = op == "replace" and (i2 - i1) <= CFG["max_span_tokens"] and (j2 - j1) <= CFG["max_span_tokens"]
            spans.append(Span(k, src_txt, output[start:end], start, end, small))
    return spans


# ---------------------------------------------------------------- checks
def is_easy(word: str) -> bool:
    if not any(c.isalpha() for c in word):
        return True
    doc = NLP(word)
    return all(t.is_punct or t.like_num or t.pos_ == "PROPN" or t.lower_ in EASY or t.lemma_.lower() in EASY
               for t in doc)


def swap_word(w: str) -> str:
    """Replace a hard word from the table; keep surrounding punctuation and a leading capital."""
    m = re.match(r"^(\W*)(.*?)(\W*)$", w)
    lead, core, trail = m.groups()
    easy = REPL.get(core.lower())
    if easy is None:
        return w
    if core[:1].isupper():
        easy = easy[:1].upper() + easy[1:]
    return lead + easy + trail


def lookup_action(span: Span):
    """C3 policy for one span: keep if every word is on the list, else replace hard words, else revert."""
    words = span.out.split()
    if all(is_easy(w) for w in words):
        return "keep", span.out
    replaced = [swap_word(w) for w in words]
    if replaced != words and all(is_easy(w) for w in " ".join(replaced).split()):
        return "replace", " ".join(replaced)
    return "revert", span.src


def apply_actions(output: str, spans: list[Span], cond: str) -> str:
    text = output
    for s in sorted((s for s in spans if cond in s.actions), key=lambda s: s.out_start, reverse=True):
        action, final = s.actions[cond]
        if action in ("revert", "replace") and final is not None:
            text = text[: s.out_start] + final + text[s.out_end:]
    return text


def grammar_flags(text: str) -> dict:
    doc = NLP(text)
    flags = {}
    long = [s.text for s in doc.sents if sum(1 for t in s if t.is_alpha or t.like_num) > CFG["long_sentence_words"]]
    passive = [s.text for s in doc.sents if any(t.dep_ in ("nsubjpass", "auxpass") for t in s)]
    abbrev = sorted({t.text for t in doc if t.is_upper and len(t.text) >= 2 and t.is_alpha
                     and f"({t.text})" not in text})
    for rule, hits in (("long_sentence", long), ("passive", passive), ("abbreviation", abbrev)):
        if hits:
            flags[rule] = (len(hits), hits[0][:200])
    return flags


# ---------------------------------------------------------------- metrics
NUMWORDS = {"one": "1", "two": "2", "three": "3", "four": "4", "five": "5", "six": "6", "seven": "7",
            "eight": "8", "nine": "9", "ten": "10", "twelve": "12", "fourteen": "14", "thirty": "30"}


def preserved(text: str, value: str) -> bool:
    low = text.lower()
    norm = " ".join(NUMWORDS.get(w, w) for w in low.split())
    return any(alt.strip().lower() in low or alt.strip().lower() in norm for alt in value.split("|"))


def words(text: str) -> int:
    return sum(1 for t in NLP.tokenizer(text) if t.is_alpha or t.like_num)


def peak_mem_mb() -> float:   # process maximum so far: a run-level figure, not per output
    return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024 / 1024   # macOS reports bytes


# ---------------------------------------------------------------- main
def load_texts(conn, paths: list[Path], limit: int | None):
    rows = [json.loads(l) for p in paths for l in open(p, encoding="utf-8") if l.strip()][:limit]
    for r in rows:
        if r["split"] != "dev":
            raise SystemExit(f"{r['id']}: split is {r['split']!r}; this config runs dev texts only")
        old = conn.execute("SELECT body FROM texts WHERE id=%s", (r["id"],)).fetchone()
        if old and old[0] != r["body"] and conn.execute(
                "SELECT 1 FROM base_outputs WHERE text_id=%s LIMIT 1", (r["id"],)).fetchone():
            raise SystemExit(f"{r['id']}: text changed after outputs exist; texts are frozen once run")
        conn.execute("""INSERT INTO texts(id,source,licence,text_type,is_synthetic,split,body,word_count,fkgl)
                        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
                        ON CONFLICT (id) DO UPDATE SET body=EXCLUDED.body, word_count=EXCLUDED.word_count,
                        fkgl=EXCLUDED.fkgl""",
                     (r["id"], r["source"], r["licence"], r["text_type"], r["is_synthetic"], r["split"],
                      r["body"], words(r["body"]), textstat.flesch_kincaid_grade(r["body"])))
        conn.execute("DELETE FROM protected_items WHERE text_id=%s", (r["id"],))
        for p in r["protected"]:
            conn.execute("INSERT INTO protected_items(text_id,kind,value) VALUES (%s,%s,%s)",
                         (r["id"], p["kind"], p["value"]))
    return rows


def run_conditions(spans, output, tok_spans):
    """Returns {cond: (text, extra_seconds, flags)} for C1..C5 on the same base output."""
    reach = [s for s in spans if s.reachable]
    res = {"C1": (output, 0.0, {})}

    t0 = time.perf_counter()
    for s in reach:
        s.prob = span_prob(tok_spans, s.out_start, s.out_end)
        s.actions["C2"] = ("revert", s.src) if s.prob is not None and s.prob < CFG["prob_threshold"] else ("keep", s.out)
    c2_s = time.perf_counter() - t0
    res["C2"] = (apply_actions(output, spans, "C2"), c2_s, {})

    t0 = time.perf_counter()
    for s in reach:
        s.actions["C3"] = lookup_action(s)
        s.on_wordlist = s.actions["C3"][0] == "keep"
    c3_text = apply_actions(output, spans, "C3")
    c3_s = time.perf_counter() - t0
    res["C3"] = (c3_text, c3_s, {})

    t0 = time.perf_counter()
    flags4 = grammar_flags(c3_text)
    res["C4"] = (c3_text, c3_s + time.perf_counter() - t0, flags4)

    # C5: probability first; spans it keeps then go through lookup (C3 decisions reused), then grammar
    t0 = time.perf_counter()
    for s in reach:
        s.actions["C5"] = s.actions["C2"] if s.actions["C2"][0] == "revert" else s.actions["C3"]
    c5_text = apply_actions(output, spans, "C5")
    flags5 = grammar_flags(c5_text)
    res["C5"] = (c5_text, c2_s + c3_s + time.perf_counter() - t0, flags5)
    return res


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int)
    ap.add_argument("--seeds", type=int, nargs="+", default=CFG["seeds"])
    args = ap.parse_args()

    tok, model = load_model()
    with connect() as conn:
        texts = load_texts(conn, [ROOT / p for p in ([CFG["texts"]] if isinstance(CFG["texts"], str) else CFG["texts"])], args.limit)
        conn.commit()
        for seed in args.seeds:
            run_id = conn.execute(
                """INSERT INTO runs(model,backend,quantization,seed,temperature,prompt_version,target_level,hardware)
                   VALUES (%s,'transformers','none',%s,%s,%s,%s,%s) RETURNING id""",
                (CFG["model"], seed, CFG["temperature"], CFG["prompt_version"], CFG["target_level"],
                 f"Apple M3 Pro, CPU-only, {torch.get_num_threads()} threads, {CFG['dtype']}")).fetchone()[0]
            n_preamble = 0
            for r in texts:
                prompt_ids, gen_ids, gen_s = generate(tok, model, r["body"], seed)
                t0 = time.perf_counter()
                output, tok_spans = token_probs(tok, model, prompt_ids, gen_ids)
                score_s = time.perf_counter() - t0
                m = PREAMBLE.match(output)          # drop "Here's the rewritten text:" lead-ins
                if m:
                    cut = m.end()
                    output = output[cut:]
                    tok_spans = [(s - cut, e - cut, p) for s, e, p in tok_spans if e > cut]
                    n_preamble += 1
                truncated = len(gen_ids) >= CFG["max_new_tokens"]   # cut off by the token limit: rater would see a fake omission
                spans = align(r["body"], output)
                conds = run_conditions(spans, output, tok_spans)

                b_id = conn.execute("""INSERT INTO base_outputs(run_id,text_id,output,gen_seconds,peak_mem_mb,truncated)
                                       VALUES (%s,%s,%s,%s,%s,%s) RETURNING id""",
                                    (run_id, r["id"], output, gen_s, peak_mem_mb(), truncated)).fetchone()[0]
                for s in spans:
                    s.db_id = conn.execute(
                        """INSERT INTO changed_spans(base_output_id,sentence_idx,source_span,output_span,reachable,
                           probability,on_wordlist) VALUES (%s,%s,%s,%s,%s,%s,%s) RETURNING id""",
                        (b_id, s.sent_idx, s.src, s.out, s.reachable, s.prob, s.on_wordlist)).fetchone()[0]
                    for cond, (action, final) in s.actions.items():
                        conn.execute("INSERT INTO span_actions VALUES (%s,%s,%s,%s)", (s.db_id, cond, action, final))

                for cond, (text, extra_s, flags) in conds.items():
                    if cond in ("C2", "C5"):
                        extra_s += score_s
                    src_cond = "C3" if cond == "C4" else cond   # C4 = C3 text plus grammar flags
                    changed = any(s.actions.get(src_cond, ("keep",))[0] != "keep" for s in spans)
                    prot = [p["value"] for p in r["protected"]]
                    co_id = conn.execute(
                        """INSERT INTO condition_outputs(base_output_id,condition,output,word_count,fkgl,
                           protected_preserved,protected_total,post_seconds,flagged)
                           VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id""",
                        (b_id, cond, text, words(text), textstat.flesch_kincaid_grade(text),
                         sum(preserved(text, v) for v in prot), len(prot), extra_s,
                         changed or bool(flags))).fetchone()[0]
                    for rule, (n, ex) in flags.items():
                        conn.execute("INSERT INTO grammar_flags VALUES (%s,%s,%s,%s)", (co_id, rule, n, ex))
                conn.commit()
                n_reach = sum(s.reachable for s in spans)
                print(f"seed {seed} {r['id']}: {len(gen_ids)} tokens in {gen_s:.1f}s "
                      f"({len(gen_ids) / gen_s:.1f} tok/s), spans {n_reach}/{len(spans)} reachable"
                      + ("  TRUNCATED at max_new_tokens" if truncated else ""), flush=True)
            print(f"seed {seed}: stripped a lead-in line from {n_preamble} outputs")
    print("done")


if __name__ == "__main__":
    main()
