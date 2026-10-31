# Experimental protocol (draft, not frozen)

Status: draft for November. Supervisor has answered memo questions 1–3. Freeze the reach definition, the
codebook and the go/no-go rule before labelling starts; freeze everything else before the held-out run.

## 1. Hypothesis
H1: C5 has fewer harmful errors per 100 words than C1, preserves protected information at least as
well, and keeps most of C1's simplification (preliminary: at least 80% of its FKGL gain and no clear rise in
human simplicity flags, see sections 7 and 9).
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

### Reach definition (frozen for dev and held-out)
A changed span is **reachable** if, inside a matched sentence pair (sentence-embedding cosine of at least 0.45),
the word-level diff gives a single replacement of at most 3 words on each side. Nothing else is filtered.
Insertions, deletions and longer rewrites are unreachable. The definition is the same for dev and held-out,
and is not changed after labelling starts.

Pilot evidence (8 texts, 2 seeds, 16 outputs, run 2026-10-26): 158 changed spans, 40 reachable (25%),
34 pure insertions. By hand, about 10 of the 40 reachable spans were fragments, meaning pieces of a rewritten
sentence cut by the diff around stray shared words, not word swaps. Three filters were tried and rejected:
unchanged neighbours (removed nothing), sentence overlap (swaps and fragments overlap in value), and
content word plus no punctuation (removed 7, including one real error, and kept 4 fragments).
Handling: the annotator marks fragments (`f`) while labelling (docs/06_codebook.md). Fragments are excluded
from the AUC and their share is reported as a limitation.

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
- Implemented scoring (pilot scripts): geometric-mean token probability under a plain softmax (temperature 1), while
  generation samples at temperature 0.3 with top-p 0.9. State this when reporting the AUC and use the same scoring to set tau.
- Freeze before the first dev run, together with the codebook: prompt (`dev-v1`), config, texts, and the replacement list
  `wordlists/replacements.tsv`. The list may be extended only from the 8 pilot texts, never from outputs of the dev texts.
  Outputs that hit the token limit are marked `truncated` and are excluded from annotation or flagged, because the
  cut-off would be read as an omission. Peak memory is a run-level figure (process maximum), not per output.
- Grammar rule set: short list, e.g. sentence length limit, passive voice flag, unexplained abbreviation.
  Decide whether rules rewrite or only flag.

## 6. Go/no-go check (January)
> Amended 2026-10-31 for held-out and later: span labels are derived from output tags (codebook v0.2.5, section 11 of this protocol). The rules below applied to the dev set as written.
- Annotate changed spans on dev texts as harmful / not harmful. Plan 30-40 dev texts, aiming for at least
  150 labelled spans and at least 40 harmful ones. Report the harmful count next to the AUC.
- Compute AUC of the probability signal with a 95% bootstrap interval that resamples texts (seeds of one
  text are not independent).
- The definition of a reachable span (max_span_tokens, alignment) is fixed once for dev and held-out,
  before labelling. It is not relaxed on dev only.
- Decision rule, fixed before labelling:
  - Go: lower bound of the interval is above 0.5.
  - Inconclusive: point estimate is 0.60 or higher but the lower bound is not above 0.5. Add dev texts once, then decide.
  - No-go: otherwise. Continue with C3 and C4 only (lookup and grammar).
- Spans the annotator marks `discuss` count as the annotator's best guess in the main analysis. Sensitivity:
  re-run with all discuss spans as harmful and once as all harmless, and report the three decisions. If they
  differ, report that.
- Tau for C2 is set on dev only, after a GO, and frozen before held-out generation. Rule (preliminary): the
  largest tau that reverts at most 20% of the harmless dev spans (`tau_max_harmless_reverted`). Report the
  share of harmful spans it reverts. Fragments are excluded. `src/auc_decision.py` prints the value.
- Grammar rule: set the target flagged share before looking at held-out data, and report the rule's
  precision against the harm labels as well as its flag rate.

## 7. Measures
| Measure | Type | Notes |
|---|---|---|
| Harmful errors per 100 words | Primary | Blind harm tags; reachable vs. unreachable reported separately |
| Preserved names, dates, numbers | Secondary | Automatic match against source |
| Readability | Secondary | e.g. FKGL, word length, sentence length |
| Share of output the checks can reach | Secondary | From alignment |
| Speed, peak memory on CPU-only laptop | Secondary | Per text, per condition |
| Share of flagged outputs | Usability (brief 3b) | |

Readability has two guards, and neither claims that the text became easy to read:
1. FKGL guard, narrow job: the checks did not undo the simplification (C5 keeps at least 80% of C1's FKGL
   gain, preliminary). FKGL is not validated against human judgment; the literature in Literature/Evaluation.md
   reports near-zero correlation between FKGL and human simplicity judgments at sentence level. It is used
   only to detect that C5 threw the simplification away, and is always stated "on the FKGL proxy".
2. Human guard, independent of FKGL: the share of outputs the annotator flags for insufficient simplification
   (lexical or structural, docs/06_codebook.md). C5 may have at most 10 percentage points more flagged
   outputs than C1 (preliminary).
Success needs both guards. If they disagree, the result is reported with both and is not called a success on
simplification.

## 8. Harm taxonomy
Defined in docs/06_codebook.md (v0.2), which is the single source for categories, examples and rules.
The design is outcome-based, after Wu & Arase: a few categories, described by their effect on a reader who
acts on the text. Categories, in the codebook's order of seriousness:
- Altered condition or obligation
- Wrong or changed number, date, time, name
- Meaning change
- Omission (defined by consequence)
- Hallucination / unsupported addition
- Unclear reference
- Repetition
- Other (with a note)

Not harm, tracked separately: insufficient simplification, as a lexical / structural flag.
Each tag carries severity 1–3, a quote copied from the output (the smallest wrong piece), and `reachable`. Only severity 2–3 counts as harm; the C5 vs C1 comparison is also reported with all tags as a pre-specified sensitivity check, and agreement is measured on the severity 1 / 2 boundary.
`reachable` is computed, not judged by hand: the quote must be at most 3 words and overlap a reachable changed
span from the aligner, which is the frozen reach definition of section 4. The same split is therefore used in
every analysis. An omission has no quote and is unreachable. If the quote occurs more than once in the output,
the rater gives the occurrence number (`quote#2`), and the importer asks for it. Known limit: if the changed
span's own text appears twice in the output, either occurrence counts as that span.

## 9. Success criteria
Success: C5 < C1 on harm per 100 words, preservation C5 ≥ C1, and both simplification guards met: C5 keeps at
least 80% of C1's FKGL gain (X = 80%, preliminary; the memo says "most of C1's simplification"; stored as
`min_simplification_kept`) and has at most 10 percentage points more simplicity-flagged outputs than C1
(preliminary; `max_simplicity_flag_increase`). Confirm both before the held-out run.
Partial success: harm reduced but preservation below C1 or a simplification guard missed.
Stability: direction of effect holds across all seeds.

### Analysis plan (frozen with the codebook)
- Pairing: a (text, seed) enters the analysis only if both its C1 and its C5 output have been reviewed by the
  primary annotator. The views report harm per 100 words on reviewed outputs only, and show "pending
  annotation" until every C1 and C5 output is reviewed, so partial results cannot be misread.
- Counted labels: the primary annotator's only. Second-person and consistency labels feed the agreement
  analysis and are never counted in harm figures (`rater_role`; the views and scripts filter on it).
- Unit and resampling: texts. C1 and C5 are resampled together (paired), and all seeds of a text stay together.
  5000 resamples, 95% percentile interval. Fewer than 30 texts is reported as unreliable.
- Criterion 1, harm: reduction = C1 minus C5 harm per 100 words. Met if the lower bound of the interval is above 0.
- Criterion 2, preservation: C5 minus C1 is at least 0 (point estimate, interval reported).
- Criterion 3, FKGL guard: C5's mean FKGL gain divided by C1's is at least 0.80 (point estimate, interval
  reported; proxy with a narrow job, see section 7).
- Criterion 4, human simplicity guard: the share of outputs flagged for insufficient simplification is, for C5
  minus C1, at most +10 percentage points (point estimate, interval reported; preliminary,
  `max_simplicity_flag_increase`). This guard does not depend on FKGL.
- Verdict: success = all four met. Partial = criterion 1 met, another missed. Inconclusive = reduction above
  0 in the point estimate but the interval includes 0. Negative = no reduction (reported as a valid result, H0).
- Reachable and unreachable harm are reported separately. Direction per seed is reported as stability.
- Sensitivity: the same analysis without outputs marked `discuss`.
- Implementation: `src/verdict.py` (interval and verdict); the view `v_c5_vs_c1` gives point values only.
  The AUC check is `src/auc_decision.py`.

## 10. Annotation
- Condition labels hidden. Order randomised.
- Roles in the database (`rater_role`): `primary` (counted), `second` and `consistency` (agreement only).
  Only one primary annotator is allowed; the importer refuses a second one so harm cannot be counted twice.
- Research Project:
  - First annotator (primary): the researcher, blind setup.
  - Second person: labels a random subset (about 20% of spans and outputs) blind, after a tutorial. This
    gives the inter-rater agreement and is the human check used to judge success. Who: TBD.
  - Consistency check: the researcher re-labels the same subset at least a week later without seeing the
    first labels. This is intra-rater agreement, not a second rater, and is reported as a consistency check.
- Thesis: three expert raters (German and wider human check, deferred).

## 11. Deviations and amendments (log)
| Date | What | Who and why | Applies to |
|---|---|---|---|
| 2026-10-31 | Codebook v0.2.5: the span label for the AUC is derived from severity 2-3 output tags (harmful if a tag's quote overlaps the span; harmless otherwise; fragments still marked by the annotator; spans overlapped only by a quote of more than 3 words left out; no `discuss` on spans). | Decided by the researcher, after seeing the dev results. On the 32 dev texts, 14 of 32 spans labelled harmful in Unit 1 overlapped no severity 2-3 tag, so the AUC used a broader harm definition than the primary measure. | Held-out and later. Not applied to the dev decision, which stands under v0.2.4 (AUC 0.569, NO-GO). The tag-derived dev AUC (0.546 [0.405, 0.693], NO-GO) is reported as a sensitivity analysis. A third variant that drops the untagged harmful spans (0.607, INCONCLUSIVE) is reported but not used for a decision: it removes data selectively. |

Open before held-out: the importer and sheets for the derived span labels, and a new freeze date for the codebook.

### 11.1 Pivot to sentence- and fact-level checks: proposal and Gate A (written 2026-10-31, before any screen is computed)
Source: `Project 3 pivot plan.md` (2026-10-31). Status: proposal by the researcher; the supervisor has not yet been consulted (questions in the plan).
Reason: on dev, 17 of 90 severity 2-3 tags (19%) lie where word-level checks can act, and the probability AUC is NO-GO (0.569 [0.409, 0.726]). All decisions from here on are made with the dev results known.

Gate A (offline screen on the 64 C1 outputs of the 32 dev texts; no new generation). The rule is fixed here, before the numbers are computed:
- Unit: output sentence. A sentence is harmful if the quote of a severity 2-3 tag lies in it. Omission tags have no quote and enter only after their source sentence is recorded (backfill); until then they are reported separately.
- Harm recall of a check = harmful sentences it flags / all harmful sentences. Flag rate = flagged sentences / all sentences, pooled over outputs.
- Random flagging control: in each output flag the same number of sentences at random. Its expected recall is computed exactly (flags per output / sentences per output, weighted by that output's harmful sentences), so there is no sampling noise from the control.
- A direction goes on if its flag rate is at most 30% of sentences and the lower bound of (recall minus random recall) is above 0, by a 95% bootstrap over texts (5000 resamples, all seeds of a text together). For D4 and D5 the sentence-level AUC lower bound must also be above 0.5.
- Directions are judged one by one, not as a ranking; per-category recall is reported descriptively. With 90 tags on dev the screen asks only whether a check beats random flagging.
- D1 (facts), D2 (conditions) and D3 (coverage) are rule-based and fixed in code before the screen, without tuning on dev. Any change to a rule after the screen is logged with date and reason.
- If no direction passes, the negative-result route is taken: I1 plus the screen, reported as evidence that lightweight post-hoc checks do not carry over to whole-text simplification with this model.

### 11.2 Digit guard (D1-digit): analysis fixed on 2026-10-31, before it was computed
Question: how far can a sentence-level check keep numbers, times and dates secure? D1-digit is D1 (src/sentence_screen.py) restricted to digit facts (numbers, times, dates; names and weekdays are left out). A group of output sentences aligned to one source sentence is flagged if a source digit fact is missing in it, or if it contains a digit fact that occurs nowhere in the source.
Reported on the 64 dev C1 outputs, descriptive, no pass/fail rule beyond Gate A:
- Baseline: share of source digit facts that appear in the output, and share of outputs that lose or alter at least one.
- Agreement with the hand lists: for protected items of kind number or date, whether D1-digit flags an output in which the automatic proxy (`protected_preserved`) misses such an item, and the reverse.
- Recall of `wrong_number_date_name` tags whose quote holds a digit fact, flag rate on sentences with digit facts that carry no such tag, and the number of such tags left unflagged.
- Residual: `wrong_number_date_name` tags per 100 words that remain after flagged sentences are assumed fixed.
This is exploratory: the facts extractor was written before the dev tags were compared with it, but the dev labels are known.

### 11.3 Extractor fix after the first D1 and digit-guard runs (2026-10-31, dev labels known)
The facts extractor counted the markers of numbered lists ("1.", "2.", ...) as number facts, which produced false flags. It now ignores ordered-list markers at the start of a line. Reason: a bug, found by reading which digit facts were reported as added in outputs (D06, D09). No other rule was changed. Gate A for D1 and D2 and the digit guard are reported before and after the fix.

### 11.4 D4 sentence-level probability: screen rule fixed on 2026-10-31, before it was computed
Scores per output sentence of the 64 dev C1 outputs, from one teacher-forced pass of Qwen 2.5 1.5B over the regenerated output (same seeds and prompt, so the text is identical; the run checks this):
- D4a: mean token log-probability of the sentence (low means suspicious).
- D4b: lowest probability among the changed spans inside the sentence (geometric-mean token probability as in the word-level design; a sentence without a changed span gets 1 and is never flagged).
Flag rule: a sentence is flagged if its score is at or below the 30th percentile of all dev sentence scores (so the flag rate is at most about 30%). Gate A: the lower bound of (recall minus random recall) above 0, as in 11.1, and the sentence-level AUC (low score = harmful sentence, 95% bootstrap over texts) with a lower bound above 0.5. D4a and D4b are judged separately. The contrastive score (loss with and without the source in context) is not part of this run. Omission tags are not counted. The threshold is set on the same dev sentences, so the screen is in-sample.

### 11.5 Evaluation bug in the D4 screen (2026-10-31)
Affected run: the first D4 run (started 17:28, finished 17:45; report overwritten, copy kept outside the repository). It computed the random-flag expectation over the unique sentences of a resampled set of texts but recall with their multiplicity, which biased the bootstrap difference upward: D4a showed +8 points [+8, +36] and "passes", with the interval starting at its own point estimate. Fix: the statistics sum per-text quantities with multiplicity. The corrected run (17:56) is the reported one: D4a +8 points [-2, +17], AUC 0.677 [0.605, 0.744], does not pass; D4b +2 points [-8, +12], AUC 0.555 [0.462, 0.651], does not pass. The rule of 11.4 is unchanged. Scores are cached in `results/dev24/d4_scores.json`. The D1/D2 screen (11.1) and the digit guard (11.2) were not affected: their per-text sums already used multiplicity.

### 11.6 D5 entailment check: rule fixed on 2026-10-31, before any D5 score was computed
Models. Primary: `cross-encoder/nli-deberta-v3-base` (Apache-2.0, about 184 M parameters, not gated; labels contradiction, entailment, neutral). Sensitivity: MiniCheck, variant `lytang/MiniCheck-RoBERTa-Large` (MIT, plain sequence classifier, not gated; the Flan-T5-Large variant needs the MiniCheck package and is not used). The CPU time per pair is measured on 5 dev texts first; if MiniCheck exceeds 2 s per pair on this laptop, the sensitivity run is dropped and the reason logged. Both models are fixed here and are not changed after scores are seen.
Score per output sentence (C1 outputs, dev): for an aligned pair (same aligner as before, cosine at least 0.45), the minimum of the entailment probability source sentence -> output sentence (unsupported content) and output sentence -> source sentence (lost content). For an output sentence with no aligned source sentence, the entailment probability whole source -> that sentence (one direction only). For MiniCheck the supported probability is used in the same two directions.
Flag rule: score at or below the 30th percentile of all dev sentence scores. Pass rule, as in 11.4: the lower bound of (recall - random recall) above 0 and the sentence-level AUC lower bound above 0.5, 95% bootstrap over texts, in-sample. Omission tags are not counted. Seconds per sentence are reported.

### 11.7 D3 coverage check: rule fixed on 2026-10-31, before any D3 flag is computed
Unit: source sentence (dev, C1 outputs). A source sentence is flagged if (a) no output sentence is aligned to it (cosine below 0.45 for every output sentence), or (b) its coverage is below 0.40. Coverage = share of the content lemmas of the source sentence (spaCy lemmas, lower-cased, nouns, verbs, adjectives, adverbs, numerals and proper nouns, no stop words) that occur as lemmas in the output sentences aligned to it. The value 0.40 was open when the rule was drafted and was set to 0.40 on 2026-10-31 before any coverage was computed; it may be amended before D3 is scored, with a dated entry here.
Evaluation: recall on the 20 omission tags (severity 2-3) once their source sentence index is backfilled (`results/dev24/omission_backfill.csv`): a tag is caught if its source sentence is flagged. Flag rate = flagged source sentences / all source sentences, capped at 30% as for the other checks. Random control: flag the same number of source sentences per output at random, expected recall exact. Pass: the lower bound of (recall - random recall) above 0, 95% bootstrap over texts. Omission tags whose backfilled index is missing are reported separately.

### 11.8 Exploratory combination and an extra D4a report (fixed 2026-10-31, before computing)
Combination (exploratory, not a gate): all D1 flags, then the sentences with the lowest D4a scores are added until the total flag rate reaches 30%. If D1 alone is already at or above 30% (it was 31% after the extractor fix), nothing is added and the rate stays that of D1. Same pass rule as 11.4 (recall minus random with lower bound above 0, bootstrap over texts; the AUC condition does not apply to a union).
Extra report: the sentence-level AUC of D4a separately for aligned and for unaligned output sentences, with 95% bootstrap intervals over texts.
