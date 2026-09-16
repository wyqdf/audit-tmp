# Iteration 10 — answer_space_closure (post-eval)

**Result.** average 0.573 (iteration 9: 0.557, iteration 3 best: 0.584). USPTO 0.250 (0.250),
Symptom2Disease 0.890 (0.850), LawBench 0.580 (0.576). 259 of 260 samples completed (one
`content_filter` on the multi-unit task; nothing lost to `call_budget` or timeout).

**The design note's first falsifier fired.** The single-label task stayed at 0.890, not the
0.92 its reference rule was supposed to return, so the vocabulary framing was not what the
paired gap since iteration 3 was.

**What the run measured.**
- Paired per question against iteration 9: Symptom2Disease +4, LawBench +0.5, USPTO 0 — the
  single-label move is inside the run-to-run spread of that task (0.85-0.92 across the last
  five candidates) and matches the iteration-8/10 level exactly.
- The closed branch was byte-identical in its effect on the other two corpora: replaying the
  recorded drafts, the system prompt, profile paragraph and check output are unchanged for
  them, so their flat result is the noise floor, not a regression.
- The unlisted-unit licence was not the mechanism: across every candidate from iteration 3
  on, the single-label task's wrong answers are *substitutions between listed units*
  (11 samples: pneumonia/bronchial asthma, malaria/dengue, common cold/chicken pox,
  asthma/allergy), never answers outside the label set. Closing the vocabulary cannot reach
  an error that is already inside it.
- The pre-check draft is where the score is decided: measured over the recorded
  conversations, the draft the solver first offers scores 0.880 on the single-label task and
  0.541 on the multi-unit one; the whole check apparatus moves those to 0.890/0.582. Every
  real lever is in what the solver reads before it decides.

**Takeaway.** Vocabulary licensing is exhausted as an axis on this corpus family, and so is
the check channel (measured, not assumed). What remains untouched is the *decision
procedure*: every candidate since iteration 3 tells the solver to name every unit a question
could support and to set a unit aside only for a factual reason — an instruction written for
answers that carry several units. On the single-label task that framing is wrong, and the two
candidates that measured highest there (0.91, 0.92 at iterations 1-2) predate it. Iteration 11
derives the answer count from the references and lets the decision step follow it.
