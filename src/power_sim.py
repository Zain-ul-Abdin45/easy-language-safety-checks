"""Planning calculation for the held-out size (protocol 11.19): how often would the pre-set rules be met if the held-out texts behaved like
the dev texts? Dev texts are resampled with replacement to a size n, a bootstrap interval is computed inside each resample, and the share of
resamples that meet the rule is counted. The dev effect is in-sample, so this is an optimistic upper bound for the true power.

H1: C3 against C1, harm reduction per 100 words, 95% interval, rule: lower bound above 0.
E2: D4a and D5 (DeBERTa), 97.5% interval per check (two checks), rule: lower bound of recall minus random recall above 0 and lower bound of
    the sentence-level AUC above 0.5, with the flag threshold fixed at the dev 30th percentile.
The last three columns (protocol 11.23) give the recall condition alone and the joint rule; they use the same draws as the AUC columns. The flag threshold is the dev 30th
percentile throughout (the held-out rule of exactly the lowest 30% is not simulated).
Run:  .venv/bin/python src/power_sim.py     Writes results/power_sim.md
"""
import hashlib
import json
from collections import defaultdict
from pathlib import Path

import numpy as np

from auc_decision import auc
from db import connect

ROOT = Path(__file__).resolve().parents[1]
OUTER, INNER = 200, 300
SEED = 0
rng = np.random.default_rng(SEED)
INPUTS = ["results/dev24/d4_scores.json", "results/dev24/d5_scores_primary.json"]


def sha(path):
    return hashlib.sha256((ROOT / path).read_bytes()).hexdigest()[:16]


def sentence_data(path):
    sents = [dict(x, unit=tuple(x["unit"])) for x in json.loads(Path(path).read_text())["sents"]]
    score = np.array([s["a"] for s in sents]); harm = np.array([s["harmful"] for s in sents])
    flag = score <= np.percentile(score, 30)
    units = defaultdict(list)
    for i, s in enumerate(sents):
        units[s["unit"]].append(i)
    per, idx = {}, defaultdict(list)
    for i, s in enumerate(sents):
        idx[s["text"]].append(i)
    for t in idx:
        H = Hf = E = F = N = 0
        for u, ii in units.items():
            if u[0] != t:
                continue
            h, f = harm[ii], flag[ii]
            H += h.sum(); Hf += (h & f).sum(); E += f.sum() / len(ii) * h.sum(); F += f.sum(); N += len(ii)
        per[t] = (H, Hf, E, F, N)
    return score, harm, per, idx


def e2_pass(data, texts, level, auc_only=False):
    score, harm, per, idx = data
    p = (100 - level) / 2
    def est(tx):
        H = sum(per[t][0] for t in tx)
        return np.nan if H == 0 else (sum(per[t][1] for t in tx) - sum(per[t][2] for t in tx)) / H
    ds, aus = [], []
    for _ in range(INNER):
        pick = [texts[i] for i in rng.integers(0, len(texts), len(texts))]
        d = est(pick)
        if not np.isnan(d):
            ds.append(d)
        ii = np.array([i for t in pick for i in idx[t]])
        a = auc(score[ii], harm[ii])
        if not np.isnan(a):
            aus.append(a)
    if len(ds) < INNER // 2 or len(aus) < INNER // 2:
        return (np.nan, np.nan) if auc_only else False
    if auc_only:   # D4a as primary (protocol 11.23): (lower bound of the sentence-level AUC, lower bound of recall minus random recall) from the same draws; the caller applies the bars
        return np.percentile(aus, p), np.percentile(ds, p)
    return np.percentile(ds, p) > 0 and np.percentile(aus, p) > 0.5


def main():
    with connect() as conn:
        rows = conn.execute("""SELECT b.text_id, co.condition, count(DISTINCT co.id), sum(co.word_count), 0 FROM condition_outputs co
            JOIN base_outputs b ON b.id=co.base_output_id JOIN texts t ON t.id=b.text_id WHERE t.split='dev' AND co.condition IN ('C1','C3')
            GROUP BY 1,2""").fetchall()
        tags = conn.execute("""SELECT b.text_id, co.condition, count(*) FROM harm_annotations h JOIN condition_outputs co ON co.id=h.condition_output_id
            JOIN base_outputs b ON b.id=co.base_output_id JOIN texts t ON t.id=b.text_id
            WHERE t.split='dev' AND h.rater_role='primary' AND h.severity>=2 AND co.condition IN ('C1','C3') GROUP BY 1,2""").fetchall()
    words = {(t, c): float(w) for t, c, n, w, _ in rows}
    harm = defaultdict(float)
    for t, c, n in tags:
        harm[(t, c)] = n
    texts_all = sorted({t for t, _ in words})

    def h1_lb(tx):
        ds = []
        for _ in range(INNER):
            pick = [tx[i] for i in rng.integers(0, len(tx), len(tx))]
            w1 = sum(words[(t, "C1")] for t in pick); w3 = sum(words[(t, "C3")] for t in pick)
            ds.append(100 * (sum(harm[(t, "C1")] for t in pick) / w1 - sum(harm[(t, "C3")] for t in pick) / w3))
        return np.percentile(ds, 2.5)

    d4, d5 = sentence_data(ROOT / "results/dev24/d4_scores.json"), sentence_data(ROOT / "results/dev24/d5_scores_primary.json")
    L = ["# Held-out size: how often the pre-set rules would be met if the held-out texts behaved like the dev texts (protocol 11.19)", "",
         f"Dev texts resampled with replacement to size n; {OUTER} resamples per size, {INNER} inner bootstrap draws each. The dev effect is in-sample, so these shares are optimistic. "
         "H1 uses a 95% interval; D4a and D5 use 97.5% intervals (two checks). The last two columns treat D4a as primary: sentence-level AUC lower bound (95%) above 0.5, and above 0.60 (the INCONCLUSIVE bar of 28 Oct), nothing else; both use the same bootstrap draws as each other.", "",
         "Reading the table: (1) Resampling the 32 dev texts with replacement understates between-text variation, because a resample can only contain texts, and kinds of text, already seen; real held-out texts add variation these resamples cannot show, so every share is optimistic. "
         f"(2) Monte Carlo error: each share rests on {OUTER} resamples, so its standard error is sqrt(p(1-p)/{OUTER}), at most {100 * 0.5 / OUTER ** 0.5:.1f} points (at 50%); the figure in brackets is the standard error of that cell.", "",
         f"Seed {SEED}. Inputs (SHA-256, first 16): " + ", ".join(f"{i} {sha(i)}" for i in INPUTS), "",
         "| held-out texts n | H1: C3 against C1, lower bound above 0 | D4a passes the E2 rule | D5 (DeBERTa) passes the E2 rule | D4a as primary: AUC lower bound above 0.5 | D4a as primary: AUC lower bound above 0.60 | D4a as primary: recall minus random lower bound above 0 | D4a as primary: both, AUC bound above 0.5 (partial or better) | D4a as primary: both, AUC bound above 0.60 (success, protocol 11.23) |", "|---|---|---|---|---|---|---|---|---|"]
    for n in (30, 60, 90):
        h1 = d4p = d5p = d4a = d4a60 = rec0 = joint60 = joint5 = 0
        for _ in range(OUTER):
            tx = [texts_all[i] for i in rng.integers(0, len(texts_all), n)]
            h1 += h1_lb(tx) > 0
            d4p += e2_pass(d4, tx, 97.5)
            d5p += e2_pass(d5, tx, 97.5)
            lb, rlb = e2_pass(d4, tx, 95, auc_only=True)
            d4a += lb > 0.5
            d4a60 += lb > 0.60
            rec0 += rlb > 0                      # added 2026-11-02 (protocol 11.23): same draws, so the earlier columns are unchanged
            joint5 += (lb > 0.5) and (rlb > 0)
            joint60 += (lb > 0.60) and (rlb > 0)
        cell = lambda k: f"{100 * k / OUTER:.0f}% (±{100 * (k / OUTER * (1 - k / OUTER) / OUTER) ** 0.5:.1f})"
        L.append(f"| {n} | {cell(h1)} | {cell(d4p)} | {cell(d5p)} | {cell(d4a)} | {cell(d4a60)} | {cell(rec0)} | {cell(joint5)} | {cell(joint60)} |")
        print(L[-1], flush=True)
    text = "\n".join(L)
    (ROOT / "results/power_sim.md").write_text(text)
    print(text)


if __name__ == "__main__":
    main()
