# Iteration 7 — attested_rendering_audit (design note, pre-eval)

**Where iterations 3-6 left the loss.** Four measured facts set the direction.

1. *The check never repaired anything, and it made noise.* Best measured remains iteration 3
   (0.584; then 0.563, 0.559, 0.561). At iteration 3 the check re-opened candidates, and the
   post-eval measured 0 of 41 wrong law drafts repaired; its two-sided specificity notes fired
   on ~10 law samples and one of them (`受贿` / `非国家工作人员受贿`) oscillated into the
   32-call budget. Its markup rule demanded any bracketed token in the question, so on 5 of 60
   chemistry samples the draft was told the question "asks for" `[nH]`, `[N+]`, `[N-]` - atoms
   written once inside the input structure, not format requirements. Iteration 6's mechanical
   check was silent instead (100 of 100 law samples "checks out"; 3 piece notes), and where it
   spoke the model overruled it on doctrine (ex14: "the facts show no 包庇 conduct").
2. *What moved the multi-unit task was the wording.* Iteration 3's "name every candidate, set
   aside only for a factual reason" took the label task 0.52 -> 0.58. Iteration 6 removed that
   wording and the same task fell to 0.54 with the check silent, so the wording, not the audit,
   was doing the work.
3. *The residual is knowledge, not selection.* On the free-form task no candidate has ever
   solved 18 of 30 questions, and 33 of 43 failing samples share no component with the gold. On
   the label task 25 of 50 missing gold units appear nowhere in the references shown for that
   question, and 26 of 46 wrong samples substitute a related charge. On the single-label task
   the nearest reference carrying the gold diagnosis is at similarity rank 1 for 35 of 50
   questions and inside the shown set for 48 of 50, including every sample that flapped.
4. *A draft unit that is a piece of an attested unit is the one defect the check can prove.*
   Replayed over iteration 6's drafts: the piece note and its "extends a piece" variant fire on
   7 of 100 label samples, all of them wrong answers, and 0 of 160 samples on the other two
   tasks. The permissive wording ("keep it on its own only if the facts make it a complete unit
   by itself") left the choice open; the piece relation is a fact about how the references
   render the matter, so it can be read as one.

**Change.** The check reports attested renderings and nothing else; the decision wording goes
back to iteration 3's.

1. `check_answer` now says, for a draft unit the vocabulary does not list: that it is a piece
   of a reference unit the references always use whole, or that it extends a piece they only
   ever use inside a longer unit - in both cases *the whole unit is what they render*, with the
   counts. Near-miss spellings and the structure check stay. The re-open channel is gone:
   `considered` is inert, and the unit-relation notes on attested units are gone with it.
2. Markup is required only when the question *states* it (the tag occurs twice, as a format
   instruction does in its example), so an atom or citation that occurs once is never demanded
   of the draft.
3. The system prompt, skill and nudge carry iteration 3's decision rules again (name every
   candidate first, set a unit aside only for a fact, whole units, exact spelling) and describe
   the check as a rendering report; the nudge keeps the single forced call and says a check
   that reports nothing ends the matter.

**Hypothesis.** Reporting only attested renderings in the pre-submit check, while keeping the
fact-based candidate wording, raises the mean validation score above the 0.584 of iteration 3 -
mainly by turning drafts that use a piece of an attested unit, or an extension of one of its
pieces, into the whole unit the references render (7 of 100 label samples, 0 of 160 elsewhere),
and by removing the check's own noise - without regressing the single-label and free-form
tasks.

**Falsifiers to look for in the results.**
- The label task does not exceed 0.58: the piece drafts were rejected on doctrine rather than
  on rendering, the check channel is closed for good, and iteration 8 must spend its change on
  evidence rather than on the check.
- Symptom2Disease falls below 0.89: the check never speaks there, so the restored wording is
  the cause, and the enumeration rule has to be conditioned on the profile's shape.
- USPTO falls below 0.283: the shape line's completeness question is inducing extra components
  in free-form answers, and it has to be limited to label-like profiles.
- `call_budget` losses recur: the single-check rule in the nudge is not being read.
