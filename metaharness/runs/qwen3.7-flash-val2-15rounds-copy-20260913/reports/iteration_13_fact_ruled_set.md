# Iteration 13 — fact_ruled_set (post-eval)

**Result.** average 0.5678 (iteration 12: 0.5933; best so far 0.5933). USPTO 0.283 (0.300),
Symptom2Disease 0.880 (0.910), LawBench 0.540 (0.570). All 260 samples completed, so the
drop is a result and not a completion artifact — but it is three samples on the one-unit
corpus and two on the set corpus, i.e. inside the per-task band every candidate since
iteration 3 has lived in (0.85-0.92 / 0.54-0.59 / 0.20-0.30).

**What the run says about the change.** The iteration changed four things; replaying the
recorded 260 samples separates them.
- *The set-branch decision rule ("a unit is set aside only by a quoted fact") did not
  convert.* 120 candidate lines were written over the run; 8 named a unit the target
  contains (7%) and 2 were carried into the final answer. The same channel in iteration 12
  was 117/8/1. Making the line a defect rather than a remark moved nothing.
- *The loss it was aimed at is not reachable from the draft's own candidates.* Of the 61
  missing units on the set corpus, 33 are not in the training vocabulary at all (the
  corpus names charges the 200 references never use), and on 25 of the 43 wrong samples the
  check named nothing and the solver's notes never mentioned the missing unit. Only 3 of
  the 61 appear verbatim in the question. A channel keyed to what the solver named cannot
  reach a unit it never considered.
- *The one-unit corpus moved 0.91 -> 0.88 with a byte-identical prompt and check* (the
  branch splits on `single_unit`, and that branch was untouched), which is the cleanest
  noise measurement in the experiment: 3 samples on 100.
- *The two mechanical repairs are separable and sound.* The unreadable-final-answer repair
  fires on 0-2 final turns per run of this harness family (in iteration 12's run one of
  them was the sample that scored empty). Replaying iteration 12's set-corpus calls through
  both libraries, the replacement rendering changes the written-out line on 5 of 110 calls
  (e.g. an offer of 'X;X、Y' - the same unit twice, refused and the unit lost - becomes the
  replacement 'X、Y'), and drops 2 requests the draft already answers.

**Takeaway.** Writing more rules into the decision step does not move a corpus whose loss
is unseen vocabulary; the check's advice is already as complete as its inputs allow. Keep
the two mechanical repairs, restore the iteration-12 rendering, and stop spending the
iteration on the wording of the decision step.
