Project 3 pivot plan: from word-level to sentence- and fact-level checks
Oct 31, 2026 · @Zain
Summary
The word-level design has a ceiling: on dev, only 17 of 90 harmful errors (19%) sit where the checks can act, and the probability AUC is a NO-GO at 0.569 [0.409, 0.726]. The pivot keeps the research question and moves the checks to the level where the harm is: sentences and facts.
1. Freeze the current dev results as intermediate report I1. It becomes a chapter of the final report, not a discarded attempt.
2. Screen six candidate directions offline on the labels you already have, before building anything new.
3. Build only the directions that beat random flagging, freeze the protocol, then run held-out once.

Stays
Changes
Question
Can lightweight local checks make small-model Easy Language safer?
Checks work on sentences and facts, not word spans
Setup
Qwen 2.5 1.5B, prompt, seeds, CPU, aligner
Action is flag for review (primary) plus targeted repair (secondary), not revert
Measure
Harm per 100 words, codebook, guards, paired bootstrap over texts
Primary becomes residual harm in unflagged text, at a matched flag rate, against random flagging
Data
32 dev texts, held-out set untouched
Omission tags get a source-sentence index (codebook v0.3)
Step 1: freeze the dev results as intermediate findings
Step 1 turns what you have into a citable result: I1, word-level safety checks on whole onboarding texts (dev, 32 texts, 64 text-seed units). It runs about 6 to 8 pages and becomes a chapter of the final report. Plan about 40 h, Nov 2 to Nov 13.
What I1 reports
1. Setup as run: config, model, prompt, seeds, τ, word list, codebook v0.2.4 for spans, with the commit hash and date.
2. The pre-registered go/no-go: AUC 0.569 [0.409, 0.726], NO-GO. Add the two sensitivity variants (0.607 tag-confirmed, 0.546 tag-derived) and say the decision holds under all three.
3. Reach: 30% of changed spans are reachable. Of the 90 severity 2–3 tags, 19% overlap a reachable span, 50% sit in rewrites or insertions, 22% are omissions and 7% touch no changed span.
4. The ceiling: even a perfect word-level filter removes at most about 17/90 × 2.60 ≈ 0.49 harmful errors per 100 words, out of 2.60.
5. Condition effects against C1 and the random-revert control (your tables 1 and 2). C3, the planned NO-GO fallback, falls inside the random range (share 0.217). C2's result above random is reported as descriptive only, for the reason in your own note.
6. Label quality: 14 of the 32 spans labelled harmful overlap no severity 2–3 tag. This motivated codebook v0.2.5.
7. Conclusion: on dev, word-level checks do not carry over to whole-text rewrites. The main cause is reach, not only a weak signal. This is the motivation for Step 2.
Housekeeping, so the pivot stays clean
[ ] Tag the code intermediate-1 and dump the easylang_p3 database and results/ to an archive
[ ] Add a change-log entry: pivot decided on the date you decide it, after seeing dev, with the reason (reach ceiling plus NO-GO)
[ ] Generate nothing on held-out texts. Keep their file hashes in the log
[ ] Keep codebook v0.2.4 and v0.2.5 files frozen as they are; v0.3 starts as a copy
[ ] Send I1 to the supervisor together with the pivot proposal (Step 2 and the directions)
Step 2: the new level, sentences and facts
The checks move to the unit where 81% of the dev harm sits. A check either flags a sentence for staff review, or, as a secondary condition, repairs it. The pipeline, aligner and codebook stay. Only the unit, the action and the primary measure change.
Units
• Sentence pair: each output sentence and its aligned source sentence (your existing embedding aligner, cosine at least 0.45).
• Unmatched source sentence: a source sentence that no output sentence aligns to. This is a candidate omission, flagged at the place where it should appear.
• Fact: a number, date, time, name, identifier, obligation word or condition, extracted automatically from the source sentence.
Action
• Flag (primary). The prototype returns the text plus a list of flagged sentences for staff, as the memo already describes. Flagging never undoes simplification, so it cannot fail the FKGL guard.
• Repair (secondary). A flagged sentence is regenerated alone, with its source sentence and its facts in the prompt. If that still fails the check, it falls back to the source sentence. Repair changes the text, so the guards apply.
Measures
• Residual harm per 100 words (primary for flags): severity 2–3 harm left in sentences that were not flagged, assuming staff fix what is flagged. C1 flags nothing, so all its harm is residual.
• Flag rate: share of sentences flagged, which stands for reviewer effort. A check that flags everything is useless, so every comparison is at a matched flag rate.
• Random-flag control: flag the same number of sentences per output at random. This replaces the random-revert control and answers the same question: does the choice add anything?
• Harm per 100 words after repair (primary for repair): as in the original plan, with the three guards.
• Overhead: check time against generation time, bound 25%.
Sentence labels from the existing tags. A sentence is harmful if the quote of a severity 2–3 tag lies in it. Omission tags have no quote, so each of the 20 dev omissions needs its source sentence recorded once (a backfill of about 30 minutes). From codebook v0.3, the annotator records the source sentence index for every omission tag. Nothing else in the codebook changes.
Candidate directions and how to screen them
Six directions each target a harm category you already measured. D1 to D3 are rule-based and cheap. D4 keeps the Hayakawa signal at the new unit. D5 adds a small NLI model. D6 turns flags into repairs. By category, D1 to D3 alone aim at 49 of the 90 dev tags (54%), against the word-level ceiling of 19%.
Direction
What it checks
Targets (dev tags, sev 2–3)
CPU cost
Screen on existing labels
D1 Fact check
Numbers, dates, times, names, IDs from the source (regex plus small NER, normalised: three = 3, 09:00 = 9 AM) are present and unchanged in the aligned output sentence. Output facts with no source are flagged too
wrong_number_date_name (13), part of hallucination
Very low
Recall of the 13 tags; precision and recall of automatic extraction against your hand protected-item lists
D2 Condition check
Obligation and condition words per aligned pair: must, must not, may, should, need to, required, optional; if, unless, only, when; before, by, until, within, no later than. Synonym classes so "you have to" = must
altered_condition (16)
Very low
Recall of the 16 tags; flag rate on harmless sentences
D3 Coverage check
Source sentences with no aligned output sentence, or with low coverage of their content words and facts
omission (20)
Very low (aligner already runs)
Recall of the 20 omissions after the backfill
D4 Sentence probability
Mean token log-probability of the output sentence, and the lowest changed-span probability inside it, from the same forward pass
meaning_change (41), all categories
None extra
Sentence-level AUC with bootstrap over texts, same GO rule as before
D5 NLI check
A small public NLI cross-encoder (DeBERTa-v3 size, chosen and fixed before the screen) scores entailment both ways: source to output (unsupported content) and output to source (lost content)
meaning_change (41), hallucination, omission
Moderate; measure seconds per sentence
Sentence-level AUC; CPU time against generation time
D6 Targeted repair
Regenerate only flagged sentences with source and facts in the prompt; fall back to the source sentence
Whatever D1–D5 flag
One short generation per flagged sentence
Not screened offline; built only after Gate A
The screen (Step 2a) runs on the 64 C1 outputs you already labelled: no new generation, and no new annotation beyond the omission backfill. For each of D1 to D5, report:
• recall of harmful sentences against flag rate, compared with random flagging at the same rate, with a paired bootstrap over texts
• sentence-level AUC for the scored checks (D4, D5)
• per category: which tags each check catches, so overlaps between checks are visible
• CPU seconds per text
Gate A (proposed, fix the wording before you compute anything): a direction goes on if, at a flag rate of at most 30% of sentences, its harm recall beats random flagging with a lower bound above 0. For D4 and D5 the AUC lower bound must also be above 0.5. If no direction passes, take the negative-result route: I1 plus the screen, written up as evidence that lightweight post-hoc checks do not carry over to whole-text simplification with this model.
Further directions, beyond the Research Project. These go in the exposé as outlook, not as work:
• D7 Sentence-by-sentence generation. Simplify one source sentence at a time. Rewrites stay inside one sentence, so reach rises and the word-level checks from I1 can be tested again. It changes C1, so it needs its own baseline.
• D8 Self-check prompting. Ask the same 1.5B model whether a sentence keeps the meaning. A cheap comparison point for D5, expected to be weak at this size.
• D9 Second model, longer and real texts, German. As already planned for the thesis.
Order of work and timeline
The 900 hours stay. The first five weeks go to the write-up and the offline screen, so nothing new gets built before Gate A shows it is worth building.
Gate A can end the build early: if no check beats random flagging, Phase 3 becomes the negative-result write-up. Dates assume a start on Nov 2, 2026, and the hours are a planning proposal.
Exposé text, ready to adapt
The blocks below replace or extend sections of Exposé 3. Section numbers refer to that draft. Figures in brackets come from dev and should be checked against the final I1 numbers.
Abstract (replace)
Small language models that run locally can write Easy Language without sending sensitive text to an external service, but they change names, dates, conditions and duties, and a reader who acts on such a text acts wrongly. An intermediate study on 32 development texts showed that word-level checks, including a token-probability filter after Hayakawa et al., cannot reach most of this harm: only 19% of harmful errors lie in word swaps the checks can judge, and the probability signal did not separate harmful from harmless changes (AUC 0.57). This Research Project therefore moves the checks to sentences and facts. It tests rule-based fact, condition and coverage checks, sentence-level probability and a small entailment model on the output of Qwen 2.5 1.5B for onboarding texts. Checks flag sentences for staff review or repair them. The main measures are the harm left in unflagged text at a fixed flag rate, compared with random flagging, and the harm per 100 words after repair, with guards for meaning preservation and simplicity. The study reports the outcome as it is, including a negative one.
4 Research question (replace)
Can lightweight checks that run locally on sentences and facts make English Easy Language from a small model safer, without a loss of meaning or simplicity beyond the pre-set guards, and without overhead above 25% of generation time?
• H1 (flagging): at a flag rate of at most 30% of sentences, the combined checks leave less harm per 100 words in unflagged text than random flagging at the same rate. Lower bound of the difference above 0.
• H2 (repair): the combined checks with targeted repair have fewer harmful errors per 100 words than the unchanged output (C1), and pass the guards.
• H0: no difference from random flagging, and no reduction after repair.
• Q1: which harm categories does each check catch, and how much do the checks overlap?
• Q2: does the token-probability signal separate harmful from harmless changes at sentence level, where it failed at word level?
• Q3: how much overhead does each check add per text?
5.2 Conditions (replace the table). The final set is fixed at Gate A (December), after the offline screen. Candidate conditions:
Condition
Treatment
C1 Baseline
Output unchanged, nothing flagged
C2 Probability
Flags sentences whose probability score is below τ (D4)
C3 Facts and conditions
Flags sentences with a missing or changed fact, obligation or condition (D1, D2)
C4 Coverage and entailment
Flags omitted source content and sentences that fail entailment (D3, D5)
C5 All flags
Union of the flags that passed Gate A
C6 All flags plus repair
C5, then flagged sentences are regenerated alone, with the source sentence as fallback (D6)
As before, all conditions work on the same base output per text and seed, so differences come from the checks alone. The word-level conditions from the intermediate study are reported in a separate chapter as a reference result.
5.3 Intermediate results and gates (replace go/no-go)
The word-level design was run on the 32 dev texts. Its pre-registered go/no-go gave NO-GO (AUC 0.569, 95% interval [0.409, 0.726]). Lookup-based reverting did not beat reverting the same number of spans at random. Only 19% of harmful errors lay in reachable spans, which caps any word-level effect at about a fifth of the harm. These results are reported as intermediate findings and motivate the change of unit. All later decisions were made after seeing them and are logged with date and reason. The held-out texts were not used. Two gates follow. Gate A (December) screens each check on the existing dev labels, and a check goes on only if it beats random flagging. Gate B (January) freezes prompt, checks, thresholds and codebook before the single held-out run.
6.1 Success rule (replace the first part)
The primary measure for flagging is residual harm per 100 words, meaning severity 2–3 errors in sentences that were not flagged. It is compared with random flagging of the same number of sentences per output, by paired bootstrap over texts. For repair, the primary measure is harmful errors per 100 words, C6 against C1, with the three guards as before. Results are reported per harm category, so it stays visible which kind of harm each check reaches.
New section: Possible improvement directions
The intermediate results point to where lightweight checks could still help, and which steps fall outside this project.
1. Fact preservation. Numbers, dates, times and names are extracted from the source and must reappear in the aligned output sentence. This is cheap, rule-based and directly tied to the errors a reader acts on.
2. Obligations and conditions. Easy Language must not change "must" into "may", or drop an "unless" or a deadline. A small lexicon of modal, conditional and deadline words, with synonym classes, compares source and output sentence by sentence.
3. Coverage. A source sentence without a matching output sentence marks a likely omission. Omissions made up 22% of dev harm and cannot be found by any check that only looks at the output.
4. Probability at sentence level. The signal of Hayakawa et al. is tested again on the unit where the harm lies, which shows whether it failed because of the unit or because of the signal.
5. Entailment. A small natural language inference model checks in both directions whether the output follows from the source. It targets meaning changes, the largest category (41 of 90 dev tags).
6. Targeted repair. Only flagged sentences are regenerated, which keeps most of the simplification while removing the flagged harm.
7. Outlook (thesis). Sentence-by-sentence generation keeps rewrites inside one sentence and could make word-level checks useful again. Further steps are self-check prompting as a comparison, a second model, longer and real onboarding texts, and German.
8 Risks (add)
Sentence-level checks may flag too much, so every comparison is made at a matched flag rate. Entailment models are trained on general text and may misread short second-person Easy Language sentences, so thresholds are set on dev and the error is reported. Automatic fact extraction is kept separate from the hand-made protected-item lists, which stay the evaluation reference for the preservation guard. Repair can introduce new errors, so repaired outputs are annotated blind like all others.
Risks, honesty rules and questions for the supervisor
The biggest risk is that dev has too few harmful items to choose between checks: 90 tags in all, 13 to 41 per category. Gate A therefore asks only whether a check beats random flagging, not which check is best.
Risk
Effect
Mitigation
Few harmful items on dev
Wide intervals; per-category recall is unstable
Gate A uses pooled recall against random; categories reported descriptively; held-out larger
Checks flag almost everything
High recall that means nothing (C4 grammar flagged 100% of outputs)
Matched flag rate, bound 30% of sentences, random-flag control
NLI misreads Easy Language
Second-person, split sentences read as non-entailment
Threshold on dev, report false-flag rate on harmless sentences
Circular preservation guard
The check and the guard use the same list
Automatic extraction for checks; hand lists only for evaluation
Repair adds new errors
Harm moves rather than drops
Repaired outputs annotated blind with the rest
Time for building five checks
Phase 3 slips
Gate A drops directions early; D1–D3 are a few days each
Honesty rules
• Every decision after 2026-10-31 is logged with date, reason and the fact that dev results were known.
• Gate A and Gate B rules are written down before the numbers they decide on are computed.
• Held-out texts are not generated on, read for tuning or annotated until Gate B.
• C2's result above random at word level is never cited as evidence for the probability signal.
• If nothing passes Gate A, the negative result is the main finding, as the memo already allows.
Questions for the supervisor
1. Do you accept the change of unit as a change of method under the approved question, with I1 as an intermediate result?
2. Is flag-for-review, measured as residual harm at a matched flag rate, acceptable as the primary measure, with repair as the secondary one?
3. Is a 30% flag-rate bound reasonable for onboarding staff, or should it come from the usability side of the brief?
4. Should I1 be a chapter of the final report, or a separate milestone document?
5. Who is the second rater for the held-out subset?
Recent work and positioning
Every ingredient of the pivot already exists in recent work. What has not been tested, in the sources found, is whether these checks make a small, CPU-local generator's Easy-to-Read output safer, with harm judged by what the reader would do and omissions included. That combination is the contribution.
Work
What it does
Supports
Gap this project fills
CLEF SimpleText Task 2, 2025 and 2026
Shared task: is each simplified sentence faithful to its source? Detection and classification of overgeneration
Step 2 as a whole
Biomedical abstracts, large or fine-tuned detectors, additions only; no omissions, obligations or small generator
writerslogic, CLEF 2026 (2nd place)
DeBERTa-v3-large NLI fine-tuned on 350K (source, sentence) pairs
D5
Large fine-tuned model
CYUT, CLEF 2026
Numerical-mismatch and negation flags; contrastive perplexity; notes that plain probability indicators often fail; F1 0.81 falls to 0.46 without source retrieval
D1, D2, D4, I1
Biomedical; 8B model
SummaC
Sentence-pair NLI scores aggregated over a document
D5
Built for summaries
MiniCheck
770M fact-checker at GPT-4 accuracy
D5
General grounding, not simplification
LettuceDetect
Token-level unsupported-span detector (ModernBERT)
D5, review UI
RAG answers
Cripwell et al. 2024
SummaC and QAFactEval for document simplification, with recall-oriented variants scored per input sentence
D3
Not a filter, an evaluation
HULAT2, MER-TRANS 2026
Easy-to-Read generation routed by checks on numbers, dates, negations, conditions; evaluate and regenerate up to two times
D1, D2, D6
Spanish; Gemini and 7B; no direct factual-consistency measure
Broto-Ortega et al., ICCHP 2026
Gemma 3 4B with Easy-to-Read guidelines in the prompt; human evaluation of content preservation
Small-model Easy-to-Read
No safety checks
Devaraj et al. 2022
Factuality taxonomy for simplification; metrics catch deletions but miss insertions and substitutions
Harm measure needs labels
Pre-LLM systems
Vendeville et al. 2025 (SIGIR)
Error taxonomy and test collection for simplification
Codebook
Taxonomy only
MeaningBERT
Trained meaning-preservation metric (co-author Saggion, also on Hayakawa et al.)
Automatic comparison score
Sentence-level score, not a flag
Changes this suggests for the plan
• D4: add a contrastive score. Compare Qwen's loss on the output sentence with the source in context against its loss without it, in two forward passes. Keep raw probability as the I1 baseline.
• D5: screen SummaC-style sentence-pair NLI and MiniCheck first; both fit CPU. LettuceDetect can mark the exact words inside a flagged sentence for staff.
• D3: cite Cripwell et al. for the recall-oriented, per-source-sentence design.
• Positioning sentence for the exposé: prior work detects additions in long scientific texts with large detectors; this project tests lightweight, local checks for additions, omissions and changed obligations in short Easy-to-Read workplace texts from a 1.5B generator.
Evaluation-v2.md: what it gives the pivot
Evaluation-v2.md is a set of literature notes, not an evaluation procedure: 11 papers, most in the same seven fields (task and level, language, model, what was rated, raters and items, agreement, limitations). The layout maps straight onto a related-work table. Several notes back the pivot directly.
Group
Papers in the notes
What it gives the project
Error codebooks
Wu & Arase
Basis of the codebook (already used)
Do automatic metrics work?
Alva-Manchego et al.; Newsela-Likert meta-evaluation; LENS; ASSET; document-level aggregation paper
Why harm needs human labels; which automatic scores to report
Who judges
Small LMs as evaluators; Artstein & Poesio
Limits of model judges; how to report agreement
Use context
Kim et al. (TSAR 2024); MultiLS-PT
How writers want to work with a tool
What the notes imply
1. Kim et al. supports flag-for-review. Municipal writers wanted modular, explainable suggestions and final editorial control, not automatic sentence rewrites. Cite it where the exposé justifies flag over revert.
2. The small-LM evaluator paper predicts D8 will fail. Models under 5B gave flat scores and zero correlation without a reference. Keep D8 as a comparison point only, or drop it.
3. The document-level aggregation paper backs sentence-level flags. Averaged document scores missed localised hallucinations, because correct sentences pulled the average up.
4. Borrow its synthetic-error test. That paper injected six error types and checked whether each metric penalised them. Plant wrong numbers, flipped must/may, dropped unless, and deleted sentences into C1 outputs. This gives hundreds of known-answer items for D1 to D3, against 13 to 20 real tags. Real tags stay the main evidence; synthetic errors are a stress test.
5. How to use automatic scores.
    ◦ FKGL has near-zero correlation with human simplicity at sentence level (Alva-Manchego et al.). Use it at text level only, always called a proxy.
    ◦ BERTScore recall tracked meaning preservation in the meta-evaluation; report it as a cheap comparison.
    ◦ LENS needs references and these texts have none; use LENS-SALSA if a learned score is wanted.
    ◦ Report Spearman or Kendall, not only Pearson; single outliers inflated Pearson in that paper.
6. Wu & Arase v3 includes Llama-3.2-3B. A better citation for small-model meaning errors than the GPT-4 version the exposé cites.
Fixes to the notes
[ ] Wu & Arase: the ICC of 0.62 sits under Task 1 in one place and Task 2 in another; check the paper and keep one
[ ] Wu & Arase: field 5 is unnumbered and the summary repeats the table; trim to match the other entries
[ ] Add title and authors for the Newsela-Likert meta-evaluation, or it cannot be cited
[ ] Reduce MultiLS-PT to one line or drop it (Portuguese, word-level)
Entries to add, in the same seven fields
[ ] Devaraj et al. 2022
[ ] SummaC, MiniCheck, LettuceDetect
[ ] Cripwell et al. 2024
[ ] CLEF SimpleText Task 2, 2025 and 2026
[ ] MER-TRANS 2026: HULAT2, Broto-Ortega et al.
[ ] Hayakawa et al. (the signal I1 tested)
Sources
• Overview of the CLEF 2025 SimpleText Task 2
• Overview of the CLEF 2026 SimpleText Task 2
• CYUT at CLEF 2026 SimpleText
• writerslogic CLEF 2026 SimpleText code
• Cripwell et al., Evaluating Document Simplification
• Laban et al., SummaC
• Tang et al., MiniCheck
• Kovács and Recski, LettuceDetect
• Devaraj et al., Evaluating Factuality in Text Simplification
• Vendeville et al., Resource for Error Analysis in Text Simplification
• HULAT2 at MER-TRANS 2026
• Broto-Ortega et al., ICCHP 2026
• Beauchemin et al., MeaningBERT