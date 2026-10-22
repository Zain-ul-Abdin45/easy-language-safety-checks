# Project 3: Safety checks for small local models that write English Easy Language

KI-InnOMATiV plain-language project · Research Project Nov 2026 – Apr 2027 · 900 h

Source of truth: the idea memo (October 2026). The earlier pitch (`Project_3_Pitch.md`) is superseded where it differs.

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
| `src/` | Pipeline code (from December) |
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
| `v_probability_auc` | January go/no-go: AUC of the probability signal on dev |
| `v_reach` | Share of changed spans the word-level checks can reach |
| `v_c5_vs_c1` | Each success criterion met or not, and a verdict per seed |
| `v_stability` | Same verdict on every seed, and whether German goes ahead |
| `v_progress` | Hours spent against the 900 h plan (log hours in `work_log`) |

Thresholds live in `p3.success_criteria`. The 0.70 simplification threshold is a placeholder until decided.
