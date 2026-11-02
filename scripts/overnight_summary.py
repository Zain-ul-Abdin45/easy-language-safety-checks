"""Builds results/v3/overnight_summary.md from the stage log folder of one overnight run. Usage: overnight_summary.py LOGDIR OVERHEAD_SCHEMA"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
log, schema = (ROOT / sys.argv[1]).resolve(), sys.argv[2]
rd = lambda p: (ROOT / p).read_text() if (ROOT / p).exists() else ""
L = [f"# Overnight v3 run: summary", "", f"Log folder: `{log.relative_to(ROOT)}`. Overhead-run schema: `{schema}`.", "", "## Stages", "", "| stage | status | seconds |", "|---|---|---|"]
for line in (log / "status.tsv").read_text().splitlines():
    n, st, sec, *_ = line.split("\t")
    L.append(f"| {n} | {'**' + st + '**' if st not in ('ok', 'dry') else st} | {sec} |")

rep = rd(f"results/v3/{schema}_report.md")
L += ["", "## Clean overhead run", ""]
if rep:
    keep = [l for l in rep.splitlines() if l.startswith(("Outputs:", "Generator", "Cold start", "On mains", "**Timing is not clean", "No output flagged", "**Measured outputs", "| D5, both", "| **Full pipeline", "| C2 ", "| C5 ", "| Check"))]
    L += keep + ["", f"Full report: `results/v3/{schema}_report.md`."]
else:
    L += ["Not run (the machine did not become ready, or the stage failed): see the stage table and `run.log`."]

L += ["", "## D5 timing study", ""]
st = rd("results/v3/d5_timing_study.md")
L += (st.splitlines()[3:] if st else ["Not run."])

L += ["", "## Reproduction of the dev results", ""]
rc = rd("results/v3/repro_report.md")
if rc:
    L += [l for l in rc.splitlines() if "DIFFERS" in l or "MISSING" in l or l.startswith(("All reported", "**")) or l.startswith("## ")]
    L += ["", "Full table: `results/v3/repro_report.md`."]
else:
    L += ["Not run or the comparison failed."]

L += ["", "## Go/no-go interval (0.404 or 0.409)", ""]
auc = (log / "qwen_auc_decision.log").read_text() if (log / "qwen_auc_decision.log").exists() else ""
ctl = rd("results/v3/repro/qwen/controls.md")
found = lambda txt: sorted(set(re.findall(r"0\.569 \[[0-9.]+, [0-9.]+\]", txt)))
L += [f"- `src/auc_decision.py` (seed 0, 5000 resamples) prints: {', '.join(found(auc)) or 'no match; see qwen_auc_decision.log'}",
      f"- `controls.md` section 4, first row, re-run now prints: {', '.join(found(ctl)) or 'no match'}",
      f"- as reported in `results/dev24/controls.md`: {', '.join(found(rd('results/dev24/controls.md')))}"]
(ROOT / "results/v3/overnight_summary.md").write_text("\n".join(L) + "\n")
print("\n".join(L))
