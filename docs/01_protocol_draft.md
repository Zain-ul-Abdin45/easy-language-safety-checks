# Experimental protocol (draft, not frozen)

Status: draft for November. Freeze after supervisor answers memo questions 1–3.

## 1. Hypothesis
H1: C5 has fewer harmful errors per 100 words than C1, preserves protected information at least as
well, and keeps most of C1's simplification.
H0 (reported as a valid negative result): C5 does not reduce harm; word-level checks do not carry over
to whole texts with this model and these rules.

## 2. Materials
- 50–100 public or synthetic onboarding-style texts (see `02_data_plan.md`).
- Split into dev (tuning thresholds, word lists, rules) and held-out (final run only).
- Target level, word lists and grammar rules frozen before held-out generation.

## 3. Generation
- Model: Qwen 2.5 1.5B Instruct, run locally.
- One base output per text and seed. All five conditions post-process that same output.
- Prompt: one fixed instruction prompt, written and frozen on dev. Record it verbatim here.
- Decoding: TBD (temperature, max tokens). Record seeds.

## 4. Alignment (memo Fig. 1, step C)
1. Align source and output sentences (e.g. similarity-based alignment).
2. Align words within aligned sentence pairs.
3. A "changed span" is an output word or phrase that replaces a source word or phrase.
4. Unaligned output (split, reordered, inserted content) is logged as "unreachable" and its share reported.

## 5. Conditions
| ID | Policy applied to changed spans |
|---|---|
| C1 | None |
| C2 | Revert span to source if model probability of the substitute is below threshold τ |
| C3 | If substitute not on approved list: replace with listed alternative, else revert |
| C4 | C3, then grammar rules |
| C5 | C2, then C3, then grammar rules |

Open design decisions:
- Probability definition: substitute token probability given context, as in Hayakawa et al. Confirm
  their exact formulation (prompted vs. fine-tuned scoring) before implementing.
- Grammar rule set: short list, e.g. sentence length limit, passive voice flag, unexplained abbreviation.
  Decide whether rules rewrite or only flag.

## 6. Go/no-go check (January)
- Annotate changed spans on dev texts as harmful / not harmful.
- Compute AUC of the probability signal.
- If near chance (define cut-off now, e.g. AUC ≤ 0.55), continue with C3 and C4 only.

## 7. Measures
| Measure | Type | Notes |
|---|---|---|
| Harmful errors per 100 words | Primary | Blind harm tags; reachable vs. unreachable reported separately |
| Preserved names, dates, numbers | Secondary | Automatic match against source |
| Readability | Secondary | e.g. FKGL, word length, sentence length |
| Share of output the checks can reach | Secondary | From alignment |
| Speed, peak memory on CPU-only laptop | Secondary | Per text, per condition |
| Share of flagged outputs | Usability (brief 3b) | |

## 8. Harm taxonomy (adapt from Hayakawa et al.)
- Meaning change
- Omission
- Wrong or changed number, date, name
- Hallucination / unsupported addition
- Altered condition or instruction
- Unclear reference
- Insufficient simplification (not harm, tracked separately)

## 9. Success criteria
Success: C5 < C1 on harm per 100 words, preservation C5 ≥ C1, readability gain of C5 ≥ X% of C1's
gain (define X before held-out run).
Partial success: TBD (e.g. harm reduced but simplification loss above X).
Stability: direction of effect holds across all seeds.

## 10. Annotation
- Annotator(s): TBD. Condition labels hidden. Order randomised.
- Research Project: self-annotation with blind setup plus a second pass on a subset.
- Thesis: three expert raters.
