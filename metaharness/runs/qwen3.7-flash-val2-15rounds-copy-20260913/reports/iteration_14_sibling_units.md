# Iteration 14 — sibling_units (post-eval)

**Result: average 0.5944** (free-form 0.333, one-unit 0.890, set-answering 0.560) — the
highest of the fifteen runs so far, +0.027 over iteration 13's 0.5678. The gain is almost
entirely the free-form corpus (0.283 -> 0.333, 3 samples of 60) and it is the *only* run in
which that corpus has cleared 0.30 twice in a row.

**What changed.** Iteration 13's decision rules were removed and iteration 12's rendering
restored (system prompt and skill byte-identical to iteration 12 for every corpus); the two
mechanical repairs were kept (unreadable-final-answer resubmit, replacement rendering of the
written-out offer); and the check's two false claims about edge-sharing units were demoted
from defects to remarks about the relation between the names.

**Why it moved.** The comparison with iteration 13 is the cleanest available control: the
one-unit corpus's prompt, memory and check output were byte-identical between the two runs
and it still moved 0.910 -> 0.880 (iteration 13) -> 0.890, i.e. 1-2 samples of flap. The set
corpus moved 0.540 -> 0.560 (+2 samples) after losing the three-branch decision text and
gaining back the iteration-12 rules; the free-form corpus moved +3 samples after the false
"the references say it more specifically" note stopped firing (30 firings, of which 8 named a
unit the answer did not need, 14 changed a draft, 0 fixed one).

**Takeaway.** Both directions of the prompt experiments now agree: the two iterations that
*removed* asserted text gained (13 -> 14), and the two that *added* it lost (12 -> 13). The
remaining loss is not instruction-following. What pays is deleting a statement the check
makes that is not true of the corpus — the gain is small but it is the only channel that has
reproduced.

**Caveat for the next iteration.** The three corpora's sample counts (60/100/100) put one
standard error on the average at ~0.028, so 0.5944 is not distinguishable from 0.5678. The
flip counts above are the evidence, not the averages; the next iteration should be judged the
same way.
