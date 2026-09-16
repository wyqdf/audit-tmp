# Iteration 6 — settled_draft_audit (design note, pre-eval)

**Where iterations 4-5 left the loss.** Two measured facts set the direction.

1. *Extending the audit has cost score twice.* it3 0.584 → it4 0.563 → it5 0.559. The
   causes are in the traces, not in the aggregate: it4's symmetric relation notes made one
   sample flip 16 times and lose the call budget; it5's act ledger made the generation task
   disconnect substituents the it3 run had kept (`USPTO ex16`: it3 "the benzylic bromide is
   reverted to a methyl, existing ring substituents remain unchanged" → correct; it5
   "we disconnect the added bromine atoms: the aryl bromide is reverted to a C-H bond" →
   wrong), and its coverage-only check *certified* that wrong draft ("Ledger: all 3 entries
   have a unit in the draft"). Over-predicting samples went 0 → 1 → 3.
2. *The audit never repaired anything.* Replayed over it3's own predictions, the check
   changed 2 of 100 LawBench samples and both went from one wrong answer to another. The
   single-answer task lost 3 samples exactly when the "name every candidate you could
   support / re-open what you set aside" wording arrived (0.92 at it2 → 0.89 from it3 on),
   and its traces show why: the check listed the rejected diagnoses with reference cases
   that answer them, and the model had to re-argue a choice it had already got right.

**Change.** The audit keeps only what is mechanical, and says so out loud.

1. **The check no longer re-opens anything.** `_considered_audit`, `mentioned_units`,
   `_audit_rank`, `evidence`, `_excerpt`, `piece_units` and the narrower/broader relation
   notes are gone, and `considered` is now an inert optional argument (still accepted, so a
   call that passes it cannot error). What remains: missing markup, unbalanced structure,
   the shape line as information, a draft unit that is a piece of an attested unit, and a
   near-miss spelling.
2. **A clean draft is affirmed.** "No surface problem found … work through the points
   below" is replaced by "The draft checks out … Verdict: submit this draft unchanged",
   and the middleware nudge says the same. This is the new mechanism: the forced check
   used to arrive as a list of doubts even when it had nothing, which is exactly the turn
   where a correct answer gets re-decided.
3. **The prompt stops demanding an enumeration.** "Name every unit the question could
   support before you choose" becomes "decide from the facts, then render"; the skill's
   step 4 becomes "decide once", keeping the rules that carried it3 (a unit may be set
   aside only for a factual reason; an unlisted unit is not a reason to change it).
4. **Required markup is told apart from data.** `_required_markup` now keeps only tags the
   question *states* (used twice, as a format instruction is, plus closing forms). Before,
   any bracketed token counted, so a SMILES atom like `[N+]` was reported as missing markup.

**Hypothesis.** Auditing only mechanical defects and affirming a draft that has none raises
the mean validation score above the 0.584 of iteration 3 - recovering the single-answer
samples that the candidate-enumeration wording cost (0.89 → 0.92) and the generation samples
that it4/it5's relation steering and over-decomposition cost (USPTO 0.217 → 0.283) - without
losing the multi-unit gain (LawBench 0.57 → 0.58), since no iteration measured the re-open
channel repairing a sample.

**Falsifiers to look for in the results.**
- Symptom2Disease stays at 0.89: the enumeration wording was not what moved it and the
  single-answer task is at its ceiling, not suppressed by the check.
- LawBench falls: the permissive vocabulary wording was doing work through the re-open
  channel after all, and that channel should be restored rather than dropped.
- USPTO does not recover: it3's 0.283 was itself variance across 30 questions, and only
  `call_budget`/over-prediction changes are real.
- Fewer than 90 of 100 law samples call `check_answer`: the affirmative wording reads as
  "nothing to check", the middleware is the only thing running it, and the check is inert.
