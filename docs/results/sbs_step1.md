# Experiment S, step 1: label-free comparison (dev, Qwen, seeds 1 and 2)

64 text and seed units from 32 texts. Base = whole-text C1 (schema p3); S = sentence-by-sentence C1 (schema p3_sbs). Rule fixed in protocol 11.15 before any S output existed. Intervals: 95% bootstrap over texts of the difference S minus base.

| measure | base C1 | S | difference [95%] | rule | met |
|---|---|---|---|---|---|
| (a) reachable share of changed spans | 30.3% (184 / 607) | 31.2% (236 / 756) | +0.9 points [-5.1, +6.8] | S at least 50% | no |
| (b) output sentences with no aligned source | 28.1% | 27.4% | -0.8 points [-9.9, +8.0] | S below base | yes |
| (c) FKGL gain kept (S / base) | 5.46 grades | 5.37 grades | 0.98 [0.91, 1.06] | at least 0.80 | yes |
| (d) protected items preserved (hand lists) | 0.553 | 0.659 | +0.106 [+0.044, +0.169] | S not lower | yes |
| (e) words per output | 54.0 | 62.8 | | report | |
| (e) outputs cut at the token limit | 0 | 0 | | report | |
| extra: source sentences with no aligned output sentence | 20.0% | 9.1% | -10.9 points [-18.1, -4.8] | report | |

Step 1 rule: **not met, S is not labelled; reported as a negative result**.