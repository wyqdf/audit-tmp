# Iteration 10 — answer_space_closure (design note, pre-eval)

**Where iteration 9 left the loss.** Four measured facts set the direction.

1. *The retriever is finished as a lever.* Tuning the feature size raised the gold-unit
   coverage of the shown set (0.470 -> 0.570 at the same 20 references) and moved no score,
   because the questions that gained coverage were already answered right: of the single-label
   task's 100 samples, `shown&right` went 20 -> 27 while `unshown&wrong` stayed at 40. For 21 of
   the 50 multi-unit validation questions the gold units appear nowhere in the 200 training
   references, so no selector can reach them. P(right | gold units visible) has been 0.90 under
   every candidate since iteration 3.

2. *One regression has stood since iteration 3 and survived every attempt to explain it away.*
   Paired per example against the two iterations before it, every candidate from iteration 3
   onward sits 1.5-3.5 samples (of 100) *below* the iteration-1/2 level on the single-label
   task — seven comparisons, same sign — while gaining 2-5 samples on the multi-unit task.
   Iterations 6 and 7 tried to recover it by touching the check and did not.

3. *What changed between those iterations is what the harness says about the vocabulary.*
   Iteration 2: "Reference labels (copy character for character; never add, remove, reorder or
   re-word characters ... never shorten a label to one of its fragments)." Iteration 3 replaced
   that with "this is evidence about vocabulary, not a closed list: a correct unit may be
   missing from it. When the facts call for a unit that is not here, write that unit yourself",
   and the system prompt with "set a unit aside only for a factual reason: being absent from the
   reference vocabulary is not one".

4. *That instruction is false on the single-label corpus, and it is the one thing no iteration
   measured.* 100% of its reference answers are built only out of units used more than once, in
   a 22-unit inventory over 200 references, and all 50 validation golds are a training answer
   verbatim. On the multi-unit corpus the same sentence is true (57% of answers reuse their
   units, 151 units, 137 of 200 answers carry a single one) and is where iteration 3's gain came
   from. One sentence, true of one corpus and false of the other.

**Change.** The harness derives which of the two the references are, and every place that
speaks about the units follows the derivation.

1. `build_profile` computes `reused_share`: the share of reference answers built only out of
   units the references use more than once. `closed_vocabulary` holds when the inventory is
   label-like and that share is at least 0.9.
2. The profile paragraph states the measured fact and its consequence in the closed branch
   ("the answer is one of them ... a unit that is not here is not a unit this task's answers are
   built from"); the open branch keeps iteration 9's paragraph word for word.
3. The system prompt's vocabulary rule follows the same flag: the closed branch drops the
   licence to answer outside the list and states the answer is one of the profile's set.
4. Skill step 3 stops asserting either reading and defers to the profile's statement.
5. The check calls an unlisted unit a defect on a closed corpus (it is not one of the answers
   the task accepts) and its notes are otherwise unchanged; on an open corpus its output is
   untouched.

**Measured separation (training only).** `reused_share` is 1.00 / 0.57 / 0.00 and the flag is
closed / open / open on the three corpora. On the two open corpora the system prompt, the
profile text and the check output are byte-identical to iteration 9's (verified over the 100
recorded drafts), so a move there is a move in the solver, not in the prompt.

**Hypothesis.** Deriving from the training references whether the units they use are the answer
space of the task or a sample of it, and making the profile, the system prompt, the skill and
the check follow that derivation, raises the mean above iteration 3's 0.584 and iteration 9's
0.557, mainly by returning the single-label task from 0.85 to its iteration-2 level of 0.92 —
its failures are substitutions between *listed* units and its corpus provably closes — without
moving the multi-unit and free-form tasks, whose prompts and checks are unchanged bytes.

**Falsifiers to look for in the results.**
- The single-label task stays at or below 0.89: the framing is not what the paired gap was,
  and the search has to move to the solver's step budget instead.
- The multi-unit task moves by more than its own flapping (outside 0.54-0.60): a corpus at
  `reused_share` 0.57 was classified wrongly and the threshold has to rise.
- The single-label task falls below 0.83: closing the vocabulary makes the solver keep a listed
  unit the facts rule out, i.e. it converts substitutions instead of preventing them.
- `call_budget` or timeout losses appear: the longer profile paragraph is costing turns.
