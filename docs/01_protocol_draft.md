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
