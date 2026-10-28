"""January go/no-go: AUC of the probability signal on labelled dev spans, with a bootstrap interval over texts
and the three-way decision of protocol section 6.

Run:  .venv/bin/python src/auc_decision.py [--boot 5000 --seed 0]

Spans used: dev split, reachable, labelled y or n (fragments and unlabelled excluded), with a probability.
Low probability should mean harmful, so AUC = P(prob of a harmless span > prob of a harmful span), ties half.
Texts are resampled, not spans, because seeds and spans of one text are not independent.
Thresholds come from p3.success_criteria (auc_go_lower, auc_inconclusive_point).

Sensitivity: spans the annotator marked `discuss` are re-run once as all harmful and once as all harmless.
Tau for C2 (protocol section 6): the largest value that reverts at most tau_max_harmless_reverted of the
harmless dev spans, reported with the share of harmful spans it would revert. Only meaningful after a GO.
"""
import argparse
from datetime import datetime

import numpy as np

from db import connect

MIN_HARMFUL = 40   # planned minimum number of harmful spans (protocol section 6)


def auc(prob, harmful):
    bad, ok = prob[harmful], prob[~harmful]
    if len(bad) == 0 or len(ok) == 0:
        return np.nan
    diff = ok[:, None] - bad[None, :]
    return float(((diff > 0) + 0.5 * (diff == 0)).mean())


def decide(point, lower, go_lower, inconclusive_point):
    if np.isnan(point) or np.isnan(lower):
        return "no data"
    if lower > go_lower:
        return "GO: keep the probability step"
    if point >= inconclusive_point:
        return "INCONCLUSIVE: add dev texts once, then decide"
    return "NO-GO: continue with lookup and grammar only (C3, C4)"


def compute(conn, boot=5000, seed=0, discuss="as_labelled"):
    """discuss: 'as_labelled' (main analysis), 'harmful' or 'harmless' (sensitivity for spans marked discuss)."""
    rows = conn.execute("""SELECT b.text_id, cs.probability::float, cs.harmful_gold, cs.discuss
                           FROM changed_spans cs JOIN base_outputs b ON b.id = cs.base_output_id
                           JOIN texts t ON t.id = b.text_id
                           WHERE t.split = 'dev' AND cs.reachable AND NOT cs.fragment
                             AND cs.harmful_gold IS NOT NULL AND cs.probability IS NOT NULL""").fetchall()
    crit = dict(conn.execute("SELECT key, threshold::float FROM success_criteria").fetchall())
    go_lower, inc_point = crit["auc_go_lower"], crit["auc_inconclusive_point"]
    if not rows:
        return {"decision": "no data", "n_spans": 0}
    tid = np.array([r[0] for r in rows])
    prob = np.array([r[1] for r in rows])
    harm = np.array([r[2] for r in rows], dtype=bool)
    disc = np.array([r[3] for r in rows], dtype=bool)
    if discuss == "harmful":
        harm = harm | disc
    elif discuss == "harmless":
        harm = harm & ~disc
    texts = np.unique(tid)
    by_text = {t: np.flatnonzero(tid == t) for t in texts}
    point = auc(prob, harm)
    rng = np.random.default_rng(seed)
    draws = []
    for _ in range(boot):
        pick = rng.choice(texts, size=len(texts), replace=True)
        idx = np.concatenate([by_text[t] for t in pick])
        a = auc(prob[idx], harm[idx])
        if not np.isnan(a):
            draws.append(a)
    lower, upper = (np.percentile(draws, [2.5, 97.5]) if len(draws) > 1 else (np.nan, np.nan))
    return {"n_spans": len(rows), "n_harmful": int(harm.sum()), "n_harmless": int((~harm).sum()),
            "n_texts": len(texts), "n_discuss": int(disc.sum()), "auc": point,
            "tau": tau_on_dev(prob, harm, crit.get("tau_max_harmless_reverted", 0.20)),
            "n_texts_": len(texts), "auc_": point, "ci_low": float(lower), "ci_high": float(upper),
            "boot_used": len(draws), "boot_requested": boot,
            "enough_harmful": int(harm.sum()) >= MIN_HARMFUL,
            "decision": decide(point, lower, go_lower, inc_point),
            "rule": f"GO if lower bound > {go_lower}; INCONCLUSIVE if AUC >= {inc_point} but lower bound <= {go_lower}; else NO-GO"}


def tau_on_dev(prob, harm, max_harmless_reverted):
    """Largest tau with at most `max_harmless_reverted` of harmless spans below it (a span is reverted if prob < tau)."""
    ok = np.sort(prob[~harm])
    if len(ok) == 0:
        return None
    k = int(np.floor(max_harmless_reverted * len(ok)))
    tau = float(ok[k]) if k < len(ok) else float(ok[-1])   # spans strictly below ok[k] are reverted: at most k
    bad = prob[harm]
    return {"tau": tau, "harmless_reverted": float((ok < tau).mean()),
            "harmful_reverted": float((bad < tau).mean()) if len(bad) else None}


def sensitivity(conn, boot=5000, seed=0):
    return {m: compute(conn, boot, seed, m) for m in ("harmful", "harmless")}


def as_markdown(r, sens=None):
    if r["n_spans"] == 0:
        return "_no labelled dev spans yet_"
    warn = "" if r["enough_harmful"] else f"\n\nWarning: fewer than {MIN_HARMFUL} harmful spans; the interval is not reliable."
    return (f"{r['n_spans']} spans ({r['n_harmful']} harmful, {r['n_harmless']} harmless) from {r['n_texts']} dev texts.  \n"
            f"AUC {r['auc']:.3f}, 95% bootstrap interval over texts [{r['ci_low']:.3f}, {r['ci_high']:.3f}] "
            f"({r['boot_used']} of {r['boot_requested']} resamples usable).  \n"
            f"Decision: **{r['decision']}**  \nRule: {r['rule']}.{warn}"
            + (_sens_md(r, sens) if sens else "") + _tau_md(r))


def _sens_md(r, sens):
    if not r["n_discuss"]:
        return "\n\nSensitivity: no span is marked discuss."
    lines = [f"\n\nSensitivity for the {r['n_discuss']} span(s) marked discuss (main analysis uses the annotator's best guess):",
             "", "| discuss spans counted as | AUC | 95% interval | decision |", "|---|---|---|---|"]
    for m, x in sens.items():
        lines.append(f"| {m} | {x['auc']:.3f} | [{x['ci_low']:.3f}, {x['ci_high']:.3f}] | {x['decision']} |")
    same = len({x["decision"] for x in sens.values()} | {r["decision"]}) == 1
    lines.append("\nThe decision is " + ("the same in all three runs." if same else "NOT the same in all three runs: report this."))
    return "\n".join(lines)


def _tau_md(r):
    t = r.get("tau")
    if not t:
        return ""
    hr = "n/a" if t["harmful_reverted"] is None else f"{t['harmful_reverted']:.0%}"
    return (f"\n\nTau for C2 on dev (preliminary rule): {t['tau']:.3f}, reverts {t['harmless_reverted']:.0%} of harmless and {hr} of "
            f"harmful spans. Use only if the decision is GO.")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--boot", type=int, default=5000)
    ap.add_argument("--seed", type=int, default=0)
    a = ap.parse_args()
    with connect() as conn:
        res = compute(conn, a.boot, a.seed)
        sens = sensitivity(conn, a.boot, a.seed) if res["n_spans"] else None
    print(f"Run: {datetime.now().astimezone():%Y-%m-%d %H:%M:%S %Z}\n" + as_markdown(res, sens))
