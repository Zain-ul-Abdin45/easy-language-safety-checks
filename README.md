# Safety checks for small local models that write English Easy Language

Research Project at TH OWL (Master's programme Information Technology), written in the context of KI-InnOMATiV, a project on AI-supported inclusive onboarding in public administration. A small language model rewrites onboarding texts into English Easy Language on a laptop, without sending the text to an external service. This repository holds the code, the data plan, the protocol and the pilot results of a study that tests whether lightweight local checks make that output safer.

## Research questions
Can lightweight checks that run locally make English Easy Language from a small model safer? The scope is English onboarding texts, one fixed prompt and no fine-tuning. Qwen 2.5 1.5B is the main model, and Llama 3.2 1B is the second. The main question has three sub-questions.

1. **Word level.** Can word-level checks find and undo harmful changes to key facts such as dates, times and conditions?
2. **Sentence level.** Can sentence-level checks find harmful sentences that word-level checks miss?
3. **Cost.** What do the checks cost in time and memory on a laptop, and possibly on a server?

An error is harmful if a reader who acts on the output would do something different from a reader who acts on the source.

## Status (8 Nov 2026)
The pilot is done on 32 development texts. The 60 held-out texts are not yet written and have not been read or run.

- **Word level.** Word checks reach about one fifth of the harmful errors (17 of 90), because most harm sits in rewritten or inserted sentences and in omissions. The word-list check lowers harm by about as much as reverting words at random.
- **Sentence level.** No sentence check met the pre-set rule on Qwen. The sentence confidence score is the most consistent signal (AUC about 0.68 on both models). The support check is weaker.
- **Sentence-by-sentence generation** did not raise the share of changes that word checks can reach (31% against 50% required), so it was not pursued.
- **Next.** Write the held-out texts, freeze prompt, word list and codebook, and run the checks once.

Result summaries are in `docs/results/` (start with `pilot_summary.md`). Decisions, with date and reason, are logged in section 11 of `docs/01_protocol_draft.md`, which is the source of truth for the design.

## Names in the exposé and in the code
The exposé uses plain names. The code, the database and the protocol use short codes. This table links them.

| Name in the exposé | Code | What it is |
|---|---|---|
| unchanged output | C1 | The base output of the model, no check |
| probability filter | C2 | Reverts a changed word that the model finds unlikely (threshold `tau`) |
| word-list check | C3 | Keeps a changed word if it is on the easy-word list, else uses the table alternative, else reverts |
| word-list check with grammar flags | C4 | C3, then marks for long sentences, passive voice and unexplained abbreviations (flags only) |
| all-three version | C5 | Probability filter, then word-list check, then grammar flags |
| sentence confidence score | D4a | Mean token probability of an output sentence; the lowest 30% of sentences are flagged |
| support check | D5 | A language-inference model judges whether the matched source sentence supports the output sentence |
| number, condition and coverage screens | D1, D2, D3 | Pilot screens for numbers and dates, conditions, and uncovered source sentences |
| main comparison (question 1) | H1 | Word-list check against unchanged output, harmful errors per 100 words |
| descriptive comparison | E1 | Probability filter and all-three version against unchanged output |
| sentence-level verdict (question 2) | E2 | Does the sentence confidence score find harmful sentences better than random flagging |
| screen of sentence-level checks | Gate A | Pilot rule: a check must beat random flagging at a flag rate of at most 30% |
| go/no-go | | Pilot rule for the probability signal, decided on its AUC |
| sentence-by-sentence generation | Experiment S | Isolated pilot test of generating one sentence at a time |
| decision log entries such as 11.23 | | Numbered entries in section 11 of the protocol |

## Folder layout
| Path | Contents |
|---|---|
| `docs/` | Protocol and decision log, data plan, terminology, literature outline, pilot guide, codebook; `archive/` holds superseded planning notes |
| `config/` | Parameters: `pilot.yaml`, `second_model.yaml`, `sbs.yaml`, `freeze.yaml`, `model_pins.yaml` (`experiment.yaml` is superseded) |
| `data/` | Source texts (dev and held-out; held-out untouched until the freeze) |
| `wordlists/` | Approved list (Dale-Chall easy words) and the replacement table |
| `src/` | Pipeline (generation, alignment, checks, report), annotation import and export, AUC decision, Gate A screens (`d3_screen.py`, `d4_screen.py`, `d5_screen.py`, `digit_guard.py`), `power_sim.py`, experiment S |
| `results/` | Summaries at the top; per-run reports in `dev24/`, `llama_dev24/`, `second_model/`, `sbs/`; `*.sql` backups (git-ignored) |
| `db/` | `schema.sql` (base schema and result views, no DROP), `migrations/` (numbered changes), `reset_dev_only.sql` (guarded wipe of one unlabelled dev schema) |
| `docs/results/` | Committed result summaries (the `results/` folder is git-ignored) |
| `tests/`, `scripts/` | v3 tests (token round trip, prompt-date pin, held-out guard, flag rule, driver) and the unattended runs (`overnight_v3.sh`, `repro_llama_pinned.sh`) |

## AI assistance
An AI assistant (Claude, Anthropic) was used for code and analysis scripts, number checks against files and sources, and feedback on drafts; an LLM assistant helped draft the onboarding texts, which the author checked. The research design, the decisions, the labelling and the conclusions are the author's. The exposé declares this as well.

## How to run
| Part | Details |
|---|---|
| Python | `.venv` (Python 3.11, uv), packages in `requirements.txt` |
| Database | PostgreSQL 14, database `easylang_p3`; schema `p3` (Qwen), `p3_second` (Llama), `p3_sbs` (experiment S), selected with `DB_SCHEMA` |
| Settings | `.env` (connection string, model name); `ANNOTATE_DIR` and `PILOT_CONFIG` select the results folder and config |

```
.venv/bin/python src/check_env.py              # verify environment and database
python src/migrate.py --schema p3                # create or upgrade a schema: base file once, then db/migrations/*.sql; never drops anything
python src/migrate.py --schema p3 --status       # list what is applied
```

Note: `v_c5_vs_c1` and `src/verdict.py` implement the original comparison of the all-three version against the unchanged output. After the pilot the main comparison is the word-list check against the unchanged output (protocol 11.10); the views have not been changed yet.

### Views that answer "how far do we get?"
| View | Question |
|---|---|
| `v_condition_metrics` | Harm per 100 words, preservation, readability gain, speed, memory, share flagged, per condition and seed |
| `v_probability_auc` | AUC point estimate only (fragments excluded) with counts. The interval and the decision come from `src/auc_decision.py`. |
| `v_reach` | Share of changed spans the word-level checks can reach |
| `v_c5_vs_c1` | Point values of each success criterion and a verdict per seed. The interval-based verdict is `src/verdict.py`. |
| `v_stability` | Same verdict on every seed, and whether German goes ahead |
| `v_progress` | Hours spent against the 900 h plan (log hours in `work_log`) |

Scripts that need more than SQL:
- `src/auc_decision.py`: 95% bootstrap interval of the AUC over texts, the GO / INCONCLUSIVE / NO-GO decision (protocol §6), the `discuss` sensitivity run, and tau for C2.
- `src/verdict.py`: paired bootstrap over texts for C5 vs C1 and the verdict (protocol §9).
- Both print in the pilot report. Only `primary` labels are counted; `second` and `consistency` labels (`rater_role`, tables `span_labels`, `harm_annotations`, `output_flags`) are for the agreement analysis.

Thresholds live in `p3.success_criteria`:
- `min_simplification_kept` = 0.80, **preliminary**, a narrow FKGL guard: C5 must keep at least 80% of C1's FKGL gain, i.e. the checks did not undo the simplification. FKGL is a proxy, not validated against human judgment. The memo says "most of C1's simplification"; 80% is one reading of that.
- `max_simplicity_flag_increase` = 0.10, **preliminary**, the second guard, independent of FKGL: C5 may have at most 10 percentage points more outputs flagged for insufficient simplification than C1 (human flag, codebook §3).
- Harm rates in `v_condition_metrics` use reviewed outputs only; `v_c5_vs_c1` shows "pending annotation" until every C1 and C5 output is reviewed.
- `auc_go_lower` = 0.50 and `auc_inconclusive_point` = 0.60: the go / inconclusive / no-go rule, fixed before labelling (protocol §6).

## License
Code: MIT. Texts and documents: CC BY 4.0.
