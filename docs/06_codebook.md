# Annotation codebook (v0.2.5, frozen)

Status: frozen on 2026-10-31 for the held-out set. Any later change needs a new version, a date and a reason in the change log, and
none may be made after held-out labelling has started. Open points at the end are not rule changes.
v0.2.5 (2026-10-31) changes how span labels are made (section 1a). It applies to the held-out set and later. The dev set was
labelled under v0.2.4 and is reported under that rule, with the v0.2.5 rule as a sensitivity analysis.
Works with `src/annotate.py` (blind sheets in `results/`). Condition labels and probabilities are hidden.
Design follows the outcome-based idea of Wu & Arase (few categories, no linguistic training needed, errors
described by their effect on the reader). Our harm categories are written for onboarding texts where a reader
acts on the text.

## 0. Scope and decision procedure
You label: changed spans (Unit 1, dev only) and whole outputs (Unit 2, all conditions). You see the source and
the output. You do not see the condition, the probability, or the labels of other annotators.
You do not label: harmless paraphrases, style, tone, register, or fluency.

**One question decides harm:** would a reader who acts on the output do something different from a reader who
acts on the source? If yes, it is harmful. If the answer is "only if they misread it", it is not.

## 1. Unit 1: changed span, rule v0.2.4 (used for the dev set)
Sheet `annotate_spans.csv`, columns `harmful` and `discuss`. Judge the output span in its sentence against the
source.

| Value | Meaning |
|---|---|
| `y` | harmful: the answer to the decision question is yes |
| `n` | not harmful: same meaning, even if the wording is simpler or a little odd |
| `f` | fragment: the diff cut a rewritten sentence into pieces, so the pair is not a word swap |

`discuss` = `y` when you are unsure. Still enter `y`, `n` or `f` as your best guess. Discuss items go to the
second pass.

Rules
1. Style, tone and register are not harm.
2. Loss or change of a protected item (name, date, time, number, role, recipient, condition) inside the span is `y`.
3. A pair is a fragment if the output span has no counterpart of the source span in meaning, because the model
   restructured the sentence (for example "where → if you had", "and → to", "a → your"). If the span is a real
   swap of the source phrase, even a bad one, it is not a fragment.
4. If unsure between fragment and real error: `y` if the sentence as a whole loses meaning at that point,
   otherwise `f`. Set `discuss`.
5. Do not use the probability, the condition, or other seeds of the same text to decide.

Pilot examples (from the pilot outputs; labels are draft positions, not ground truth)
| Source → output | Label | Reason |
|---|---|---|
| the HR department → get paid | `y` | the recipient is lost and replaced by an unrelated phrase |
| warden, Ms. Clara → leader, Mr. | `y` | name and title changed |
| mandatory → brief | `y` | an obligation is weakened to a description |
| line manager → boss | `n` | same role, simpler word |
| identification badge → ID card | `n` | same object |
| floor warden → floor leader | `y`, `discuss` | the fire role may be lost; a reader may not know who to report to |
| and → to | `f` | diff piece inside a rewritten sentence |
| login → time, it asks | `f` | crosses a clause boundary |

## 1a. Unit 1 from v0.2.5 (held-out and later; prospective)
A span is no longer judged for harm separately. Label the output (Unit 2) first. The span label is then derived by script:
- `harmful`: the quote of at least one severity 2-3 tag overlaps the span.
- `harmless`: no severity 2-3 tag overlaps the span.
- `f` (fragment): unchanged from v0.2.4; the annotator still marks it.
- A span overlapped only by a quote of more than three words is left out of the AUC (neither class), consistent with the
  reachability rule.
- Severity 1 tags do not make a span harmful.
- The `discuss` flag on spans is dropped. Use `discuss` on the output only.

Why. In the dev set, 14 of the 32 spans labelled harmful in Unit 1 overlapped no severity 2-3 tag (11 no tag, 3 only
severity 1), so the AUC used a broader definition of harm than the primary measure. Deriving the span label from the tags
gives one source of truth and removes the span-harm labelling on held-out. The dev spans are not re-labelled by hand: the
derived labels are computed by script and reported as a sensitivity analysis (`src/controls.py`, section 4 of its report).

## 2. Unit 2: output (all conditions, for harmful errors per 100 words)
Sheet `annotate_outputs.csv`. Identical outputs across conditions are merged into one item.
- `errors`: tags separated by `;;`, each tag `category|severity|quote`, for example
  `wrong_number_date_name|3|before noon;;omission|2|`.
  The quote is the smallest wrong piece, copied from the output. It is checked against the output text on
  import. If it occurs more than once in the output, add the occurrence number, `before noon#2` for the second
  one; the import asks for it. Leave the quote empty only for an omission. Write `none` if you checked the output and found no error.
  Empty rows count as not yet annotated.
- `simplicity`: `lexical`, `structural` or `both` when the output is harder to read than it needs to be.
  Empty = no problem. This is not harm and is counted separately (section 4).
- `discuss`: `y` when unsure.

### Categories
Examples marked (constructed) are invented for illustration. The others come from the pilot outputs.
One output can have several tags. Several different errors in one span or sentence each get their own tag.
The same error is never tagged twice under two categories: choose the first category in the order of
seriousness below that fits.

Order of seriousness (use it to choose when two categories fit, and to read severity):
1. `altered_condition`, 2. `wrong_number_date_name`, 3. `meaning_change`, 4. `omission`, 5. `hallucination`,
6. `unclear_reference`, 7. `repetition`, 8. `other`.

| Category | Definition | Applies when | Does not apply when | Example | Counter-example |
|---|---|---|---|---|---|
| `altered_condition` | An if / when / unless / deadline-condition or an obligation level (must, may, should, must not) changes. | The reader would act differently because a requirement became optional, or the reverse, or a trigger changed. | The condition is only reworded with the same force. | (constructed) "Elevators must not be utilised under any circumstances" → "Use the stairs if you can" | → "Don't use elevators" (same force; the "under any circumstances" wording is dropped but the rule stands) |
| `wrong_number_date_name` | A number, date, time, name, title or identifier is changed, lost or made vague. | The exact value matters for acting. | A number is rewritten with the same value ("three" → "3"). | P03: "no later than 09:00" → "before noon"; P01: "Assembly Point B" → "the assembly point"; "Ms. Clara Jensen" → "Mr. Jensen" | "09:00" → "9 AM" |
| `meaning_change` | A statement says something different from the source. | The new sentence is true or false in different situations than the source. | The change is only simpler wording for the same fact. | "HR department" → "get paid" (recipient replaced) | "line manager" → "boss" |
| `omission` | Content the reader needs in order to act is missing. | Defined by consequence: a deadline, a condition, a warning, a recipient or a required step is gone. | Detail that does not change what the reader does (a courtesy phrase, a repeated point). | (constructed) "must be submitted to the HR department" dropped, so the reader does not know where to send the certificate | Dropping "In the event of" when the condition is kept elsewhere |
| `hallucination` | Content with no basis in the source is added. | A fact, step, number or promise appears that the source does not contain. | Neutral framing words with no new fact. | (constructed) "ask HR for a refund form" added when the source mentions no refund | "Here is the rewritten text:" (lead-in; stripped automatically) |
| `unclear_reference` | A pronoun or phrase no longer points to one clear thing, or a named person or place is replaced by a vague phrase. | The reader cannot tell who or what is meant. | The reference is clear from the previous sentence. | (constructed) "report to your floor warden, Ms. Clara Jensen" → "Tell them", no antecedent in the output | "the premises" → "the building" |
| `repetition` | A fragment or sentence is duplicated without need. | The same content appears twice in a row or in one paragraph. | A deliberate repeat of a key warning that the source itself repeats. | (constructed) the same sentence twice in one output | A rule repeated because the source repeats it |
| `other` | Harmful by the decision question but none of the above. | Add a short note in the sheet. | A category above fits. | | |

`reachable` is not typed. The importer computes it from your quote: reachable if the quote is at most 3 words
and overlaps a reachable changed span (the frozen reach definition). So quote the smallest wrong piece, not a
whole sentence: a long quote counts as unreachable. An omission has no quote and is unreachable. (This is the
lexical / structural split of Wu & Arase seen from our checks: reachable errors are word swaps, unreachable
ones come from restructuring.)

Harm count: only severity 2 and 3 count as harm (decision question, section 0). Severity 1 is a minor note and is
not counted in harmful errors per 100 words. Tag severity 1 only when the wording could mislead some readers; a
change no reader would act on ("valid photo ID" → "valid ID") is not tagged. The C5 vs C1 comparison is also
reported with all tags (severity 1–3) as a pre-specified sensitivity check. The severity 1 / 2 boundary is the
least reliable rating, so agreement is measured on exactly that boundary. Labels made under v0.2.3 or earlier are
development data; re-label on a fresh set after the freeze.

Severity: 1 = reader can still act correctly; 2 = reader may act wrongly; 3 = reader will act wrongly, or a
safety, legal or pay consequence follows.

Critical omission is defined by consequence: if leaving it out can change a deadline, a condition, a warning, a
recipient or a safety step, it is an omission of severity 2–3, however short it is. Missing detail that changes
nothing the reader does is not tagged.

## 3. Simplicity flag (not harm)
`simplicity` marks outputs that are harder than needed:
- `lexical`: a difficult word, or a more complex word than the source, appears (for example a technical term
  where a plain word fits).
- `structural`: the sentence structure makes reading harder (long sentence, stacked clauses, passive chain).
Not tagged: text that is merely not as simple as it could be, when it is still easy for the target reader.
Reported separately from harm, never added to the harm count.

## 4. Procedure
1. Read the source, then the output. Apply the decision question (section 0).
2. Spans (v0.2.4: enter `y` / `n` / `f`; from v0.2.5: mark only fragments `f`). Outputs: list errors in the order they appear, using the seriousness order only
   to choose between two fitting categories, and copy a short quote for each.
3. When unsure, enter your best guess and set `discuss`. Do not leave an item empty. Do not look up the
   condition.
4. Time each session. Record minutes per output on the first 20–30 pilot outputs: ____ min (fill in). The
   planning figure in the report (3 minutes) is replaced by this number.
5. Annotate spans and outputs in separate sessions. Spans first. Order is randomised by the export.
6. Import with the right role: `--role primary` for the researcher, `--role second` for the second person,
   `--role consistency` for the repeat. Only primary labels are counted in harm figures. The second person gets
   the subset sheets from `export --subset 0.2`.
7. Each import stores `labelled_by` and `labelled_at` for spans, and `created_at` for output tags and flags.
   Keep the timestamps. If labels are changed later, re-import and note the date in the change log.

## 5. Development and reliability
Development of the codebook
1. Annotate 20–30 pilot outputs yourself. Every time you hesitate, write down why and add a rule here.
2. Revise. A few days later, label a new small set and check whether you reproduce your own earlier labels.
3. Freeze the codebook. Any later change needs a version, a date and a reason in the change log.
4. Give the codebook to the second rater with a tutorial. Wu & Arase used a 2.5-hour tutorial, a qualification
   test and discussion sessions until consensus; plan at least the tutorial and a discussion session on the
   `discuss` items. If the second rater would have to ask a question to apply a rule, the answer goes into the
   codebook.

Reliability reporting
- Consistency check (self): re-label a random 20% of spans and outputs at least one week later without
  looking at the first labels. This is intra-rater agreement, not a second rater, and is reported as a
  consistency check.
- Second person: a non-author labels the same subset blind, after the tutorial. This is inter-rater agreement
  and the human check used to judge success in the Research Project.
- Report observed agreement, Cohen's kappa and the label prevalence together. When one label dominates
  (for example most spans `n`), kappa can be low although raw agreement is high; the prevalence figure shows
  whether that is the cause.
- Output categories are not mutually exclusive, so agreement is computed per category as present / absent, not
  as one nominal scale, and also pooled over all harm categories (harmful output yes / no). Per-category kappa
  on a few dozen harmful items is unstable; report it with the count.
- Disagreements are resolved by discussion and the resolved label is stored as the gold label; both original
  labels are kept.

Limits to state in the thesis
- The researcher is not a member of the target readership. The second rater should be a non-author, and a
  reader from the target group would be better for the simplicity flag.
- The unit is a paragraph, not a sentence. Wu & Arase worked on sentence pairs, so their agreement figures are
  not directly comparable.

## Open points
- Confirm with the supervisor whether severity 3 needs a fixed definition per text type.
- Decide who the second person is for the Research Project subset. The thesis phase uses three expert raters.
- Decide whether the simplicity flag is annotated on dev only or also on held-out.

## Change log
| Date | Change |
|---|---|
| 2026-10-26 | Draft v0.1 |
| 2026-10-28 | v0.2: added repetition category, simplicity flag, discuss flag, category fields with examples and counter-examples, seriousness order, critical omission by consequence, reliability plan (intra- vs inter-rater, prevalence, binary per-category kappa), tutorial |
| 2026-10-28 | v0.2.1: second person moved into the Research Project; self-repeat renamed consistency check |
| 2026-10-28 | v0.2.2: output tags are category, severity and quote (separated by a vertical bar); reachable is computed from the quote; roles primary, second, consistency |
| 2026-10-28 | v0.2.3: quote occurrence number when a quote is not unique |
| 2026-10-28 | v0.2.4: only severity 2–3 counts as harm; severity 1 is a minor note; all-tags sensitivity check; severity 1/2 agreement; pilot labels are development data |
| 2026-10-31 | v0.2.5 FROZEN: no rule changed; the importer (`src/annotate.py`) now reads a spans sheet with a `fragment` column only and derives the span label from the severity 2-3 tags (`annotate.py derive` is a dry run). Dev labels stay under v0.2.4. |
| 2026-10-31 | v0.2.5 (prospective, made after the dev results were seen; decided by the researcher): span labels are derived from severity 2–3 output tags instead of being judged separately; discuss dropped on spans; applies to held-out and later; dev reported under v0.2.4 with the v0.2.5 rule as a sensitivity analysis. Reason: 14 of 32 dev spans labelled harmful overlapped no severity 2–3 tag |
