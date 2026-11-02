"""Why does D5 cost what it costs? v2 recorded 0.045 s per sentence (the exposé's 0.04); the first v3 output took about 0.46 s per sentence.
Candidate causes tested on the same real dev pairs: cold first call, thread count (v2's d5_screen sets cpu_count-1 threads, the v3 driver keeps the
generation thread count), and batching (input order in chunks of 16 as in v2, versus all pairs of an output in one length-sorted batch).
Every row is timed warm (after a discarded call), median of 3 repeats, per output as the pipeline would call it.

Run:  .venv/bin/python src/d5_timing_study.py [--outputs 12]         Writes results/v3/d5_timing_study.md
"""
import argparse
import os
import statistics
import time
from pathlib import Path

import torch

N_DEFAULT_THREADS = torch.get_num_threads()          # before d5_screen changes it
import d5_screen as D                                # noqa: E402
import tokens_store as T                             # noqa: E402
from d5_stored import entail_one_batch               # noqa: E402
from db import connect                               # noqa: E402

ROOT = Path(__file__).resolve().parents[1]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--outputs", type=int, default=12)
    a = ap.parse_args()
    machine = T.machine_state()
    tok, model, idx = D.load_model("primary")
    with connect() as c:
        units = D.load(c)[: a.outputs]
    per_out = [[(p, h) for _, _, p, h in D.pairs_of(u)] for u in units]
    n_pairs, n_sent = sum(map(len, per_out)), sum(len(u["out"]) for u in units)

    def pass_over(strategy):
        res = []
        for pairs in per_out:
            res.append(D.entail(tok, model, idx, pairs, bs=16) if strategy == "v2" else entail_one_batch(D, tok, model, idx, pairs))
        return res

    def timed(strategy, threads):
        torch.set_num_threads(threads)
        pass_over(strategy)                                           # warm-up, discarded
        ts, scores = [], None
        for _ in range(3):
            t0 = time.perf_counter(); scores = pass_over(strategy); ts.append(time.perf_counter() - t0)
        return statistics.median(ts), scores

    # cold: the very first call of the process, before anything is warm
    torch.set_num_threads(N_DEFAULT_THREADS)
    t0 = time.perf_counter(); D.entail(tok, model, idx, per_out[0], bs=16); cold = time.perf_counter() - t0

    rows, ref = [], None
    for strategy, label in (("v2", "v2 way: input order, chunks of 16"), ("one", "all pairs of an output in one length-sorted batch")):
        for threads in sorted({N_DEFAULT_THREADS, max(1, (os.cpu_count() or 4) - 1)}):
            t, sc = timed(strategy, threads)
            ref = ref or sc
            diff = max(abs(x - y) for r1, r2 in zip(ref, sc) for x, y in zip(r1, r2))
            rows.append((label, threads, t, diff))
    L = ["# D5 timing study (DeBERTa-v3-base NLI, no model swap)", "",
         f"{len(units)} dev outputs, {n_sent} output sentences, {n_pairs} NLI pairs ({n_pairs / n_sent:.2f} per sentence). Warm, median of 3 repeats of a pass over all outputs; "
         f"each output is scored as one call, as the pipeline does. Generation default threads {N_DEFAULT_THREADS}; d5_screen (v2) sets {max(1, (os.cpu_count() or 4) - 1)}.",
         f"Machine: mains {machine['on_ac']}, low-power {machine['low_power_mode']}, other busy: {', '.join(machine['other_busy']) or 'none'}, load {machine['load1']}.", "",
         f"v2 recorded 0.045 s per sentence for this model (`results/dev24/d5_scores_primary.json`). First call of the process (cold, {len(per_out[0])} pairs): {cold:.2f} s.", "",
         "| batching | threads | seconds per output | ms per pair | seconds per sentence | max score difference vs the v2 way |", "|---|---|---|---|---|---|"]
    for label, th, t, diff in rows:
        L.append(f"| {label} | {th} | {t / len(units):.2f} | {1000 * t / n_pairs:.0f} | {t / n_sent:.3f} | {diff:.1e} |")
    best = min(rows, key=lambda r: r[2])
    base = next(r for r in rows if r[0].startswith("v2") and r[1] == N_DEFAULT_THREADS)
    L += ["", f"Fastest: {best[0]} at {best[1]} threads, {best[2] / n_sent:.3f} s per sentence. The v3 driver's setting (v2 way is not used; one sorted batch at {N_DEFAULT_THREADS} threads) "
          f"is {next(r for r in rows if r[0].startswith('all') and r[1] == N_DEFAULT_THREADS)[2] / n_sent:.3f} s per sentence. v2 way at the generation thread count: {base[2] / n_sent:.3f} s per sentence.",
          "Reading: compare the 0.045 s per sentence of v2 with the warm rows above. If the warm figure at the generation thread count is far above 0.045 and the figure at the d5_screen thread "
          "count is close to it, the gap is the thread count (v2 scored with more threads than generation used), not the model or the batching; if all warm rows are close to 0.045, the first v3 "
          "figure was the cold call on a busy machine."]
    out = ROOT / "results/v3"; out.mkdir(parents=True, exist_ok=True)
    (out / "d5_timing_study.md").write_text("\n".join(L) + "\n")
    print("\n".join(L))


if __name__ == "__main__":
    main()
