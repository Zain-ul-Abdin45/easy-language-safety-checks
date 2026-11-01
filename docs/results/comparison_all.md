# All dev-set numbers in one place (Qwen 2.5 1.5B, dev24, C1 outputs, primary labels)

Compiled 2026-10-31 from the report files named in each section. Nothing here is recomputed. Exploratory and in-sample, 32 texts, one annotator, codebook v0.2.4. The rules were fixed before computing (protocol 11.1–11.8); results are logged in 11.9, the decision in 11.10.

## 1. Primary question: do the conditions reduce harm? (`controls.md`)

C1 harm: 2.60 severity 2–3 tags per 100 words (90 tags, 64 outputs). Go/no-go on the pooled AUC: 0.569 → NO-GO, so C3 vs C1 is primary.

| condition | harm reduction per 100 w [95%] | preservation change [95%] | FKGL gain kept [95%] |
|---|---|---|---|
| C2 | +0.38 [+0.11, +0.73] | +0.036 [+0.011, +0.071] | 0.98 [0.96, 1.00] |
| C3 | +0.14 [-0.00, +0.33] | +0.017 [+0.003, +0.033] | 1.00 [0.99, 1.01] |
| C4 | +0.14 [-0.00, +0.33] | +0.017 [+0.003, +0.032] | 1.00 [0.99, 1.01] |
| C5 | +0.38 [+0.11, +0.73] | +0.045 [+0.017, +0.080] | 0.97 [0.95, 0.99] |

Random-revert control (descriptive, not a p-value): actual reduction vs random reverting of the same number of spans. C2 +0.38 vs +0.24 (+0.14, +0.35); C3 +0.14 vs +0.10 (+0.03, +0.17); C5 +0.38 vs +0.28 (+0.17, +0.38).

## 2. Where the harm is (`controls.md`)

| category | tags | per 100 w | reachable | unreachable |
|---|---|---|---|---|
| meaning_change | 41 | 1.19 | 13 | 28 |
| omission | 20 | 0.58 | 0 | 20 |
| altered_condition | 16 | 0.46 | 2 | 14 |
| wrong_number_date_name | 13 | 0.38 | 2 | 11 |

Overlaps an unreachable change 45 (50%); omission 20 (22%); reachable span 17 (19%) + 2 with a long quote; no changed span 6 (7%).

## 3. Sentence-level checks, Gate A (270 output sentences, 68 harmful)

Pass rule: flag rate ≤ 30%, lower bound of (recall − random recall) > 0, and for D4/D5 the AUC lower bound > 0.5. 95% bootstrap over texts.

| check | flagged | recall | random | difference [95%] | AUC [95%] | Gate A | source file |
|---|---|---|---|---|---|---|---|
| D1 facts | 84 / 270 (31%) | 40% | 36% | +4 [-7, +16] | – | no | `screen_d1_d2.md` |
| D2 conditions | 83 / 270 (31%) | 32% | 30% | +2 [-9, +12] | – | no | `screen_d1_d2.md` |
| D3 coverage < 0.40 (source sentences, 20 omission tags) | 159 / 220 (72%) | 85% | 85% | +0 [-12, +16] | – | no (rate above cap) | `screen_d3.md` |
| D4a mean log-probability | 81 / 270 (30%) | 44% | 37% | +8 [-2, +17] | 0.677 [0.605, 0.744] | no | `screen_d4.md` |
| D4b lowest changed-span probability | 81 / 270 | 37% | 35% | +2 [-8, +12] | 0.555 [0.462, 0.651] | no | `screen_d4.md` |
| D5 NLI deberta-v3-base (primary) | 81 / 270 | 37% | 28% | +9 [-0, +18] | 0.546 [0.450, 0.643] | no | `screen_d5.md` |
| D5 MiniCheck (sensitivity) | 81 / 270 | 32% | 26% | +6 [-2, +15] | 0.571 [0.493, 0.652] | no | `screen_d5.md` |
| Combination D1 then D4a (exploratory) | 84 / 270 (31%) | 40% | 36% | +4 [-7, +16] | – | no | `screen_d3.md` |

D4a AUC by group: aligned 0.705 [0.623, 0.775] (194 sentences, 52 harmful); unaligned 0.656 [0.429, 0.830] (76, 16).

## 4. Recall by category (tags caught / tags in a flagged sentence)

| check | meaning_change (40) | altered_condition (16) | wrong_number_date_name (13) |
|---|---|---|---|
| D1 facts | 11 | 6 | 11 |
| D2 conditions | 9 | 8 | 6 |
| D4a | 17 | 10 | 3 |
| D4b | 15 | 4 | 7 |
| D5 deberta (primary) | 11 | 9 | 5 |
| D5 MiniCheck | 12 | 5 | 5 |

## 5. Numbers and digits (`digit_guard.md`)

- Source digit facts 150; 29 (19%) missing from the output, 121 (81%) kept; 24 of 64 outputs lose one; 16 add a digit not in the source.
- Of 13 `wrong_number_date_name` tags, 3 quotes hold a digit; all 3 are in a flagged sentence. Flags: 46 of 270 sentences; 38 of 121 digit sentences without such a tag (31%).
- Number-error tags per 100 words if flagged sentences are fixed: 0.29 (without the guard 0.38).
- Agreement with the hand lists: 49 of 64 outputs agree (24 both flag, 25 both clean); 15 disagree.

## 6. Reading

- No sentence-level check passes Gate A on the dev set. D4a (AUC 0.677) and D5-primary (difference +9 [-0, +18]) each come close on one condition and fail the other.
- D1 is the only check that catches digit/name errors well (11 of 13), but it flags 31% of sentences and adds little for the other categories.
- Omissions (22% of harm) and unreachable rewrites (50%) are outside what a word-swap revert can touch; D3 does not find omissions better than random flagging.
- Carried to held-out (11.10): D4a and D5-primary only, rules unchanged.

## 7. Second model: Llama 3.2 1B on the same 32 texts (`results/llama_dev24/`, protocol 11.13)

| check | flagged | recall | random | difference [95%] | AUC [95%] | Gate A |
|---|---|---|---|---|---|---|
| D1 facts | 48 / 319 (15%) | 24% | 19% | +5.4 [+0.4, +10.6] | – | passes (Llama only, exploratory) |
| D2 conditions | 108 / 319 (34%) | 40% | 35% | +4.9 [-2.0, +11.9] | – | no |
| D3 coverage (source sentences; 8 omission tags) | 62 / 220 (28%) | 75% | 28% | +47 [+19, +69] | – | passes (Llama only, exploratory; 5 of 13 tags unfilled) |
| D4a mean log-probability | 85 / 281 (30.25%) | 49% | 40% | +10 [+1, +20] | 0.683 [0.586, 0.765] | no (cap exceeded by 0.25 points) |
| D4b lowest changed-span probability | 85 / 281 | 28% | 30% | -1 [-7, +5] | 0.489 [0.415, 0.573] | no |
| D5 deberta (primary) | 96 / 319 | 40% | 33% | +7 [-1, +16] | 0.597 [0.517, 0.681] | no |
| D5 MiniCheck | 96 / 319 | 40% | 35% | +5 [-4, +13] | 0.623 [0.548, 0.700] | no |

Llama conditions: C1 harm 2.18 per 100 words; go/no-go AUC 0.597 [0.448, 0.735] (NO-GO); C2 +0.05, C3 -0.09, C4 -0.09, C5 -0.02 against C1; random revert +0.13 / +0.11 / +0.22 for C2 / C3 / C5. D3 for Llama rests on 8 of 13 omission tags (the other 5 could not be filled from the researcher's file, protocol 11.18).

## 8. Isolated experiment S: sentence-by-sentence generation (`results/sbs/step1.md`, protocol 11.15 and 11.16)

| measure | base C1 | S | difference [95%] | rule | met |
|---|---|---|---|---|---|
| reachable share of changed spans | 30.3% (184 / 607) | 31.2% (236 / 756) | +0.9 points [-5.1, +6.8] | at least 50% | no |
| output sentences with no aligned source | 28.1% | 27.4% | -0.8 points [-9.9, +8.0] | below base | yes |
| FKGL gain kept (S / base) | 5.46 | 5.37 | 0.98 [0.91, 1.06] | at least 0.80 | yes |
| protected items preserved | 0.553 | 0.659 | +0.106 [+0.044, +0.169] | not lower | yes |
| words per output | 54.0 | 62.8 | | report | |
| source sentences with no aligned output sentence | 20.0% | 9.1% | -10.9 points [-18.1, -4.8] | report | |

Rule not met, so S is not labelled (negative result for reach). The last two rows are post hoc.
