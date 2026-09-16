# Iteration 3 — considered_unit_audit (post-eval)

**Result.** average 0.584 (iteration 2: 0.558). USPTO 0.283 (0.233), Symptom2Disease
0.890 (0.920), LawBench 0.580 (0.520). All 260 samples completed.

**What worked.** Treating the reference units as evidence rather than a closed list, and
forcing the check to run, moved the multi-unit task: LawBench 0.52 -> 0.58 and micro-F1
0.641 -> 0.705. The middleware fired (92 of 100 LawBench samples called `check_answer`,
against 53 in iteration 2), and the shape note started being read.

**What it cost.** Symptom2Disease slipped 0.92 -> 0.89 (3 samples, within noise for 50
questions, and no answer was changed by the check there).

**The check did not decide anything.** Draft and final answer agree in 96 of 100 LawBench
samples and 100 of 100 Symptom2Disease samples: of 41 wrong law drafts, 39 were resubmitted
unchanged and 2 changed to another wrong answer. Zero wrong drafts were repaired, zero
correct ones broken. The +0.06 on LawBench came from the prompt wording, not the audit.

**Why the audit is inert.**
- It ranks the candidates it re-opens by corpus frequency, so the three it puts back are
  the three most common units the model already rejected, not the one it dropped. One
  failure named `drug reaction`, left it out of `considered`, and was shown the evidence
  for `peptic ulcer disease`, `allergy` and `dengue` instead.
- Every re-opened unit was mentioned in the model's next message (10 of 10 law samples,
  6 of 6 symptom samples) and rejected anyway, usually on a convention prior ("the dataset
  labels this case with the broader charge") rather than a fact.
- The nudge itself grants permission to ignore the output ("change your answer only if the
  check gives you a factual reason to"), and the draft was already fixed in the message
  that called the check, so the check arrives after the decision, not before it.

**Where it still loses.** LawBench recall (0.680) trails precision (0.760) and no sample
over-predicts: 14 wrong answers are strict subsets, 8 partial, 20 share no unit. 82% of the
val charges never appear in the 200 training references and the top-20 retrieved answers
cover the gold in 26% of questions, so retrieval cannot repair the knowledge-side misses.
USPTO is unchanged by any of this: 32 of 43 failing samples share no component with the
target and only 3 of 66 missing components exist anywhere in the training answers.

**Takeaway.** Do not widen the candidate net again — widen what the check *says* and how it
ranks, or the score will not move. Two measured gaps to close: the re-opened units must be
chosen by evidence (how well this question matches the cases that answer them) instead of
by frequency, and the check must state the distinguishing element that separates a draft
unit from its attested relative, plus the fact that the answer is matched as an exact unit,
so a common broader unit stops looking like the safe choice.
