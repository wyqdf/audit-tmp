# Iteration 6 — settled_draft_audit (post-eval)

**Result.** average 0.561 (iteration 3: 0.584). USPTO 0.283 (0.283), Symptom2Disease 0.860
(0.890), LawBench 0.540 (0.580). All 260 samples completed, no `call_budget` loss.
Per sample against iteration 3: USPTO +3/-3, Symptom2Disease +2/-5, LawBench +1/-5.

**The design note's second falsifier fired.** LawBench fell 0.58 -> 0.54 although the check
had been reduced to mechanical defects. The mechanism cannot be the mechanical check: on
LawBench it ran 116 times over 100 samples and said "checks out" in 100 of them, fired the
piece note 3 times, and found no near-miss spelling, no missing markup and no unbalanced
structure at all. What the iteration also changed was the *decision wording* - "name every
unit the question could support" became "decide from the facts, then render", and the skill's
step became "decide once". LawBench is exactly the task whose gain at iteration 3 was
attributed to that wording, so removing it is the likely cause of the loss.

**The first falsifier fired too.** Symptom2Disease did not return to 0.92; it fell to 0.86
(5 samples lost, 2 won). That task is at its ceiling: its 4 hard examples are wrong under
every candidate, the gold diagnosis is among the 20 references shown in every sample that
flaps (0, 4, 13, 30, 31, 36), and the flips are model-uncertainty pairs (pneumonia/bronchial
asthma, malaria/dengue). Neither the check nor its absence moves it.

**USPTO held its best value (0.283).** The it3 -> it6 flips there are 3 fixed / 3 broken, all
on examples that have flapped under every candidate since iteration 1; the 18 examples no
candidate has ever solved stayed unsolved.

**Takeaway for iteration 7.** The mechanical check is silent, so there is nothing left to
remove from it, and the decision wording is what moves the multi-unit task. Keep the wording;
if the check is to say anything, it must be a fact about how the references *render* the
units the draft already uses - never an alternative to the decision.
