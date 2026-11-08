> Planning notes from 31 Oct 2026 (outcome added 1 Nov 2026). Superseded by the exposé and the current protocol; kept for the record.

# Project 3 pivot: plan and outcome

Plan written 31 Oct 2026 · outcome recorded 1 Nov 2026 · Zain ul Abdin

The first version of this file was the pivot plan of 31 Oct 2026. It is kept in the git history (commit `352974a`). This version records what was planned, what was done and what came out.

## 1. Summary

- **The plan.** The word-level checks reached only a small part of the harm, and the probability signal failed its go/no-go. The plan moved the checks to sentences and facts, screened five candidate checks on the existing dev labels (Gate A), and would have built only the checks that beat random flagging.
- **The outcome.** No sentence-level check passed Gate A on Qwen, the deciding model. Sentence probability (D4a) is the most consistent signal (AUC about 0.68 on both models) but misses the pre-set rule. A second model (Llama 3.2 1B) gives the same go/no-go result. An isolated test of sentence-by-sentence generation did not raise reach.
- **What stands.** The word-level design is the base. Its result is a NO-GO with a small, uncertain effect for the lookup condition. The sentence-level work is a second, exploratory line. The held-out set was not touched.
- **What is open.** The supervisor's decision on the framing (section 8), the held-out size and texts, and the exposé blanks.

## 2. Starting point (31 Oct 2026)

All figures are from the 32 dev texts (64 text and seed outputs), one annotator, codebook 0.2.4.

| Item | Value |
|---|---|
| Harmful errors in the unchanged output (C1) | 2.60 per 100 words (90 tags of severity 2 to 3) |
| Changed spans that are reachable by a word-level check | 30% (184 of 607) |
| Harmful errors in reachable spans (frozen definition) | 17 of 90 (19%) |
| Go/no-go, AUC of span probability | 0.569 [0.404, 0.726], NO-GO |
| Continuation after a NO-GO (protocol, 28 Oct) | Continue with C3 and C4 only (lookup and grammar); C3 against C1 is the primary comparison, since C4 has the same text as C3 |
| Where the harm sits | rewrites and insertions 50% (45), omissions 22% (20), no changed span 7% (6), reachable span with a long quote 2% (2), reachable span 19% (17) |

The ceiling follows from this: a perfect word-level filter could remove at most 17/90 × 2.60 ≈ 0.49 harmful errors per 100 words.

## 3. The plan as written

| Step | What was planned |
|---|---|
| 1. Freeze the dev results | Report them as intermediate result I1 (about 40 h, 2 to 13 Nov): setup, go/no-go with sensitivity variants, reach, ceiling, condition effects with the random-revert control, label quality, conclusion. Housekeeping: tag `intermediate-1`, archive, change-log entry, no generation on held-out, send I1 to the supervisor. |
| 2. Screen sentence and fact checks | Six candidates on the 64 labelled C1 outputs, with no new generation: D1 facts, D2 conditions, D3 coverage, D4 sentence probability, D5 entailment, D6 targeted repair (not screened offline). Unit: output sentence; action: flag for review; measure: residual harm at a matched flag rate against random flagging. |
| Gate A | A check goes on if, at a flag rate of at most 30%, its recall of harmful sentences beats random flagging with a lower bound above 0; for D4 and D5 the AUC lower bound must also be above 0.5. If nothing passes, take the negative-result route. |
| 3. Build and held-out | Build only the checks that pass, freeze the protocol (Gate B, January), run held-out once. |
| Outlook | D7 sentence-by-sentence generation, D8 self-check prompting, D9 second model, longer and real texts, German. |

The plan expected D1 to D3 together to aim at 49 of the 90 dev tags (54%), against the 19% word-level ceiling.

## 4. How it went

### Step 1: freeze the dev results

| Planned item | Status |
|---|---|
| Go/no-go and sensitivity variants | Done. NO-GO as labelled; the tag-confirmed variant is INCONCLUSIVE (0.607 [0.445, 0.769]), the tag-derived variant is NO-GO (0.546 [0.405, 0.693]). The plan said the decision holds under all three; it does not (see section 7). |
| Reach, ceiling, condition effects, random-revert control | Done (`results/dev24/controls.md`, `results/comparison_all.md`). |
| Label quality | Done: 14 of 32 harmful spans overlap no severity 2 to 3 tag. This led to codebook 0.2.5, made prospectively and frozen on 31 Oct. |
| Change-log entry | Done: protocol sections 11.1 to 11.18, each dated. |
| Held-out texts untouched | Done: nothing generated, read or annotated. |
| I1 as a separate document | Not written. The results are in `results/summary_for_conclusion.md` and `results/supervisor_summary.md`. |
| Tag `intermediate-1` and archive | Not done. |
| Send I1 to the supervisor | Not sent. The summary for the supervisor is written. |

### Step 2: the sentence-level screen

All rules were written into the protocol before the scores were computed. Three changes happened during execution and are logged: an evaluation bug in D4 (the first run falsely showed D4a passing; corrected and rerun), an extractor fix in D1 (numbered-list markers were counted as facts), and a threshold for D3 (coverage 0.40, fixed before scoring).

Qwen, 270 output sentences (68 harmful). Difference is recall minus random-flag recall in percentage points, with the 95% interval over texts.

| Check | Flag rate | Recall | Difference [95%] | AUC [95%] | Gate A |
|---|---|---|---|---|---|
| D1 facts | 31% | 40% | +4 [−7, +16] | n/a | no |
| D2 conditions | 31% | 32% | +2 [−9, +12] | n/a | no |
| D3 coverage (source sentences, 20 omissions) | 72% | 85% (random 85%) | +0 [−12, +16] | n/a | no, rate above the cap |
| D4a mean log-probability | 30% | 44% | +8 [−2, +17] | 0.677 [0.605, 0.744] | no |
| D4b lowest changed-span probability | 30% | 37% | +2 [−8, +12] | 0.555 [0.462, 0.651] | no |
| D5 DeBERTa-v3 NLI | 30% | 37% | +9 [−0, +18] | 0.546 [0.450, 0.643] | no |
| D5 MiniCheck | 30% | 32% | +6 [−2, +15] | 0.571 [0.493, 0.652] | no |
| D1 then D4a (exploratory) | 31% | 40% | +4 [−7, +16] | n/a | no |

D6 (repair) was not screened, as planned, because no check passed. Digits: 81% of 150 source digit facts are kept; a digit check flags all 3 digit-related number tags, but only 3 of the 13 number tags involve a digit, and it also flags 31% of correct digit sentences.

### Second model

Llama 3.2 1B was run on the same 32 texts with the same rules and labelled in full.

| Item | Qwen | Llama |
|---|---|---|
| C1 harm per 100 words | 2.60 | 2.18 |
| Harmful errors in reachable spans | 17 of 90 (19%); 2 more with a long quote | 8 of 97 (8%); 23 more with a long quote |
| Go/no-go AUC | 0.569, NO-GO | 0.597 [0.448, 0.735], NO-GO |
| C3 against C1 per 100 words | +0.14 [−0.00, +0.33] | −0.09 [−0.25, +0.02] |
| D4a: difference, AUC | +8 [−2, +17], 0.677 | +10 [+1, +20], 0.683 (flag rate 30.25%, cap 30%) |
| D1 | +4 [−7, +16] | +5.4 [+0.4, +10.6] (passes) |
| D3 | +0 [−12, +16] | +47 [+19, +69] at 28% flag rate (passes; 8 of 13 omission tags filled) |

Qwen decides (protocol 11.14, written after the Llama sentence-level scores were seen), so the Llama passes are exploratory. D3 passes for Llama probably because its outputs keep more of the source words, so fewer source sentences fall under the coverage threshold (not tested).

### Isolated experiment S: sentence-by-sentence generation (outlook item D7)

Rule fixed before any output (protocol 11.15), separate schema and config. Each source sentence was rewritten on its own, 64 outputs on the dev texts, label-free comparison with the base C1.

| Measure | Base C1 | S | Rule | Met |
|---|---|---|---|---|
| Reachable share of changed spans | 30.3% | 31.2% | at least 50% | no |
| Output sentences with no source | 28.1% | 27.4% | below base | yes |
| FKGL gain kept | 5.46 | 5.37 (0.98) | at least 0.80 | yes |
| Protected items preserved | 0.553 | 0.659 | not lower | yes |

The rule was not met, so S was not labelled. Two observations outside the rule: S outputs are longer (62.8 against 54.0 words), and fewer source sentences have no aligned output sentence (9.1% against 20.0%).

### Other work added to the plan

- Per-seed check of the go/no-go: 0.581 (seed 1) and 0.553 (seed 2), overlapping intervals; no seed is preferred.
- Codebook 0.2.5 and the importer: span labels are derived from severity 2 to 3 tags (frozen 31 Oct, dry run and rollback test on dev).
- Sentence-level work as a detection question: which automatic signals find harmful sentences.

## 5. Plan against outcome

| Plan | Outcome |
|---|---|
| The harm is at sentence level, so sentence-level checks can reach it. | Partly. The harm is there, but the checks do not find it better than random flagging at 30%. |
| D1 to D3 together aim at 54% of the dev tags. | D1 recall 40%, D2 32%, D3 equal to random on Qwen. The checks are cheap, but they flag too much or too little. |
| D4 may work at sentence level where it failed at word level. | AUC 0.677 and 0.683, better than the word-level 0.569, but the rule is missed (Qwen: lower bound −2; Llama: flag rate 30.25%). |
| D5 catches meaning changes. | AUC 0.546 (Qwen) and 0.597 (Llama); recall by category: 11 of 40 meaning changes on Qwen. |
| Flag for review at a flag rate of up to 30% saves reviewer effort. | At 30%, D4a catches 44% (Qwen) and 49% (Llama) of harmful sentences, against 37% and 40% for random flagging. |
| Repair (D6) follows the checks that pass. | Not built; nothing passed. |
| Sentence-by-sentence generation raises reach (D7). | Reach 31.2% against 30.3%. Not labelled. |
| Gate A in December. | Done on 31 Oct and 1 Nov, ahead of the plan. |
| First five weeks go to the write-up and the screen. | The screen was run on 31 Oct and 1 Nov. The I1 write-up and the exposé update are still open. |

## 6. What the results mean

- Word-level checks cannot do much on whole-text rewrites. The cause is reach, not only a weak signal.
- Sentence-level checks do not beat random flagging on Qwen. Sentence probability is the only consistent signal; it ranks harmful sentences better than chance but misses the rule.
- The base remains the primary comparison (lookup against the unchanged output). Its dev effect is about 5% of C1's harm with an interval that reaches 0, so the held-out run is expected to give a wide interval.
- The second model confirms the structure of the result and does not change the decision.
- The final report can be written on any outcome. The negative result is a result.

## 7. Corrections to the original plan text

| Original statement | Correction |
|---|---|
| Go/no-go AUC 0.569 [0.409, 0.726] | 0.569 [0.404, 0.726] from `src/auc_decision.py` (the other interval came from a different bootstrap stream). |
| The decision holds under all three variants | It does not: tag-confirmed is INCONCLUSIVE, tag-derived is NO-GO. |
| C4 grammar flagged 100% of outputs | 100% was the pilot (8 texts). On the 32 dev texts C4 flagged 89% and C5 94%. |
| Omissions need a source-sentence index in codebook 0.3 | Handled by a backfill sheet instead; no codebook 0.3. Codebook 0.2.5 was frozen on 31 Oct. |
| Primary measure is residual harm at a matched flag rate | The primary comparison stays C3 against C1; the sentence-level checks are exploratory. |
| Reach: 19% overlap a reachable span | 17 of 90 (19%) by the frozen definition; 2 more overlap one with a long quote. The breakdown adds to 90 (17 + 20 + 45 + 6 + 2). |
| The plan's "tag-confirmed" and "tag-derived" values | Taken from `controls.py`, section 4, which uses its own bootstrap: 0.607 and 0.546. |

## 8. Open items

**Decisions (supervisor and Zain)**

1. Framing: keep the base with detection as exploratory, add detection as a second research question, or label the S outputs to test the two side observations (about 134 unique outputs).
2. The five questions from the original plan are unanswered: change of unit, primary measure, the 30% flag-rate bound, form of I1, second rater.
3. Held-out size and source of the texts.

**Work**

- Exposé: update with the Llama D3 row and the outlook line; fill registration number, examiner, dates; check the INLG 2025 and Inclusion Europe details; read the four papers added in related work (SummaC, MiniCheck, Cripwell et al., DeBERTaV3).
- Codebook: minutes per output (section 4.4) and the consistency re-label of 20%.
- Repository: commit the remaining changes; tag `intermediate-1` and archive.

## 9. Literature notes carried over

Read as abstracts only, not full texts: SummaC, MiniCheck, Cripwell et al. 2024 and DeBERTaV3 (checked on 1 Nov 2026 for title, authors and venue). Not yet opened: CLEF SimpleText Task 2 (2025, 2026), CYUT, writerslogic, LettuceDetect, HULAT2, Broto-Ortega et al., Devaraj et al., Vendeville et al., MeaningBERT. These came from search results and need reading before they are cited.

Fixes still open in Evaluation-v2.md: the Wu and Arase entry (field 5 layout), MultiLS-PT (one line or drop), and entries to add for Devaraj et al., SummaC, MiniCheck, LettuceDetect, Cripwell et al., the CLEF tasks, MER-TRANS, and Hayakawa et al. The ICC of 0.62 and the Newsela-Likert title and authors were corrected on 31 Oct.
