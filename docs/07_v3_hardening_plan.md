# v3 hardening experiment (plan, not part of the exposé v2)

Status: proposal, 2 Nov 2026. Nothing here changes the protocol, the codebook, the exposé or any dev result. If the experiment works, its outcome is written into protocol section 11 as new decisions. If it fails, v2 stands as it is.

## 0. Ground rules (how v2 stays untouched)

| Rule | How |
|---|---|
| v2 is pinned | `git tag v2-expose-state` on the current commit (after committing or stashing the three modified files and `src/power_sim.py`). |
| Work happens off main | Branch `exp/v3-hardening`. Merge only after the verdict in section 9. |
| New code is additive | New files under `src/v3/` and `config/v3/`. Existing `src/*.py` are imported, never edited, except for two small, flagged fixes (section 4, items 4 and 5). |
| New data lives elsewhere | Schemas `p3_v3_repro` and `p3_v3_smoke`, plus a read-only copy of `p3` as `p3_dev_frozen`. The existing `p3`, `p3_second`, `p3_sbs` are not written to. |
| Dev outputs are never regenerated | The 32 stored texts are the labelled ground truth. Reproduction recomputes numbers from them. |
| Everything reports to `results/v3/` | Nothing is written into `results/dev24/`, `results/llama_dev24/` and so on. |

## 1. What the repo looks like now (checked)

| Area | State in v2 | Consequence for the plan |
|---|---|---|
| Schemas | Three already exist (`p3`, `p3_second`, `p3_sbs`), selected by `DB_SCHEMA` in `src/db.py`. `p3` holds dev and held-out texts together (`texts.split`). | The separation idea is half done. The remaining risk is `db/schema.sql` starting with `DROP SCHEMA IF EXISTS p3 CASCADE`, and dev and held-out sharing one schema. |
| Generation | `pilot.generate()` produces token IDs; `pilot.token_probs()` computes probabilities in a second forward pass, then rebuilds character offsets by decoding prefixes. Only per-span probabilities are stored. | Token IDs and per-token log-probabilities are not persisted, so D4a and the Llama mismatch cannot be audited later. |
| D4 | `d4_screen.collect()` re-scores text by re-tokenizing. | This is the source of the D4 bug and the 8 Llama mismatches. |
| Alignment | `pilot.align()` matches each output sentence to its best source sentence (threshold 0.45) with spaCy sentences. Source to output (unmatched source sentences) is not stored. | Omissions and D3 recompute it separately. |
| D5 | `d5_screen.py` hard-codes the entailment index (`("cross-encoder/nli-deberta-v3-base", 1)`), truncation at 512, no revision pin. | Read `id2label`; pin revisions; log truncations. |
| Flag rule | `sentence_screen.MAX_FLAG_RATE = 0.30`, percentile based. | Llama's 30.25% comes from ties. Needs a tie rule. |
| Held-out guard | None in code. `pilot.py` refuses changed text only after outputs exist. | Add a frozen-flag guard. |
| Environment | `config/pilot.yaml` has model name, no revision, no versions, no config hash. | Add a run manifest. |
| Power simulation | `src/power_sim.py` exists, untracked. | Commit it (it is already a script) and make it read the frozen numbers. |

## 2. Hypothesis of the experiment

If generation stores token IDs and log-probabilities, sentences and alignment are stored once with offsets, and every check is pinned, then:

- H-A: all dev numbers in the current reports are reproduced exactly (or each difference is explained and logged).
- H-B: the frozen pipeline runs end to end on new throwaway texts, within the 25% overhead bound once timed honestly (cold and steady state).
- H-C: D4a evaluated from stored log-probabilities gives the same AUC as the current D4 on the 24 outputs that matched, and a defined value on the 8 Llama outputs that did not.

Success is a yes/no per hypothesis. There is no new scientific claim; this is an instrumentation and reproducibility experiment.

## 3. Stage order (strict)

| # | Stage | Output | Gate to continue |
|---|---|---|---|
| 0 | Pin v2 (tag, branch, commit stray files) | tag `v2-expose-state` | `git status` clean |
| 1 | Separate databases | `p3_dev_frozen` (read-only), `p3_v3_repro`, `p3_v3_smoke`; a numbered migrations folder `db/migrations/` | `pg_dump` of `p3` before and after has the same checksum |
| 2 | Store tokens and log-probs | New table `output_tokens`; new generator `src/v3/generate.py` | Unit test: decoded stored IDs equal the stored text |
| 3 | Reproduction run | `results/v3/repro_report.md` + diff table | Every reported dev number matches, or a logged cause for each difference |
| 4 | Smoke run on 3 to 5 new texts | `results/v3/smoke_report.md`, timings | End to end without manual steps; overhead measured |
| 5 | Freeze | `config/v3/freeze.yaml` with protocol commit hash; guard enabled | Held-out loader refuses without the flag (test) |

Held-out texts are not written, generated or loaded until stage 5 is committed.

Stage 2 caveat: the 32 dev outputs have no stored token IDs. Re-tokenizing them is what caused the bug. For the dev set, the stage-2 table is filled by teacher-forcing the stored text once (tokenize with offsets, score) and marking those rows `source = 'retokenized'`. Newly generated texts (smoke, later held-out) are marked `source = 'generation'`. Report D4a separately for both and state the difference.

## 4. Work items

### 4.1 Generation (`src/v3/generate.py`)

1. Request `output_scores` and `return_dict_in_generate` so token IDs and log-probs come from the same pass that sampled them. Keep the second forward pass as a cross-check only (log the maximum absolute difference).
2. Store per token: `output_id`, `position`, `token_id`, `char_start`, `char_end` (from the tokenizer's offset mapping on the raw text), `logprob`.
3. Run manifest per run, stored in `runs.manifest` (jsonb): model revision hash, chat template hash, torch, transformers, tokenizers, sentence-transformers and spaCy versions, thread count, seed, prompt text, config hash, git commit.
4. Output cleaning as a logged step: raw text kept, cleaned text kept, a `cleaning_log` of removed lead-in and closing notes, and a `hit_token_limit` flag at 450 tokens. (Current `PREAMBLE` regex in `pilot.py` is the starting point; wrap it, do not edit it.)
5. Two small flagged fixes in existing files, each with its own commit and a regression test: none are applied until stage 3 shows the reproduction still matches without them.

### 4.2 Segmentation and alignment (`src/v3/segment.py`)

1. One splitter (spaCy `en_core_web_sm`, version pinned) used for source, output and tag placement.
2. Tables `sentences(id, text_id|output_id, side, idx, char_start, char_end)` and `alignments(out_sentence_id, src_sentence_id, cosine, direction)`, stored in both directions; many-to-one allowed when the model splits a sentence.
3. Threshold 0.45 and the reach rule stay as they are. Test: the aligned/unaligned counts equal those in the current reports.

### 4.3 Checks

| Check | Change | Test |
|---|---|---|
| D4a | Reads stored log-probs; sentence to tokens by offsets | AUC equals current D4 on matching outputs |
| D5 | `id2label` lookup instead of index 1; revision pinned; truncation length set and each truncation logged | Fails loudly if no label contains "entail" |
| MiniCheck | Revision pinned | Same scores within tolerance |
| 30% rule | Flag exactly k = floor(0.3·n) lowest scores; ties broken by a fixed key (sentence id ascending). Written into the protocol before any held-out computation | Llama flag rate is at most 30.0% |
| Digit check | Normalisation frozen (number words, 09:00 = 9 AM, date formats), extractor version string logged | Regression test for the extractor bug |
| C2 to C5 | τ, word list and replacement table frozen as files with SHA-256; seeds fixed for random revert and random flag | Hashes in the manifest |
| Timing | All checks in the generation process; report cold (model load) and steady state | 25% bound reported both ways |

The tie rule changes Llama's flag set slightly (30.25% to at most 30%). It is reported as a documented v3 difference, not folded into the reproduction match.

### 4.4 Annotation tooling

1. Importer for codebook v0.2.5: span harm computed from tags; annotators mark fragments only.
2. Omission tags require a source-sentence index (codebook v0.3 proposal; importer rejects without). This is a codebook change, so it stays in a draft file until the supervisor agrees. v0.2.5 stays frozen.
3. Roles: `annotator_1`, `annotator_2`, `gold`. Original labels are kept; gold is a new row.
4. Automatic time per output (open and save timestamps).
5. Blinding: export sheets carry no condition or score; identical outputs merged; random order with a stored seed.

### 4.5 Analysis (`src/v3/report.py`, new; `pilot_report.py` untouched)

- Sentence labels derived from tag quotes.
- Precision, false-flag rate, category × check table.
- D4a AUC for aligned and unaligned sentences separately.
- Residual harm per 100 words in unflagged sentences.
- 97.5% intervals for E1 and E2.
- Power simulation: `src/power_sim.py` reads the frozen effect inputs and prints the [x]% for the primary.
- Guards applied only to conditions that change the text (C2 to C5).

### 4.6 Data hygiene

1. Migrations, not rebuilds: `db/migrations/0001_*.sql` and so on; a `schema_version` table. `db/schema.sql` stays for v2 but gets a header warning.
2. Every run row and results file stamped with git commit and config hash.
3. Guard in the loader: held-out texts load only if `freeze.yaml` contains `frozen: true` and a protocol commit that is an ancestor of HEAD.
4. Tests in `tests/`: D4 evaluation bug, digit extractor bug, D5 label lookup, tie rule, held-out guard, and the reproduction test that compares to numbers in `results/*.md`.

### 4.7 Pilot guide update (`docs/05_pilot_guide.md`, only after the verdict)

Apply the replacement table from your list: stored log-probs, frozen τ (exploratory), Dale-Chall list kept for C3, grammar rules flag only, reproduction on 32 plus smoke on 3 to 5 texts, projection 60 held-out × 2 seeds (about 230 outputs to annotate), spans derived from tags.

## 5. Reproduction run: what "matches" means

- Integer counts (units, labelled sentences, harmful sentences, aligned and unaligned): exact.
- Rates and proportions: exact to the printed precision.
- AUC and intervals: exact for point estimates; bootstrap intervals exact with the stored seed.
- Anything that differs gets a row in `results/v3/repro_diff.md` with a cause (known bug, tie rule, retokenization) and is never silently adjusted.

## 6. Smoke run

3 to 5 new throwaway onboarding texts, not dev, not held-out, stored in `data/smoke/` and never labelled. They test the pipeline end to end and give timings. They are deleted from consideration for the held-out set (so they cannot leak into it).

## 7. Risks

| Risk | Mitigation |
|---|---|
| Tooling drift changes tokenization on re-run | Dev rows retokenized once and frozen; manifest records versions |
| Scope creep into the held-out run | Stage 5 gate; guard in code |
| Tie rule or D5 label fix moves numbers | Reported as v3 differences, outside the reproduction match |
| Time | Estimated 40 to 60 h; fits inside Phase 3's 180 h only if it replaces, not adds to, held-out preparation. Confirm with supervisor |
| Codebook v0.3 (omission index) conflicts with frozen 0.2.5 | Draft only; applies to held-out only if approved |

## 8. Decisions needed from you

1. Is it acceptable that the 32 dev rows are retokenized once (marked `retokenized`) since no token IDs were stored?
2. Is the "at most 30%" tie rule acceptable, given it will change Llama's flagged set slightly?
3. Is the v0.3 omission-index requirement for held-out only, or also for relabelling dev?
4. Does this count towards the Phase 3 hours?

## 9. Verdict and what happens next

- All three hypotheses hold: write the changes into protocol section 11 as decisions, merge, and continue to writing the held-out texts.
- Reproduction fails with unexplained differences: stop, keep v2 as it is, and report the discrepancy to the supervisor.
- Smoke run exceeds the 25% bound: the bound is a preliminary figure; record the measured value and discuss, no pipeline change.

## 10. Implementation notes (2 Nov 2026, supersedes file names above)

Done, uncommitted: pins (`config/model_pins.yaml`), D5 label assertion, `src/power_sim.py`, base schema without DROP, `src/migrate.py`, `db/migrations/001_token_storage.sql`, `db/reset_dev_only.sql`, `src/tokens_store.py`, `tests/test_d5_labels.py`, `tests/test_token_roundtrip.py`.

- Files are flat in `src/` like the rest of the repo (`tokens_store.py`, not `src/v3/generate.py`).
- Reset and held-out: `p3_heldout` is created at the freeze with `migrate.py --schema p3_heldout`; `reset_dev_only.sql` refuses it, and refuses any schema with label rows.
- Dev rows get no token table (decision 2 Nov): dev D4 stays on re-tokenized text and the report says so.
- Still to do: a generation driver that writes base outputs, tokens and conditions into a v3 schema; D4a/D4b readers from `output_tokens` (`tokens_store.sentence_logprob`, `prob_spans` are ready); tie rule; held-out guard; two-direction alignment table (migration 002); reproduction test.
