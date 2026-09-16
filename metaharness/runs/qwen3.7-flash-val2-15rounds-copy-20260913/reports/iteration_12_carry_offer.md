# Iteration 12 — carry_offer (post-eval)

**Result.** average 0.593 (iteration 11: 0.581; best before it: 0.584). USPTO 0.300 (0.283),
Symptom2Disease 0.910 (0.900), LawBench 0.570 (0.560). 260 of 260 samples completed.

**The move is one sample per task, and nothing in the run separates it from noise.** Paired
against iteration 11 that is +1/+1/+1 with no task outside its own band (USPTO 0.20-0.30,
Symptom2Disease 0.85-0.92, LawBench 0.54-0.59). The design note's falsifiers did not fire
either way: no task fell below its band, so the defect framing carried no excluded candidate,
and the multi-unit task did not rise, so the channel did not convert.

**What replaying the run measures about that channel — the check is nearly inert.**
- Over the 260 samples, the pre-submit check changes the answer it was given on **2 samples**
  (one on USPTO, one on LawBench) and breaks none.
- Over the 110 LawBench check calls there are **122 written-out offers; 3 are exactly the
  target** (they were offered before this iteration too). Carrying every named-but-dropped
  candidate would fix **2 of the 44 wrong samples** — the retention channel's ceiling.
- Adding the units those answers were missing would fix **15 of 44** — but the solver named
  the missing unit in only **12 of 61** cases, so that channel has nothing to act on: the loss
  is generated on the first call, before any draft exists to defend.

**Two mechanical defects the run exposes.** (1) The written-out form joins a draft unit with
the candidate it is a *variant* of ("X罪" + the reference unit X、Y offered as "X罪;X、Y"),
an answer that carries the same unit twice; the offer was refused and the unit lost.
(2) One USPTO sample submitted a JSON string that was never closed; the answer it had already
checked twice read as empty and scored zero.

**Takeaway.** Extending what the check says is exhausted — it can only act on units the solver
already named, and it names almost none of what it is missing. Iteration 13 moves the rule to
the decision step (a unit may only be set aside by a *quoted fact*, not by how offences are
counted), scopes it to the corpus shape that has this loss, and repairs the two renderings.
