"""Re-time one generation to see whether a slow output was the model or the machine. Generates the same text and seed N times in one process with
the pinned model, records seconds, tokens, tokens/s and the machine state before each run, and checks every repeat produced the same token IDs.
No database, no checks, nothing stored except results/v3/timing_recheck_<text>_s<seed>.md.

Run:  .venv/bin/python src/timing_recheck.py --text S04 --seed 1 --n 4 [--texts data/smoke/smoke_texts.jsonl]
"""
import argparse
import json
import statistics
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--text", required=True)
    ap.add_argument("--seed", type=int, required=True)
    ap.add_argument("--n", type=int, default=4)
    ap.add_argument("--texts", default="data/smoke/smoke_texts.jsonl")
    a = ap.parse_args()
    import tokens_store as T
    row = next(json.loads(l) for l in open(ROOT / a.texts) if json.loads(l)["id"] == a.text)
    tok, model = T.load_model_pinned()
    L = [f"# Timing recheck: {a.text}, seed {a.seed}, {a.n} repeats in one process", "",
         "| repeat | tokens | gen s | tok/s | mains | low power | load | other busy | same token IDs as repeat 1 |", "|---|---|---|---|---|---|---|---|---|"]
    first, secs = None, []
    for i in range(1, a.n + 1):
        m = T.machine_state()
        g = T.generate_tokens(tok, model, row["body"], a.seed)
        first = first or g["ids"]
        secs.append(g["gen_s"])
        L.append(f"| {i} | {len(g['ids'])} | {g['gen_s']:.1f} | {len(g['ids']) / g['gen_s']:.1f} | {'yes' if m['on_ac'] else '**no**'} | {m['low_power_mode']} | {m['load1']} | "
                 f"{', '.join(m['other_busy']) or '-'} | {'yes' if g['ids'] == first else '**NO**'} |")
        print(L[-1], flush=True)
    L += ["", f"Median {statistics.median(secs):.1f}s, range {min(secs):.1f} to {max(secs):.1f}s. The run-1 smoke figure for this output was 36.8s for 54 tokens "
          f"(see results/v3/p3_v3_smoke_report_run1.md)."]
    out = ROOT / "results/v3"; out.mkdir(parents=True, exist_ok=True)
    (out / f"timing_recheck_{a.text}_s{a.seed}.md").write_text("\n".join(L) + "\n")


if __name__ == "__main__":
    main()
