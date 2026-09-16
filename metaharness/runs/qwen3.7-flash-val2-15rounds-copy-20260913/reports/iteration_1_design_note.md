# Iteration 1 — reference_profile (design note, pre-eval)

**Change.** Memory is no longer a flat dump of training pairs. `prepare_memory.py` now
derives, from the training references only:

1. **Answer shape** — the separators the reference answers actually use (a candidate
   separator counts only if it appears in ≥15 % of answers and splits them into >1.2
   parts on average), and the distribution of parts per answer.
2. **Reference vocabulary** — the answer parts with counts, plus whole reference
   answers that recur, emitted only when the answers look label-like (short median
   length and a bounded distinct count, or ≥50 % of part occurrences recurring).
   Free-form answer sets (long, all-distinct SMILES) get no label list.
3. **Question families** — question headers shared by several references, each with
   the answer parts that recur inside it.

The solver prompt is now `question + profile + closest references + skill`. References
are ranked by IDF-weighted character-n-gram cosine with an MMR diversity pass, family
members first; if the whole memory fits the budget it is quoted in full, ordered
family-first (no information is lost versus the baseline dump). Three tools replace
the single one: `retrieve_examples(query)`, `search_examples(keyword)` and
`check_answer(draft)`, which reports shape, required markup and any part that is not a
verbatim reference label together with its closest labels.

**Hypothesis.** Grounding answers in the training-derived profile (verbatim labels,
answer shape) plus ranked references and a pre-submit check raises the mean validation
score above the 0.428 baseline, mainly by removing surface-form label mismatches and
multi-part under-prediction, without regressing tasks that have no label vocabulary.

**Falsifiers to look for in the results.**
- If LawBench barely moves, the model saw the label list but ignored it, and the
  check-then-resubmit loop is the part that needs strengthening.
- If USPTO regresses, quoting the memory in family-first order is worse than the
  shuffled dump, and the profile's per-family recurring reagents are a harmful prior.
- If a task with a novel label (not in the reference vocabulary) is answered with a
  listed label instead, the "prefer the listed spelling" rule is too strong and needs
  to be scoped to near-matches only.
