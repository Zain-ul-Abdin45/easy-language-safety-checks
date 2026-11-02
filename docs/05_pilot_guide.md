# How to pilot

The pilot runs the whole pipeline on a small dev sample. It answers three questions before the protocol
is frozen:

1. **Does the pipeline work end to end?** Generation, alignment, C1–C5, metrics, database.
2. **How much can the word-level checks reach?** If most changes are phrase rewrites, C2–C5 can only
   touch a small share of the output. That limits what the study can show.
3. **How large can the full study be?** Generation time, memory and annotation hours, projected from
   the pilot to the full run.

## Sample
`data/dev/pilot_texts.jsonl`: 8 synthetic onboarding texts (safety, schedule, reporting, IT access,
leave, travel, data protection, working hours), 50–80 words each, 49 protected items.
Protected items may list alternatives separated by `|` (e.g. `three|3`).

## Steps
```
.venv/bin/python src/pilot.py --limit 2 --seeds 1   # smoke test, about 1-2 minutes
.venv/bin/python src/pilot.py                       # 8 texts x 2 seeds
.venv/bin/python src/pilot_report.py                # results/pilot_report.md
.venv/bin/python src/annotate.py export             # blind sheets in results/
#   fill results/annotate_outputs.csv (errors) and results/annotate_spans.csv (harmful y/n)
.venv/bin/python src/annotate.py import --annotator <your name>
.venv/bin/python src/pilot_report.py                # now with AUC and C5 vs C1 verdict
```
To create or upgrade a schema: `.venv/bin/python src/migrate.py --schema <name>` (never deletes data). To start a throwaway dev schema again, `db/reset_dev_only.sql` wipes it, but only if `ALLOW_DEV_RESET=<name>` is set and the schema holds no labels; labelled schemas are restored from a `pg_dump`, never reset.

## Pilot implementation choices (to confirm or change before freezing)
| Part | Pilot choice | Why / open point |
|---|---|---|
| Backend | Transformers, CPU, float32 | Needs token probabilities; CPU matches the low-end hardware proxy |
| Decoding | Sampling, temperature 0.3, seeds 1 and 2 | Seeds give run-to-run variation for the stability check |
| Probability signal | Geometric mean probability of the output tokens in a changed span, from the model's own generation | Approximates Hayakawa et al.; check their exact scoring |
| Threshold τ | 0.30 | Placeholder. Tune on dev once spans are labelled |
| Sentence alignment | Most similar source sentence by sentence embedding (all-MiniLM-L6-v2); cosine below 0.45 = no source | Word overlap alone missed paraphrases in the first pilot run |
| Lead-in lines | "Here is the rewritten text:" is removed before the checks | Happened in 4 of 16 outputs |
| Reachable span | Replacement of at most 3 words on each side | Longer rewrites, insertions = unreachable |
| Approved word list | Dale-Chall easy words (about 2,940) plus names and numbers | US school list, not an Easy-to-Read list. Swap once target level is decided |
| Replacements | 32 hand-written pairs in `wordlists/replacements.tsv` | Extend from what dev outputs show |
| Grammar rules | Flag only: sentence > 15 words, passive voice, unexplained abbreviation | Rules do not rewrite text, so C4 text = C3 text |
| Preservation | Case-insensitive match of protected items, number words normalised | Automatic proxy; annotation is the real measure |

## What to look at in the report
- **Share reachable.** Low share means the checks can only act on a small part of the output.
- **Preservation C1 vs C5.** Reverting should not lose protected items.
- **FKGL gain C1 vs C5.** How much simplification the checks undo.
- **Projection table.** Hours of CPU generation and annotation for 100 texts x 3 seeds.
