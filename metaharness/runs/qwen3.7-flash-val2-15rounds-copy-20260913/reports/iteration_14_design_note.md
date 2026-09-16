# Iteration 14 — sibling_units (design note, pre-eval)

**Where thirteen iterations left the loss.** Replayed over the recorded runs rather than
over the scores.

1. *The prompt stops moving anything.* Since iteration 3 the three corpora have lived in
   0.85-0.92 (one unit), 0.54-0.59 (a set of units), 0.20-0.30 (free-form), and the swings
   between adjacent iterations are one to three samples. The cleanest measurement of the
   noise is iteration 13: the one-unit corpus's system prompt, skill and check output were
   byte-identical to iteration 12's, and its accuracy moved 0.910 -> 0.880.
2. *The decision rules added in iterations 12-13 are inert.* Over iteration 13's run the
   check wrote 120 "candidate not carried" lines; 8 named a unit the target contains (7%)
   and 2 were carried into the final answer. Iteration 12: 117 proposals, 8, 1. Every
   measured channel is in that range - neighbor answers (top-5 references recover 8 of 61
   missing units, 240 false proposals), co-occurrence (4 of 61, breaking 19 correct
   samples), similarity substitution (0 fixed, 31 broken), family-recurring components (0
   of 64 missing components). The calibration - proposals as remarks, not defects - is the
   right one; making them bind would trade ~3 fixes for ~2 breaks.
3. *The set corpus's missing units are mostly not in the vocabulary at all.* Of the 61
   units its wrong answers are missing, 33 appear in no training reference, and only 3
   appear verbatim in the question. On 25 of the 43 wrong samples the check named nothing
   and the solver's notes never mentioned the missing unit. No memory-side channel can
   reach a name the memory has never seen; the solver has to produce it from the corpus's
   spelling conventions, and no amount of decision-step wording supplies it.
4. *Two defects the check states as fact are false.* `related_units` relates units by
   shared edges (one name carrying the other's text at a head or tail). On a corpus whose
   units are names, that relation is not a refinement, and the check asserted it was: the
   draft reaches the branch as a *listed* unit, and the note then said the references "say
   it more specifically" with the longer form, or that the longer form "is never used by the
   references" - false for a unit the references use. Replayed over the recorded calls, 30
   firings of the first claim named a unit the answer needed in 6 and a unit it did not in
   8 correct drafts; the second fired 49 times.

**Change.** Iteration 12's rendering, restored, plus its two verified mechanical repairs,
plus the false claims removed.

1. **Restore iteration 12's prompts** (the highest-scoring rendering measured, 0.593): the
   branch-specific decision rules of iteration 13 go, and with them the third branch, whose
   text existed only to carry those rules. The system prompt and skill are byte-identical to
   iteration 12's for every corpus; the guide is produced by untouched code.
2. **Keep the two repairs, which are separable from the regression.** The unreadable-final-
   answer repair reproduces the benchmark's extraction on the recorded final turns of this
   harness family and fires on 0-2 turns per run - in iteration 12's run one of them is the
   sample that scored empty after being checked twice. The replacement rendering fixes the
   written-out offer that joined a draft unit with the candidate it spells differently
   ("X;X、Y", refused, unit lost).
3. **Stop the check asserting what is not so.** The two related-unit notes now report the
   relation between the names (shared edge, not refinement) and leave the choice to the
   facts, and the note for a listed draft unit never calls a listed unit unused. The
   candidate side of the same code learns one distinction: a candidate the vocabulary does
   not list, that only attaches text to a unit the draft carries, is already answered, so
   the check stops asking for it.

**Measured separation (training and recorded traces only).** All 3271 recorded `check_answer`
calls replayed through both libraries: 0 exceptions; 317 outputs change - 249 where only the
related-unit note's wording changes, 47 where only the written-out offer changes (the
replacement), 21 both. The unreadable-answer repair changes no check output; it acts on
final turns, where it fires on at most 2 per run. Nothing in the memory path is touched, so
the derived profile, vocabulary, groups and reference selection are identical to
iteration 12's.

**Hypothesis.** Restoring the rendering that scored 0.593, keeping the two repairs that act
on mechanical failures, and removing the check's two false claims returns the average to at
least iteration 12's level: the set-answering corpus comes back to its 0.54-0.59 band (0.540
under iteration 13's rendering), the one-unit corpus to 0.85-0.92 (0.880), and the free-form
corpus to 0.20-0.30 (0.283) - with the free-form corpus gaining the sample that the
unreadable-answer repair recovers.

**Falsifiers to look for in the results.**
- The set-answering corpus stays at or below 0.56: the iteration-13 rules were not the
  cause of its drop and the decision step is not where its loss lives.
- The one-unit corpus falls below 0.85: the related-unit note, which no longer pushes a
  solver off a listed unit toward a shorter one, was carrying more fixes than the recorded
  runs show (49 firings, 14 changes, 0 fixes, 0 breaks).
- The free-form corpus falls below 0.20: the unreadable-answer repair fires on a turn that
  was readable to the benchmark and costs a turn (recorded: 2 firings in iteration 12's run,
  one of them the empty sample).
- Any corpus moves by more than 3 samples in either direction: the comparison is measuring
  sampling noise, as iteration 13's byte-identical one-unit corpus showed, and the next
  iteration should spend its budget on a corpus-level mechanism rather than on the check.
