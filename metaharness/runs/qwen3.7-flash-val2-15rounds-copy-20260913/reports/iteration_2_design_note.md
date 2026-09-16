# Iteration 2 — atomic_reference_units (design note, pre-eval)

**Change.** Separators are now *validated* before they are allowed to cut answers.

1. `piece_attestation(targets, sep)` = share of a separator's pieces that also occur as
   complete reference answers. `derive_separators` keeps a separator as a **label
   separator** only when its attestation is at least `max(0.15, 0.4 × best)`; the rest are
   **inner punctuation** (they occur inside answers but never join stand-alone units).
   On the observed training sets this keeps `;` (0.33 attestation) and rejects `、` (0.00),
   which previously fragmented charge names.
2. The label inventory is cut with the label separators only, so an inventory entry is
   always a whole reference answer or a validated unit — never a fragment. Answer shape
   ("1 part in 68 %, 2 parts in 29 %") is reported from the shape separators, which fall
   back to the most frequent candidate when nothing is attested, so free-form tasks keep
   their part structure.
3. The profile names the inner punctuation explicitly ("`、` appears inside 30 % of the
   reference answers but never separates units that stand alone … the labels below already
   contain it where it applies"), so the solver is told *why* a label must not be split.
4. `check_answer` now splits the draft into shape parts and label units separately and
   reports three new, deterministic label faults: a draft unit that is a fragment of a
   longer reference label (with that label), a reference label with characters added, and
   word-boundary matching so partial words (`flu` in `reflux`) are not false positives.
5. Each question type also reports its answer-length spread (`1 unit in 60 %, 2 units in
   40 %`), and the system prompt makes the `check_answer` pass mandatory.

**Hypothesis.** Validating separators by piece attestation instead of raw frequency, and
building the label inventory only from validated units, removes fragment labels from the
profile; the solver then answers with whole reference units, which raises mean validation
accuracy above the 0.550 of iteration 1, mainly by converting label truncations into exact
matches, without regressing the tasks that have no label vocabulary.

**Falsifiers to look for in the results.**
- If the label task does not improve, the fragments were not what the model was copying,
  and the remaining errors are label-choice errors that need a different mechanism.
- If it regresses, the inner-punctuation note is being read as "never emit that
  character", or dropping a separator from the shape split mis-states the answer length.
- If a task with a genuinely free-form answer loses part-count guidance, the fallback to
  the most frequent candidate separator is not enough and shape needs its own evidence.
