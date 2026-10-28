"""Pilot report: what the pipeline reaches now, and what a full run would cost.

Run:  .venv/bin/python src/pilot_report.py [--texts 100 --seeds 3]
Writes results/pilot_report.md and prints it.
"""
import argparse
from datetime import datetime
from pathlib import Path

import pandas as pd

import verdict as verdict_mod
from auc_decision import as_markdown, compute, sensitivity
from db import connect

OUT = Path(__file__).resolve().parents[1] / "results/pilot_report.md"


def q(conn, sql):
    cur = conn.execute(sql)
    return pd.DataFrame(cur.fetchall(), columns=[d.name for d in cur.description])


def md(df):
    return df.to_markdown(index=False) if len(df) else "_no data_"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--texts", type=int, default=100, help="planned number of texts for the full run")
    ap.add_argument("--seeds", type=int, default=3, help="planned number of seeds")
    a = ap.parse_args()
    with connect() as conn:
        metrics = q(conn, """SELECT condition, count(*) n, round(avg(co.word_count),1) words,
                 round(avg(t.fkgl - co.fkgl),2) fkgl_gain, round(avg(co.fkgl),2) fkgl,
                 round(sum(protected_preserved)::numeric/sum(protected_total),3) preservation,
                 round(avg(flagged::int),2) share_flagged, round(avg(post_seconds),3) check_seconds
                 FROM condition_outputs co JOIN base_outputs b ON b.id=co.base_output_id JOIN texts t ON t.id=b.text_id
                 GROUP BY condition ORDER BY condition""")
        src = q(conn, "SELECT count(*) texts, round(avg(word_count),1) words, round(avg(fkgl),2) fkgl FROM texts "
                      "WHERE id IN (SELECT text_id FROM base_outputs)")
        reach = q(conn, """SELECT count(*) spans, sum(reachable::int) reachable,
                 round(avg(reachable::int),3) share_reachable,
                 sum((source_span IS NULL AND NOT reachable)::int) pure_insertions,
                 round(percentile_cont(0.1) WITHIN GROUP (ORDER BY probability)::numeric,3) p10_prob,
                 round(percentile_cont(0.5) WITHIN GROUP (ORDER BY probability)::numeric,3) median_prob
                 FROM changed_spans""")
        actions = q(conn, """SELECT condition, action, count(*) n FROM span_actions GROUP BY 1,2 ORDER BY 1,2""")
        actions = actions.pivot(index="condition", columns="action", values="n").fillna(0).astype(int).reset_index() \
            if len(actions) else actions
        flags = q(conn, """SELECT co.condition, g.rule, sum(g.n) hits, count(*) outputs_with_rule
                 FROM grammar_flags g JOIN condition_outputs co ON co.id=g.condition_output_id GROUP BY 1,2 ORDER BY 1,2""")
        speed = q(conn, """SELECT r.seed, count(*) texts, round(avg(b.gen_seconds),1) gen_s_per_text,
                 round(max(b.peak_mem_mb)) peak_mem_mb, max(r.hardware) hardware
                 FROM base_outputs b JOIN runs r ON r.id=b.run_id GROUP BY r.seed ORDER BY r.seed""")
        ann = q(conn, """SELECT (SELECT count(*) FROM output_reviews WHERE rater_role='primary') annotated_outputs,
                 (SELECT count(*) FROM harm_annotations WHERE rater_role='primary') harm_tags""")
        uniq = conn.execute("SELECT count(DISTINCT (base_output_id, md5(output))) FROM condition_outputs").fetchone()[0]
        total_co = conn.execute("SELECT count(*) FROM condition_outputs").fetchone()[0]
        verdict = q(conn, "SELECT * FROM v_c5_vs_c1")
        auc = q(conn, "SELECT * FROM v_probability_auc")
        auc_dec = compute(conn)
        v_main, v_sens = verdict_mod.compute(conn, split="dev")
        auc_sens = sensitivity(conn) if auc_dec["n_spans"] else None
        runs = q(conn, "SELECT min(created_at) first_generation, max(created_at) last_generation, count(*) runs FROM runs")
        example = q(conn, """SELECT b.text_id, r.seed, cs.source_span, cs.output_span, round(cs.probability,3) prob,
                 max(CASE WHEN sa.condition='C2' THEN sa.action END) c2, max(CASE WHEN sa.condition='C3' THEN sa.action END) c3,
                 max(CASE WHEN sa.condition='C3' THEN sa.final_span END) c3_final
                 FROM changed_spans cs JOIN base_outputs b ON b.id=cs.base_output_id JOIN runs r ON r.id=b.run_id
                 JOIN span_actions sa ON sa.span_id=cs.id WHERE cs.reachable
                 GROUP BY cs.id, 1,2,3,4,5 ORDER BY 5 LIMIT 12""")

    gen_s = speed["gen_s_per_text"].astype(float).mean() if len(speed) else float("nan")
    words_per_text = float(src["words"].iloc[0]) if len(src) else float("nan")
    full_outputs = a.texts * a.seeds
    proj = pd.DataFrame([
        ("Base generations", full_outputs),
        ("Generation time, hours (CPU-only)", round(full_outputs * gen_s / 3600, 1)),
        ("Condition outputs stored", full_outputs * 5),
        ("Unique outputs to annotate (pilot ratio)", round(full_outputs * 5 * uniq / max(total_co, 1))),
        ("Annotation hours at 3 min per output", round(full_outputs * 5 * uniq / max(total_co, 1) * 3 / 60, 1)),
        ("Spans to label for AUC (pilot ratio, dev 20%)",
         round(int(reach["reachable"].iloc[0] or 0) / max(int(speed["texts"].sum()) if len(speed) else 1, 1)
               * a.texts * 0.2 * a.seeds)),
    ], columns=["Full run estimate", f"{a.texts} texts x {a.seeds} seeds"])

    stamp = datetime.now().astimezone()
    report = f"""# Pilot report
Report generated: {stamp:%Y-%m-%d %H:%M:%S %Z}

## Generation runs in the database
{md(runs)}

## Sample
{md(src)}

## Generation speed and memory (per seed)
{md(speed)}

## Conditions (all pilot outputs)
FKGL gain = source grade level minus output grade level (higher = simpler).
{md(metrics)}

## Reach of the word-level checks
Reachable = single replacements of up to 3 words. Pure insertions = output sentences or phrases with no source.
{md(reach)}

## What the checks did to reachable spans
{md(actions)}

## Grammar rule flags
{md(flags)}

## Lowest-probability spans (what C2 reverts first)
{md(example)}

## Harm annotation
{md(ann)}

Unique outputs needing annotation: {uniq} of {total_co} condition outputs.

## January go/no-go (needs span labels)
{md(auc)}

{as_markdown(auc_dec, auc_sens)}

## C5 vs C1 (needs harm annotation)
{md(verdict)}

Paired bootstrap over texts (dev, pilot):

{verdict_mod.as_markdown(v_main, v_sens)}

## How far can the full study go?
{md(proj)}
"""
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(report)
    OUT.with_name(f"pilot_report_{stamp:%Y%m%d_%H%M%S}.md").write_text(report)   # keep every run
    print(report)


if __name__ == "__main__":
    main()
