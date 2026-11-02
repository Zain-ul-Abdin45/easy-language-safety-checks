"""Gate A screen, part 2: D4 sentence-level probability on the dev labels (protocol 11.4).

The token probabilities of the C1 outputs are not stored, so each output is regenerated with its seed (the text is identical,
which the script checks) and scored in the same forward pass. Scores per output sentence:
  D4a  mean token log-probability of the sentence (low = suspicious)
  D4b  lowest probability among the changed spans inside the sentence (1 if there is none)
Flag rule: score at or below the 30th percentile of all dev sentence scores. Gate A: flag rate <= 30%, lower bound of
(recall - random recall) > 0, and sentence-level AUC lower bound > 0.5 (low score = harmful sentence), 95% bootstrap over texts.

Run:  .venv/bin/python src/d4_screen.py [--boot 5000 --seed 0]     (about 10-15 minutes, CPU)
Writes results/<ANNOTATE_DIR>/screen_d4.md.
"""
import argparse
import math
import os
from collections import defaultdict
from pathlib import Path

import numpy as np

import annotate as A
from auc_decision import auc
from db import connect
from pilot import NLP, generate, load_model, token_probs

ROOT = Path(__file__).resolve().parents[1]


def collect(conn, tok, model, scorer=None):
    """scorer (optional, added for the Llama retokenization sensitivity): scorer(body, seed, out) -> (raw text, token spans) in place of regenerating. Default = v2."""
    rows = conn.execute("""SELECT co.id, b.id, b.text_id, r.seed, t.body, co.output FROM condition_outputs co
                           JOIN base_outputs b ON b.id=co.base_output_id JOIN runs r ON r.id=b.run_id JOIN texts t ON t.id=b.text_id
                           WHERE co.condition='C1' AND t.split='dev' ORDER BY b.text_id, r.seed""").fetchall()
    sents = []   # one dict per non-empty sentence
    mismatch = 0
    for n, (co_id, b_id, text_id, seed, body, out) in enumerate(rows, 1):
        if scorer is None:
            prompt_ids, gen_ids, _ = generate(tok, model, body, seed)
            raw, tspans = token_probs(tok, model, prompt_ids, gen_ids)
        else:
            raw, tspans = scorer(body, seed, out)
        off = raw.find(out.strip())
        if off < 0:
            mismatch += 1
            continue
        all_s = list(NLP(out).sents)
        span_p = defaultdict(list)
        for k, p in conn.execute("SELECT sentence_idx, probability::float FROM changed_spans WHERE base_output_id=%s AND probability IS NOT NULL", (b_id,)).fetchall():
            span_p[k].append(p)
        tags = conn.execute("""SELECT category, output_quote, quote_occurrence FROM harm_annotations WHERE condition_output_id=%s
                               AND rater_role='primary' AND severity>=2 AND output_quote IS NOT NULL""", (co_id,)).fetchall()
        harm = [set() for _ in all_s]
        for cat, q, occ in tags:
            need, seen, nq = (occ or 1), 0, A.norm(q)
            for k, s in enumerate(all_s):
                c = len(A.find_all(A.norm(s.text), nq))
                if c and seen + c >= need:
                    harm[k].add(cat)
                    break
                seen += c
        for k, s in enumerate(all_s):
            if not any(not t.is_punct and not t.is_space for t in s):
                continue
            a, z = s.start_char + off, s.end_char + off
            lp = [math.log(max(p, 1e-12)) for st, en, p in tspans if st < z and en > a]
            sents.append(dict(unit=(text_id, seed), text=text_id, a=float(np.mean(lp)) if lp else 0.0,
                              b=min(span_p[k]) if span_p[k] else 1.0, harmful=bool(harm[k]), cats=sorted(harm[k])))
        print(f"  {n}/{len(rows)} {text_id} seed {seed}", flush=True)
    return sents, mismatch


def evaluate(sents, key, boot, rng, flag_fn=None):
    """flag_fn (optional, added for the tie-rule sensitivity line): maps the score array to a boolean flag array. Default = the v2 rule."""
    score = np.array([s[key] for s in sents])
    if flag_fn is None:
        thr = np.percentile(score, 30)
        flag = score <= thr
    else:
        flag = flag_fn(score)
        thr = float(score[flag].max()) if flag.any() else float("nan")
    harm = np.array([s["harmful"] for s in sents])
    texts = sorted({s["text"] for s in sents})
    units = defaultdict(list)
    for i, s in enumerate(sents):
        units[s["unit"]].append(i)
    by_text = defaultdict(list)
    for i, s in enumerate(sents):
        by_text[s["text"]].append(i)

    # per text: harmful sentences, harmful sentences flagged, expected flagged harmful sentences under random flagging
    # (same number of flags per (text, seed) unit), flagged and total sentences. Resampled texts are summed with their multiplicity.
    per = {}
    for t in texts:
        H = Hf = E = F = N = 0
        for u, ii in units.items():
            if u[0] != t:
                continue
            h, f = harm[ii], flag[ii]
            H += h.sum(); Hf += (h & f).sum(); E += f.sum() / len(ii) * h.sum(); F += f.sum(); N += len(ii)
        per[t] = (H, Hf, E, F, N)

    def est(tx):
        H = sum(per[t][0] for t in tx)
        if H == 0:
            return np.nan, np.nan, np.nan, np.nan
        rec, rnd = sum(per[t][1] for t in tx) / H, sum(per[t][2] for t in tx) / H
        return rec, rnd, rec - rnd, sum(per[t][3] for t in tx) / sum(per[t][4] for t in tx)
    point = est(texts)
    d = np.array([est(list(rng.choice(texts, len(texts)))) for _ in range(boot)])
    lo, hi = np.nanpercentile(d[:, 2], [2.5, 97.5])
    # sentence-level AUC: low score should mean harmful, so AUC = P(score of harmless > score of harmful)
    a_point = auc(score, harm)
    ds = []
    for _ in range(boot):
        pick = rng.choice(texts, len(texts))
        idx = np.array([i for t in pick for i in by_text[t]])
        v = auc(score[idx], harm[idx])
        if not np.isnan(v):
            ds.append(v)
    alo, ahi = np.percentile(ds, [2.5, 97.5])
    cat = defaultdict(lambda: [0, 0])
    for s, f in zip(sents, flag):
        for c in s["cats"]:
            cat[c][0] += 1
            cat[c][1] += int(f)
    return dict(thr=thr, rate=point[3], rec=point[0], rnd=point[1], diff=point[2], lo=lo, hi=hi, auc=a_point, alo=alo, ahi=ahi,
                cat=dict(cat), n=len(sents), H=int(harm.sum()), F=int(flag.sum()))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--boot", type=int, default=5000)
    ap.add_argument("--seed", type=int, default=0)
    a = ap.parse_args()
    rng = np.random.default_rng(a.seed)
    cache = ROOT / os.environ.get("ANNOTATE_DIR", "results") / "d4_scores.json"
    if cache.exists():
        import json
        d = json.loads(cache.read_text())
        sents, mismatch = [dict(x, unit=tuple(x["unit"])) for x in d["sents"]], d["mismatch"]
    else:
        import json
        tok, model = load_model()
        with connect() as conn:
            sents, mismatch = collect(conn, tok, model)
        cache.parent.mkdir(exist_ok=True)
        cache.write_text(json.dumps(dict(sents=sents, mismatch=mismatch)))
    L = ["# Gate A screen, part 2: D4 sentence-level probability (dev, C1 outputs)", "",
         f"{len(sents)} sentences, {sum(s['harmful'] for s in sents)} harmful. Outputs whose regenerated text did not contain the stored output: {mismatch}.", "",
         "Rule fixed before computing (protocol 11.4): flag = score at or below the 30th percentile of all sentence scores; goes on if "
         "the lower bound of (recall - random recall) > 0 and the AUC lower bound > 0.5 (95% bootstrap over texts). In-sample, descriptive.", "",
         "| score | flagged / sentences | recall | random recall | difference [95%] | AUC [95%] | Gate A |", "|---|---|---|---|---|---|---|"]
    res = []
    for key, name in [("a", "D4a mean log-probability of the sentence"), ("b", "D4b lowest changed-span probability")]:
        r = evaluate(sents, key, a.boot, rng)
        ok = r["lo"] > 0 and r["alo"] > 0.5 and r["rate"] <= 0.30 + 1e-9
        L.append(f"| {name} | {r['F']} / {r['n']} | {100 * r['rec']:.0f}% | {100 * r['rnd']:.0f}% | {100 * r['diff']:+.0f} points "
                 f"[{100 * r['lo']:+.0f}, {100 * r['hi']:+.0f}] | {r['auc']:.3f} [{r['alo']:.3f}, {r['ahi']:.3f}] | {'passes' if ok else 'does not pass'} |")
        res.append((name, r))
    L += ["", "Recall by category of the tag in the sentence:", "", "| score | category | caught / tags |", "|---|---|---|"]
    for name, r in res:
        for c, (n, f) in sorted(r["cat"].items(), key=lambda x: -x[1][0]):
            L.append(f"| {name} | {c} | {f} / {n} |")
    text = "\n".join(L)
    out = ROOT / os.environ.get("ANNOTATE_DIR", "results")
    out.mkdir(exist_ok=True)
    (out / "screen_d4.md").write_text(text)
    print(text)


if __name__ == "__main__":
    main()
