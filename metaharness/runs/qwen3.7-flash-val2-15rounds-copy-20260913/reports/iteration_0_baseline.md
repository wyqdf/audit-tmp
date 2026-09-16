# Iteration 0 — baseline (post-eval)

**What it is.** One `retrieve_examples` tool that returns training Q/A pairs, shuffled
with a hash seed, truncated at 30 000 chars; a four-line skill that says "match the
examples"; answers wrapped in JSON by an answer guard. Memory stores the full loader
prompt per example.

**Result.** average 0.428 (USPTO 0.183, Symptom2Disease 0.830, LawBench 0.270),
260/260 samples ok, no partial runs.

**Where it lost.**
- LawBench: 19 of 100 samples are *only* wrong on label surface form — the prediction
  is right except for a trailing character the references never use (e.g.
  `单位行贿罪` vs `单位行贿`). Stripping it would move the task from 0.27 to 0.46.
  58 % of samples need several labels and only 13.8 % of those exact-match (27 %
  partial F1), so multi-part recall is the second failure mode.
- USPTO: 0.183 exact / 0.278 jaccard; misses are disconnections on the main scaffold,
  the co-reagent is usually right. The tool dumps all 50 references in random order,
  so same-reaction-type references (Boc2O for protections, NBS for FGA) are not
  adjacent and the recurring reagents are never surfaced.
- Symptom2Disease: 0.830; residual errors are genuine near-neighbour confusions
  (pneumonia/bronchial asthma, malaria/dengue) — random-shuffled context does not
  help discriminate them.
- 20 of 260 samples never called the tool at all, so retrieval was not guaranteed.

**Takeaway.** The memory was never *summarised*: it was a raw dump. The cheap wins are
(a) derive the reference answer profile (label vocabulary, part count, separators)
and state it explicitly, (b) rank references instead of shuffling them, and (c) make
the model check its draft against that profile before submitting.
