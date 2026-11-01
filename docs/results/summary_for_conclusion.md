# Project 3: results so far and technique (written 2026-10-31, to conclude the dev phase)

Question: can cheap checks on the output of a small local model (word-level probability, word list, grammar flags; later sentence-level checks) reduce harmful errors in English Easy Language onboarding texts without losing the simplification?
All numbers are dev-set, one annotator, codebook v0.2.4, exploratory. Held-out texts were not generated or read.

## 1. Technique

1. **Texts.** 32 dev onboarding-style texts (8 pilot + 24 dev24), about 58 words each. Held-out set: not created yet.
2. **Generation (C1).** Qwen 2.5 1.5B Instruct (second model: Llama 3.2 1B Instruct), CPU float32, temperature 0.3, top-p 0.9, max 450 new tokens, seeds 1 and 2. One shared base output per (text, seed).
3. **Changed spans.** The output is aligned to the source with all-MiniLM-L6-v2 (cosine 0.45). A span is *reachable* if it is a single replacement of at most 3 words; everything else (insertions, rewrites, omissions) is unreachable.
4. **Word-level checks, applied to the same base output:** C2 reverts spans whose model probability is low; C3 reverts spans from a replacement word list; C4 flags grammar rules only; C5 does all of them.
5. **Labels.** One annotator. Output level: tags `category|severity|quote`; only severity 2–3 counts as harm (harm per 100 words). Span level (dev): harmful / not / fragment. Codebook v0.2.5 (frozen 2026-10-31) derives span labels from the tags for held-out.
6. **Go/no-go on the probability signal:** AUC of the span probability against the harmful label, 95% bootstrap over texts (5000). GO if the lower bound is above 0.5; INCONCLUSIVE if the point estimate is at least 0.60; otherwise NO-GO and C3 vs C1 becomes primary.
7. **Controls:** random-revert control (same number of spans reverted at random; descriptive); harm breakdown by category and reach; span-label vs tag consistency check.
8. **Sentence-level screen (Gate A, rules fixed before computing, protocol 11.1–11.8):** units are output sentences, source sentences and facts. Flag rate capped at 30%; the lower bound of (recall − random-flag recall) must be above 0, and for D4/D5 the AUC lower bound above 0.5. Checks: D1 numbers/times/dates/names, D2 modals and conditions, D3 source-sentence coverage, D4a/D4b token probability, D5 NLI entailment (deberta-v3-base; MiniCheck as sensitivity). Digit guard as a separate analysis.

## 2. Results, Qwen 2.5 1.5B (32 dev texts, 64 outputs)

| Question | Result |
|---|---|
| C1 harm | 2.60 severity 2–3 tags per 100 words (90 tags) |
| Go/no-go AUC (probability signal) | 0.569 [0.404, 0.726], 32 harmful spans → **NO-GO** |
| C2 vs C1, harm reduction per 100 w | +0.38 [+0.11, +0.73] (random-revert +0.24, range +0.14 to +0.35) |
| C3 vs C1 (primary) | +0.14 [−0.00, +0.33] (random +0.10, range +0.03 to +0.17) |
| C4 vs C1 | +0.14 [−0.00, +0.33] |
| C5 vs C1 | +0.38 [+0.11, +0.73] (random +0.28, range +0.17 to +0.38) |
| Simplification kept (FKGL gain C/C1) | C2 0.98, C3 1.00, C4 1.00, C5 0.97 |
| Reach | 184 of 607 changed spans reachable (30%); only 19 of 90 harmful tags (21%, 17 plus 2 with a long quote) overlap a reachable span |
| Where the harm sits | unreachable rewrite/insertion 50%, omission 22%, reachable 19%, no changed span 7% |
| Categories | meaning_change 41, omission 20, altered_condition 16, wrong_number 13 |
| AUC by seed | seed 1 0.581 [0.379, 0.761]; seed 2 0.553 [0.380, 0.730]; no seed preferred |
| AUC by text set | pilot 0.808 [0.633, 0.952] (7 harmful); dev24 0.512 [0.324, 0.697] (25 harmful) |

Sentence-level checks (270 sentences, 68 harmful), Gate A:

| Check | Flag rate | Recall | Random | Difference [95%] | AUC [95%] | Gate A |
|---|---|---|---|---|---|---|
| D1 facts | 31% | 40% | 36% | +4 [−7, +16] | – | no |
| D2 conditions | 31% | 32% | 30% | +2 [−9, +12] | – | no |
| D3 coverage (220 source sentences, 20 omissions) | 72% | 85% | 85% | +0 [−12, +16] | – | no |
| D4a mean log-prob | 30% | 44% | 37% | +8 [−2, +17] | 0.677 [0.605, 0.744] | no |
| D4b min changed-span prob | 30% | 37% | 35% | +2 [−8, +12] | 0.555 [0.462, 0.651] | no |
| D5 deberta (primary) | 30% | 37% | 28% | +9 [−0, +18] | 0.546 [0.450, 0.643] | no |
| D5 MiniCheck | 30% | 32% | 26% | +6 [−2, +15] | 0.571 [0.493, 0.652] | no |

Digits: 81% of 150 source digit facts are kept; 24 of 64 outputs lose one; a digit check flagged 3 of 3 digit-related number tags (13 number tags in all, only 3 with a digit) but also 31% of clean digit sentences.

## 3. Results, Llama 3.2 1B Instruct (second model; same 32 texts, same prompt and seeds; labelled 2026-11-01)

Labels: 87 unique outputs (168 tags) and 159 span labels (23 harmful, 90 not harmful, 46 fragments) by the same annotator, codebook v0.2.4 (schema `p3_second`, reports in `results/llama_dev24/`). The 8 pilot texts were labelled earlier.

| Question | Qwen | Llama |
|---|---|---|
| C1 harm per 100 words | 2.60 (90 tags) | 2.18 (97 tags) |
| Go/no-go AUC | 0.569 [0.404, 0.726], NO-GO | 0.597 [0.448, 0.735], NO-GO (28 harmful spans; point estimate just under 0.60) |
| Go/no-go, only tag-confirmed spans | 0.607 [0.445, 0.769], INCONCLUSIVE | 0.613 [0.443, 0.819], INCONCLUSIVE |
| Fragments among reachable spans | 25 of 184 (14%) | 58 of 213 (27%) |
| C2 vs C1 per 100 w | +0.38 [+0.11, +0.73] | +0.05 [+0.00, +0.12] |
| C3 vs C1 per 100 w | +0.14 [-0.00, +0.33] | -0.09 [-0.25, +0.02] |
| C4 vs C1 | +0.14 | -0.09 |
| C5 vs C1 | +0.38 [+0.11, +0.73] | -0.02 [-0.17, +0.11] |
| Random revert (C2 / C3 / C5) | +0.24 / +0.10 / +0.28 | +0.13 / +0.11 / +0.22 |
| Reach (reachable / changed spans) | 184 / 607 (30%) | 213 / see report |
| Harmful tags in a reachable span (frozen definition) | 17 of 90 (19%); 2 more overlap one with a long quote | 8 of 97 (8%); 23 more overlap one with a long quote |
| Where the harm sits | unreachable 50%, omission 22% | unreachable 52%, omission 13% |
| Largest categories | meaning_change 41, omission 20 | meaning_change 45, altered_condition 18, hallucination 14 |
| Digit facts kept | 81% | 92% |

Sentence-level checks, Llama (319 sentences, 82 harmful; D4 281 sentences, 71 harmful, because the regenerated text did not match the stored output for 8 outputs):

| Check | Flag rate | Recall | Random | Difference [95%] | AUC [95%] | Gate A |
|---|---|---|---|---|---|---|
| D1 facts | 15% | 24% | 19% | +5.4 [+0.4, +10.6] | – | passes (Llama only; exploratory, not carried forward) |
| D2 conditions | 34% | 40% | 35% | +4.9 [-2.0, +11.9] | – | no |
| D3 coverage (source sentences) | 28% (62 / 220) | 75% (6 of 8 omissions) | 28% | +47 [+19, +69] | – | passes (Llama only; 8 tags, 5 of 13 unfilled; exploratory) |
| D4a mean log-prob | 30.25% | 49% | 40% | +10 [+1, +20] | 0.683 [0.586, 0.765] | no (flag rate 0.25 points above the cap) |
| D4b lowest span prob | 30% | 28% | 30% | -1 [-7, +5] | 0.489 [0.415, 0.573] | no |
| D5 deberta | 30% | 40% | 33% | +7 [-1, +16] | 0.597 [0.517, 0.681] | no |
| D5 MiniCheck | 30% | 40% | 35% | +5 [-4, +13] | 0.623 [0.548, 0.700] | no |

Reading: both models give NO-GO and the same pattern. C3 does not reduce harm, and C5 does no better than reverting at random. Llama's checks do worse than Qwen's (C3 and C5 at or below zero), and Llama adds more invented content. D4a is the best sentence-level check for both models (AUC 0.68). D1 passing for Llama only, with a lower bound of +0.4, is a borderline, post-hoc result. The pilot-only Llama figures from the first labelling (AUC 0.686 on 5 harmful spans) are superseded.

## 3b. Isolated experiment S: sentence-by-sentence generation (rule fixed in protocol 11.15 before any output; result in 11.16; `results/sbs/step1.md`)

Qwen, same prompt, settings and seeds, but each source sentence rewritten on its own and the rewrites joined; 64 outputs on the 32 dev texts; separate schema `p3_sbs`. Label-free comparison with the base C1:

| Measure | Base C1 | S | Rule | Met |
|---|---|---|---|---|
| Reachable share of changed spans | 30.3% (184 / 607) | 31.2% (236 / 756), +0.9 [-5.1, +6.8] | at least 50% | no |
| Output sentences with no aligned source | 28.1% | 27.4% | below base | yes (wide interval) |
| FKGL gain kept (S / base) | 5.46 grades | 5.37, ratio 0.98 | at least 0.80 | yes |
| Protected items preserved (hand lists) | 0.553 | 0.659, +0.106 [+0.044, +0.169] | not lower | yes |

The rule was not met (reach did not rise), so S is not labelled and is a negative result for the reach hypothesis. Post hoc, outside the rule: S outputs are longer (62.8 against 54.0 words), and fewer source sentences have no aligned output sentence (9.1% against 20.0%, [-18.1, -4.8]); this could mean fewer omissions, which only labelling could show.

## 4. Conclusion for the dev phase

- The probability signal does not separate harmful from harmless word swaps (AUC 0.569, NO-GO); the pilot's higher value did not hold on dev24 (0.512).
- C3 vs C1 reduces harm by +0.14 per 100 words (lower bound 0.00): small, and no better than reverting the same number of spans at random.
- C2/C5 reduce harm by +0.38, but the random-revert control reaches +0.24 to +0.28, so most of the effect comes from reverting many spans, not from choosing them.
- Reach is the ceiling: only about a fifth of the harm lies in spans a word swap can reach; half is rewrites and insertions, a fifth omissions.
- No sentence-level check (D1–D5) passed Gate A. D4a (AUC 0.677) and D5 deberta (+9 [−0, +18]) are the closest, each failing one condition. Only these two are carried to held-out (protocol 11.10).
- Sentence-by-sentence generation did not raise the reach of word-level checks (31.2% against 30.3%, rule: 50%); not labelled.
- Seeds are not a lever: no seed is preferred.
- Second model: Llama gives the same NO-GO (0.597) and the same pattern; its checks do worse than Qwen's. D4a is the best sentence-level check for both.
- Open for later: held-out size and texts, second rater, codebook consistency re-label, supervisor questions.

## 5. Where everything is

`results/comparison_all.md` (all Gate A numbers), `results/supervisor_summary.md`, then in `results/dev24/` (Qwen): `controls.md`, `screen_d1_d2.md`, `screen_d3.md`, `screen_d4.md`, `screen_d5.md`, `digit_guard.md`, `results/sbs/step1.md`; Llama: `results/llama_dev24/` (controls.md, screen_d1_d2.md, screen_d4.md, screen_d5.md, digit_guard.md, auc report), pilot report `results/second_model/pilot_report.md`; protocol log `docs/01_protocol_draft.md` sections 11.1–11.16; codebook `docs/06_codebook.md`; scripts in `src/`.
