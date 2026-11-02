"""v3 driver: generate once per text and seed with stored token IDs and log-probabilities, apply C1-C5 to the same output, store sentences and
the two-direction alignment, and compute and store D4a, D4b and D5 per output sentence. Same checks and policies as pilot.py (imported, not
copied); C2 and D4b read the token table.

Run:  .venv/bin/python src/generate_v3.py --schema p3_v3_smoke --split smoke --texts data/smoke/smoke_texts.jsonl --seeds 1 2 [--allow-dirty]
      (create the schema first: src/migrate.py --schema p3_v3_smoke)
Refuses to run on a dirty working tree. --allow-dirty is for smoke and dev runs only (never held-out); the manifest then lists the dirty files
and a hash of the code. The generator is loaded at the revision pinned in config/model_pins.yaml, offline.
Held-out texts load only through heldout_guard and only into the schema p3_heldout. Never writes to the labelled v2 schemas.
Writes results/v3/<schema>_timing.jsonl (one line per output) and results/v3/<schema>_report.md.
"""
from __future__ import annotations

import argparse
import json
import os
import statistics
import time
from pathlib import Path

import numpy as np
import textstat

ROOT = Path(__file__).resolve().parents[1]
V2_SCHEMAS = {"p3", "p3_second", "p3_sbs"}
D4A_MATCH_TOL = 1e-9   # D4a from the table vs D4a from the same tokens in memory: identical floats, so only summation order could differ


def ingest_texts(conn, rows):
    import pilot
    for r in rows:
        old = conn.execute("SELECT body FROM texts WHERE id=%s", (r["id"],)).fetchone()
        if old and old[0] != r["body"]:
            raise SystemExit(f"{r['id']}: text differs from the stored one")
        conn.execute("""INSERT INTO texts(id,source,licence,text_type,is_synthetic,split,body,word_count,fkgl)
                        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT (id) DO NOTHING""",
                     (r["id"], r["source"], r["licence"], r["text_type"], r["is_synthetic"], r["split"], r["body"],
                      pilot.words(r["body"]), textstat.flesch_kincaid_grade(r["body"])))
        conn.execute("DELETE FROM protected_items WHERE text_id=%s", (r["id"],))
        for p in r["protected"]:
            conn.execute("INSERT INTO protected_items(text_id,kind,value) VALUES (%s,%s,%s)", (r["id"], p["kind"], p["value"]))


def run(schema: str, rows: list[dict], seeds: list[int], tok=None, model=None, load_s: float | None = None, quiet: bool = False,
        allow_dirty: bool = False, d5: bool = True, warmup: int = 0, min_measured: int = 0) -> list[dict]:
    os.environ["DB_SCHEMA"] = schema
    import torch
    import pilot
    import tokens_store as T
    from d4_stored import d4_scores
    from db import connect
    from segment_store import store_alignment

    if schema in V2_SCHEMAS:
        raise SystemExit(f"{schema} is a labelled v2 schema; the driver does not write there")
    heldout = any(r["split"] == "heldout" for r in rows)
    if (schema == "p3_heldout") != heldout:
        raise SystemExit("held-out texts go to p3_heldout and nothing else does")
    git = T.git_state()
    if git["dirty"] and (heldout or not allow_dirty):
        raise SystemExit("refusing to run: the working tree has uncommitted changes"
                         + (" (never allowed for held-out)" if heldout else " (--allow-dirty is for smoke/dev runs)")
                         + ": " + ", ".join(git["dirty_files"][:8]) + (" ..." if len(git["dirty_files"]) > 8 else ""))
    if pilot.CFG.get("generation", "whole") != "whole":
        raise SystemExit("token storage supports generation: whole only")
    if len(rows) * len(seeds) - warmup < min_measured:
        raise SystemExit(f"{len(rows) * len(seeds)} outputs minus {warmup} warm-up is fewer than the {min_measured} measured outputs required")
    if tok is None:
        t0 = time.perf_counter(); tok, model = T.load_model_pinned(); load_s = time.perf_counter() - t0
    d5_load_s, D5 = None, None
    if d5:
        import d5_stored
        t0 = time.perf_counter(); D5 = d5_stored.load_d5(); d5_load_s = time.perf_counter() - t0
    threads = torch.get_num_threads()
    timing = []
    with connect() as conn:
        if not conn.execute("SELECT 1 FROM schema_migrations WHERE version LIKE '003%'").fetchone():
            raise SystemExit(f"{schema} is not migrated to 003: run src/migrate.py --schema {schema}")
        ingest_texts(conn, rows)
        conn.commit()
        n = 0
        for seed in seeds:
            manifest = T.run_manifest(tok, model, seed, pilot.INSTRUCTION)
            run_id = conn.execute(
                """INSERT INTO runs(model,backend,quantization,seed,temperature,prompt_version,target_level,hardware,manifest)
                   VALUES (%s,'transformers','none',%s,%s,%s,%s,%s,%s) RETURNING id""",
                (pilot.CFG["model"], seed, pilot.CFG["temperature"], pilot.CFG["prompt_version"], pilot.CFG["target_level"],
                 f"{manifest['threads']} threads, {pilot.CFG['dtype']}", json.dumps(manifest))).fetchone()[0]
            for r in rows:
                n += 1
                machine = T.machine_state()                                   # before the timed generation, outside every timer
                g = T.generate_tokens(tok, model, r["body"], seed)
                cleaned, cut, _ = T.clean_output(g["raw"])
                b_id = conn.execute("""INSERT INTO base_outputs(run_id,text_id,output,gen_seconds,peak_mem_mb,truncated) VALUES (%s,%s,%s,%s,%s,%s)
                                       RETURNING id""", (run_id, r["id"], cleaned, g["gen_s"], pilot.peak_mem_mb(), g["hit_limit"])).fetchone()[0]
                T.store_tokens(conn, b_id, g, cut)
                tok_spans = T.prob_spans(T.load_tokens(conn, b_id))        # C2 and D4b read the stored tokens, not the in-memory ones
                t0 = time.perf_counter(); spans = pilot.align(r["body"], cleaned); align_s = time.perf_counter() - t0
                conds = pilot.run_conditions(spans, cleaned, tok_spans)
                t0 = time.perf_counter(); seg = store_alignment(conn, r["id"], b_id, r["body"], cleaned); seg_s = time.perf_counter() - t0
                for s in spans:
                    s.db_id = conn.execute(
                        """INSERT INTO changed_spans(base_output_id,sentence_idx,source_span,output_span,reachable,probability,on_wordlist)
                           VALUES (%s,%s,%s,%s,%s,%s,%s) RETURNING id""",
                        (b_id, s.sent_idx, s.src, s.out, s.reachable, s.prob, s.on_wordlist)).fetchone()[0]
                    for cond, (action, final) in s.actions.items():
                        conn.execute("INSERT INTO span_actions VALUES (%s,%s,%s,%s)", (s.db_id, cond, action, final))
                post = {}
                for cond, (text, extra_s, flags) in conds.items():
                    if cond in ("C2", "C5"):
                        extra_s += g["score_s"]
                    post[cond] = extra_s
                    src_cond = "C3" if cond == "C4" else cond
                    changed = any(s.actions.get(src_cond, ("keep",))[0] != "keep" for s in spans)
                    prot = [p["value"] for p in r["protected"]]
                    co_id = conn.execute(
                        """INSERT INTO condition_outputs(base_output_id,condition,output,word_count,fkgl,protected_preserved,protected_total,post_seconds,flagged)
                           VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id""",
                        (b_id, cond, text, pilot.words(text), textstat.flesch_kincaid_grade(text), sum(pilot.preserved(text, v) for v in prot),
                         len(prot), extra_s, changed or bool(flags))).fetchone()[0]
                    for rule, (k, ex) in flags.items():
                        conn.execute("INSERT INTO grammar_flags VALUES (%s,%s,%s,%s)", (co_id, rule, k, ex))

                # D4a / D4b from the table (timed), then D5 (timed); the shared teacher-forced pass (g["score_s"]) is timed in generate_tokens
                span_min = {}
                for s in spans:
                    if s.prob is not None:
                        span_min[s.sent_idx] = min(span_min.get(s.sent_idx, 1.0), s.prob)
                t0 = time.perf_counter(); scores = d4_scores(conn, b_id, span_min); d4a_s = time.perf_counter() - t0
                d5_scores, n_pairs, d5_s = {}, 0, 0.0
                if D5:
                    from d5_stored import score_output
                    t0 = time.perf_counter(); d5_scores, n_pairs = score_output(conn, b_id, *D5); d5_s = time.perf_counter() - t0
                for sid, (a, b) in scores.items():
                    conn.execute("INSERT INTO sentence_scores VALUES (%s,'D4a',%s),(%s,'D4b',%s)", (sid, a, sid, b))
                for sid, v in d5_scores.items():
                    conn.execute("INSERT INTO sentence_scores VALUES (%s,'D5',%s)", (sid, v))

                # integrity: round trip from the database, lead-in cut, and D4a from the table vs from the same tokens in memory
                rt = T.check_round_trip(conn, tok, b_id, g)
                mem = [(a - cut, z - cut, lp) for (a, z), lp in zip(g["offsets"], g["logp"]) if z > cut]
                bounds = {sid: (a, z) for sid, a, z in conn.execute("SELECT id, char_start, char_end FROM sentences WHERE base_output_id=%s AND has_words", (b_id,))}
                d4a_diff = max((abs(scores[sid][0] - T.sentence_logprob(mem, *bounds[sid])) for sid in scores), default=0.0)
                conn.commit()
                timing.append(dict(order=n, text=r["id"], seed=seed, tokens=len(g["ids"]), gen_s=g["gen_s"], tok_per_s=len(g["ids"]) / g["gen_s"],
                                   tf_s=g["score_s"], align_s=align_s, store_s=seg_s, d4a_s=d4a_s, d5_s=d5_s, n_pairs=n_pairs, post=post,
                                   hit_limit=g["hit_limit"], warmup=n <= warmup, lead_in_cut=cut, lead_in=g["raw"][:cut] if cut else "", roundtrip=rt,
                                   roundtrip_ok=all(rt.values()), d4a_diff=d4a_diff, machine=machine,
                                   unaligned_out=seg["unaligned_out"], unmatched_src=len(seg["unmatched_src"])))
                if not quiet:
                    print(f"seed {seed} {r['id']}: {len(g['ids'])} tokens, gen {g['gen_s']:.1f}s ({len(g['ids']) / g['gen_s']:.1f} tok/s), "
                          f"checks C5 {post['C5']:.2f}s, D5 {d5_s:.2f}s, round trip {'ok' if all(rt.values()) else 'FAILED ' + str(rt)}"
                          + ("" if machine["on_ac"] else "  [on battery]"), flush=True)
    assert torch.get_num_threads() == threads, "thread count changed during the run"
    out = ROOT / "results/v3"; out.mkdir(parents=True, exist_ok=True)
    (out / f"{schema}_timing.jsonl").write_text("\n".join(json.dumps(t) for t in timing) + "\n")
    (out / f"{schema}_report.md").write_text(report(schema, timing, load_s, d5_load_s, manifest, warmup))
    return timing


def _stats(vals):
    return (statistics.median(vals), max(vals)) if vals else (float("nan"), float("nan"))


def report(schema, timing, load_s, d5_load_s, manifest, warmup: int = 0) -> str:
    """Overhead = seconds a check adds / generation seconds of the same output.
    C2-C5: post_seconds as in v2 (C2 and C5 include the teacher-forced pass). D4a incremental = reading the table and averaging per sentence, valid when the
    teacher-forced pass is already paid (C2 or C5 run); D4a incl. pass = the pass plus D4a. D5 = all NLI pairs of the output, both directions for aligned
    sentences. Full pipeline = alignment + teacher-forced pass + D4a + D5 (the C3 lookup is sub-percent and not added). The extra alignment in
    store_alignment is bookkeeping that duplicates pilot.align, so it is not counted."""
    first = timing[0]
    rest = timing[warmup:] if warmup else timing[1:]   # warm-up outputs are not in the statistics
    meas = rest
    rows = [("C2 probability", lambda t: t["post"]["C2"]), ("C3 lookup", lambda t: t["post"]["C3"]), ("C4 lookup + grammar", lambda t: t["post"]["C4"]),
            ("C5 all three", lambda t: t["post"]["C5"]),
            ("D4a incremental (pass shared with C2/C5)", lambda t: t["d4a_s"]), ("D4a incl. teacher-forced pass", lambda t: t["tf_s"] + t["d4a_s"]),
            ("D5, both directions", lambda t: t["d5_s"]),
            ("Alignment alone", lambda t: t["align_s"]),
            ("**Full pipeline** (alignment + pass + D4a + D5)", lambda t: t["align_s"] + t["tf_s"] + t["d4a_s"] + t["d5_s"])]
    ov = lambda f, t: f(t) / t["gen_s"]
    m = [t["machine"] for t in timing]
    warn = [f"output {t['order']} ({t['text']} s{t['seed']})" for t in timing if not t["machine"]["on_ac"] or t["machine"]["low_power_mode"]
            or (t["machine"]["cpu_speed_limit"] or 100) < 100 or t["machine"]["other_busy"]]   # load average lags our own previous work, so it is shown but not a criterion
    L = [f"# v3 run report: schema {schema}", "",
         f"Outputs: {len(timing)}; texts: {len({t['text'] for t in timing})}; seeds: {sorted({t['seed'] for t in timing})}. Hit the token limit: {sum(t['hit_limit'] for t in timing)}. "
         f"Lead-in removed: {sum(t['lead_in_cut'] > 0 for t in timing)}.",
         f"Generator `{manifest['model']}` at revision `{manifest['model_revision'][:10]}` (weights SHA-256 pinned), torch {manifest['torch']}, transformers {manifest['transformers']}, "
         f"{manifest['threads']} threads, git `{manifest['git_commit'][:10]}`{' DIRTY (' + str(len(manifest['git_dirty_files'])) + ' files), code hash ' + manifest['code_sha256'][:10] if manifest['git_dirty'] else ''}.",
         f"Cold start, paid once per process and not part of per-output overhead: generator load {load_s:.1f}s" + (f", D5 model load {d5_load_s:.1f}s." if d5_load_s is not None else "."), "",
         "## Machine state", "",
         f"On mains for {sum(x['on_ac'] for x in m)}/{len(m)} outputs; low-power mode on for {sum(bool(x['low_power_mode']) for x in m)}; "
         f"load average before generation: median {statistics.median(x['load1'] for x in m):.1f}, max {max(x['load1'] for x in m):.1f} on {m[0]['cpus']} CPUs; "
         f"other processes using at least 10% CPU at the start of an output: {sum(bool(x['other_busy']) for x in m)}/{len(m)}.",
         ("**Timing is not clean for: " + ", ".join(warn) + ".** Treat the figures below as indicative only." if warn else "No output flagged: on mains, no low-power mode, low load, nothing else busy."), "",
         "## Overhead of the checks as a share of generation time", "",
         f"| Check | {'Warm-up output (not in the statistics)' if warmup else 'First output (cold)'} | {'Measured' if warmup else 'Steady'}, median | {'Measured' if warmup else 'Steady'}, max |", "|---|---|---|---|"]
    for name, f in rows:
        med, mx = _stats([ov(f, t) for t in rest])
        L.append(f"| {name} | {ov(f, first):.1%} | " + (f"{med:.1%} | {mx:.1%} |" if rest else "n/a | n/a |"))
    fullf = rows[-1][1]; d5f = rows[6][1]
    verdict_rows = [("D5 alone", d5f), ("Full pipeline", fullf)]
    tps = [t["tok_per_s"] for t in rest]
    if rest:
        L += ["", f"**Measured outputs: {len(meas)}** ({'at least 20 as required' if len(meas) >= 20 else 'FEWER than the 20 required'}), after {warmup or 1} discarded. Against the preliminary 25% bound: " +
              "; ".join(f"{n}: median {statistics.median(ov(f, t) for t in meas):.1%}, max {max(ov(f, t) for t in meas):.1%}, outputs above 25%: {sum(ov(f, t) > 0.25 for t in meas)} of {len(meas)}" for n, f in verdict_rows) + "."]
    L += ["", f"Bound under test: 25% of generation time (preliminary). {'Warm-up' if warmup else 'Cold'} = the first {warmup or 1} output(s) of the process, after the loads above. {'Measured' if warmup else 'Steady'} = outputs {(warmup or 1) + 1} to {len(timing)}. "
          f"Generation speed, steady: median {statistics.median(tps):.1f} tokens/s (range {min(tps):.1f} to {max(tps):.1f})." if rest else "", "",
          "## Overhead against output length", "",
          "| Output length | Outputs | Median gen s | Median full-pipeline s | Median full-pipeline overhead |", "|---|---|---|---|---|"]
    full = rows[-1][1]
    for lo, hi, name in ((0, 50, "up to 50 tokens"), (51, 80, "51 to 80 tokens"), (81, 10 ** 6, "over 80 tokens")):
        ts = [t for t in timing if lo <= t["tokens"] <= hi]
        if ts:
            L.append(f"| {name} | {len(ts)} | {statistics.median(t['gen_s'] for t in ts):.1f} | {statistics.median(full(t) for t in ts):.2f} | {statistics.median(ov(full, t) for t in ts):.1%} |")
    if len(timing) >= 4:
        x = np.array([t["tokens"] for t in timing], float); y = np.array([full(t) for t in timing])
        b, a = np.polyfit(x, y, 1)
        t_tok = statistics.median(1 / v for v in tps) if rest else float("nan")
        L += ["", f"Straight-line fit of full-pipeline seconds on output tokens ({len(timing)} outputs): {a:.2f}s + {1000 * b:.1f} ms per token. With the median steady generation time of "
              f"{1000 * t_tok:.0f} ms per token, the extrapolated overhead is " + ", ".join(f"{(a + b * k) / (k * t_tok):.0%} at {k} tokens" for k in (60, 150, 450)) +
              ". An extrapolation from a handful of short outputs: the fixed cost (D5 and the teacher-forced pass) dominates short outputs, so a long output should look better, not worse."]
    L += ["", "## Per output", "",
          "| # | text | seed | tokens | gen s | tok/s | pass s | D4a s | D5 s (pairs) | align s | full pipeline | mains | load | round trip | D4a table vs memory |",
          "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for t in timing:
        L.append(f"| {t['order']} | {t['text']} | {t['seed']} | {t['tokens']} | {t['gen_s']:.1f} | {t['tok_per_s']:.1f} | {t['tf_s']:.2f} | {t['d4a_s']:.3f} | {t['d5_s']:.2f} ({t['n_pairs']}) | "
                 f"{t['align_s']:.2f} | {ov(full, t):.1%} | {'yes' if t['machine']['on_ac'] else '**no**'} | {t['machine']['load1']} | "
                 f"{'pass' if t['roundtrip_ok'] else '**FAIL**'} | {t['d4a_diff']:.1e} |")
    ok = sum(t["roundtrip_ok"] for t in timing)
    L += ["", "## Integrity", "",
          f"Round trip (from the database: stored IDs decode to the raw text; offsets tile the text; output = raw[clean_cut:]; IDs equal the in-memory IDs; the cut text is one lead-in line and nothing else): **{ok}/{len(timing)} outputs pass all five checks**."
          + ("" if ok == len(timing) else " Failures: " + ", ".join(f"{t['text']} s{t['seed']} {[k for k, v in t['roundtrip'].items() if not v]}" for t in timing if not t["roundtrip_ok"]) + "."),
          f"D4a read from the table vs computed from the same tokens in memory: maximum difference {max(t['d4a_diff'] for t in timing):.1e} over {len(timing)} outputs "
          f"({'all within' if all(t['d4a_diff'] <= D4A_MATCH_TOL for t in timing) else '**NOT all within**'} {D4A_MATCH_TOL:g}).", "",
          "### Lead-in removals", "", "| text | seed | characters cut | removed text | only a lead-in line |", "|---|---|---|---|---|"]
    for t in timing:
        if t["lead_in_cut"]:
            L.append(f"| {t['text']} | {t['seed']} | {t['lead_in_cut']} | `{t['lead_in']!r}` | {'yes' if t['roundtrip']['lead_in_only'] else '**NO**'} |")
    return "\n".join(L) + "\n"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--schema", required=True)
    ap.add_argument("--split", required=True, choices=["dev", "smoke", "heldout"])
    ap.add_argument("--texts", nargs="*")
    ap.add_argument("--seeds", type=int, nargs="+", default=[1, 2])
    ap.add_argument("--limit", type=int)
    ap.add_argument("--allow-dirty", action="store_true", help="smoke and dev runs only; the manifest records the dirty files and a code hash")
    ap.add_argument("--no-d5", action="store_true")
    ap.add_argument("--warmup", type=int, default=0, help="the first N outputs are run and stored but left out of the timing statistics")
    ap.add_argument("--min-measured", type=int, default=0, help="refuse to start unless at least this many outputs are measured after the warm-up")
    a = ap.parse_args()
    from heldout_guard import load_texts
    rows = load_texts(a.split, a.texts)[: a.limit]
    run(a.schema, rows, a.seeds, allow_dirty=a.allow_dirty, d5=not a.no_d5, warmup=a.warmup, min_measured=a.min_measured)


if __name__ == "__main__":
    main()
