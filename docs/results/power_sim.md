# Held-out size: how often the pre-set rules would be met if the held-out texts behaved like the dev texts (protocol 11.19)

Dev texts resampled with replacement to size n; 200 resamples per size, 300 inner bootstrap draws each. The dev effect is in-sample, so these shares are optimistic. H1 uses a 95% interval; D4a and D5 use 97.5% intervals (two checks). The last two columns treat D4a as primary: sentence-level AUC lower bound (95%) above 0.5, and above 0.60 (the INCONCLUSIVE bar of 28 Oct), nothing else; both use the same bootstrap draws as each other.

Reading the table: (1) Resampling the 32 dev texts with replacement understates between-text variation, because a resample can only contain texts, and kinds of text, already seen; real held-out texts add variation these resamples cannot show, so every share is optimistic. (2) Monte Carlo error: each share rests on 200 resamples, so its standard error is sqrt(p(1-p)/200), at most 3.5 points (at 50%); the figure in brackets is the standard error of that cell.

Seed 0. Inputs (SHA-256, first 16): results/dev24/d4_scores.json 1a82aeebd01601cb, results/dev24/d5_scores_primary.json d791a384807e562b

| held-out texts n | H1: C3 against C1, lower bound above 0 | D4a passes the E2 rule | D5 (DeBERTa) passes the E2 rule | D4a as primary: AUC lower bound above 0.5 | D4a as primary: AUC lower bound above 0.60 | D4a as primary: recall minus random lower bound above 0 | D4a as primary: both, AUC bound above 0.5 (partial or better) | D4a as primary: both, AUC bound above 0.60 (success, protocol 11.23) |
|---|---|---|---|---|---|---|---|---|
| 30 | 30% (±3.3) | 22% (±2.9) | 8% (±2.0) | 99% (±0.7) | 48% (±3.5) | 28% (±3.2) | 28% (±3.2) | 21% (±2.9) |
| 60 | 84% (±2.6) | 51% (±3.5) | 18% (±2.7) | 100% (±0.0) | 82% (±2.7) | 60% (±3.5) | 60% (±3.5) | 52% (±3.5) |
| 90 | 99% (±0.7) | 75% (±3.1) | 26% (±3.1) | 100% (±0.0) | 94% (±1.7) | 81% (±2.8) | 81% (±2.8) | 80% (±2.9) |