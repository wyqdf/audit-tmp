# Iteration 5 — act_ledger_audit (post-eval)

**Result.** average 0.559 (iteration 3: 0.584, iteration 4: 0.563). USPTO 0.217 (0.283 at
it3), Symptom2Disease 0.890 (0.890), LawBench 0.570 (0.580). One `call_budget` loss on
Symptom and one empty prediction.

**The design note's first falsifier fired.** No supersets appeared on the multi-unit task
(15 subsets, same as it3), but the generation task lost samples to over-decomposition:
USPTO wrong samples with *more* parts than the gold went 0 (it3) → 1 (it4) → 3 (it5), and
it3 → it5 broke 4 USPTO samples while fixing 0. `ex16` is the clean case: the product has
an aryl bromide and a benzylic bromide; it3 reasoned "the benzylic bromide is reverted to
a methyl, existing ring substituents remain unchanged" and kept the aryl bromide; it5's
ledger framing ("one entry for each separate act") made the model disconnect *both*
bromines and lose the sample.

**The ledger check certified the over-decomposed draft.** With coverage as the audit rule,
the tool answered "Ledger: all 3 entries have a unit in the draft" for that wrong answer —
it is one-sided, so a draft that invents an extra act passes. Iteration 3's check had at
least the shape line ("36% of references have fewer parts than yours") pushing the other
way; iteration 5 removed that pressure and kept only the upward one.

**Where the loss is.** Not in the audit's steering: at it3 the check changed 2 of 100
LawBench samples (both to another wrong answer) and repaired 0. Off-line over it3's wrong
samples: 50 missing charges, 25 present in the training vocabulary, only 6 in the 20
references shown for that question — retrieval cannot supply them, and a 1-NN over the
training questions scores 0.14 against the harness's 0.58. The residual is model knowledge
and label noise (e.g. one val case whose facts describe a single fight but whose gold lists
three unrelated charges).

**Takeaway.** Adding machinery has now cost score in two consecutive iterations (it4
-0.021, it5 -0.025 against it3) while the two measured positive moves were prompt wording
and the profile, not the audit. Mandate for iteration 6: remove the steering, keep the
attestation, and make a clean check *affirm* the draft instead of doubting it.
