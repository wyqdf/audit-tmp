# Iteration 2 — atomic_reference_units (post-eval)

**Result.** average 0.558 (iteration 1: 0.550), 258/260 ok (2 LawBench samples lost to an
unretryable `content_filter`). USPTO 0.233 (iter 1: 0.250), Symptom2Disease 0.920 (0.910),
LawBench 0.520 (0.495).

**What worked.** Separator validation did its job: `、` no longer cuts the inventory, and no
shipped label is a fragment of a reference answer any more (iteration 1 had
`用于骗取出口退税` as a label, iteration 2 does not).

**What it cost.** Almost all of the score still comes from the prompt-injected profile.
`check_answer` ran in 53 of 100 LawBench samples and 51 of those submitted a byte-identical
answer. The one answer it changed was `销售假冒注册商标的商品` (correct) rewritten to
`假冒注册商标` (wrong), because the tool listed `假冒注册商标` as the "closest reference
label" and told the solver to use the reference spelling.

**Where it still loses (LawBench, 48 wrong of 100).**
- 25 have a gold unit the inventory does not contain (46 % of val questions have one), and
  the solver names the right unit and drops it: 29 of the 48 name a missing gold unit in
  their own notes, 15 citing "not in the reference list". "Copy character for character" is
  being read as "the list is closed".
- 10 submit an inventory unit that is a head/tail extension of the gold one (`受贿` where
  `利用影响力受贿` was the answer); the check calls that "all units match".
- 16 under-predict against 9 over-predicts, and retrieval cannot repair it: among the 10
  closest references the union of their units covers the gold for 45 % of single-unit
  answers but 1 of 16 multi-unit ones.
- USPTO misses (33 of 46 share no component with the target, 1-NN over the 50 training
  references scores 0.000 exact) are chemistry the model does not have; Symptom2Disease is
  at 0.92 and all 8 wrong samples name the correct diagnosis before submitting another.

**Takeaway.** The remaining errors are decisions, not surfaces: the solver finds the right
unit and discards it, and the verification tool either stays silent or pushes it toward the
nearest listed unit. Re-open the dropped candidates with evidence, and stop the tool from
preferring a listed unit over a correct unlisted one.
