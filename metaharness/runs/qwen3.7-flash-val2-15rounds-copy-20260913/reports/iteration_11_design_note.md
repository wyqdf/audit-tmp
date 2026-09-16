# Iteration 11 — cardinality_branch (design note, pre-eval)

**Where iteration 10 left the loss.** Three measured facts, all from the recorded runs.

1. *The score is decided before the check.* Replaying the recorded drafts, the first answer
   the solver offers scores 0.880 on the single-label task and 0.541 on the multi-unit one;
   the whole check apparatus moves those to 0.890 and 0.582 — five samples repaired, none
   broken, over the 198 samples that recorded a draft. Anything that only edits the check
   cannot pay.
2. *Multi-view and view-fusion are dead ends.* The two samples of a question agree 45-49
   times out of 50 (same prompt, temperature 0), so there is no second opinion to vote with;
   and pairing the predictions of *different* candidates as two genuine views gives an oracle
   of at most +1-2 questions over the best single view, while union and intersection both do
   worse than the single best. Measured and discarded, not assumed.
3. *The single-unit corpus is the one whose framing is wrong.* Every candidate since
   iteration 3 opens the decision with "name every answer unit the question could support and
   set a unit aside only for a factual reason" and closes it with "a missing unit and an extra
   unit both count as wrong". That is written for answers that carry several units. On the
   single-label corpus the answer is always exactly one unit — and its 11 wrong samples are
   substitutions *between listed units*, i.e. errors of choice, not of coverage. The two
   candidates that measured highest there (0.91, 0.92) predate the unit framing entirely.
   Iteration 10 tested the vocabulary half of that framing; the cardinality half was never
   tested.

**Change.** The harness derives the answer count from the references and lets the decision
step follow it.

1. `build_profile` measures the share of reference answers that are a single unit and sets
   `single_unit` when that share is at least 0.98 (over at least 10 references). The two
   corpora need opposite habits: where answers are always one unit, a second unit is a
   *different* answer rather than a more complete one; where answers carry several, dropping
   an element loses the answer the same way adding one does.
2. The system prompt gains the rule the profile measured: one-unit corpora are told the
   answer is the single unit the facts establish and that a two-unit draft is wrong even when
   one of them is right; several-unit corpora keep iteration 3's wording word for word.
3. The skill's decision step (step 4) and its closing re-open instruction follow the same
   flag: on a one-unit corpus the solver decides between candidates — the candidate that
   explains the facts the other cannot is the answer, a fact its choice leaves out is covered
   by *replacing* the unit, never by appending a second one — and a re-opened candidate can
   only enter the answer in place of the draft's unit.
4. The check calls a draft that carries more than one unit a *defect* on a one-unit corpus
   (it reads the units the draft contains, since such a corpus often joins nothing), stops
   offering the "more parts than yours - check whether an applicable part was left out"
   remark there, and states the one-unit consequence of the shape line in the profile.

**Measured separation (training only).** The single-unit share is 1.00 / 0.685 / 0.36 and
the flag is on / off / off on the three corpora. On the two off corpora the system prompt,
the rendered skill, the guide and the check output are byte-identical to iteration 3's —
verified by re-rendering both and by replaying 169 recorded `check_answer` calls, 0 of which
differ. So any movement on those tasks is the noise floor, and the single-unit task is the
only one under test.

**Hypothesis.** Deriving whether the references answer with one unit or several, and making
the system prompt, the decision step and the check follow that derivation, raises the mean
above iteration 3's 0.584 and iteration 10's 0.573, mainly by returning the single-unit task
to its iteration-1/2 level of 0.91-0.92 — its wrong answers are choices between listed units,
and the one-unit branch tells the solver to make that choice — without moving the multi-unit
and free-form tasks, whose prompts and checks are unchanged bytes.

**Falsifiers to look for in the results.**
- The single-unit task stays at or below 0.89: the decision framing was not what the paired
  gap was either, and the plateau is the model's ceiling rather than the prompt's.
- The single-unit task falls below 0.83: telling the solver a second unit is always wrong
  makes it discard a unit the facts do establish, i.e. it converts substitutions into misses.
- The new defect fires often on the single-unit task without a score move: the solver is
  carrying several units into its draft and the flag is not stopping it.
- The multi-unit or free-form task moves outside its own flapping (0.54-0.60 and 0.20-0.28):
  the branch leaked into a corpus it should not touch, and the byte-identity check was wrong.
