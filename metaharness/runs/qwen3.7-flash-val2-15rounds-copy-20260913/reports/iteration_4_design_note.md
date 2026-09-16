# Iteration 4 — precedent_audit (design note, pre-eval)

**Change.** The check stays where it is, but what it says and how it chooses what to say
changed. Iteration 3 measured the check as inert: draft and final answer agreed in 96 of
100 law samples, 0 of 11 wrong drafts were repaired, and every re-opened unit was mentioned
and rejected anyway. Four changes, each aimed at that.

1. **Re-opened by evidence, not frequency.** `support_scores` gives each unit the similarity
   of the closest reference case that answers it; `_audit_rank` orders the dropped
   candidates by that, with corpus frequency demoted to a tie-break. Replayed over
   iteration 3's own wrong samples, frequency ranking put a missing gold unit in the top 3
   for 4/42 law and 4/11 diagnosis samples; evidence ranking does 7/42 (11/42 at top 5) and
   7/11. It also fixes the observed case where the solver named the right rare unit and the
   tool showed it the three commonest instead.
2. **The distinguishing element is named.** `_relation_text` spells the relation out -
   `'非国家工作人员受贿' = '非国家工作人员' + '受贿'` - and the note asks for the element to
   be settled on the facts. The wording is symmetric on purpose: replayed over iteration-3
   drafts the note fires on 4 correct samples whose answer is the shorter unit and on 10
   wrong ones, so a one-sided "prefer the more specific unit" push would put more correct
   answers at risk than it could win.
3. **Fragments are named as fragments.** A draft unit that is one element of a reference
   unit now says so; the existing "extends a piece of a unit" note now shows the relation
   too.
4. **The question's own type is finally used.** `_set_query_group` looks for the shared
   header anywhere in the input instead of only at its start. Stored references are bare
   questions and the solver's input is wrapped in task boilerplate, so family matching, the
   family-first reference selection and the family bonus were all dead code. For tasks
   without a unit vocabulary the check now compares the draft against the type's answer
   widths and recurring units rather than the corpus-wide ones.
5. **The nudge stops licensing a no-change reply** ("change your answer only if the check
   gives you a factual reason to" is gone), and the skill states the specificity and
   precedent rules: a unit that does not match the facts is wrong even when it is commoner,
   and the closest case is the evidence for how the task names the situation.

**Hypothesis.** Choosing what to re-open by local evidence and naming the element that
separates a unit from its attested relative raises the mean validation score above the 0.584
of iteration 3, mainly by lifting the weak side of the multi-unit task (recall 0.680 against
precision 0.760, no sample over-predicting), without regressing the single-unit and
free-form tasks.

**Falsifiers to look for in the results.**
- If recall does not rise, the dropped candidates were rejected for reasons the evidence
  cannot outweigh and the audit path should be dropped rather than tuned again.
- If precision falls further than recall rises, the exactness and relative-unit wording is
  inducing extra units; the specificity note is the first thing to make conditional.
- If the free-form task's score moves on samples whose draft was already fully correct, the
  type-width note is inducing extra components.
- If the family-task split is unchanged, matching the header anywhere did not change what
  the prompt shows; check whether the guide is dominated by non-family references.
