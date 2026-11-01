"""Gate A screen, part 3: D5 entailment check on the dev labels (protocol 11.6).

Score per output sentence of the C1 outputs:
  aligned pair      min( P(entail | source sentence -> output sentence), P(entail | output sentence -> source sentence) )
  unaligned output  P(entail | whole source -> output sentence)   (one direction only)
Models (fixed in the protocol): primary cross-encoder/nli-deberta-v3-base, sensitivity lytang/MiniCheck-RoBERTa-Large.
Flag rule, pass rule and statistics are those of d4_screen.evaluate (30th percentile; recall minus random; AUC; bootstrap over texts).

Run:  .venv/bin/python src/d5_screen.py --timing 5          seconds per pair on the first 5 dev texts, no statistics
      .venv/bin/python src/d5_screen.py                      score all 64 outputs with both models and evaluate
Writes results/<ANNOTATE_DIR>/screen_d5.md and d5_scores_<model>.json.
"""
import argparse
import json
import os
import time
from pathlib import Path

import numpy as np
import torch
from transformers import AutoModelForSequenceClassification, AutoTokenizer

from d4_screen import evaluate
from db import connect
from sentence_screen import load

ROOT = Path(__file__).resolve().parents[1]
MODELS = {"primary": ("cross-encoder/nli-deberta-v3-base", 1),     # label index of "entailment"
          "minicheck": ("lytang/MiniCheck-RoBERTa-Large", 1)}      # label 1 = supported
torch.set_num_threads(max(1, (os.cpu_count() or 4) - 1))


LOCAL = {"primary": "models/nli-deberta-v3-base", "minicheck": "models/minicheck-roberta-large"}   # curl copies; the hf client resets the connection


def load_model(key):
    name, idx = MODELS[key]
    path = str(ROOT / LOCAL[key]) if (ROOT / LOCAL[key] / "config.json").exists() else name
    return AutoTokenizer.from_pretrained(path), AutoModelForSequenceClassification.from_pretrained(path).eval(), idx


@torch.no_grad()
def entail(tok, model, idx, pairs, bs=16):
    out = []
    for i in range(0, len(pairs), bs):
        chunk = pairs[i:i + bs]
        enc = tok([p for p, _ in chunk], [h for _, h in chunk], truncation=True, max_length=512, padding=True, return_tensors="pt")
        out += torch.softmax(model(**enc).logits, dim=-1)[:, idx].tolist()
    return out


def pairs_of(u):
    """List of (sentence index, direction, premise, hypothesis) for one unit."""
    body = u["src"][0].doc.text if u["src"] else ""
    res = []
    for k, s in enumerate(u["out"]):
        j = u["link"][k]
        if j is None:
            res.append((k, "whole", body, s.text))
        else:
            res.append((k, "fwd", u["src"][j].text, s.text))
            res.append((k, "bwd", s.text, u["src"][j].text))
    return res


def score_units(units, tok, model, idx):
    sents = []
    for u in units:
        ps = pairs_of(u)
        probs = entail(tok, model, idx, [(p, h) for _, _, p, h in ps])
        per = {}
        for (k, d, _, _), p in zip(ps, probs):
            per.setdefault(k, []).append(p)
        for k in range(len(u["out"])):
            sents.append(dict(unit=(u["text"], u["seed"]), text=u["text"], a=float(min(per[k])), harmful=bool(u["harm"][k]),
                              cats=sorted(u["harm"][k]), aligned=u["link"][k] is not None))
    return sents


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--timing", type=int, default=0, help="only time the first N dev texts; no statistics")
    ap.add_argument("--boot", type=int, default=5000)
    ap.add_argument("--seed", type=int, default=0)
    a = ap.parse_args()
    with connect() as conn:
        units = load(conn)
    outdir = ROOT / os.environ.get("ANNOTATE_DIR", "results")
    outdir.mkdir(exist_ok=True)
    if a.timing:
        texts = sorted({u["text"] for u in units})[:a.timing]
        sub = [u for u in units if u["text"] in texts]
        n_pairs = sum(len(pairs_of(u)) for u in sub)
        print(f"{len(sub)} outputs of {len(texts)} texts, {n_pairs} pairs")
        for key in MODELS:
            tok, model, idx = load_model(key)
            t0 = time.perf_counter()
            for u in sub:
                entail(tok, model, idx, [(p, h) for _, _, p, h in pairs_of(u)])
            dt = time.perf_counter() - t0
            print(f"{key} ({MODELS[key][0]}): {dt:.1f} s for {n_pairs} pairs = {dt / n_pairs:.2f} s per pair, {dt / len(sub):.1f} s per output")
        return
    rng = np.random.default_rng(a.seed)
    L = ["# Gate A screen, part 3: D5 entailment (dev, C1 outputs)", "",
         "Rule fixed before computing (protocol 11.6): score = min of the two entailment directions per aligned pair; whole source -> sentence for "
         "unaligned sentences; flag = score at or below the 30th percentile; goes on if the lower bound of (recall - random recall) > 0 and "
         "the AUC lower bound > 0.5 (95% bootstrap over texts). In-sample, descriptive.", "",
         "| model | flagged / sentences | recall | random recall | difference [95%] | AUC [95%] | seconds per sentence | Gate A |", "|---|---|---|---|---|---|---|---|"]
    detail = []
    for key in MODELS:
        cache = outdir / f"d5_scores_{key}.json"
        if cache.exists():
            d = json.loads(cache.read_text())
            sents, secs = [dict(x, unit=tuple(x["unit"])) for x in d["sents"]], d["secs"]
        else:
            tok, model, idx = load_model(key)
            t0 = time.perf_counter()
            sents = score_units(units, tok, model, idx)
            secs = (time.perf_counter() - t0) / len(sents)
            cache.write_text(json.dumps(dict(sents=sents, secs=secs)))
        r = evaluate(sents, "a", a.boot, rng)
        ok = r["lo"] > 0 and r["alo"] > 0.5 and r["rate"] <= 0.30 + 1e-9
        L.append(f"| {MODELS[key][0]} | {r['F']} / {r['n']} | {100 * r['rec']:.0f}% | {100 * r['rnd']:.0f}% | {100 * r['diff']:+.0f} points "
                 f"[{100 * r['lo']:+.0f}, {100 * r['hi']:+.0f}] | {r['auc']:.3f} [{r['alo']:.3f}, {r['ahi']:.3f}] | {secs:.2f} | "
                 f"{'passes' if ok else 'does not pass'} |")
        detail.append((MODELS[key][0], r))
    L += ["", "Recall by the category of the tag in the sentence:", "", "| model | category | caught / tags |", "|---|---|---|"]
    for name, r in detail:
        for c, (n, f) in sorted(r["cat"].items(), key=lambda x: -x[1][0]):
            L.append(f"| {name} | {c} | {f} / {n} |")
    text = "\n".join(L)
    (outdir / "screen_d5.md").write_text(text)
    print(text)


if __name__ == "__main__":
    main()
