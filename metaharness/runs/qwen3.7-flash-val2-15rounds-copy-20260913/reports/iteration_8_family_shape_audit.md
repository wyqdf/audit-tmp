# Iteration 8 — family_shape_audit (post-eval)

**Change.** A question type became the complete opening sentence several references share, looked
up anywhere in the text the memory receives; the pre-submit check reports the answer count of that
type as a defect; the verdict follows the report (a draft is affirmed only when the report has
nothing in it); the relation note was narrowed to a piece of an attested unit, a beginning of one,
and a short inflection.

**Result.** 0.550 (USPTO 0.20, Symptom2Disease 0.86, LawBench 0.59) against 0.573 for iteration 7,
0.561 for iteration 6 and 0.584 for the best run (iteration 3). LawBench reached its best measured
accuracy and its best F1 (0.693; P 0.717 / R 0.671 over 100 samples) — the first time the
multi-unit task has held a gain for two runs.

**What the run showed.**
- The verdict change is the part that worked. LawBench is the only task where the check still
  speaks (22 of 100 samples reported something), it is the only task where a draft moved for a
  metric reason (draft 0.570 -> final 0.590; 2 samples repaired, 0 broken), and it is the task that
  gained. Symptom2Disease was affirmed on 100 of 100 checks and USPTO on 58 of 60 with 0 drafts
  changed, so their moves (0.90 -> 0.86, 0.25 -> 0.20) are generation noise (USPTO also lost one
  sample to a network timeout), not effects of the change.
- The type-count defect did not bite: only 2 USPTO drafts were ever flagged, both kept.
- Across 780 replayed samples (iterations 3, 7, 8) the whole check apparatus repaired 3 samples and
  broke 0. The channel is real but tiny, and no further wording of it can pay for an iteration.

**Takeaway.** Report consistency is worth keeping; check tuning is exhausted. The score is set by
what the solver reads before it decides — it answers in one turn from the guide and almost never
queries the memory (0.95-1.4 tool calls per sample, retrieval in <10%). Iteration 9 spends its
change on the retrieval that builds that guide, not on the check.
