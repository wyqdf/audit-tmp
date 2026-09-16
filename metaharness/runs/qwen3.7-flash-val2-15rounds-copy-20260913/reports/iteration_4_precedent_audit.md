# Iteration 4 — precedent_audit (post-eval)

**Result.** average 0.563 (iteration 3: 0.584). LawBench 0.550 (0.580), Symptom2Disease
0.890 (0.890), USPTO 0.250 (0.283). One LawBench sample lost to `call_budget`.

**The design note's first falsifier fired.** Recall did not rise (0.653 vs 0.680) and
precision fell (0.733 vs 0.760). Per-sample against iteration 3: LawBench 4 broken /
1 fixed, USPTO 4 / 2, Symptom2Disease 1 / 1 — the audit is net-negative, not inert.

**The check ran everywhere and decided again nothing.** 136 `check_answer` calls over
100 LawBench samples, 0 samples without one. 41 of 45 wrong samples resubmitted the
draft the check had just questioned.

**New pathology: the check oscillates.** `ex43 s1` called `check_answer` 16 times
alternating `受贿` and `非国家工作人员受贿`: the specificity note fires in *both*
directions ("so are the units that say it more specifically" on the short unit, "adds
an element … never used by the references" on the long one), so a model that obeys the
tool flips forever and burns the 32-call budget. The sample is lost and ~1M input
tokens are spent on one question.

**Why re-opening cannot repair this task.** Unit-level on LawBench: 16 strict subsets,
0 supersets. 58 samples have multi-unit gold and only 23 are correct (single-unit gold
32/42). Of the 45 wrong samples only 15 ever name the missing gold unit in
`considered`; the other 30 never name it at all, so there is nothing for the audit to
re-open. Traces show the decision is *comparative*, not miss-and-forget: `ex0009`
reasons that `赌博` and `开设赌场` are two names for the same conduct and keeps the
more specific one, and `ex0014` cites the profile's own shape line ("通常为1个部分")
to justify answering with one element of `窝藏、包庇`.

**Takeaway.** The re-open channel is exhausted (two iterations, two rankings, no
repair). Move the change upstream: generate the candidate set from the *facts* (one
answer unit per distinct act the question establishes) instead of choosing among
units the vocabulary suggests, stop the corpus shape statistic from reading as a
target, and make the check idempotent so it cannot oscillate.
