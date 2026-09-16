# Iteration 7 — attested_rendering_audit (post-eval)

**Change.** The pre-submit check reports only renderings the references attest: a draft unit
that is a piece of a reference unit, or one that extends a piece of one, comes back as the
whole unit the references use; `considered` became inert and the re-open channel was deleted;
markup is required only when the question states it; the decision wording went back to
iteration 3's.

**Result.** 0.573 (USPTO 0.25, Symptom2Disease 0.90, LawBench 0.57) against 0.561 for
iteration 6 and 0.584 for the best run so far (iteration 3). The three are one standard
error apart (macro SE ≈ 0.03 over 260 samples), so this is not a measurable move.

**What the run showed.**
- The word count moved the multi-unit task back up: 0.54 (it6, mechanical check, no
  candidate wording) -> 0.57 with iteration 3's wording restored. Wording, not the audit,
  is what the multi-unit task responds to.
- The relation note is not a one-way channel. It fired on 7 law samples, and in one live
  trace it turned a *correct* two-unit draft into a dropped one: the model's second draft
  was the gold answer, the note said the added charge "extends" a piece of another unit,
  and the model reverted to the wrong single-charge draft. Draft-level accounting over the
  whole run: 2 drafts repaired by the check, 1 correct draft lost.
- The shape line was a contradiction on almost every sample: it reported a directional
  discrepancy in 101/101 law and 59/61 chemistry checks, and 63 (law) and 58 (chemistry) of
  those reports still ended "the draft checks out ... submit this draft unchanged". On one
  chemistry draft the reported discrepancy was correct (3 parts against a gold of 2) and
  was ignored.

**Takeaway.** Evidence the references can prove is worth reporting; evidence inferred from a
shared substring is not, because a wrong inference costs a correct answer and cannot be
told apart from a right one. The part count is provable, but only against the question's
own type — the corpus-wide spread is a discrepancy on nearly every draft and therefore says
nothing. Iteration 8 makes the count evidence question-specific and makes the verdict
consistent with the report.
