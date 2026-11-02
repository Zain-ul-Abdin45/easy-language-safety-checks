"""SENSITIVITY ONLY. Dev Gate A numbers for D4a, D4b and D5 under the held-out flag rule (exactly the k = floor(0.3 n) lowest sentences, ties by
sentence ID) next to the rule they were computed with (score at or below the 30th percentile). The Gate A results already reported stand as
computed; nothing here replaces them.

The old rule is recomputed first and must reproduce the published row in results/<dir>/screen_d4.md or screen_d5.md. Same bootstrap draws for both
rules (seed 0, same call order as the original screens), so any difference comes from the flag rule alone. Dev sentences carry no stored sentence ID:
the tie-break key is the position in the cached score file, which runs by text, then seed, then sentence order, the order IDs would have.

Run:  .venv/bin/python src/dev_sensitivity_tie_rule.py [--boot 5000]      Writes results/v3/dev_sensitivity_tie_rule.md
      --llama-dir results/v3/repro/llama --out dev_sensitivity_tie_rule_pinned_llama.md   re-runs it on the pinned-date Llama reproduction (319 D4 sentences)
"""
import argparse
import json
from pathlib import Path

import numpy as np

from d4_screen import evaluate
from flag_rule import flag_lowest

ROOT = Path(__file__).resolve().parents[1]
RUNS = [("Qwen 2.5 1.5B", "results/dev24", [("d4_scores.json", "a", "D4a mean log-probability", "screen_d4.md"),
                                           ("d4_scores.json", "b", "D4b lowest changed-span probability", "screen_d4.md"),
                                           ("d5_scores_primary.json", "a", "D5 DeBERTa (primary)", "screen_d5.md"),
                                           ("d5_scores_minicheck.json", "a", "D5 MiniCheck (sensitivity)", "screen_d5.md")]),
        ("Llama 3.2 1B", "results/llama_dev24", [("d4_scores.json", "a", "D4a mean log-probability", "screen_d4.md"),
                                                 ("d4_scores.json", "b", "D4b lowest changed-span probability", "screen_d4.md"),
                                                 ("d5_scores_primary.json", "a", "D5 DeBERTa (primary)", "screen_d5.md"),
                                                 ("d5_scores_minicheck.json", "a", "D5 MiniCheck (sensitivity)", "screen_d5.md")])]


def new_rule(score):
    flagged = flag_lowest(enumerate(score.tolist()))
    return np.array([i in flagged for i in range(len(score))])


def cells(r):
    return (f"{r['F']} / {r['n']} ({100 * r['F'] / r['n']:.2f}%)", f"{100 * r['rec']:.0f}%", f"{100 * r['rnd']:.0f}%",
            f"{100 * r['diff']:+.0f} [{100 * r['lo']:+.0f}, {100 * r['hi']:+.0f}]", f"{r['auc']:.3f} [{r['alo']:.3f}, {r['ahi']:.3f}]")


def published(r):   # the part of the published row that does not depend on the flag-rate column format
    return (f"| {r['F']} / {r['n']} | {100 * r['rec']:.0f}% | {100 * r['rnd']:.0f}% | {100 * r['diff']:+.0f} points "
            f"[{100 * r['lo']:+.0f}, {100 * r['hi']:+.0f}] | {r['auc']:.3f} [{r['alo']:.3f}, {r['ahi']:.3f}] |")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--boot", type=int, default=5000)
    ap.add_argument("--llama-dir", default="results/llama_dev24", help="folder with the Llama score files and screens (default: the reported v2 files)")
    ap.add_argument("--out", default="dev_sensitivity_tie_rule.md")
    a = ap.parse_args()
    runs = [(m, a.llama_dir if m.startswith("Llama") else d, c) for m, d, c in RUNS]
    L = ["# Dev sensitivity: the held-out flag rule applied to the dev scores (SENSITIVITY ONLY)", "",
         "**The Gate A results reported on 31 Oct and 1 Nov stand as computed. This table does not replace them.** It shows what the dev numbers would have been under the "
         "rule fixed for the held-out run: flag exactly the k = floor(0.3 n) lowest-scoring sentences, ties broken by sentence ID. The rule they were computed under "
         "flags every sentence at or below the 30th percentile, which can exceed 30% when scores tie.", "",
         "Both rules use the same bootstrap draws (seed 0, original call order), so differences come from the flag rule alone. The old-rule rows reproduce the published rows "
         "(checked against the screen files; a mismatch stops the script). Tie-break key for dev: position in the cached score file (text, seed, sentence order).", ""]
    changed = []
    for model, d, checks in runs:
        L += [f"## {model}", "", "| check | rule | flagged / sentences | recall | random recall | difference, points [95%] | AUC [95%] | Gate A conditions met |", "|---|---|---|---|---|---|---|---|"]
        rngs = {"old": {}, "new": {}}
        for rule in ("old", "new"):
            for fname, key, name, screen in checks:
                sents = [dict(x, unit=tuple(x["unit"])) for x in json.loads((ROOT / d / fname).read_text())["sents"]]
                # original call order: D4a then D4b share one generator per file; each D5 model file shares the D5 generator
                group = "d4" if fname.startswith("d4") else "d5"
                rng = rngs[rule].setdefault(group, np.random.default_rng(0))
                r = evaluate(sents, key, a.boot, rng, None if rule == "old" else new_rule)
                ok = r["lo"] > 0 and r["alo"] > 0.5 and r["rate"] <= 0.30 + 1e-9
                if rule == "old":
                    assert published(r) in (ROOT / d / screen).read_text(), f"{model} {name}: old rule does not reproduce the published row\n{published(r)}"
                rngs[rule].setdefault("res", {})[name] = (r, ok)
                L.append(f"| {name} | {'old: 30th percentile' if rule == 'old' else 'new: k lowest'} | " + " | ".join(cells(r)) + f" | {'yes' if ok else 'no'} |")
            print(model, rule, "done", flush=True)
        for _, _, name, _ in checks:
            (ro, oko), (rn, okn) = rngs["old"]["res"][name], rngs["new"]["res"][name]
            if oko != okn:
                changed.append(f"{model}, {name}: Gate A '{'met' if oko else 'not met'}' under the old rule, '{'met' if okn else 'not met'}' under the new rule "
                               f"(flag rate {100 * ro['rate']:.2f}% -> {100 * rn['rate']:.2f}%; difference {100 * ro['diff']:+.1f} -> {100 * rn['diff']:+.1f} points, lower bound {100 * ro['lo']:+.1f} -> {100 * rn['lo']:+.1f})")
        L.append("")
    L += ["## Where the verdict on a check would differ", ""] + ([f"- {c}" for c in changed] if changed else ["- None: no check changes its Gate A outcome under the new rule."])
    out = ROOT / "results/v3"; out.mkdir(parents=True, exist_ok=True)
    (out / a.out).write_text("\n".join(L) + "\n")
    print("\n".join(L))


if __name__ == "__main__":
    main()
