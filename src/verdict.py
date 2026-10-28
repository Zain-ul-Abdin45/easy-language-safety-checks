"""C5 vs C1 verdict with paired bootstrap intervals over texts (protocol section 9).

Run:  .venv/bin/python src/verdict.py [--split heldout] [--boot 5000 --seed 0]

Outputs used: C1 and C5 outputs that the PRIMARY annotator has reviewed (including "none"). A (text, seed) pair
is used only if BOTH its C1 and its C5 output are reviewed. Second-person and consistency labels are never counted.
Unit of resampling is the text (all seeds of a text stay together), applied to C1 and C5 together (paired).

Criteria (thresholds from p3.success_criteria):
  harm            reduction = C1 harm per 100 words minus C5. Judged on the interval: met if the lower bound is > 0.
  preservation    C5 - C1 protected-item preservation >= 0 (point estimate; interval reported).
  simplification  Guard 1, narrow job: the checks did not undo the simplification. C5 mean FKGL gain / C1 mean FKGL
                  gain >= min_simplification_kept. FKGL is a proxy, not validated against human judgment.
  simplicity flag Guard 2, independent of FKGL: share of outputs the annotator flagged as insufficiently simplified,
                  C5 minus C1 <= max_simplicity_flag_increase (point estimate; interval reported).
Verdict: success = all four met; partial = harm met, another missed; inconclusive = reduction > 0 but the
interval includes 0; negative = no reduction. Sensitivity: the same run without outputs marked discuss.
Direction per seed is reported as a stability check.
"""
import argparse
from datetime import datetime

import numpy as np

from db import connect

MIN_TEXTS = 30   # fewer texts than this: intervals are not reliable


def load(conn, split):
    rows = conn.execute("""
        SELECT b.text_id, r.seed, co.condition, co.word_count,
               (SELECT count(*) FROM harm_annotations h WHERE h.condition_output_id=co.id AND h.rater_role='primary'
                       AND h.severity>=2),
               co.protected_preserved, co.protected_total, t.fkgl::float - co.fkgl::float,
               EXISTS (SELECT 1 FROM output_flags f WHERE f.condition_output_id=co.id AND f.rater_role='primary'
                       AND f.kind='discuss'),
               EXISTS (SELECT 1 FROM output_flags f WHERE f.condition_output_id=co.id AND f.rater_role='primary'
                       AND f.kind IN ('simplicity_lexical','simplicity_structural')),
               (SELECT count(*) FROM harm_annotations h WHERE h.condition_output_id=co.id AND h.rater_role='primary')
        FROM condition_outputs co JOIN base_outputs b ON b.id=co.base_output_id JOIN runs r ON r.id=b.run_id
        JOIN texts t ON t.id=b.text_id
        WHERE t.split=%s AND co.condition IN ('C1','C5')
          AND EXISTS (SELECT 1 FROM output_reviews o WHERE o.condition_output_id=co.id AND o.rater_role='primary')""",
        (split,)).fetchall()
    crit = dict(conn.execute("SELECT key, threshold::float FROM success_criteria").fetchall())
    return rows, crit["min_simplification_kept"], crit["max_simplicity_flag_increase"]


def stats(rows):
    """rows: tuples as loaded. Returns harm per 100w (C1, C5), preservation (C1, C5), mean FKGL gain (C1, C5)."""
    out = {}
    for c in ("C1", "C5"):
        sel = [r for r in rows if r[2] == c]
        words = sum(r[3] for r in sel)
        out[c] = (100.0 * sum(r[4] for r in sel) / words if words else np.nan,
                  sum(r[5] for r in sel) / max(sum(r[6] for r in sel), 1),
                  float(np.mean([r[7] for r in sel])) if sel else np.nan,
                  float(np.mean([r[9] for r in sel])) if sel else np.nan)
    return out


def paired(rows):
    """Keep a (text, seed) only if both its C1 and its C5 output are in rows."""
    have = {}
    for r in rows:
        have.setdefault((r[0], r[1]), set()).add(r[2])
    return [r for r in rows if have[(r[0], r[1])] >= {"C1", "C5"}]


def summarise(rows, min_kept, max_flag_inc, boot, seed):
    rows = paired(rows)
    by_text = {}
    for r in rows:
        by_text.setdefault(r[0], []).append(r)
    ids = list(by_text)
    if not ids:
        return None

    def metrics(pick):
        s = stats([r for t in pick for r in by_text[t]])
        red = s["C1"][0] - s["C5"][0]
        dpres = s["C5"][1] - s["C1"][1]
        kept = s["C5"][2] / s["C1"][2] if s["C1"][2] else np.nan
        dflag = s["C5"][3] - s["C1"][3]
        return s, red, dpres, kept, dflag

    s, red, dpres, kept, dflag = metrics(ids)
    rng = np.random.default_rng(seed)
    draws = np.array([metrics(list(rng.choice(ids, size=len(ids), replace=True)))[1:] for _ in range(boot)], dtype=float)
    ci = {k: np.nanpercentile(draws[:, i], [2.5, 97.5]) for i, k in enumerate(("reduction", "preservation", "kept", "flag"))}
    met_harm = ci["reduction"][0] > 0
    met_pres = dpres >= 0
    met_simp = kept >= min_kept
    met_flag = dflag <= max_flag_inc
    if not (red > 0):
        verdict = "negative: no harm reduction"
    elif not met_harm:
        verdict = "inconclusive: reduction in the point estimate but the interval includes 0"
    elif met_pres and met_simp and met_flag:
        verdict = "success"
    else:
        verdict = "partial: harm reduced, " + ", ".join(
            n for n, ok in (("preservation below C1", met_pres), ("FKGL guard missed", met_simp),
                            ("more simplicity flags than allowed", met_flag)) if not ok)
    seeds = sorted({r[1] for r in rows})
    per_seed = {}
    for sd in seeds:
        sub = [r for r in rows if r[1] == sd]
        ss = stats(sub)
        per_seed[sd] = ss["C1"][0] - ss["C5"][0]
    return {"n_texts": len(ids), "harm_c1": s["C1"][0], "harm_c5": s["C5"][0], "reduction": red, "ci_red": ci["reduction"],
            "dpres": dpres, "ci_pres": ci["preservation"], "kept": kept, "ci_kept": ci["kept"], "min_kept": min_kept,
            "dflag": dflag, "ci_flag": ci["flag"], "max_flag_inc": max_flag_inc, "flag_c1": s["C1"][3], "flag_c5": s["C5"][3],
            "met": (met_harm, met_pres, met_simp, met_flag), "verdict": verdict, "per_seed": per_seed}


def as_markdown(main, sens):
    if not main:
        return "_no reviewed C1 and C5 outputs yet_"
    def block(r):
        return (f"| harm per 100 words | C1 {r['harm_c1']:.2f}, C5 {r['harm_c5']:.2f}; reduction {r['reduction']:.2f} "
                f"[{r['ci_red'][0]:.2f}, {r['ci_red'][1]:.2f}] | {'met' if r['met'][0] else 'not met'} (lower bound > 0) |\n"
                f"| preservation C5 - C1 | {r['dpres']:+.3f} [{r['ci_pres'][0]:+.3f}, {r['ci_pres'][1]:+.3f}] | {'met' if r['met'][1] else 'not met'} (>= 0) |\n"
                f"| simplification kept (FKGL proxy) | {r['kept']:.2f} [{r['ci_kept'][0]:.2f}, {r['ci_kept'][1]:.2f}] | "
                f"{'met' if r['met'][2] else 'not met'} (guard 1: >= {r['min_kept']:.2f}, preliminary) |\n"
                f"| simplicity flags C5 - C1 (human) | C1 {r['flag_c1']:.0%}, C5 {r['flag_c5']:.0%}; {r['dflag']:+.0%} "
                f"[{r['ci_flag'][0]:+.0%}, {r['ci_flag'][1]:+.0%}] | {'met' if r['met'][3] else 'not met'} "
                f"(guard 2: <= {r['max_flag_inc']:+.0%}, preliminary) |")
    warn = "" if main["n_texts"] >= MIN_TEXTS else f"\n\nWarning: {main['n_texts']} texts, fewer than {MIN_TEXTS}; the intervals are not reliable."
    seeds = ", ".join(f"seed {k}: {v:+.2f}" for k, v in main["per_seed"].items())
    same_dir = len({v > 0 for v in main["per_seed"].values()}) == 1
    txt = (f"{main['n_texts']} texts, 95% paired bootstrap over texts.\n\n| criterion | estimate [95% interval] | status |\n|---|---|---|\n{block(main)}"
           f"\n\nVerdict: **{main['verdict']}**\n\nStability, harm reduction per seed: {seeds} "
           f"({'same direction on every seed' if same_dir else 'direction differs between seeds: report this'}).{warn}")
    if sens:
        txt += (f"\n\nSensitivity, outputs marked discuss removed: reduction {sens['reduction']:.2f} "
                f"[{sens['ci_red'][0]:.2f}, {sens['ci_red'][1]:.2f}], verdict: {sens['verdict']}"
                f" ({'same as main' if sens['verdict'] == main['verdict'] else 'differs from main: report this'}).")
    if main.get("all_tags"):
        a = main["all_tags"]
        txt += (f"\n\nSensitivity, harm counted with all tags (severity 1-3): reduction {a['reduction']:.2f} "
                f"[{a['ci_red'][0]:.2f}, {a['ci_red'][1]:.2f}], verdict: {a['verdict']}"
                f" ({'same as main' if a['verdict'] == main['verdict'] else 'differs from main: report this'}).")
    return txt


def compute(conn, split="heldout", boot=5000, seed=0):
    rows, min_kept, max_flag = load(conn, split)
    if not rows:
        return None, None
    main = summarise(rows, min_kept, max_flag, boot, seed)
    keep = {(r[0], r[1]) for r in rows if r[8]}
    rest = [r for r in rows if (r[0], r[1]) not in keep]
    sens = summarise(rest, min_kept, max_flag, boot, seed) if keep and rest else None
    # pre-specified sensitivity: harm counted with all tags (severity 1-3) instead of severity 2-3
    main["all_tags"] = summarise([r[:4] + (r[10],) + r[5:] for r in rows], min_kept, max_flag, boot, seed)
    return main, sens


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--split", default="heldout", choices=["dev", "heldout"])
    ap.add_argument("--boot", type=int, default=5000)
    ap.add_argument("--seed", type=int, default=0)
    a = ap.parse_args()
    with connect() as conn:
        main, sens = compute(conn, a.split, a.boot, a.seed)
    print(f"Run: {datetime.now().astimezone():%Y-%m-%d %H:%M:%S %Z}, split {a.split}\n" + as_markdown(main, sens))
