"""Compare the reproduction run (results/v3/repro/<model>) with the reported dev results (results/dev24 or results/llama_dev24), file by file.
Markdown reports must be identical; the D5 table's 'seconds per sentence' column is machine timing and is masked. The cached score files are
compared number by number (the D4 file also by its count of regenerated outputs that did not match the stored text).
Run:  .venv/bin/python src/repro_compare.py        Writes results/v3/repro_report.md
"""
import difflib
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MODELS = [("Qwen 2.5 1.5B", "results/dev24", "results/v3/repro/qwen"), ("Llama 3.2 1B", "results/llama_dev24", "results/v3/repro/llama")]
MD = ["controls.md", "screen_d1_d2.md", "screen_d3.md", "screen_d4.md", "screen_d5.md", "digit_guard.md"]


def norm(name, text):
    if name == "screen_d5.md":   # mask the seconds-per-sentence cell (7th) of the model rows
        out = []
        for line in text.splitlines():
            if re.match(r"\| (cross-encoder|lytang)/", line):
                cells = line.split("|")
                if len(cells) > 8:   # category rows have fewer columns and no timing
                    cells[7] = " (timing masked) "; line = "|".join(cells)
            out.append(line)
        return "\n".join(out)
    return text


def main():
    L = ["# Reproduction of the dev results from the stored outputs", "",
         "Every dev script was re-run against the stored outputs and labels in the database (read-only) into `results/v3/repro/`, and compared with the reported files. "
         "D4 regenerates each output with its seed to score it (the v2 method); the count of outputs whose regenerated text differs from the stored one is the determinism check.", ""]
    total_bad = 0
    for model, ref, new in MODELS:
        L += [f"## {model}", "", "| file | result | detail |", "|---|---|---|"]
        for f in MD:
            a, b = ROOT / ref / f, ROOT / new / f
            if not b.exists():
                L.append(f"| {f} | **MISSING** | the reproduction did not produce it |"); total_bad += 1; continue
            ta, tb = norm(f, a.read_text()), norm(f, b.read_text())
            if ta == tb:
                L.append(f"| {f} | identical | {len(ta.splitlines())} lines |")
            else:
                d = [x for x in difflib.unified_diff(ta.splitlines(), tb.splitlines(), lineterm="", n=0) if x[:1] in "+-" and x[:3] not in ("+++", "---")]
                L.append(f"| {f} | **DIFFERS** | {len(d)} changed lines; first: `{d[0][:140]}` / `{d[1][:140] if len(d) > 1 else ''}` |"); total_bad += 1
        for fname in ("d4_scores.json", "d5_scores_primary.json", "d5_scores_minicheck.json"):
            a, b = ROOT / ref / fname, ROOT / new / fname
            if not b.exists():
                L.append(f"| {fname} | **MISSING** | |"); total_bad += 1; continue
            ja, jb = json.loads(a.read_text()), json.loads(b.read_text())
            sa, sb = ja["sents"], jb["sents"]
            if len(sa) != len(sb):
                L.append(f"| {fname} | **DIFFERS** | {len(sa)} vs {len(sb)} sentences |"); total_bad += 1; continue
            keys = [k for k in ("a", "b") if k in sa[0]]
            md = max(abs(x[k] - y[k]) for x, y in zip(sa, sb) for k in keys)
            same = all(x["harmful"] == y["harmful"] and list(x["unit"]) == list(y["unit"]) for x, y in zip(sa, sb))
            extra = f"; regenerated outputs not matching the stored text: reported {ja.get('mismatch')}, now {jb.get('mismatch')}" if "mismatch" in ja else ""
            ok = same and md < 1e-6 and ja.get("mismatch") == jb.get("mismatch")
            total_bad += not ok
            L.append(f"| {fname} | {'identical' if ok else '**DIFFERS**'} | {len(sa)} sentences, max score difference {md:.1e}, labels and units equal: {same}{extra} |")
        L.append("")
    L += ["## Verdict", "", "All reported dev files reproduced." if total_bad == 0 else f"**{total_bad} item(s) did not reproduce exactly; see the rows marked above.**"]
    out = ROOT / "results/v3/repro_report.md"
    out.write_text("\n".join(L) + "\n")
    print("\n".join(L))


if __name__ == "__main__":
    main()
