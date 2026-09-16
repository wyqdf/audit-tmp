# Iteration 15 — formula_coverage (post-eval)

**Result: average 0.5456** (free-form 0.217, one-unit 0.870, set-answering 0.550), -0.049
against iteration 14's 0.5944 and the worst run since iteration 1. The free-form corpus fell
0.333 -> 0.217 (20 -> 13 correct of 60); the other two moved 1-2 samples each.

**The mechanism did not fire; the prompt text did the damage.** `repair_turns` is 0 on all
260 samples in this run: the pre-submit accounting repair never sent an answer back, so the
whole measured effect comes from the two sentences the iteration added to the system prompt
and the skill (the profile line and the accounting remark inside `check_answer`).

**Per-sample flips against iteration 14** (same questions, same two samples each):

| corpus | correct -> wrong | wrong -> correct | both correct | both wrong |
|---|---|---|---|---|
| free-form | 7 | 0 | 13 | 40 |
| set-answering | 1 | 0 | 55 | 44 |
| one-unit | 2 | 0 | 87 | 11 |

The free-form column is the finding: seven samples that iteration 14 answered correctly were
answered wrongly, and not one of the samples the rule was aimed at was recovered. A sign test
on 7-0 gives p ~ 0.008, so this is not the +/-3-sample flap that the other two corpora show
(1-0 and 2-0 are within it). The claim the rule stated was true of the corpus - reference
formulas really do account for the material's heavy atoms - and stating it still cost the
run.

**Takeaway.** A rule that is *provably true of the answers* is not thereby safe to state:
7 of 20 correct free-form samples were lost to a sentence that only asked the solver to check
a necessary condition. The corollary is the useful one: on the free-form corpus the draft is
made in a single pass and any added constraint perturbs it, so the free-form loss has to be
attacked with something the solver reads *before* it commits, or not at all.

**Falsified as stated.** The declared falsifier "the repair turn pushes answers off drafts
that were right - visible as correct samples whose answer satisfies the accounting and still
changed" was the right worry but the wrong mechanism: the repair never ran, so the cost was
purely the prompt text. Future iterations that add prompt text should budget for this.
