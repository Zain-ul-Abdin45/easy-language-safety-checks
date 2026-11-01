"""Two post-hoc checks on the dev labels (exploratory: written after the dev results were seen).

1. Every condition against C1: harm per 100 words (severity 2-3), protected-item preservation and the share of C1's
   FKGL gain that is kept, with 95% paired bootstrap intervals over texts (all seeds of a text stay together).
2. Random-revert control: how much harm would a RANDOM choice of reachable spans to revert remove? For each base
   output, as many reachable spans are drawn at random as condition X actually reverted; a C1 harm tag (severity 2-3)
   counts as removed if its quote overlaps a drawn span. Assumption: a reverted span returns the source words, which
   are harmless. The random reduction is compared with the reduction measured on the labelled output of condition X.

Run:  .venv/bin/python src/controls.py [--split dev] [--boot 5000] [--draws 5000] [--seed 0]
Writes results/<ANNOTATE_DIR>/controls.md and prints it. Uses the primary labels only.
"""
import argparse
import os
from collections import defaultdict
from pathlib import Path

import numpy as np

import annotate as A
from auc_decision import auc, decide
from db import connect

ROOT = Path(__file__).resolve().parents[1]
CONDS = ["C1", "C2", "C3", "C4", "C5"]


def load(conn, split):
    rows = conn.execute("""
        SELECT co.id, b.id, b.text_id, r.seed, co.condition, co.word_count,
               (SELECT count(*) FROM harm_annotations h WHERE h.condition_output_id=co.id AND h.rater_role='primary' AND h.severity>=2),
               co.protected_preserved, co.protected_total, t.fkgl::float - co.fkgl::float
        FROM condition_outputs co JOIN base_outputs b ON b.id=co.base_output_id JOIN runs r ON r.id=b.run_id
        JOIN texts t ON t.id=b.text_id
        WHERE t.split=%s AND EXISTS (SELECT 1 FROM output_reviews o WHERE o.condition_output_id=co.id AND o.rater_role='primary')""",
        (split,)).fetchall()
    d = defaultdict(dict)   # (text, seed) -> condition -> row
    for r in rows:
        d[(r[2], r[3])][r[4]] = r
    return {k: v for k, v in d.items() if all(c in v for c in CONDS)}


def metrics(units, keys, cond):
    sel = [units[k][cond] for k in keys]
    words = sum(r[5] for r in sel)
    return (100.0 * sum(r[6] for r in sel) / words,
            sum(r[7] for r in sel) / max(sum(r[8] for r in sel), 1),
            float(np.mean([r[9] for r in sel])))


def vs_c1(units, boot, rng):
    texts = sorted({k[0] for k in units})
    by_text = defaultdict(list)
    for k in units:
        by_text[k[0]].append(k)
    out = {}
    for c in CONDS[1:]:
        def est(tx):
            keys = [k for t in tx for k in by_text[t]]
            h1, p1, f1 = metrics(units, keys, "C1")
            h2, p2, f2 = metrics(units, keys, c)
            return h1 - h2, p2 - p1, f2 / f1 if f1 else np.nan, h1, h2
        point = est(texts)
        draws = np.array([est(list(rng.choice(texts, len(texts)))) for _ in range(boot)])
        lo, hi = np.nanpercentile(draws[:, :3], [2.5, 97.5], axis=0)
        out[c] = (point, lo, hi)
    return out, len(texts)


def random_revert(conn, units, draws, rng):
    """Returns per condition: actual reduction, random reduction mean, 95% range, share of draws >= actual."""
    info = {}   # base output id -> (c1 output text, spans [(id, text)], tags [(quote, occurrence)], c1 words)
    for (t, s), conds in units.items():
        c1 = conds["C1"]
        text = conn.execute("SELECT output FROM condition_outputs WHERE id=%s", (c1[0],)).fetchone()[0]
        spans = conn.execute("SELECT id, output_span FROM changed_spans WHERE base_output_id=%s AND reachable ORDER BY id",
                             (c1[1],)).fetchall()
        tags = conn.execute("""SELECT output_quote, quote_occurrence FROM harm_annotations
                               WHERE condition_output_id=%s AND rater_role='primary' AND severity>=2 AND output_quote IS NOT NULL""",
                            (c1[0],)).fetchall()
        out_n = A.norm(text)
        cover = {}   # tag index -> set of span ids whose occurrence overlaps the quoted occurrence
        for i, (q, occ) in enumerate(tags):
            hits = A.find_all(out_n, A.norm(q))
            if not hits:
                continue
            q0, q1 = hits[(occ or 1) - 1] if (occ or 1) <= len(hits) else hits[0]
            cover[i] = {sid for sid, st in spans if st and any(s0 < q1 and q0 < s1 for s0, s1 in A.find_all(out_n, A.norm(st)))}
        n_tags = conn.execute("""SELECT count(*) FROM harm_annotations WHERE condition_output_id=%s AND rater_role='primary'
                                 AND severity>=2""", (c1[0],)).fetchone()[0]
        info[(t, s)] = (spans, cover, n_tags, c1[5])
    res = {}
    keys = list(units)
    words = sum(info[k][3] for k in keys)
    h1 = 100.0 * sum(info[k][2] for k in keys) / words
    for c in ["C2", "C3", "C5"]:
        n_rev = {}
        for k in keys:
            sids = [sid for sid, _ in info[k][0]]
            n_rev[k] = conn.execute("""SELECT count(*) FROM span_actions WHERE condition=%s AND action='revert' AND span_id = ANY(%s)""",
                                    (c, sids)).fetchone()[0] if sids else 0
        actual = h1 - metrics(units, keys, c)[0]
        sims = []
        for _ in range(draws):
            removed = 0
            for k in keys:
                spans, cover, _, _ = info[k]
                if not spans or not n_rev[k]:
                    continue
                chosen = {spans[i][0] for i in rng.choice(len(spans), min(n_rev[k], len(spans)), replace=False)}
                removed += sum(1 for cv in cover.values() if cv & chosen)
            sims.append(100.0 * removed / words)
        sims = np.array(sims)
        res[c] = (actual, sims.mean(), np.percentile(sims, 2.5), np.percentile(sims, 97.5), float((sims >= actual).mean()),
                  sum(n_rev.values()), sum(len(info[k][0]) for k in keys),
                  sum(1 for k in keys for cv in info[k][1].values() if cv), sum(info[k][2] for k in keys))
    return res, h1


def breakdown(conn, split):
    """Severity 2-3 tags on the C1 outputs by category and by where they sit relative to the word-level checks, and the
    harmful (y) spans against the output tags that overlap them."""
    c1 = conn.execute("""SELECT co.id, co.base_output_id, co.output, co.word_count FROM condition_outputs co
                         JOIN base_outputs b ON b.id=co.base_output_id JOIN texts t ON t.id=b.text_id
                         WHERE co.condition='C1' AND t.split=%s""", (split,)).fetchall()
    words = sum(r[3] for r in c1)
    where, bycat = defaultdict(int), defaultdict(lambda: defaultdict(int))
    for co_id, b, text, _ in c1:
        out_n = A.norm(text)
        spans = conn.execute("SELECT output_span, reachable FROM changed_spans WHERE base_output_id=%s", (b,)).fetchall()

        def overlap(q0, q1, reach):
            return any(r == reach and s and any(s0 < q1 and q0 < s1 for s0, s1 in A.find_all(out_n, A.norm(s))) for s, r in spans)
        for cat, q, occ in conn.execute("""SELECT category, output_quote, quote_occurrence FROM harm_annotations
                                           WHERE condition_output_id=%s AND rater_role='primary' AND severity>=2""", (co_id,)).fetchall():
            if not q:
                k = "omission (no quote, nothing to revert)"
            else:
                hits = A.find_all(out_n, A.norm(q))
                if not hits:
                    k = "quote not found"
                else:
                    q0, q1 = hits[(occ or 1) - 1] if (occ or 1) <= len(hits) else hits[0]
                    if overlap(q0, q1, True):
                        k = "overlaps a reachable span" + ("" if len(q.split()) <= 3 else " (quote > 3 words: counted unreachable)")
                    elif overlap(q0, q1, False):
                        k = "overlaps an unreachable change (rewrite or insertion)"
                    else:
                        k = "overlaps no changed span"
            where[k] += 1
            bycat[cat][k] += 1
    total = sum(where.values())
    L = ["## 3. Where the harm is (C1 outputs)", "",
         f"{total} tags of severity 2-3 on {len(c1)} C1 outputs ({100.0 * total / words:.2f} per 100 words).", "",
         "| category | tags | per 100 w | reachable | unreachable |", "|---|---|---|---|---|"]
    for cat, d in sorted(bycat.items(), key=lambda x: -sum(x[1].values())):
        n = sum(d.values())
        reach = d.get("overlaps a reachable span", 0)
        L.append(f"| {cat} | {n} | {100.0 * n / words:.2f} | {reach} | {n - reach} |")
    L += ["", "| where the tag sits | tags | share |", "|---|---|---|"]
    for k, v in sorted(where.items(), key=lambda x: -x[1]):
        L.append(f"| {k} | {v} | {100.0 * v / total:.0f}% |")
    sp = conn.execute("""SELECT cs.output_span, co.id, co.output FROM changed_spans cs
                         JOIN condition_outputs co ON co.base_output_id=cs.base_output_id AND co.condition='C1'
                         JOIN base_outputs b ON b.id=cs.base_output_id JOIN texts t ON t.id=b.text_id
                         WHERE cs.harmful_gold IS TRUE AND t.split=%s""", (split,)).fetchall()
    sc = defaultdict(int)
    for span, co_id, text in sp:
        out_n = A.norm(text)
        occs = A.find_all(out_n, A.norm(span)) if span else []
        cats = set()
        for cat, q, occ, sev in conn.execute("""SELECT category, output_quote, quote_occurrence, severity FROM harm_annotations
                                                WHERE condition_output_id=%s AND rater_role='primary' AND output_quote IS NOT NULL""",
                                             (co_id,)).fetchall():
            hits = A.find_all(out_n, A.norm(q))
            if hits:
                q0, q1 = hits[(occ or 1) - 1] if (occ or 1) <= len(hits) else hits[0]
                if any(s0 < q1 and q0 < s1 for s0, s1 in occs):
                    cats.add(f"{cat} (sev {sev})")
        sc[", ".join(sorted(cats)) or "no output tag overlaps this span"] += 1
    L += ["", f"The {len(sp)} spans labelled harmful, against the output tags that overlap them:", "",
          "| output tags overlapping the span | spans |", "|---|---|"]
    for k, v in sorted(sc.items(), key=lambda x: -x[1]):
        L.append(f"| {k} | {v} |")
    L += ["", "The reachable flag follows the importer's rule (quote of at most 3 words that overlaps a reachable span); omissions have "
              "no quote and are always unreachable."]
    return L


def consistency_auc(conn, split, boot, rng):
    """Sensitivity: AUC when the span label must agree with the output-level tags. A reachable dev span counts as
    tag-confirmed if the quote of a severity 2-3 tag on the C1 output overlaps it. Exploratory."""
    rows = conn.execute("""SELECT cs.id, b.text_id, cs.probability::float, cs.harmful_gold, cs.output_span, co.output, co.id
                           FROM changed_spans cs JOIN base_outputs b ON b.id=cs.base_output_id JOIN texts t ON t.id=b.text_id
                           JOIN condition_outputs co ON co.base_output_id=b.id AND co.condition='C1'
                           WHERE t.split=%s AND cs.reachable AND NOT cs.fragment AND cs.harmful_gold IS NOT NULL
                             AND cs.probability IS NOT NULL""", (split,)).fetchall()
    tid, prob, lab, conf = [], [], [], []
    for sid, t, pr, y, span, text, co_id in rows:
        out_n = A.norm(text)
        occs = A.find_all(out_n, A.norm(span)) if span else []
        hit = False
        for q, occ in conn.execute("""SELECT output_quote, quote_occurrence FROM harm_annotations WHERE condition_output_id=%s
                                      AND rater_role='primary' AND severity>=2 AND output_quote IS NOT NULL""", (co_id,)).fetchall():
            hits = A.find_all(out_n, A.norm(q))
            if hits:
                q0, q1 = hits[(occ or 1) - 1] if (occ or 1) <= len(hits) else hits[0]
                hit = hit or any(s0 < q1 and q0 < s1 for s0, s1 in occs)
        tid.append(t); prob.append(pr); lab.append(bool(y)); conf.append(hit)
    tid, prob, lab, conf = np.array(tid), np.array(prob), np.array(lab), np.array(conf)
    variants = [("as labelled in Unit 1 (the main analysis)", np.ones(len(lab), bool), lab),
                ("only tag-confirmed harmful spans; the other harmful spans dropped", ~lab | conf, lab & conf),
                ("harmful = overlaps a severity 2-3 tag (tags decide, labels ignored)", np.ones(len(lab), bool), conf)]
    L = ["## 4. Span labels against output tags: sensitivity AUC (exploratory)", "",
         f"Of the {int(lab.sum())} spans labelled harmful, {int((lab & conf).sum())} overlap a severity 2-3 tag on the C1 output, "
         f"{int((lab & ~conf).sum())} do not. Of the {int((~lab).sum())} spans labelled harmless, {int((~lab & conf).sum())} do overlap one.", "",
         "| variant | harmful / harmless | AUC [95% over texts] | rule |", "|---|---|---|---|"]
    for name, keep, pos in variants:
        idx0 = np.flatnonzero(keep)
        texts = np.unique(tid[idx0])
        by = {t: idx0[tid[idx0] == t] for t in texts}
        point = auc(prob[idx0], pos[idx0])
        ds = []
        for _ in range(boot):
            pick = rng.choice(texts, size=len(texts), replace=True)
            a = auc(prob[np.concatenate([by[t] for t in pick])], pos[np.concatenate([by[t] for t in pick])])
            if not np.isnan(a):
                ds.append(a)
        lo, hi = np.percentile(ds, [2.5, 97.5])
        L.append(f"| {name} | {int(pos[idx0].sum())} / {int((~pos[idx0]).sum())} | {point:.3f} [{lo:.3f}, {hi:.3f}] | "
                 f"{decide(point, lo, 0.5, 0.60).split(':')[0]} |")
    return L


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--split", default="dev")
    ap.add_argument("--boot", type=int, default=5000)
    ap.add_argument("--draws", type=int, default=5000)
    ap.add_argument("--seed", type=int, default=0)
    a = ap.parse_args()
    rng = np.random.default_rng(a.seed)
    with connect() as conn:
        units = load(conn, a.split)
        cmp_, n_texts = vs_c1(units, a.boot, rng)
        rr, h1 = random_revert(conn, units, a.draws, rng)
        bd = breakdown(conn, a.split) + [""] + consistency_auc(conn, a.split, a.boot, rng)
    L = [f"# Controls on the {a.split} labels (exploratory, post hoc)", "",
         f"{len(units)} (text, seed) units from {n_texts} texts; severity 2-3 harm, primary labels. "
         f"95% paired bootstrap over texts, {a.boot} resamples.", "",
         "## 1. Each condition against C1", "",
         "| condition | harm reduction per 100 w [95%] | preservation change [95%] | FKGL gain kept (C / C1) [95%] |", "|---|---|---|---|"]
    for c, (p, lo, hi) in cmp_.items():
        L.append(f"| {c} | {p[0]:+.2f} [{lo[0]:+.2f}, {hi[0]:+.2f}] | {p[1]:+.3f} [{lo[1]:+.3f}, {hi[1]:+.3f}] | "
                 f"{p[2]:.2f} [{lo[2]:.2f}, {hi[2]:.2f}] |")
    L += ["", f"C1 harm per 100 words: {h1:.2f}.", "",
          "## 2. Random-revert control", "",
          "Same number of reachable spans reverted per output as the condition did, chosen at random; a C1 harm tag counts as "
          "removed if its quote overlaps a drawn span (source words assumed harmless).", "",
          f"| condition | reverted / reachable spans | C1 tags that overlap a span | actual reduction | random reduction (mean, 95% range) | share of random draws >= actual (descriptive) |",
          "|---|---|---|---|---|---|"]
    for c, (act, m, lo, hi, p, nrev, nspan, ncov, ntag) in rr.items():
        L.append(f"| {c} | {nrev} / {nspan} | {ncov} of {ntag} | {act:+.2f} | {m:+.2f} ({lo:+.2f}, {hi:+.2f}) | {p:.3f} |")
    L += ["", "The last column compares the actual result with random selection within these data only. It is not a test across texts and not a p-value. Actual and random come from different sources (labels of the condition's own outputs against tags on the C1 output), so small differences, such as C3's, cannot be read as meaningful. Reading: if the actual reduction lies inside the random range, reverting many spans explains it and the condition's "
              "choice of spans adds nothing measurable. Only a reduction above the random range points to a useful choice. "
              "The overlap rule assigns tags to spans by quote position; tags without a quote (omissions) cannot be removed."]
    text = "\n".join(L + [""] + bd)
    outdir = ROOT / os.environ.get("ANNOTATE_DIR", "results")
    outdir.mkdir(exist_ok=True)
    (outdir / "controls.md").write_text(text)
    print(text)


if __name__ == "__main__":
    main()
