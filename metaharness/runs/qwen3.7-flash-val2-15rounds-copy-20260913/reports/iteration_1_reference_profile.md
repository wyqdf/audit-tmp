# Iteration 1 — reference_profile (post-eval)

**Result.** average 0.550 (baseline 0.428), 259/260 samples ok (1 unretryable
`content_filter` on LawBench, averaged over the 99 successful samples).

| task | baseline | reference_profile |
|---|---|---|
| USPTO | 0.183 | 0.250 |
| Symptom2Disease | 0.830 | 0.910 |
| LawBench | 0.270 | 0.495 |

**What worked.** The memory is now a derived profile plus ranked references instead of a
shuffled dump. LawBench gained most: iteration 0 lost 19/100 samples to label surface form
and this iteration's label list removed most of that. Symptom2Disease gained from having the
22 verbatim diagnoses in front of it. All three tasks improved; nothing regressed.

**What it cost.** Tool use collapsed (LawBench: 28 tool calls per 100 samples, `check_answer`
in 22 of them), so almost all of the gain came from the prompt-injected profile, and
`memory_context_chars` fell from ~28 000 to ~210 — the model reads the guide once and answers.

**Where it still loses (LawBench, 51 wrong samples of 100).**
- 17 are a *truncation of a gold label*: `毁坏国家重点保护植物` for
  `非法采伐、毁坏国家重点保护植物`, `销售伪劣产品` for `生产、销售伪劣产品`,
  `窝藏` for `窝藏、包庇`, sometimes the mirror error (splitting one label into two).
- 16 are under-predicted label counts (never over-predicted: 0 samples).
- 18 are genuine confusions between similar charge names.

**Root cause of the truncations.** `derive_separators` accepted a separator when it was
frequent enough (≥15 % of answers), and `、` passed. Splitting every answer on `、` cuts
single charge names such as `非法持有、私藏枪支、弹药` into fragments, and those fragments
then became the *authoritative* label list ("copy character for character"), so the solver
reproduced them verbatim. The same split also inflated the reported answer shape
(`1 part in 53 %` instead of the true `1 part in 68 %`).

**Takeaway.** Frequency is not evidence that punctuation separates units. Validate a
separator by whether the pieces it produces are attested as complete reference answers
elsewhere; only validated separators may cut the label inventory.
