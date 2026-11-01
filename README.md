# Project 3: Safety checks for small local models that write English Easy Language

KI-InnOMATiV plain-language project · TH OWL Research Project, 900 h, six months from November 2026

Source of truth: `docs/01_protocol_draft.md` (decision log in section 11). The idea memo (Oct 2026) and the earlier pitch are superseded where they differ. The exposé lives next to the repository in `../Expose/` (`expose.tex`, compiled with `tectonic`; the full 11-page version is `expose_full_11pages.tex`).

## Where the project stands (1 Nov 2026)
Dev stage done on 32 dev texts (Qwen 2.5 1.5B Instruct primary, Llama 3.2 1B Instruct second model); held-out texts not yet written.

| Stage | Question | Result on Qwen |
|---|---|---|
| 1 Word-level checks | Does span probability separate harmful from harmless changes? | AUC 0.569 [0.404, 0.726]: NO-GO (INCONCLUSIVE, 0.607, if only tag-confirmed spans count). Only 19% of the harm lies in reachable spans. |
| 2 Sentence-level screen (Gate A) | Does a sentence-level check beat random flagging at a flag rate of at most 30%? | No check passed. D4a (sentence log-probability) and D5 (NLI) go to the held-out run as exploratory. Llama D1 and D3 passed, exploratory because Qwen decides. |
| 3 Held-out run | C3 (lookup) against C1, one run on 60 texts | Waits on the written texts, hashing and freeze. |

Experiment S (sentence-by-sentence generation) did not raise the reachable share (31.2% against the 50% required) and was not labelled. Summaries: `results/supervisor_summary.md`, `results/comparison_all.md`, `results/summary_for_conclusion.md`, `results/power_sim.md`.

## Research question
Can lightweight checks that run locally make English Easy Language from a small model safer, without a loss of meaning or simplicity beyond pre-set guards and without post-processing overhead above a preliminary 25% of generation time?
H1 (primary): C3 has fewer harmful errors per 100 words than C1. Exploratory: E1 (probability filter, C2 and C5) and E2 (D4a and D5 flag harmful sentences, 97.5% intervals).

## Design in one line
Qwen simplifies each onboarding-style text once per seed (1 and 2); five conditions (C1 to C5) post-process that same output; harm is labelled by one annotator under codebook 0.2.5 (`docs/06_codebook.md`, frozen).

| Condition | What happens to changed spans |
|---|---|
| C1 Baseline | None |
| C2 Probability | Low-probability spans reverted to the source words |
| C3 Lookup | Spans not on the approved list replaced by an approved alternative or reverted |
| C4 Lookup + grammar | The C3 text; grammar rules only flag |
| C5 All three | Probability, then lookup, then grammar |

## Folder layout
| Path | Contents |
|---|---|
| `docs/` | Protocol and decision log, data plan, terminology, literature outline, pilot guide, codebook |
| `config/` | Frozen parameters: `pilot.yaml`, `second_model.yaml`, `sbs.yaml` |
| `data/` | Source texts (dev and held-out; held-out untouched until the freeze) |
| `wordlists/` | Approved list (Dale-Chall easy words) and the replacement table |
| `src/` | Pipeline (generation, alignment, checks, report), annotation import and export, AUC decision, Gate A screens (`d3_screen.py`, `d4_screen.py`, `d5_screen.py`, `digit_guard.py`), `power_sim.py`, experiment S |
| `results/` | Summaries at the top; per-run reports in `dev24/`, `llama_dev24/`, `second_model/`, `sbs/`; `*.sql` backups (git-ignored) |
| `db/schema.sql` | Database schema and result views |

## Plan (hours are a planning assumption)
| Phase | Months | Hours |
|---|---|---:|
| 1 Exposé, protocol, codebook freeze | M1 | 80 |
| 2 Dev labelling, go/no-go, sentence-level screen, intermediate report | M1-M2 | 190 |
| 3 Write the 60 held-out texts, baselines, freeze | M2-M3 | 120 |
| 4 Held-out run, annotation, re-label, second-person check | M4 | 110 |
| 5 Analysis, controls, sensitivity runs, verdict | M4-M5 | 130 |
| 6 Report and presentation | M5-M6 | 270 |

## Open decisions (user and supervisor)
1. Framing: base design with detection exploratory, detection as a research question, or label S.
2. Whether D5 stays in the E2 verdict.
3. Who the second rater is.
4. Whether the October hours count towards the 900 h.

## Setup
| Part | Details |
|---|---|
| Python | `.venv` (Python 3.11, uv), packages in `requirements.txt` |
| Database | PostgreSQL 14, database `easylang_p3`; schema `p3` (Qwen), `p3_second` (Llama), `p3_sbs` (experiment S), selected with `DB_SCHEMA` |
| Settings | `.env` (connection string, model name); `ANNOTATE_DIR` and `PILOT_CONFIG` select the results folder and config |

```
.venv/bin/python src/check_env.py              # verify environment and database
psql -d easylang_p3 -f db/schema.sql           # rebuild schema (DELETES all data in that schema; back up first)
```

Note: `v_c5_vs_c1` and `src/verdict.py` implement the original C5-against-C1 verdict. After the NO-GO the primary comparison is C3 against C1 (protocol 11.10); the views have not been changed.

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
