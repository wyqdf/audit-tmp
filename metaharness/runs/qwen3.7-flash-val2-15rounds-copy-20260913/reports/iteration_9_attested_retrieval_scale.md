# Iteration 9 — attested_retrieval_scale (post-eval)

**Result.** average 0.557 (iteration 8: 0.550, iteration 3: 0.584). USPTO 0.250 (0.203),
Symptom2Disease 0.850 (0.860), LawBench 0.576 (0.590). 259 of 260 samples completed (one
`content_filter` on LawBench; nothing lost to `call_budget` or timeout). Paired per sample
against iteration 8: LawBench -1, Symptom2Disease -0.5, USPTO +1.5 — a wash.

**The design note's first falsifier fired.** The multi-unit task did not exceed 0.59 (0.576),
so better-covered evidence did not convert into predictions.

**The tuning did what it claimed.** Replaying the selector over that task's 50 validation
questions: the shown set carries 0.470 of the gold units at the parent's 4-character features
and 0.570 at the chosen 2, and every gold unit is visible for 23 questions against 17. The
profile, the references shown and the check were untouched.

**Why coverage did not become score.** Cross-tabulating gold-unit visibility against outcome
(shown&right / shown&wrong / unshown&right / unshown&wrong): iteration 3 was 20/2/38/40 and
iteration 9 is 27/3/30/40. The 8 questions that gained coverage were already answered right
without it; `unshown&wrong` did not move. Coverage is not the binding constraint on the
questions that fail: for 21 of the 50, the gold units appear nowhere in the 200 training
references, so no selector can reach them. P(right | gold units visible) is 0.90 under every
candidate since iteration 3, and the score is decided by those 21 questions.

**Takeaway.** Stop tuning the retriever; the residue is on questions the corpus cannot answer
and coverage gains land on questions already solved. The one regression still standing across
iterations 3-9 is the single-label task, which paired comparisons put 1.5-3.5 samples (of 100)
below its iteration-1/2 level under every candidate since iteration 3, with the same sign in
all seven comparisons, while those candidates gained 2-5 samples on the multi-unit task.
