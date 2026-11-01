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

### 11.9 Results of D5, D3 and the 11.8 reports (2026-10-31, dev labels, rules unchanged)
Run after the rules in 11.6, 11.7 and 11.8 were committed (`03b7a5d`). No threshold or rule was changed after the scores were seen. Scripts `src/d5_screen.py`, `src/d3_screen.py`; reports `results/dev24/screen_d5.md`, `screen_d3.md`.
- D5, cross-encoder/nli-deberta-v3-base (primary): 81 of 270 sentences flagged; recall 37%, random 28%, difference +9 points [-0, +18]; AUC 0.546 [0.450, 0.643]. Does not pass.
- D5, MiniCheck-RoBERTa-Large (sensitivity): recall 32%, random 26%, difference +6 [-2, +15]; AUC 0.571 [0.493, 0.652]. Does not pass.
- D3 (coverage below 0.40): 159 of 220 source sentences flagged (72%, above the 30% cap); recall on the 20 omission tags 85% (17 of 20), random 85%, difference +0 [-12, +16]. Does not pass. The source sentence indices were suggested by Claude from the outputs and confirmed by the researcher (`omission_backfill_confirmed.csv`; rows 13, 15 and 16 were changed by the researcher).
- Combination (exploratory): D1 alone is 31%, so nothing was added; difference +4 [-7, +16].
- D4a AUC for aligned sentences 0.705 [0.623, 0.775] (194 sentences, 52 harmful), for unaligned 0.656 [0.429, 0.830] (76, 16).
- Status: no sentence-level check (D1, D2, D3, D4a, D4b, D5) passes Gate A on the dev set. The next step is a decision by the researcher.

### 11.10 Decision after Gate A: close the dev screening, fix what goes to held-out (2026-10-31, decided by the researcher)
1. The sentence-level screening on the dev set is closed. No new check, variant, threshold or flag rule is tried on the dev labels. The results in 11.9 stand as they are.
2. The primary comparison stays C3 vs C1 (the go/no-go rule gave NO-GO for the pooled AUC, 0.569).
3. Only two sentence-level checks are carried to the held-out set, with the rules exactly as written in 11.4 and 11.6: D4a (mean log-probability, flag at the 30th percentile) and D5 with cross-encoder/nli-deberta-v3-base. They are reported as a secondary, confirmatory analysis with the same pass rule (recall minus random recall with a lower bound above 0, AUC lower bound above 0.5, 95% bootstrap over texts). D5 with MiniCheck is reported as a sensitivity run only.
4. D1, D2, D3 and D4b are not carried forward. They stay in the thesis as dev-set results that did not pass.
5. Nothing in 3 is tuned on the held-out texts. The held-out texts are not generated, read or annotated before Gate B. A change to this list needs a dated entry here before the held-out scores are computed.

### 11.11 Codebook freeze and importer for derived span labels (2026-10-31, decided by the researcher)
- Codebook v0.2.5 is frozen on 2026-10-31 (`docs/06_codebook.md`). No rule text changed in the freeze. The held-out texts are labelled under it.
- `src/annotate.py`: `export` writes by default a spans sheet with the column `fragment` only (`--span-rule v0.2.4` gives the old y/n/f sheet); `import` accepts both sheets. For the v0.2.5 sheet it stores the fragment marks and then derives the span label from the severity 2-3 tags of the C1 output (`derive_span_labels`): harmful if the quote of at least one tag of at most 3 words overlaps the span, harmless if no tag overlaps it, excluded (harmful NULL) if only a quote of more than 3 words overlaps it, NULL for fragments. Derived labels are stored in `span_labels` under the annotator name `derived-v0.2.5`.
- Check on the dev data, nothing written: a dry run (`annotate.py derive`) gives 17 harmful, 138 harmless and 29 excluded or fragment of 184 spans; the full import path was run inside a transaction and rolled back (17 harmful, 162 harmless when only one fragment mark is set), and the database was unchanged afterwards (32 spans harmful_gold, 25 fragments).
- Still open and not rule changes: minutes per output (section 4, item 4), the second rater, the three open points, and the consistency re-label.

### 11.12 Per-seed check of the go/no-go AUC (2026-10-31, dev labels, descriptive)
Run to see whether one seed behaves differently. Span AUC (probability signal, 95% bootstrap over texts): pooled 0.569 [0.404, 0.726] (159 spans, 32 harmful); seed 1 0.581 [0.379, 0.761] (78 spans, 13 harmful); seed 2 0.553 [0.380, 0.730] (81 spans, 19 harmful); pilot texts 0.808 [0.633, 0.952] (33 spans, 7 harmful); dev24 texts 0.512 [0.324, 0.697] (126 spans, 25 harmful). D4a sentence-level AUC: seed 1 0.709 [0.626, 0.787], seed 2 0.638 [0.542, 0.735]. The intervals overlap and none of the seed-specific intervals excludes 0.5. No seed is preferred; both stay pooled (a text's seeds are resampled together). The high pilot value rests on 7 harmful spans and is not carried over to the dev24 texts. Choosing a seed after seeing these numbers is not done.

### 11.13 Llama 3.2 1B on the 32 dev texts: labels imported and the same analyses run (2026-11-01 data, decided by the researcher; dev results for Qwen known)
- Labels: 87 unique outputs (168 tags, severity 3: 55, 2: 75, 1: 38; 10 `none`) and 159 span labels (23 harmful, 90 not harmful, 46 fragments, 4 discuss) by the primary annotator, in `p3_second`, under codebook v0.2.4 (span labels typed by hand, as for Qwen). The output sheet was repaired mechanically (cells with commas had lost their quoting) and 13 rows were corrected by the researcher before import. Backup before import: `results/p3_second_backup_before_llama_dev24_import.sql`. Reports in `results/llama_dev24/`.
- Rules and thresholds are those used for Qwen; nothing was changed after seeing the Llama numbers.
- Go/no-go AUC 0.597 [0.448, 0.735] (28 harmful, 127 harmless spans): NO-GO (the point estimate is just under 0.60); the decision is the same with discuss spans counted as harmful (0.563) or harmless (0.522).
- C1 harm 2.18 per 100 words (97 tags). C2 +0.05, C3 -0.09 [-0.25, +0.02], C4 -0.09, C5 -0.02 per 100 words against C1; random reverting of the same number of spans gives +0.13, +0.11 and +0.22 for C2, C3 and C5. 52% of the tags overlap an unreachable change, 13% are omissions.
- Sentence-level checks (319 sentences, 82 harmful; D4 281 sentences because the regenerated text did not match the stored output for 8 outputs): D1 +5.4 [+0.4, +10.6] at 15% flag rate (passes the Gate A rule for Llama only; exploratory, not carried forward); D2 +4.9 [-2.0, +11.9] at 34%, does not pass; D4a +10 [+1, +20], AUC 0.683 [0.586, 0.765], flag rate 30.25% (above the 30% cap by rounding), does not pass; D4b -1 [-7, +5], AUC 0.489; D5 deberta +7 [-1, +16], AUC 0.597 [0.517, 0.681]; D5 MiniCheck +5 [-4, +13], AUC 0.623 [0.548, 0.700]. None of D4a, D4b, D5 passes.
- Decision 11.10 is unchanged: the Qwen result stands and only D4a and D5-primary go to held-out. The Llama results are a second-model comparison, reported with the Qwen results.

### 11.14 Gate A wording, deciding model and source numbers (2026-11-01, dev results of both models known)
- Recall unit: per sentence. Harm recall = harmful sentences flagged / harmful sentences, where a sentence is harmful if the quote of a severity 2-3 tag lies in it (11.1). The per-category tables count tags (a sentence with two tags counts twice) and are descriptive. Omission tags have no quote and are outside the sentence recall (D3 has its own source-sentence unit, 11.7). The flag rate is flagged sentences / all sentences pooled over outputs.
- Llama D4a: 85 of 281 sentences flagged = 30.25%, 0.25 points above the 30% cap (Qwen D4a: 81 of 270 = 30.0%). The cut is the 30th percentile of the model's own sentence scores and the sentence count is not a multiple that gives exactly 30%. The rule was not changed.
- Which model decides: Qwen 2.5 1.5B, the primary model of the design. The decision on Gate A, on the go/no-go and on what goes to held-out (11.10) rests on Qwen only. Llama is a second-model comparison; its results (11.13) are reported next to Qwen's and cannot pass or fail a direction on their own. D1's pass for Llama only (+5.4 [+0.4, +10.6]) is therefore exploratory.
- Source numbers, fixed here, and used in the exposé and the report:
  - Reach: 17 of 90 severity 2-3 tags (19%) are reachable under the frozen definition (quote of at most 3 words that overlaps a reachable span); count taken from the database (`harm_annotations.reachable`, C1, primary, severity 2-3, dev). The figure 19 of 90 in the random-revert table of `controls.md` counts every tag that overlaps a reachable span, including quotes longer than 3 words, and is used only inside that control.
  - Go/no-go AUC: 0.569 [0.404, 0.726], from `src/auc_decision.py` (seed 0, 5000 resamples; run 2026-11-01), as in the dev report. The value [0.409, 0.726] in 11.1 and in section 4 of `controls.md` comes from a different bootstrap stream in `controls.py` and is replaced by [0.404, 0.726] everywhere. Section 4 of `controls.md` keeps its own sensitivity values (tag-confirmed 0.607, tag-derived 0.546) because they are all computed in that script.

### 11.15 Isolated experiment S: sentence-by-sentence generation (rule fixed 2026-11-01, before any S output exists; dev results of both models known)
Purpose. The word-level design is the base and stays unchanged. S tests whether a different way of generating lowers the harm and raises the reach of word-level checks, so that the supervisor can compare the base with this option. It is isolated: own config (`config/sbs.yaml`, prompt version `dev-sbs-v1`), own schema (`p3_sbs`), own results folder (`results/sbs`); nothing from it enters the base results, the exposé figures or the held-out set. It uses the 32 dev texts only. It does not reuse any existing label to tune anything; the existing Qwen labels are used only as the comparison for C1 after S is labelled. It is an amendment to 11.10 item 1 (no new check tried on dev): it adds a new generation variant, written down here first.
Design. Qwen 2.5 1.5B Instruct, same instruction, sampling settings (temperature 0.3, top-p 0.9, 450 tokens per sentence) and seeds 1 and 2 as the base. Each source sentence (spaCy segmentation) is rewritten on its own with the instruction applied to that sentence; the rewrites are joined with a space and form the S base output. All five conditions (C1 to C5 on top of S) run on it as in the base.
Step 1, label-free (computed automatically, no annotation). On the 64 S outputs against the 64 base C1 outputs of the same texts and seeds: (a) reachable share of changed spans (base: 184 of 607 = 30.3%); (b) share of output sentences with no aligned source sentence (base: 76 of 270 = 28.1%); (c) FKGL gain kept (S / base C1); (d) protected-item preservation (hand lists, C1 S vs base C1); (e) words per output and truncated outputs. Bootstrap intervals over texts are reported.
Step 1 rule, fixed now: S goes to labelling only if (a) is at least 50%, (b) is below the base value, (c) is at least 0.80 and (d) is not lower than the base. If it fails, S is reported as a negative result with these numbers and nothing is labelled.
Step 2, only after a pass. The researcher labels the S outputs with the frozen codebook v0.2.5 (output tags; span labels derived). Primary measure: harmful errors per 100 words, S's C1 against the base C1 (paired bootstrap over texts, seeds together). S counts as an improvement if the lower bound of the reduction is above 0 and the same three guards as in 6.1 hold. Secondary, descriptive: the reachable share of harm (tags in reachable spans), C3 against S's C1, and the random-revert control on S.
Reporting. The base results and S are reported side by side; whether S replaces the base is the supervisor's decision. No threshold or rule above is changed after S outputs exist.

### 11.16 Experiment S, step 1 result (2026-11-01, label-free, rule of 11.15 unchanged)
Generation: 64 S outputs (32 dev texts, seeds 1 and 2), no output cut at the token limit, lead-in lines stripped from 15 (seed 1) and 11 (seed 2) outputs. Report: `results/sbs/step1.md`, script `src/sbs_step1.py`, data in schema `p3_sbs`.
- (a) reachable share of changed spans: S 31.2% (236 of 756) against base 30.3% (184 of 607), +0.9 points [-5.1, +6.8]. The rule required at least 50%: not met.
- (b) output sentences with no aligned source: 27.4% against 28.1% (-0.8 points [-9.9, +8.0]): met, but the interval is wide.
- (c) FKGL gain kept 0.98 [0.91, 1.06]: met. (d) protected items preserved (hand lists) 0.659 against 0.553 (+0.106 [+0.044, +0.169]): met.
- Not in the rule, reported: words per output 62.8 against 54.0; source sentences with no aligned output sentence 9.1% against 20.0% (-10.9 points [-18.1, -4.8]).
- Step 1 rule not met (reach did not rise), so S is not labelled and is reported as a negative result for the reach hypothesis. The two secondary observations (more protected items preserved, fewer uncovered source sentences) are post hoc and were not part of the rule; they suggest S may lose less content, which only labelling could show. Labelling S anyway would be a change of the rule after the result and needs its own dated entry with the researcher's reason; it is not done here.

### 11.17 Llama D4 coverage, fragments and the tag-confirmed variant (2026-11-01, logged after the Llama results)
- D4 coverage for Llama: the regenerated text did not match the stored output for 8 of the 64 C1 outputs, so D4a and D4b use 281 of 319 sentences (71 of 82 harmful sentences). The 8 outputs are all pilot texts, listed as text/seed: P03/2, P05/1, P05/2, P06/1, P06/2, P07/2, P08/1, P08/2. They are not the outputs with the most harm: 11 of 38 sentences are harmful (29%) against 71 of 281 (25%) in the matched outputs, and they hold 13% of the harmful sentences with 12% of the sentences. The probable cause (not checked) is that the Llama pilot outputs were generated in an earlier separate run, so seeded sampling did not reproduce. D1, D2 and D5 use all 319 sentences. The Llama D4a result is reported with this coverage.
- Fragments among reachable spans: Qwen 25 of 184 (14%); Llama 58 of 213 (27%).
- Go/no-go with only tag-confirmed harmful spans (controls.py, section 4): Qwen 0.607 [0.445, 0.769] and Llama 0.613 [0.443, 0.819], both INCONCLUSIVE under the pre-registered rule (point estimate at least 0.60, lower bound not above 0.5); tag-derived labels give 0.546 and 0.528 (NO-GO). The pre-registered primary (labels as given) stays NO-GO for both; the variants are reported as sensitivity analyses, as the exposé states.
- Reach is stated strictly (quote of at most three words) for both models in every document: Qwen 17 of 90 (19%), Llama 8 of 97 (8%); the long-quote overlaps (2 and 23) are given in brackets.

### 11.18 Llama D3 (2026-11-01, rule of 11.7 unchanged, Llama results known for the other checks)
Backfill for Llama: the researcher's file for the 13 severity 2-3 omission tags (`results/llama_dev24/omission_backfill.csv`, kept as received in `_work/omission_backfill_user_file_as_received.csv`) listed the omissions as tags with their wording, not as sentence numbers. The sentence index was taken from that wording (matched to the source sentence that holds the missing content; `omission_backfill_confirmed.csv`, notes column per row). 8 of the 13 tags could be filled; 5 could not (D01/2: the omission has no wording; D08/1, P03/1, P06/1, P06/2: the researcher's file lists no omission for the output), and they are reported as missing as 11.7 provides. The researcher's file differs from the database tags in several outputs (for example D13/1 and D24/1 list two omissions where the database has one); the database labels were not changed.
Result (`results/llama_dev24/screen_d3.md`): 62 of 220 source sentences flagged (28%, within the 30% cap); omission recall 75% (6 of 8) against 28% for random flagging, difference +47 points [+19, +69] by 95% bootstrap over texts. This passes the rule of 11.7 for Llama. Qwen did not pass (72% flagged, recall 85% = random, 11.9), and Qwen decides (11.14), so D3 stays dropped from the held-out list (11.10); the Llama pass is exploratory. It rests on 8 tags and a partial backfill, and the difference between the models comes from how much each rewrites: Llama's outputs keep more of the source's content words, so fewer source sentences fall under the coverage threshold. Exploratory combination for Llama (D1 flags, then D4a up to 30%): 85 of 281 flagged, +5 [-2, +13], does not pass. D4a aligned AUC 0.697 [0.599, 0.782] (237 sentences, 58 harmful), unaligned 0.529 [0.375, 0.731] (44, 13).
