# Project 3: where the dev study stands and what needs a decision

Safety checks for small local models that write English Easy Language. Qwen 2.5 1.5B (Llama 3.2 1B as comparison), 32 development texts, 64 outputs per model, one annotator. All results are from the dev set and exploratory. The held-out set has not been generated or read.

## Base design: word-level checks (the original plan)

| | Qwen | Llama |
|---|---|---|
| Harmful errors in the unchanged output, per 100 words | 2.60 | 2.18 |
| Share of harmful errors in spans a word-level check can reach | 19% (17 of 90) | 8% (8 of 97; a further 23 overlap a reachable span with a quote of more than three words) |
| Go/no-go, AUC of span probability (rule: GO if the lower bound is above 0.5) | 0.569 [0.404, 0.726], NO-GO | 0.597 [0.448, 0.735], NO-GO |
| Same, only spans confirmed by an output tag | 0.607 [0.445, 0.769], INCONCLUSIVE | 0.613 [0.443, 0.819], INCONCLUSIVE |
| Fragments among reachable spans | 25 of 184 (14%) | 58 of 213 (27%) |
| Lookup condition (C3) against unchanged output, reduction per 100 words | +0.14 [-0.00, +0.33] | -0.09 [-0.25, +0.02] |
| Probability filter (C2, C5), reduction per 100 words / reverting the same number of spans at random | +0.38 / +0.24 to +0.28 | +0.05, -0.02 / +0.13, +0.22 |

Reading: most harm (50% rewrites and insertions, 22% omissions on Qwen) lies outside word swaps, so no word-level check can remove more than about 0.49 of the 2.60 errors per 100 words. The probability of a changed span does not separate harmful from harmless changes, and the lookup condition lowers harm by about 5%.

## Option 1: detect harmful sentences (no new generation)

Gate A asked whether a sentence-level check flags harmful sentences better than random flagging at a flag rate of at most 30%. Rules were fixed before the scores were computed.

| Check | Qwen: recall minus random [95%], AUC | Llama |
|---|---|---|
| D1 numbers, dates, names | +4 [-7, +16] | +5.4 [+0.4, +10.6] |
| D2 conditions | +2 [-9, +12] | +4.9 [-2.0, +11.9] |
| D3 source coverage (omissions) | +0 [-12, +16]; flags 72% of source sentences | +47 [+19, +69] at 28% flag rate; 8 omission tags (5 could not be filled); passes for Llama only |
| D4a sentence probability | +8 [-2, +17], AUC 0.677 | +10 [+1, +20], AUC 0.683 (flag rate 30.25%, cap 30%; 281 of 319 sentences) |
| D5 entailment (DeBERTa-v3) | +9 [-0, +18], AUC 0.546 | +7 [-1, +16], AUC 0.597 |

No check passed on Qwen, which is the deciding model. Sentence probability (D4a) is the most consistent signal across both models (AUC about 0.68) but misses the pre-set rule; a digit check catches the number errors it can see but flags many correct sentences.

## Option 2: sentence-by-sentence generation (isolated experiment, rule fixed before generation)

The idea was to keep every change inside one sentence so more changes become reachable. The reachable share was 31.2% against 30.3% for whole-text generation (the rule required 50%), so it is not labelled. It preserved more protected items (0.659 against 0.553) and left fewer source sentences uncovered (9.1% against 20.0%), but these were outside the rule and need labelling to mean anything.

## Decision needed

A. Keep the word-level design as the base and primary comparison (lookup against unchanged output), and report the results above as intermediate findings.
B. Add detection (Option 1) as a second research question next to the base, using D4a and D5 on the held-out set.
C. Label the sentence-by-sentence outputs (about 134 unique outputs) to see whether the two side observations turn into fewer harmful errors.
Open questions: the primary measure, the flag-rate bound, who the second rater is, and how large the held-out set should be.
