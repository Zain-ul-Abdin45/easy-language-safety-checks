"""Gate A screen, part 4: D3 coverage check (protocol 11.7), exploratory combination and D4a aligned/unaligned AUC (protocol 11.8).

D3 unit: source sentence of a dev C1 output. Flag if no output sentence is aligned to it, or its content-lemma coverage in the aligned
output sentences is below 0.40. Recall on the omission tags whose source sentence index was backfilled (omission_backfill_confirmed.csv).
Run:  ANNOTATE_DIR=results/dev24 .venv/bin/python src/d3_screen.py      Writes results/<ANNOTATE_DIR>/screen_d3.md
"""
import csv
import json
import os
from collections import defaultdict
from pathlib import Path

import numpy as np

from auc_decision import auc
from d4_screen import evaluate
from db import connect
from sentence_screen import MAX_FLAG_RATE, flags, load

ROOT = Path(__file__).resolve().parents[1]
THRESHOLD = 0.40
POS = {"NOUN", "VERB", "ADJ", "ADV", "NUM", "PROPN"}


def lemmas(sent):
    return {t.lemma_.lower() for t in sent if t.pos_ in POS and not t.is_stop and not t.is_punct}


def d3_flags(u):
    res = []
    for j, s in enumerate(u["src"]):
        ks = [k for k, l in enumerate(u["link"]) if l == j]
        content = lemmas(s)
        if not ks:
            res.append(True); continue
        got = set().union(*[lemmas(u["out"][k]) for k in ks])
        res.append(bool(content) and len(content & got) / len(content) < THRESHOLD)
    return res


def main():
    boot, rng = 5000, np.random.default_rng(0)
    outdir = ROOT / os.environ.get("ANNOTATE_DIR", "results")
    with connect() as conn:
        units = load(conn)
    ukey = {(u["text"], u["seed"]): u for u in units}
    fl = {k: d3_flags(u) for k, u in ukey.items()}
    tags = list(csv.DictReader(open(outdir / "omission_backfill_confirmed.csv", encoding="utf-8-sig")))
    per = defaultdict(lambda: [0, 0, 0.0])    # text -> tags, caught, expected under random
    miss = 0
    for r in tags:
        if not r["source_sentence_index"].strip():
            miss += 1; continue
        k = (r["text_id"], int(r["seed"])); j = int(r["source_sentence_index"]) - 1
        p = per[r["text_id"]]
        p[0] += 1; p[1] += int(fl[k][j]); p[2] += sum(fl[k]) / len(fl[k])
    texts = sorted(per)
    def est(tx):
        n = sum(per[t][0] for t in tx)
        return (sum(per[t][1] for t in tx) / n, sum(per[t][2] for t in tx) / n) if n else (np.nan, np.nan)
    rec, rnd = est(texts)
    d = np.array([(lambda e: e[0] - e[1])(est(list(rng.choice(texts, len(texts))))) for _ in range(boot)])
    lo, hi = np.percentile(d, [2.5, 97.5])
    nsrc = sum(len(v) for v in fl.values()); nfl = sum(sum(v) for v in fl.values())
    rate = nfl / nsrc
    ok = lo > 0 and rate <= MAX_FLAG_RATE
    n_tags = sum(p[0] for p in per.values())
    L = ["# Gate A screen, part 4: D3 coverage, combination, D4a aligned/unaligned (dev, C1 outputs)", "",
         "## D3 coverage (protocol 11.7, threshold 0.40)", "",
         f"Source sentences: {nsrc}; flagged: {nfl} ({100 * rate:.0f}%). Omission tags with a backfilled sentence index: {n_tags} (missing: {miss}). "
         "The index was suggested by Claude and confirmed by the researcher.", "",
         "| flagged / source sentences | flag rate | omission recall | random recall | difference [95%] | Gate A |", "|---|---|---|---|---|---|",
         f"| {nfl} / {nsrc} | {100 * rate:.0f}% | {100 * rec:.0f}% ({sum(p[1] for p in per.values())} / {n_tags}) | {100 * rnd:.0f}% | "
         f"{100 * (rec - rnd):+.0f} points [{100 * lo:+.0f}, {100 * hi:+.0f}] | {'passes' if ok else 'does not pass'} |", ""]
    # ---- 11.8 combination and aligned/unaligned AUC
    d4 = json.loads((outdir / "d4_scores.json").read_text())["sents"]
    d5 = json.loads((outdir / "d5_scores_primary.json").read_text())["sents"]
    sents = [dict(x, unit=tuple(x["unit"])) for x in d4]
    assert [tuple(x["unit"]) for x in d4] == [tuple(x["unit"]) for x in d5], "sentence order differs between D4 and D5 caches"
    for s, x in zip(sents, d5):
        s["aligned"] = x["aligned"]
    d1 = []
    for key in sorted(ukey):
        d1 += flags(ukey[key])[0]
    # d4 sentences come in the order of load(), which is sorted by text id and seed
    order = [tuple(s["unit"]) for s in sents]
    assert len(d1) == len(sents) and order == sorted(order), "D1 flag order does not match"
    for s, f in zip(sents, d1):
        s["c"] = -100.0 if f else s["a"]
    r = evaluate(sents, "c", boot, rng)
    L += ["## Exploratory combination (protocol 11.8): D1 flags, then lowest D4a up to 30%", "",
          f"Flagged {r['F']} / {r['n']} ({100 * r['rate']:.0f}%); recall {100 * r['rec']:.0f}%, random {100 * r['rnd']:.0f}%, difference "
          f"{100 * r['diff']:+.0f} points [{100 * r['lo']:+.0f}, {100 * r['hi']:+.0f}]. "
          f"{'Passes' if r['lo'] > 0 and r['rate'] <= 0.30 + 1e-9 else 'Does not pass'} the recall-minus-random rule. Exploratory, not a gate.", ""]
    L += ["## D4a sentence-level AUC, aligned vs unaligned output sentences (protocol 11.8)", "",
          "| group | sentences | harmful | AUC [95%] |", "|---|---|---|---|"]
    for name, flagv in [("aligned", True), ("unaligned", False)]:
        sub = [s for s in sents if s["aligned"] == flagv]
        sc = np.array([s["a"] for s in sub]); hm = np.array([s["harmful"] for s in sub])
        by = defaultdict(list)
        for i, s in enumerate(sub):
            by[s["text"]].append(i)
        tx = sorted(by)
        pt = auc(sc, hm)
        ds = []
        for _ in range(boot):
            idx = np.array([i for t in rng.choice(tx, len(tx)) for i in by[t]])
            v = auc(sc[idx], hm[idx])
            if not np.isnan(v):
                ds.append(v)
        a, b = np.percentile(ds, [2.5, 97.5]) if ds else (np.nan, np.nan)
        L.append(f"| {name} | {len(sub)} | {int(hm.sum())} | {pt:.3f} [{a:.3f}, {b:.3f}] |")
    text = "\n".join(L)
    (outdir / "screen_d3.md").write_text(text)
    print(text)


if __name__ == "__main__":
    main()
