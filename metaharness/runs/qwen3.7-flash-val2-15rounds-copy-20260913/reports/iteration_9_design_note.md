# Iteration 9 — attested_retrieval_scale (design note, pre-eval)

**Where iteration 8 left the loss.** Four measured facts set the direction.

1. *The check channel is inert, and every recent iteration has been spent on it.* Replaying the
   drafts the check saw against the gold: iteration 3 repaired 0 samples for a metric reason,
   iteration 7 repaired 1, iteration 8 repaired 2 (LawBench 0.570 -> 0.590, 0 broken) — 3 samples in
   780, while iterations 4-8 were all changes to that channel. In iteration 8, 258 of 260 samples
   submitted the draft unchanged (Symptom 100/100 and USPTO 58/60 checks affirmed).
2. *The solver answers in one turn from the guide.* Tool calls per sample are 0.95-1.4, retrieval
   in under 10% of samples (0 of 60 on the free-form task in iteration 8). The evidence the guide
   puts in front of it is the answer.
3. *The retrieval feature size was a hand-set constant.* Ranking is 4-character TF-IDF cosine.
   Measured on the training references themselves (nearest neighbour answers alike as often as
   this): legal corpus 0.183 at 4 characters against 0.300 at 2; the single-label corpus 0.795 at 4
   against 0.715 at 2; the free-form corpus flat (0.94-0.96 across sizes). A corpus whose units
   carry meaning in two characters was ranked with four-character features.
4. *What that costs is measurable in the guide.* Replaying the selector over the multi-unit task's
   50 validation questions: the shown set carries 0.483 of the gold units at 4 characters and 0.587
   at 2, and questions whose gold units are all shown rise from 0.380 to 0.480, at the same 20
   references and the same guide size (14 705 -> 14 567 characters). That task's residual error is
   under-prediction (14 samples missing units, 0 samples over-predicting), so evidence coverage
   there is the binding constraint.

**Change.** The references choose the retrieval feature size, instead of a constant choosing it.

1. `select_gram_size` ranks every training case against the rest for each candidate size (2, 3, 4,
   6) and asks whether the nearest case is one that *answers alike* — a shared answer unit when the
   profile is label-like, the question type the case states when the references come in types. The
   size that puts alike answers at the top of each other's lists wins.
2. The choice is self-supervised: it uses only training questions and answers, holds nothing out,
   and needs no held-out split.
3. A corpus that expresses no clear preference keeps the default: the best size has to beat the
   worst by 0.05 or nothing is tuned. On the two measured corpora that means the legal corpus moves
   to 2 characters and the other two keep 4, so the change fires only where the references asked
   for it.
4. The chosen size is stored in the memory as `gram_size`; `MemoryView` reads it and falls back to
   the constant when a memory predates the field. The profile, the references shown, the guide
   wording, the skill and the check are untouched.

**Hypothesis.** Letting the references choose the retrieval feature size by nearest-neighbour
answer agreement raises the mean validation score above iteration 8's 0.550 and iteration 3's 0.584,
mainly by putting more of the multi-unit task's gold units in front of the solver (replayed: shown
unit recall 0.483 -> 0.587, full coverage 0.380 -> 0.480, same 20 references, same guide size)
where the residual error is missing units, without changing the single-label and free-form tasks,
whose corpora keep the default size.

**Falsifiers to look for in the results.**
- The multi-unit task does not exceed 0.59: better-covered evidence does not convert into
  predictions, the residual is knowledge rather than retrieval, and retrieval work is finished.
- The single-label or free-form task moves by more than its own flapping: the preference threshold
  let the tuning fire on a corpus that had no preference, and it has to be raised.
- The multi-unit task's precision falls while recall rises: two-character features match surface
  phrasing and the shown precedents pull in units of the wrong case, so the size has to be chosen
  against answer-side agreement at more than the nearest neighbour.
- Preparation or per-question cost rises into `call_budget`/timeout losses: the tuning is too
  expensive at 60 probes and has to be sampled harder.
