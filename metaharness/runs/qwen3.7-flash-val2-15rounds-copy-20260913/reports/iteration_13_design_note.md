# Iteration 13 — fact_ruled_set (design note, pre-eval)

**Where iteration 12 left the loss.** Replayed over its own recorded run, not over the score.

1. *The pre-submit channel is spent.* It changes the submitted answer on 2 of 260 samples. On
   the corpus that answers with a set of units there are 122 written-out offers and 3 are
   exactly the target; carrying every candidate the solver named and dropped would fix 2 of
   the 44 wrong samples.
2. *The loss is generated on the first call.* 44 of 101 samples there are wrong, 29 of them by
   a missing unit plus a wrongly spelled one and 14 by a missing unit alone; none by an extra
   unit. Adding the units those answers were missing would fix 15 of the 44. The solver names
   the missing unit in only 12 of the 61 units it misses, so every channel keyed to its own
   candidate list has nothing to carry.
3. *The unit is not hidden from it.* 37 of the 61 missing units appear in the material the
   prompt already carries (the vocabulary list and the reference cases shown), and 20 appear
   in the solver's own reasoning, where
   they are ruled out by reasons about the *law*: "属于开设赌场的典型行为，不再单独评价为赌博罪"
   (the conduct is fully evaluated by the other unit), "特别法优于一般法" (the other unit is
   the more specific one). The corpus does not count offences that way - it answers with every
   unit its judgment establishes - which is why those reasons are the ones to name.
4. *Retrieval cannot name them either*, and this iteration did not re-litigate it: units that
   co-occur in the training answers recover 0 of the 61 (and fire on 8 of 57 correct samples);
   the markers that separate acts in a judgment's text ("（一）", "1.", "另查明") carry no
   signal (3 multi-unit golds against 2 single-unit ones among the marked questions); and none
   of the 61 appears verbatim in the question.
5. *Two mechanical losses.* The check's written-out offer joins a draft unit with the candidate
   it is a variant of, so the offer carries the same unit twice and is refused (recorded, and
   the unit lost with it). And one answer was submitted as a JSON string that was never closed,
   so a checked answer scored as empty.

**Change.** One derived branch, one decision rule, two repairs.

1. **A third branch.** The profile already measures `single_unit` (all reference answers are one
   unit) and `label_like` (the answers are drawn from a vocabulary). Together they separate the
   three corpora this experiment runs: one-unit (the answer is a *choice*), several-units-from-a-
   vocabulary (the answer is a *set*), and free-form (no vocabulary rules apply). Rendering was
   verified by replay: for the one-unit and free-form branches the system prompt and the skill
   are byte-identical to iteration 12's.
2. **On the set branch, a unit is set aside only by a quoted fact.** The decision step now says
   a unit that cannot be ruled out with a fact of the question belongs to the answer, and names
   the reasons that do not rule one out, including the two the traces actually use: another unit
   covering the same conduct, and that unit being the more specific one. The same list is added
   to the check's defect line, so the decision step, the skill and the check say one thing.
3. **The offer is a replacement when the draft's unit is the candidate spelled otherwise**
   (contains it, extends it, or extends one of its elements with attached text), instead of a
   join that carries the unit twice. Sharing a head or a tail is *not* enough - the vocabulary
   is full of units that share one and are different units - and replaying all 273 recorded
   check calls, this changes the offer on 5 calls (2 samples, all of them the intended case:
   the offer becomes the replacement and the target's offer count over the run rises 3 -> 5)
   and drops the request on 2 calls where the draft already carries the whole unit.
4. **A turn with no readable `final_answer` gets one repair turn**, read with the same
   acceptance rule the benchmark uses (verified: on all 260 recorded final turns the guard
   agrees with that extraction, and fires on exactly the one that scored empty).

**Measured separation (training only).** Nothing in the memory changes: the derivation is
untouched, and rebuilding the profile from the stored references still measures the same
branch per corpus. The check-side edits were replayed over every recorded `check_answer` call
(273 calls: 0 exceptions, 0 changes outside the intended class).

**Hypothesis.** Making the decision step rule candidates out only by a quoted fact of the
question - and repairing the two mechanical losses - converts more of the 15 samples that a
missing unit alone makes wrong than the 2 the candidate channel could reach, so the set-answering
corpus rises above its 0.54-0.59 band, while the one-unit corpus stays in 0.85-0.92 and the
free-form corpus in 0.20-0.30, whose prompts are byte-identical to iteration 12's.

**Falsifiers to look for in the results.**
- The set-answering corpus stays in band: the solver's reasons are its legal knowledge, not
  its instructions, and the next lever is not the wording of the decision step.
- It falls below 0.52: the rule admits units no fact establishes - visible as new *superset*
  errors, which the corpus has none of today (0 of 44 wrong samples).
- The one-unit corpus falls below 0.85: the "quoted fact" rule leaks into the choice branch,
  where a second unit is a different answer rather than a more complete one.
- The free-form corpus moves at all: the branch scoping is wrong, since its prompt and check
  output are unchanged.
- Fewer than 90 of 100 samples on the set-answering corpus call `check_answer`: the longer
  decision step reads as an answer in itself and the check stops being visited.
