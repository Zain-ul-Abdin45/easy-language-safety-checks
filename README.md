# Project 3: Safety checks for small local models that write English Easy Language

KI-InnOMATiV plain-language project · Research Project Nov 2026 – Apr 2027 · 900 h

Source of truth: `docs/01_protocol_draft.md`. The idea memo (Oct 2026) is being expanded into the exposé and is superseded where the two differ; the earlier pitch (`Project_3_Pitch.md`) is superseded too.

## Research question
Can a probability filter, combined with a lookup table and grammar checks, make English Easy Language
from a small local model safer, without an unacceptable loss of meaning, simplicity, or speed?

## Design in one line
Qwen 2.5 1.5B simplifies 50–100 onboarding-style texts once per text and seed; five conditions (C1–C5)
post-process that same output; C5 is compared with C1 on harmful errors per 100 words.

| Condition | What happens to changed words |
|---|---|
| C1 Baseline | None |
| C2 Probability | Low-confidence changes reverted to source word |
| C3 Lookup | Changes not on approved list replaced by approved alternative or reverted |
| C4 Lookup + grammar | C3, then grammar rules |
| C5 All three | Probability, then lookup, then grammar |

## Folder layout
| Path | Contents |
|---|---|
| `docs/` | Protocol, data plan, terminology, literature review |
| `config/` | Frozen experiment parameters |
| `data/raw`, `data/dev`, `data/heldout` | Source texts; dev for tuning, held-out never touched before final run |
| `wordlists/` | Approved word lists per target level |
| `src/` | Pilot scripts exist (generation, alignment, checks, report, annotation sheets, AUC decision); full pipeline from December |
| `results/` | Outputs, annotations, metrics |
| `db/schema.sql` | Experiment database schema and result views |

## Timeline and status
| Month | Hours | Main output | Status |
|---|---:|---|---|
| November | 140 | Review draft, terminology, data plan, protocol | In progress |
| December | 60 | Model running locally, first baseline | |
| January | 160 | Checks implemented, go/no-go on probability signal, pilot ready | |
| February | 200 | Pilot across all five conditions | |
| March | 200 | Analysis and March review | |
| April | 140 | Submission and reproducibility package | |

## Open questions for the supervisor (memo §8)
1. Easy-to-Read (Inclusion Europe) vs. plain language (ISO 24495-1)?
2. Human check and German stage in the thesis: acceptable?
3. Negative result acceptable as main finding?

## Setup
| Part | Details |
|---|---|
| Python | `.venv` (Python 3.11, uv), packages in `requirements.txt` |
| Database | PostgreSQL 14, database `easylang_p3`, schema `p3`, built from `db/schema.sql` |
| Settings | `.env` (connection string, model name) |

```
.venv/bin/python src/check_env.py              # verify environment and database
psql -d easylang_p3 -f db/schema.sql           # rebuild schema (DELETES all p3 data)
psql -d easylang_p3 -c "select * from p3.v_c5_vs_c1"
```

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
