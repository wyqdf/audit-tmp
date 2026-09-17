# qwen3.7-flash-val2-skillv4-15rounds-20260916 — evolution notes
Outer loop: metametaharness. Skill: meta-meta-harness (skillv4 text, see `metametaharness/versions/20260917-skillv4.SKILL-as-used.md`).

## Round 0
- branch: `main` | commit `ea3b299c22126cde8683a506fd968f0be49771ba` | tree `9f49dd7221d29df0c6f8b80f8f04a8b2b2b607f7`
- score: average 0.4366666666666667 | USPTO 0.2, Symptom2Disease 0.8, LawBench 0.31
- commit message: Issue: Establish the baseline

**Note**

# Evolution Notes

- **Root baseline** (no parent). The imported harness is a one-shot few-shot pipeline: `prepare_memory.py` copies every train example (`input`/`target`, plus `raw_question` when present) once into `memory.json`, and the solver exposes a single `retrieve_examples` tool that shuffles all examples with an input-derived seed and truncates the result at 30 000 characters, under a one-line system prompt plus a 4-line skill file. This is the reference point every later candidate is measured against.

- **Baseline evaluation (val, 2 samples/question; 260 expected samples, 257 successful, completion 0.9885; `rankable: true`):** `{"USPTO": 0.2, "Symptom2Disease": 0.8, "LawBench": 0.31, "average": 0.4367, "status": "partial"}`. Failed samples stay in the denominator and count as wrong. The equal-weight mean is held down by USPTO and LawBench, so those two tasks carry essentially all of the headroom; the spread across tasks (0.20-0.80) is far larger than any single-task noise. [[/workspace/runs/9f49dd7221d29df0c6f8b80f8f04a8b2b2b607f7/results/summary.json]]

- USPTO (0.20) fails on chemistry rather than format: 35 of the 47 wrong answers share no product component with the target (median Jaccard 0.0), i.e. the retrosynthetic disconnection itself is wrong; only 3 wrong answers are a proper subset of the target (a dropped small co-product such as `.OO` or `.N`). The retrieved few-shot context is large (mean 45 896 chars/sample) yet does not transfer to the specific transformation. [[/workspace/runs/9f49dd7221d29df0c6f8b80f8f04a8b2b2b607f7/USPTO/conversations/0029/sample-0.json]]

- LawBench (0.31; 67 of 98 successful samples wrong) fails mostly on answer-surface fidelity, not legal reasoning: 18 of the 67 wrong predictions match the target exactly once a trailing 「罪」 is removed from each label ("破坏电力设备罪" vs "破坏电力设备"), and 18 collapse a multi-label target ("赌博;开设赌场") to a single label. Both are addressable through general answer-verification and label-fidelity discipline rather than domain knowledge. [[/workspace/runs/9f49dd7221d29df0c6f8b80f8f04a8b2b2b607f7/LawBench/conversations/0009/sample-0.json]]

- The "call `retrieve_examples` before answering" instruction is not reliably obeyed: one LawBench sample returned its own plan as the answer — `{"reasoning": "调用 retrieve_examples 获取参考案例。", "final_answer": "调用 retrieve_examples 获取参考案例。"}` with zero tool calls — and 18 samples across tasks answered after a single model call with no retrieval at all. Retrieval-skipping samples score lower on LawBench (0.14 vs 0.33) and Symptom2Disease (0.00, 1 sample), but higher on USPTO (0.30 vs 0.18, n=10), where the retrieved context may be more distracting than helpful. [[/workspace/runs/9f49dd7221d29df0c6f8b80f8f04a8b2b2b607f7/LawBench/conversations/0013/sample-0.json]]

- Symptom2Disease (0.80) is the strongest task because the input itself enumerates the closed label set, so few-shot retrieval transfers directly; its 20 wrong samples are 19 isolated misclassifications plus one empty prediction (`"None"`). A change that helps elsewhere should not regress this task. [[/workspace/runs/9f49dd7221d29df0c6f8b80f8f04a8b2b2b607f7/Symptom2Disease/conversations/0037/sample-0.json]]

- **Execution failures (3/260, 1.2%):** USPTO ex0 sample 1 hit a provider `ReadTimeout` at 423 s against a 420 s client timeout — a retryable error that did not recover on the second attempt; LawBench ex21/ex33 inputs were rejected non-retryably by the provider's `content_filter` (`DataInspectionFailed`). All three count as wrong answers in the score, so 1.2% of the mean is lost to infrastructure effects. [[/workspace/runs/9f49dd7221d29df0c6f8b80f8f04a8b2b2b607f7/USPTO/conversations/0000/sample-1.json]]

## Round 1
- branch: `codex/answer-convention-repair` | commit `d7b155f0d6d296b753c7aff57c4a26a93ccb2093` | tree `bca9cc83e78c40aec26b992045b54b53d51b049b`
- score: average 0.49333333333333323 | USPTO 0.25, Symptom2Disease 0.82, LawBench 0.41
- commit message: Issue: Half of the task with the most headroom is lost to answer wording rather than to reasoning: on the baseline, LawBench scored 0.31 with 69 of 100 samples wrong, and 33 of those wrong answers were surface variants of the target (20 wrote the charge with a 「罪」 suffix that never appears in the 200 training answers, 13 collapsed a multi-label target to one label). The harness never compared its answer with what the memory actually writes, so the model's own prior about charge names won over the examples it had just read (/workspace/runs/9f49dd7221d29df0c6f8b80f8f04a8b2b2b607f7/LawBench/conversations/0000/sample-1.json: the retrieved context contains "单位行贿" and the answer still came back as "单位行贿罪").

**Note**

# Evolution Notes

- Chosen from the baseline evidence rather than from a guess about the model: the baseline's
  LawBench loss was concentrated in answer *wording* (20 of 69 wrong answers differed from the
  target only by a trailing 「罪」, 13 collapsed a multi-label target), while the retrieved context
  already contained the exact wording the model failed to copy — 43 of 100 predictions carried
  the 「罪」 suffix while 0 of 200 training answers did. So the mechanism was to make the memory
  authoritative for the answer's surface form instead of hoping the model would infer the
  convention. `prepare_memory.py` now derives an answer profile from the training answers, and
  `AnswerVerificationMiddleware` gives the model one repair turn when its final answer contains
  an item that is a near-variant (<=3 characters added or dropped) of one the memory writes.

- The check is scoped by a statistic of the memory, not by task identity: a memory whose answers
  repeat a bounded set of short items is vocabulary-like (Symptom2Disease 22 items / 200 answers,
  LawBench 175 / 327, USPTO 50 distinct in 50), so the free-form task is never checked and the
  check cannot fire there. Verified offline before evaluation on the baseline traces: 28 of 69
  wrong LawBench answers were flagged and 0 of 31 correct ones were, and in the run the same
  gate held — the repair fired in exactly 28 LawBench samples and in no other task.

- Observed effect matches the intended one: LawBench 0.31 -> 0.41, average 0.4367 -> 0.4933, with
  28 repair turns (one each) and predictions carrying a 「罪」 suffix down from 43 to 20. A repaired
  sample kept reasoning unchanged and only the wording fixed, e.g. 「非法种植毒品原植物罪」 ->
  「非法种植毒品原植物」, turning a wrong answer into a right one
  [[/workspace/runs/bca9cc83e78c40aec26b992045b54b53d51b049b/LawBench/conversations/0004/sample-0.json]].

- The 20 remaining 「罪」 predictions are the limit of this mechanism: they are the cases where the
  target's wording is absent from the training memory, so no near-variant exists to quote and the
  check stays silent by design (firing there would have flagged correct answers too — 8 of the 31
  correct samples have that property).

- Two limits worth keeping. (1) Quoting a split item can cut off part of a composite label: in
  [[/workspace/runs/bca9cc83e78c40aec26b992045b54b53d51b049b/LawBench/conversations/0038/sample-0.json]]
  the check saw "领导传销活动罪" (from "组织、领导传销活动罪") and quoted "领导传销活动" alone, and the
  model dropped the "组织、" prefix — the only correct -> wrong flip among the 28 fired samples.
  Quoting the whole memory answer, not the split item, is the obvious follow-up. (2) Half of the
  reported gain is run-to-run variance, not the mechanism: USPTO (0.20 -> 0.25) and Symptom2Disease
  (0.80 -> 0.82) moved with no repair firing, and 8 of the 14 LawBench wrong -> correct flips came
  from unfired samples; only 6 of the 14 are attributable to the repair, next to that 1 regression.

- Unchanged by this iteration and still the largest remaining buckets: LawBench multi-label
  collapse (13 wrong in the baseline, 19 here — noisiest bucket, and this mechanism does not touch
  it), and USPTO, where the whole 50-example memory already fits in the retrieved context yet the
  answers are 0% covered and only 13% of target components appear, so its 0.20-0.25 is a reasoning
  and knowledge limit rather than a memory or format one. One sample also burned all 32 model calls
  on file exploration ([[/workspace/runs/bca9cc83e78c40aec26b992045b54b53d51b049b/Symptom2Disease/conversations/0007/sample-1.json]]),
  a pre-existing failure mode of the file tools, not of the check.

- Full result and per-sample evidence: [[/workspace/runs/bca9cc83e78c40aec26b992045b54b53d51b049b/results/summary.json]].

## Round 2
- branch: `codex/answer-composition-repair` | commit `3340e638dae378a4bf828d9390084a6b1c9cbbf5` | tree `e2c96b80fe6f6045ce76e249acfdb3eaab900dfd`
- score: average 0.4988888888888889 | USPTO 0.21666666666666667, Symptom2Disease 0.83, LawBench 0.45
- commit message: Issue: The repair turn quotes answer items torn out of the answers they belong to, so when the memory never writes a charge on its own the model is told to write a fragment. On the parent (bca9cc8) that turned a correct answer wrong — "领导传销活动" quoted out of "组织、领导传销活动" (/workspace/runs/bca9cc83e78c40aec26b992045b54b53d51b049b/LawBench/conversations/0038/sample-0.json) — and degraded another, "运输" quoted out of "走私、贩卖、运输、制造毒品" and then written as the answer (conversations/0026/sample-0.json). The response was also read as word runs instead of the units its answer is made of, so "[罪名]盗窃罪;盗窃枪支、弹药、爆炸物罪" was matched piecewise ("盗窃枪支" -> "盗窃", "爆炸物罪" -> "爆炸物") and the model dropped a charge it had (conversations/0017/sample-0.json). 15 of that run's 59 wrong LawBench answers have their exact target answer in the training memory, so the wording they failed to copy was available.

**Note**

# Evolution Notes

- Chosen from the parent's own evidence rather than from a new guess: the repair turn quoted
  answer items without the answers they are written in, which is the same defect behind the
  parent's documented correct->wrong flip (「领导传销活动」 quoted out of 「组织、领导传销活动」)
  and behind a degraded answer (「运输」 quoted out of 「走私、贩卖、运输、制造毒品」, then written
  as the answer). The profile now carries the memory's complete answers with counts, and the
  notice quotes a complete answer whenever the memory writes the departing charge only inside
  one or two of them; the response is parsed the way the memory's answers are parsed, so an
  item is a whole charge rather than a word run. The intent was to let the model copy the
  memory's composition (「窝藏、包庇」, not 「窝藏」) while never losing a charge it had identified.

- Observed effect on the intended task: LawBench 0.41 -> 0.45, average 0.4933 -> 0.4989. The
  check fired in 24 LawBench samples (26 notices; 0 in Symptom2Disease and USPTO, which the
  memory-shape gate keeps out) and the complete-answer quote is what produced the fixes:
  [[/workspace/runs/e2c96b80fe6f6045ce76e249acfdb3eaab900dfd/LawBench/conversations/0014/sample-0.json]]
  (「窝藏罪」 -> 「窝藏、包庇」, target 窝藏、包庇) and
  [[/workspace/runs/e2c96b80fe6f6045ce76e249acfdb3eaab900dfd/LawBench/conversations/0036/sample-0.json]]
  (「拐卖妇女罪」 -> 「拐卖妇女、儿童」, both samples of that example fixed).

- The failure mode that the same quote invites also occurred, exactly where the offline risk
  check said it would: a complete answer can belong to another case, and the model adopts its
  extra charges. [[/workspace/runs/e2c96b80fe6f6045ce76e249acfdb3eaab900dfd/LawBench/conversations/0010/sample-1.json]]
  was correct in the parent (「聚众扰乱社会秩序」) and came back as 「故意伤害;聚众扰乱社会秩序」
  after the notice quoted that complete answer;
  [[/workspace/runs/e2c96b80fe6f6045ce76e249acfdb3eaab900dfd/LawBench/conversations/0045/sample-1.json]]
  likewise wrote 「过失致人死亡;破坏生产经营」 for a target of 过失致人死亡. So within the fired
  samples the composition quote fixed 3 and broke 3 — net zero — and the reported LawBench gain
  is mostly variance: of the 8 wrong->correct and 4 correct->wrong flips, 4 and 1 respectively
  happened where the check never fired (e.g. ex38, the parent's regression case, was answered
  「组织、领导传销活动」 on the first pass with no repair this time).

- Parsing the response as its judged units removed the degradation without a new notice: for
  the same sample where the parent's notice tore 「运输毒品罪」 down to 「运输」, the new notice
  quoted the complete answer 「非法制造、买卖、运输、邮寄、储存枪支、弹药、爆炸物」 (an unrelated
  firearms charge, since the drug answer writes 「运输」 inside a longer item and is not one of its
  compositions) and the model kept its own wording
  [[/workspace/runs/e2c96b80fe6f6045ce76e249acfdb3eaab900dfd/LawBench/conversations/0026/sample-0.json]].
  The footer's "keep every item you identified" is what made that safe; the composition hint
  itself was misleading there.

- Unchanged and still the largest bucket: LawBench collapse (a wrong answer whose charges are a
  strict subset of the target) went 20 -> 16, and the check only touches it when the missing
  charge happens to sit in the same memory answer (ex36). USPTO 0.25 -> 0.2167 is noise on a
  task the check cannot run on (its memory is not vocabulary-like) and where 13 of 60 answers are
  right against 40 wrong answers sharing no component with the target.

- Next step this evidence points to: quote a complete answer only when it plausibly belongs to
  the case at hand — the model's other items should attest to it, or the question's own retrieved
  neighbours should contain it — instead of whenever the memory writes the charge in only one
  or two compositions. Full result and per-sample evidence:
  [[/workspace/runs/e2c96b80fe6f6045ce76e249acfdb3eaab900dfd/results/summary.json]].

## Round 3
- branch: `codex/relevance-ranked-retrieval` | commit `7628d2a1729edc0c110a00bb7ccb94498972bf5f` | tree `8b90b9c533d81d047bcfa360458b9b5b1f664fb9`
- score: average 0.5255555555555556 | USPTO 0.26666666666666666, Symptom2Disease 0.88, LawBench 0.43
- commit message: Issue: The examples the solver copies its answer from were an arbitrary slice of the memory, not the ones that bear on the question. `retrieve_examples` shuffled the whole pool with a per-question seed and cut it at 30000 characters, which on the parent (e2c96b8) left 73% of the LawBench memory invisible: 54.8 of 200 examples per question, a different random 55 for every question, so 26 of 100 samples had their exact target answer somewhere in the memory and not in the context. Offline, the same budget filled with the closest examples covers the target answer for 36% of val questions against 16% for the random slice (leave-one-out on the training questions: 42% vs 27.5%). This is the memory the harness is supposed to be copying its wording from, and for the task with the most headroom it was mostly discarded.

**Note**

# Evolution Notes

- Chosen from a measurement of the parent's own retrieval rather than from a new guess about
  the model: on the parent (e2c96b8) the retrieved context held 54.8 of the 200 LawBench
  examples, a different random slice per question, so 26 of 100 samples had their exact target
  answer in the memory and not in front of the model. Ranking the pool by tf-idf cosine over
  character 2-grams of the question covers the target answer for 36% of val questions against
  16% for the random slice, at the same 30000-character budget (offline, leave-one-out over the
  training questions: 42% vs 27.5%; bigrams beat unigrams, trigrams and 4-grams, and adding the
  answers to the document side changes coverage by less than a point). The intent was to spend
  the context the harness already pays for on the examples closest to the question instead of
  on an arbitrary slice of the memory.

- The intended effect happened and was measured directly, and it did not produce accuracy. In
  the run, 32 LawBench samples have the exact target answer in the retrieved context (16 on the
  parent) and 27 of those are correct (84%, against the parent's 81% conditional rate), but the
  42 samples whose target is in the memory at all went 32 -> 30 correct. The samples that gained
  visibility are the ones that were already right, and the 10 that lost it are the ones with no
  near-analog in the memory at all (3 of 10 correct), so visibility marks which questions have a
  similar training case rather than causing the answer. This matches the parent's bucket
  accounting — only 10 of its 55 wrong LawBench answers had their target anywhere in the memory
  — and says the remaining LawBench loss is wording and composition, not coverage.

- The average rose on the two tasks this change was not aimed at, and only ordering can explain
  it there: USPTO 0.2167 -> 0.2667 and Symptom2Disease 0.83 -> 0.88, with essentially the same
  example sets (USPTO shows all 50 both before and after; Symptom 175 -> 171 of 200). Nine
  USPTO samples and seven Symptom2Disease samples flipped, which is the same order as the 15 and
  10 flips seen across the three parent runs, so the effect is plausible but not separable from
  run-to-run spread. The clearest instance of the defect being fixed is
  [[/workspace/runs/8b90b9c533d81d047bcfa360458b9b5b1f664fb9/Symptom2Disease/conversations/0021/sample-0.json]]:
  the two nearest same-label training cases for a persistent dengue/allergy confusion were
  exactly the ones the parent's random slice had dropped, and with them ranked first the model
  answered "allergy" for the first time in the lineage. The model also cites the ranked examples
  in its reasoning — "align closely with the clinical presentation of bronchial asthma as seen
  in" [[/workspace/runs/8b90b9c533d81d047bcfa360458b9b5b1f664fb9/Symptom2Disease/conversations/0004/sample-0.json]]
  and "Following the pattern from protection reaction examples"
  [[/workspace/runs/8b90b9c533d81d047bcfa360458b9b5b1f664fb9/USPTO/conversations/0005/sample-0.json]]
  (an exact-target answer for a case the parent got wrong) — and for one USPTO case the ranked
  context is enough for the model to carry the product's stereochemistry into the answer
  [[/workspace/runs/8b90b9c533d81d047bcfa360458b9b5b1f664fb9/USPTO/conversations/0002/sample-1.json]].

- Where the ranking does help on LawBench is salience rather than coverage: the two LawBench
  wins whose target answer was already visible in both runs are cases where the model had
  written a shorter or wrong charge and now copies the memory's full one —
  [[/workspace/runs/8b90b9c533d81d047bcfa360458b9b5b1f664fb9/LawBench/conversations/0011/sample-1.json]]
  (「买卖国家机关证件罪」 -> 「伪造、变造、买卖国家机关公文、证件、印章」) and
  [[/workspace/runs/8b90b9c533d81d047bcfa360458b9b5b1f664fb9/LawBench/conversations/0043/sample-1.json]]
  (「受贿」 -> 「非国家工作人员受贿」, the memory's wording for a case whose charge the model had
  under-specified). Both were wrong on the parent with the same context available.

- The residual failure mode is unchanged and is now the largest single cause of LawBench churn:
  four of the six correct -> wrong flips re-added 「罪」 to a charge whose wording the memory does
  not contain (「非法采伐、毁坏国家重点保护植物」 and 「以危险方法危害公共安全」), which the repair
  turn cannot reach by construction, e.g.
  [[/workspace/runs/8b90b9c533d81d047bcfa360458b9b5b1f664fb9/LawBench/conversations/0008/sample-0.json]].
  Three LawBench samples were lost to content_filter rejections of the question text before any
  retrieval happened (one such error occurs in every run, including the parent's), so the
  reported 0.43 understates the task by about three samples.

- Full result and per-sample evidence:
  [[/workspace/runs/8b90b9c533d81d047bcfa360458b9b5b1f664fb9/results/summary.json]]. Next step this
  evidence points to: coverage is not the binding constraint on LawBench, so the remaining
  mechanism work belongs on composition — a repair that can tell "the memory writes this item
  inside a longer charge name" from "the memory writes this item inside another charge" would
  keep the parent's fix (「窝藏」 -> 「窝藏、包庇」) without its regression (「聚众扰乱社会秩序」 ->
  「故意伤害;聚众扰乱社会秩序」), and the four 「罪」 flips above need the same kind of evidence
  when the memory has no wording to quote at all.

## Round 4
- branch: `codex/answer-ending-convention` | commit `e5d4cc50d51004875db81b49655f98163e98048c` | tree `3c5c61e1a2505a79fcd73b63596601425207a4bb`
- score: average 0.5344444444444444 | USPTO 0.23333333333333334, Symptom2Disease 0.88, LawBench 0.49
- commit message: Issue: The check that compares an answer with the memory's wording used two kinds of evidence the harness had no right to: quotes the model had never read, and the memory's own way of ending an item. On the parent (8b90b9c) a composition quote came from anywhere in the memory, and both samples where a quote changed a correct answer for the worse had never read the quoted answer — "生产、销售伪劣产品;非法经营" was quoted into ex12.1, whose first pass was the correct "生产、销售伪劣产品" (/workspace/runs/8b90b9c533d81d047bcfa360458b9b5b1f664fb9/LawBench/conversations/0012/sample-1.json), and "强奸;侮辱" into ex44.1, whose target is 侮辱 (conversations/0044/sample-1.json). Separately, no memory item ends with 「罪」 (0 of 175, though 5 items carry the character inside them) while 35 of 100 first-pass answers end an item that way; the near-variant check reaches only 8 of the 14 samples where that is the only difference from the target, and the other 6 — 「破坏电力设备罪」, 「非法采伐、毁坏国家重点保护植物罪」, 「以危险方法危害公共安全罪」, 「销售伪劣产品罪」 — got no notice at all, because the memory writes no near-variant to quote.

**Note**

# Evolution Notes

- Chosen from the parent's own evidence rather than from a new guess. The parent's repair turn
  quoted complete memory answers without asking whether the model had ever read them, and both
  samples where that changed an answer for the worse quoted an answer that was not in the
  retrieved context: on the parent, ex12.1 was the correct "生产、销售伪劣产品" on its first pass
  and came back as "生产、销售伪劣产品;非法经营" after the notice quoted that answer, and ex44.1
  wrote "强奸;侮辱" for a target of 侮辱 after the notice quoted "强奸;侮辱"
  ([[/workspace/runs/8b90b9c533d81d047bcfa360458b9b5b1f664fb9/LawBench/conversations/0012/sample-1.json]],
  [[/workspace/runs/8b90b9c533d81d047bcfa360458b9b5b1f664fb9/LawBench/conversations/0044/sample-1.json]]).
  The second half of the evidence is the memory's answer shape: none of the 175 memory items ends
  with 「罪」 although 5 of them carry the character inside ("包庇毒品犯罪分子", "传授犯罪方法"), while
  35 of 100 first-pass answers end an item with it. The near-variant check reached only 8 of the 14
  samples whose only departure from the target was that trailing character, because the memory
  writes no near-variant for the other 6 to quote (「破坏电力设备罪」, 「非法采伐、毁坏国家重点保护植物罪」,
  「以危险方法危害公共安全罪」, 「销售伪劣产品罪」). The intent was to make the check's evidence local to
  what the model read and to let the memory's own item endings be evidence at all.

- The intended effect happened on the task it was aimed at and is attributable this time: LawBench
  0.43 -> 0.49, average 0.5256 -> 0.5344, first-pass 35 -> 49 against the parent's 35 -> 43, with
  27 notices instead of 21 and 15 wrong -> correct flips instead of 9. The locality restriction is
  what recovered the parent's two documented casualties: ex12.1 now keeps "生产、销售伪劣产品"
  ([[/workspace/runs/3c5c61e1a2505a79fcd73b63596601425207a4bb/LawBench/conversations/0012/sample-1.json]])
  and ex44.1 is answered "侮辱" instead of "强奸;侮辱"
  ([[/workspace/runs/3c5c61e1a2505a79fcd73b63596601425207a4bb/LawBench/conversations/0044/sample-1.json]]).
  Among the samples where a complete answer was quoted, the two that became correct are ones whose
  quote really was in the retrieved context: ex14.1 「窝藏罪」 -> 「窝藏、包庇」
  ([[/workspace/runs/3c5c61e1a2505a79fcd73b63596601425207a4bb/LawBench/conversations/0014/sample-1.json]])
  and ex36.1 「拐卖妇女罪」 -> 「拐卖妇女、儿童」
  ([[/workspace/runs/3c5c61e1a2505a79fcd73b63596601425207a4bb/LawBench/conversations/0036/sample-1.json]]).

- The new ending evidence is safe but so far unproductive. It fired in 3 samples and changed the
  answer in all 3 without touching any first-pass-correct answer (checked offline on all three
  earlier runs: of the 35 answers that end an item the way no memory item does, none was correct on
  its first pass). None of the three turned correct: ex12.0 dropped the 「罪」 but dropped the correct
  「生产」 with it ([[/workspace/runs/3c5c61e1a2505a79fcd73b63596601425207a4bb/LawBench/conversations/0012/sample-0.json]]),
  and ex33.0/ex33.1 were wrong about the charge itself (target 拐骗儿童). Sentence the notice gives is
  narrower than the class it was measured on — the 35 violations are counted by ending alone, the
  notice additionally requires the memory to write the rest of the item — which is what keeps it at
  3 samples and 0 regressions.

- The one correct -> wrong flip this run is the near-variant rule read in the wrong direction, and it
  is the concrete next step. "以危险方法危害公共安全" was matched to the memory item
  "过失以危险方法危害公共安全" because the memory item merely *contains* the answer item, and the notice
  told the model the memory writes it as the negligent charge, which the model then did
  ([[/workspace/runs/3c5c61e1a2505a79fcd73b63596601425207a4bb/LawBench/conversations/0031/sample-0.json]]).
  The good matches all differ at an end (「单位行贿」+「罪」, 「拐卖妇女」 inside 「拐卖妇女、儿童」); this one
  differs at the front. Requiring the two strings to agree from one end would keep every fix this
  lineage has made and drop this flip.

- Unchanged and explained elsewhere: USPTO (0.2667 -> 0.2333) and Symptom2Disease (0.88 -> 0.88) got
  0 notices — the vocabulary-shape gate keeps the check off both memories — and USPTO's 8 flipped
  samples (+3/-5) are the same run-to-run spread the parent's own note measured, not a regression of
  this change. LawBench also lost ex14.0 and ex27.1, which were correct in the parent, to the same
  spread (ex14.0's sibling ex14.1 was fixed here by the mechanism). Two of the six net LawBench
  samples are infrastructure: ex5.0, ex5.1 and ex47.0 failed with provider content_filter rejections
  in the parent and completed here. Full result and per-sample evidence:
  [[/workspace/runs/3c5c61e1a2505a79fcd73b63596601425207a4bb/results/summary.json]].

## Round 5
- branch: `codex/answer-variant-agreement` | commit `d8f5ef0abc4f02e9f3862c392228c57f30d7afd5` | tree `37a3ebb74a30bacfa2ab2379c86fa408af47a2fd`
- score: average 0.5644444444444444 | USPTO 0.2833333333333333, Symptom2Disease 0.89, LawBench 0.52
- commit message: Issue: The check matched an answer item to a memory item by containment, so it read two different charges as one wording whenever either string contained the other. On the parent (e5d4cc5) that is the one correct->wrong flip its own note left behind: the memory item 「过失以危险方法危害公共安全」 merely ends with the answer's 「以危险方法危害公共安全」, the notice reported it as the memory's way of writing that charge, and the model wrote the negligent charge instead (/workspace/runs/3c5c61e1a2505a79fcd73b63596601425207a4bb/LawBench/conversations/0031/sample-0.json: 「盗窃;以危险方法危害公共安全」 -> 「盗窃;过失以危险方法危害公共安全」). The same containment flagged a correct answer one example over: the separator rule splits 「生产、销售伪劣产品」 into 「生产」 and 「销售伪劣产品」, the second piece is contained in the memory item 「生产、销售伪劣产品」, and the model was told the memory writes otherwise (conversations/0012/sample-1.json). In the other direction containment needs the answer item to be a substring of the memory's item at all, which puts out of reach the charges the model writes by dropping a piece of the memory's charge: 「非法采伐国家重点保护植物」 against the memory's 「非法采伐、毁坏国家重点保护植物」 got no notice in either sample of that example, nor in conversations/0046/sample-0.json or conversations/0008/sample-0.json.

**Note**

# Evolution Notes

- Chosen from the parent's own evidence rather than from a new guess. The parent's note ended
  on the one correct->wrong flip it had left: 「以危险方法危害公共安全」 was matched to the memory
  item 「过失以危险方法危害公共安全」 because that item merely *ends with* the answer item, and the
  notice told the model the memory writes it as the negligent charge
  ([[/workspace/runs/3c5c61e1a2505a79fcd73b63596601425207a4bb/LawBench/conversations/0031/sample-0.json]]).
  The same blind containment also flagged a *correct* answer in that run — the separator rule
  splits 「生产、销售伪劣产品」 in two, and the piece 「销售伪劣产品」 is contained in the memory item
  「生产、销售伪劣产品」 ([[/workspace/runs/3c5c61e1a2505a79fcd73b63596601425207a4bb/LawBench/conversations/0012/sample-1.json]]).
  Read the other way, containment needs the answer item to be a substring of the memory's item,
  which put the charges the model writes by dropping a piece of the memory's charge out of reach:
  「非法采伐国家重点保护植物」 against the memory's 「非法采伐、毁坏国家重点保护植物」 got no notice at all,
  in either sample of that example or in conversations/0046 and conversations/0008 of the same run.
  The intent was to make the match itself carry the evidence — read the two strings together from
  the front instead of looking for one inside the other — so that the notice speaks about the
  charges the memory writes with a piece dropped or a 「罪」 appended, and stays silent about a
  longer charge that merely shares the answer item's ending.

- Measured offline before evaluating, on the 400 recorded first passes of the four earlier runs:
  the new matcher flags 114 of 268 wrong answers and 0 of 132 correct ones, against 107 and 3 for
  the parent, i.e. it strictly dominates on this corpus — it gains the dropped-piece family and
  loses both correct-answer flags while losing no flag that ever helped.

- The intended effect happened on the task it was aimed at and is attributable: LawBench
  0.49 -> 0.52, average 0.5344 -> 0.5644. The cleanest attribution is ex13.0, whose first pass was
  identical in both runs: 「非法采伐国家重点保护植物」 drew no notice on the parent (wrong) and now draws
  the memory's complete answer 「非法采伐、毁坏国家重点保护植物;非法占用农用地」 (right), and the model copied
  only the charge that shares its beginning
  ([[/workspace/runs/37a3ebb74a30bacfa2ab2379c86fa408af47a2fd/LawBench/conversations/0013/sample-0.json]]).
  The parent's documented casualty is gone with the same rule: ex31.0 is no longer matched to the
  negligent charge, and the notice that changed its answer for the worse cannot fire
  ([[/workspace/runs/37a3ebb74a30bacfa2ab2379c86fa408af47a2fd/LawBench/conversations/0031/sample-0.json]]).
  Of the 22 notices this run fired, 0 landed on an answer that was already correct, 15 converted a
  wrong first pass and 7 did not; the parent's 27 notices contained 2 such flags and one of them
  was the flip above.

- Other notices that fired and converted, where only the first pass differs between the runs so the
  gain is shared with run-to-run spread: 「窝藏罪」 -> 「窝藏、包庇」 ([[/workspace/runs/37a3ebb74a30bacfa2ab2379c86fa408af47a2fd/LawBench/conversations/0014/sample-0.json]])
  and 「非法采伐、毁坏国家重点保护植物罪」 -> the memory's wording without the trailing 「罪」
  ([[/workspace/runs/37a3ebb74a30bacfa2ab2379c86fa408af47a2fd/LawBench/conversations/0008/sample-0.json]]).

- Unchanged and explained elsewhere: USPTO 0.2333 -> 0.2833 and Symptom2Disease 0.88 -> 0.89 both
  got 0 notices — the vocabulary-shape gate keeps the check off both memories, which the new
  matcher does not touch — so their movement is the run-to-run spread this lineage has measured
  before, not an effect of this change
  ([[/workspace/runs/37a3ebb74a30bacfa2ab2379c86fa408af47a2fd/results/summary.json]]). LawBench
  lost one sample to a provider content_filter rejection of the question text, which counts as a
  wrong answer, so the reported 0.52 is one sample under what the harness answered.

- The visible limit of the new rule, and the next step this evidence points to: an item that
  departs in two ways at once still gets nothing. 「非法采伐国家重点保护植物罪」 drops a piece of the
  memory's charge *and* carries the 「罪」 the memory never writes, and the two mechanisms each see
  only one of the two departures — the variant rule in `_closest_known` needs the shared ending,
  the ending rule in `_ending_notice` needs the rest of the item to be a part the memory's answers
  are made of. Three samples of this run are exactly that shape and all three stayed wrong
  ([[/workspace/runs/37a3ebb74a30bacfa2ab2379c86fa408af47a2fd/LawBench/conversations/0013/sample-1.json]],
  [[/workspace/runs/37a3ebb74a30bacfa2ab2379c86fa408af47a2fd/LawBench/conversations/0046/sample-0.json]],
  [[/workspace/runs/37a3ebb74a30bacfa2ab2379c86fa408af47a2fd/LawBench/conversations/0008/sample-1.json]]).
  Letting the ending rule ask the variant test of the item it has stripped would reach them without
  loosening either rule's standard.

## Round 6
- branch: `codex/answer-ending-variant` | commit `3bb9672c9bf50cf8cc48a057e605b8d81af464df` | tree `cd1bd0d40a39e7f9807fa0f12a58902c73abec2d`
- score: average 0.5333333333333333 | USPTO 0.2, Symptom2Disease 0.88, LawBench 0.52
- commit message: Issue: The ending rule and the variant rule each see only one of the two ways an answer item can depart from the memory's wording, so an item that departs both ways at once drew no notice at all. On the parent (d8f5ef0) that is the family its own note left behind: 「非法采伐国家重点保护植物罪」 drops the piece 「、毁坏」 of the memory item 「非法采伐、毁坏国家重点保护植物」 and carries the trailing 「罪」 that no memory item ends with (0 of 175 end with it, though 5 carry it), and the two mechanisms split the departures between them. The variant rule reads the two strings from the front and needs them to share an ending, which the trailing 「罪」 breaks (「非法采伐国家重点保护植物罪」 and 「非法采伐、毁坏国家重点保护植物」 share no tail); the ending rule needs the rest of the item to be one of the parts the memory's answers are made of, and 「非法采伐国家重点保护植物」 is not one — the memory's parts here are 「非法采伐」, 「毁坏国家重点保护植物」 and the joined charge, not the answer's reading of them. Three samples of the parent's run are exactly that shape and all three stayed wrong, with no notice on any of them (/workspace/runs/37a3ebb74a30bacfa2ab2379c86fa408af47a2fd/LawBench/conversations/0008/sample-1.json: 「非法毁坏国家重点保护植物罪」; conversations/0013/sample-1.json and conversations/0046/sample-0.json: 「非法采伐国家重点保护植物罪」, both against the target 「非法采伐、毁坏国家重点保护植物」).

**Note**

# Evolution Notes

- Chosen from the parent's own evidence rather than from a new guess: the parent's note ended on
  the one shape its two rules could not see, an item that drops a piece of the memory's charge
  *and* carries an ending the memory never uses, and named the step that reaches it — let the
  ending rule ask the variant test of the item it has stripped. That is the whole of the change;
  the same two readings of the same strings, applied to the string the ending rule has made, so
  nothing is quoted that the memory does not write and the requirement that the memory write the
  charge is kept in both branches.

- Measured offline before evaluating, on the 592 recorded first passes of the six earlier runs
  ([[/workspace/runs/37a3ebb74a30bacfa2ab2379c86fa408af47a2fd/LawBench/memory.json]] for the
  profile they were scored against): the check flags 180 of 392 wrong answers against the parent's
  165, and 0 of 200 correct ones in both — the 15 new flags are all the two-way-departure family,
  and each of them, followed literally, lands on the target wording. The rule adds no flag on any
  of the 66 items the 100 val targets are made of, nor on the memory's own 175 items and 143
  answers, so a correct answer that reproduces the memory's wording cannot trip it; the parent's
  false-positive shape (the splitter's own pieces) is untouched because the ending rule still needs
  the memory to write the rest of the item either way.

- The intended effect happened and is attributable, but the family is too narrow to move LawBench:
  the run fired 25 notices against the parent's 22 and converted 18 of them against 15, LawBench
  stayed at 52/100 and the average fell 0.5644 -> 0.5333. The one first pass of this shape the run
  produced drew the new message and was corrected to the memory's wording
  ([[/workspace/runs/cd1bd0d40a39e7f9807fa0f12a58902c73abec2d/LawBench/conversations/0046/sample-1.json]]:
  「非法采伐国家重点保护植物罪」 -> 「非法采伐、毁坏国家重点保护植物」); the parent's identical first pass one
  sample over got no notice at all and stayed wrong
  ([[/workspace/runs/37a3ebb74a30bacfa2ab2379c86fa408af47a2fd/LawBench/conversations/0046/sample-0.json]]).
  The rest of that family was already recovered this run by the two older rules — 「非法采伐、毁坏国家重点保护植物罪」
  through the ending rule's part test and 「非法采伐国家重点保护植物」 through the composition quote
  ([[/workspace/runs/cd1bd0d40a39e7f9807fa0f12a58902c73abec2d/LawBench/conversations/0013/sample-0.json]]) — so
  the change's own contribution is one sample, which is the honest size of a family that is 15 of
  592 first passes concentrated in 3 val questions.

- The fall in `average` is not this change: USPTO 0.2833 -> 0.20 and Symptom2Disease 0.89 -> 0.88
  are the two tasks whose memories the vocabulary gate keeps the check off, and neither run fired a
  single notice there; 41 of 60 USPTO predictions differ between the two runs on identical inputs,
  which is the provider's non-determinism, and this lineage has measured USPTO between 0.20 and
  0.2833 across runs that never touched it
  ([[/workspace/runs/cd1bd0d40a39e7f9807fa0f12a58902c73abec2d/results/summary.json]]). LawBench's 52/100
  is three content-filter rejections under what the harness answered (52 of the 97 scored samples,
  53.6%), the parent lost one the same way.

- The limit this evidence leaves, and where the remaining LawBench wording errors actually are: the
  run's 16 unreached wrong answers whose items are spelled differently from the memory are almost
  all charges the memory never writes at all — 「销售假冒注册商标的商品」, 「破坏电力设备」,
  「以危险方法危害公共安全」, 「帮助毁灭、伪造证据」, 「窃取、收买、非法提供信用卡信息」, 「伪造、变造金融票证」 — so no
  wording can be quoted back, and the only rule that would reach them is "the memory never ends an
  item with this character, drop it", which is unsound here: 「帮助毁灭、伪造证据」 (ends 「据」) and 「窃取」
  (ends 「取」) are both val target items the same rule would tell the model to shorten
  ([[/workspace/runs/cd1bd0d40a39e7f9807fa0f12a58902c73abec2d/LawBench/conversations/0030/sample-0.json]]).
  The larger population is the 23 wrong answers whose items are all memory wording and which are
  simply missing charges; their targets are absent from the training memory in all but one case, so
  there is no evidence a wording check could report — which points the next iteration at the
  retrieval and context side rather than at the check.

## Round 7
- branch: `codex/answer-name-pieces` | commit `5402cb12d7832d6ca7a7dda11607b0a5f7f0d9c9` | tree `b000c8efdc1973bb7b24cd9430e5f9a612f2bf24`
- score: average 0.5333333333333333 | USPTO 0.25, Symptom2Disease 0.87, LawBench 0.48
- commit message: Issue: The check reads the memory's inventory as a list of charges and stays silent on every answer item that is in it, but the inventory is what the memory's answers are cut into at the separators a grader would read them on, and a charge whose name carries punctuation inside it is in the inventory twice over — as the whole name and as the pieces it is cut into. Which separator joins charges is in the memory itself: the units a joining separator cuts an answer into keep reappearing as units of other answers (0.41 of them for 「;」), while a name's own punctuation cuts it into units that appear nowhere else (0.03 for 「、」). So 「窝藏」 and 「拐卖妇女」 are only ever what 「窝藏、包庇」 and 「拐卖妇女、儿童」 are cut into, and an answer that writes one of them as a charge of its own has dropped the rest of the name — yet on the parent (3bb9672) it drew no notice at all, because the parent skipped every item the inventory holds. Five of the 492 recorded first passes of the six earlier runs are that shape and all five stayed wrong with no notice (8b90b9c5 .../LawBench/conversations/0014/sample-1.json: 「窝藏」 against 「窝藏、包庇」; cd1bd0d4 .../conversations/0036/sample-0.json: 「拐卖妇女」 against 「拐卖妇女、儿童」), and every one of the six runs has at least one.

**Note**

# Evolution Notes

- Chosen from the parent's own evidence rather than from a new guess. The parent's skip rule
  — an item the memory writes is nothing to report — reads the inventory as a list of
  charges, but the inventory is what the memory's answers are cut into at the separators a
  grader would read them on, and a charge whose name carries punctuation inside it is in it
  twice over. Which separator joins charges is in the memory: the units a joining separator
  cuts an answer into keep reappearing as units of other answers (0.41 of the 74 units for
  「;」) while a name's own punctuation cuts it into units that appear nowhere else (0.03 of
  the 58 for 「、」). So the check now asks the memory which items it writes as charges — a
  complete answer, or a unit of an answer joined by that separator — and treats the rest as
  pieces of a longer name, reporting a piece only when the answer writes it as a charge of
  its own (a stretch between the joining separators) and quoting the memory's spelling of
  the whole name.

- Measured offline before evaluating, on the 492 recorded first passes of the six earlier
  runs, against the profile they were scored against
  ([[/workspace/runs/37a3ebb74a30bacfa2ab2379c86fa408af47a2fd/LawBench/memory.json]]): the
  check fires 147 times against the parent's 142, all 5 new notices on wrong first passes,
  and 0 of the 173 correct first passes fire in either version. The new branch can only be
  reached by an item the memory never writes as a charge, and neither the 50 val targets nor
  the 200 training targets has a stretch that is one of the 58 pieces, so an answer that
  reproduces the memory's wording cannot trip it; the parent's notices are all still written
  (nothing is lost to the new branch).

- The intended effect happened in the run and is attributable: the run drew 30 notices
  against the parent's 25, none on a correct first pass, 19 of them converted against 18,
  and two are notices only the new rule can write — 「窝藏」 -> 「窝藏、包庇」
  ([[/workspace/runs/b000c8efdc1973bb7b24cd9430e5f9a612f2bf24/LawBench/conversations/0014/sample-0.json]])
  and 「拐卖妇女」 -> 「拐卖妇女、儿童」
  ([[/workspace/runs/b000c8efdc1973bb7b24cd9430e5f9a612f2bf24/LawBench/conversations/0036/sample-0.json]]),
  both correct after the rewrite. The parent's rules stayed silent on that exact first pass
  and the sample stayed wrong
  ([[/workspace/runs/cd1bd0d40a39e7f9807fa0f12a58902c73abec2d/LawBench/conversations/0036/sample-0.json]]),
  and the same shape cost the parent's neighbour run a sample one example over
  ([[/workspace/runs/8b90b9c533d81d047bcfa360458b9b5b1f664fb9/LawBench/conversations/0014/sample-1.json]]:
  first pass 「窝藏」, no notice, target 「窝藏、包庇」).

- The average did not move (0.5333 -> 0.5333) and LawBench fell 0.52 -> 0.48 on the model's
  own first passes, not on the mechanism: only 29 of this run's 98 first passes were right
  against the parent's 34 of 97, and every one of the 9 correct->wrong flips had a wrong
  first pass in this run. On the 59 samples whose first pass was identical in both runs the
  candidate reversed none and gained exactly the one sample the parent could not fix
  (conversations/0036/sample-0). USPTO 0.20 -> 0.25 and Symptom2Disease 0.88 -> 0.87 are
  spread where the change cannot fire at all: neither of their memories holds a separator, so
  no item is ever a piece of a longer name (155 predictions, 0 notices), and this lineage has
  measured USPTO between 0.20 and 0.2833 across runs that never touched it
  ([[/workspace/runs/b000c8efdc1973bb7b24cd9430e5f9a612f2bf24/results/summary.json]]).

- Additional finding, the next step this run's evidence points at: the composition quote the
  parent introduced can still pull a charge into a correct answer. ex0045/0's first pass
  「过失致人死亡罪」 drew the notice "the memory writes that charge only inside the complete
  answer 「过失致人死亡;破坏生产经营」", and the model copied the extra charge and lost the
  sample ([[/workspace/runs/b000c8efdc1973bb7b24cd9430e5f9a612f2bf24/LawBench/conversations/0045/sample-0.json]]);
  the parent's run of the same question had a correct first pass and scored it
  ([[/workspace/runs/cd1bd0d40a39e7f9807fa0f12a58902c73abec2d/LawBench/conversations/0045/sample-0.json]]).
  The quoted answer is a composition of two charges the memory joins with its joining
  separator, while the quotes that help — 「窝藏、包庇」, 「虚开增值税专用发票、用于骗取出口退税、抵扣税款发票」
  — are answers the memory writes as one charge; the check does not use that distinction yet,
  and the reading it now has of which answers are single charges is what it would need.

## Round 8
- branch: `codex/answer-unwritten-ending` | commit `a311512caa2aaa9eed919dc914ac8b9473ba30f8` | tree `4383c6264deaf3410877e957b8f891f1f3da2936`
- score: average 0.5455555555555556 | USPTO 0.21666666666666667, Symptom2Disease 0.88, LawBench 0.54
- commit message: Issue: The ending rule reports an item that ends the way no memory item ends only when the memory also writes the rest of the item — as one of the parts its answers are made of, or as a near-variant of one of its items — so a charge the memory writes no spelling of at all is passed over in silence, which is where the largest remaining wording family sits. On the parent (5402cb1) that is both samples of ex0003: 「破坏电力设备罪」 against the target 「破坏电力设备」, no notice on either (/workspace/runs/b000c8efdc1973bb7b24cd9430e5f9a612f2bf24/LawBench/conversations/0003/sample-0.json). Measured offline over the 688 recorded first passes of the seven runs that carry an answer profile (bca9cc83 ... b000c8ef), 45 of them write a charge with a trailing 「罪」 that the parent's check stays silent on and would land exactly on the target once the character is dropped (破坏电力设备罪 -> 破坏电力设备, 销售假冒注册商标的商品罪 -> 销售假冒注册商标的商品, 以危险方法危害公共安全罪 -> 以危险方法危害公共安全, 非法运输毒品原植物种子罪 -> 非法运输毒品原植物种子, ...), 5 to 10 per run; the character is the one piece of evidence the memory does give, since 0 of its 175 items ends with 「罪」 while 5 of them carry it. Modification: `answer_conventions._unwritten_ending_notice` — a new branch of `answer_notice` that reports an item on the memory's ending alone. It fires when the answer writes the item as a charge of its own (a stretch between the joining separators), the last character never ends a memory item but is carried by at least two of them (so one item's spelling cannot be all there is to it), the remainder is at least as long as the shortest item the memory writes (the character is dropped rather than the charge), and no longer memory spelling contains the item (a longer spelling means the charge is a piece of a name, which the piece rules report). The rule is reachable only after the existing ending rule and the near-variant reading have both declined, reads no key the profile did not already carry, and is derived from the memory's own statistics, not from any task. Results: {"evaluation_result": {"USPTO": 0.2167, "Symptom2Disease": 0.88, "LawBench": 0.54, "average": 0.5456, "status": "partial"}, "message": "The expected effect occurred and is attributable. LawBench 0.48 -> 0.54 (54/100 against the parent's 48, the highest of the nine runs), average 0.5333 -> 0.5456. The run drew the same 30 notices as the parent; 8 of them carry the new branch, 3 of those converted (ex0003 both samples 「破坏电力设备罪」 -> 「破坏电力设备」, ex0007 sample-0 「持有伪造的发票罪」 -> 「持有伪造的发票」) and none fell on an answer that was already right. The two samples of ex0003 are the cleanest attribution: the parent's first pass was the same string and drew no notice at all. USPTO 0.25 -> 0.2167 cannot be this change — the memory is not vocabulary-like there and 0 of its 417 recorded first passes differ under the new code — it is the 0.20-0.2833 spread those runs have always shown."}

**Note**

# Evolution Notes

- Chosen from the parent's own evidence rather than from a new guess. The parent's ending
  rule only speaks when the memory also writes the rest of the item — as one of the parts
  its answers are made of, or as a near-variant of one of its items — and every remaining
  wording family with no memory spelling behind it therefore passed in silence. The
  evidence the memory does give about an item it never writes is its ending: 0 of its 175
  items ends with 「罪」 while 5 of them carry the character, so 20% of the answer items in
  the recorded runs add a character the memory's wording drops. The intent was to let that
  statistic stand on its own, under guards that keep it off a charge the answer did not
  write as a charge of its own, off a one-item accident of spelling (the character must be
  carried by two items), off a remainder too short to be an item (the character is dropped,
  not the charge) and off a piece of a longer name the memory does write.

- Measured offline before evaluating, on the 688 recorded first passes of the seven runs
  that carry an answer profile ([[/workspace/runs/b000c8efdc1973bb7b24cd9430e5f9a612f2bf24/LawBench/memory.json]]):
  the check fires on 45 first passes the parent's stays silent on, 5 to 10 per run, and 20
  of them land exactly on the target once the character is dropped; 0 of the 232
  exactly-correct first passes fire in either version, and nothing fires on the memory's
  own 143 answers or on any of the 46 val targets. The two val targets the guards remove
  are 「窃取、收买、非法提供信用卡信息」 (the item 「窃取」 ends with a character carried by
  4 items) and 「故意伤害;帮助毁灭、伪造证据」 (「帮助毁灭、伪造证据」 ends with one carried
  by a single item) — both would have been told to drop a character the target keeps.

- The intended effect happened in the run and is attributable: LawBench 0.48 -> 0.54
  (54/100 against the parent's 48, the highest LawBench of the nine runs) and average
  0.5333 -> 0.5456. The run drew the same 30 notices as the parent, 8 of them carrying the
  new branch, 3 of them converted, and none on an answer that was already right. The
  cleanest attribution is ex0003, whose first pass was the identical string in both runs:
  the parent drew no notice and stayed wrong on both samples and the new branch corrected
  both to the memory's wording
  ([[/workspace/runs/b000c8efdc1973bb7b24cd9430e5f9a612f2bf24/LawBench/conversations/0003/sample-0.json]]:
  「破坏电力设备罪」 no notice, wrong;
  [[/workspace/runs/4383c6264deaf3410877e957b8f891f1f3da2936/LawBench/conversations/0003/sample-0.json]]:
  「破坏电力设备罪」 -> 「破坏电力设备」, right). ex0007/sample-0 is the same shape one charge
  over: the parent's notice named only 「虚开增值税专用发票罪」 and the answer lost the other
  charge, while the new branch reported 「持有伪造的发票罪」 and the memory's wording came back
  whole ([[/workspace/runs/4383c6264deaf3410877e957b8f891f1f3da2936/LawBench/conversations/0007/sample-0.json]]).

- The five new-branch notices that did not convert are answers whose remaining error is a
  different charge, not a different ending — 「非法运输毒品原植物种子罪」 -> 「非法运输毒品原植物种子」
  against a target of 「非法买卖、运输、携带、持有毒品原植物种子、幼苗」, and 「销售假冒注册商标的商品罪」
  against 「生产、销售伪劣产品」 — so the branch is at the limit of what an ending can fix, and the
  subset of the wrong answers that drop a charge (112 of the 688 first passes, 2 of them
  reported) is still out of its reach. The other two tasks are untouched by construction: the
  new code changes 0 of the 417 recorded USPTO and 0 of the 659 Symptom2Disease first passes,
  and USPTO's 0.25 -> 0.2167 is the 0.20-0.2833 spread those runs have always shown rather
  than an effect of this change.

## Round 9
- branch: `codex/whole-memory-quotes` | commit `cadc26b582d0fb65eab6408437e01fd8e5231129` | tree `ceeb3c6c371878d0818744024906d9acd941dc6a`
- score: average 0.5266666666666667 | USPTO 0.2, Symptom2Disease 0.87, LawBench 0.51
- commit message: Issue: The memory the solver copies its answer wording from is read through one tool call whose output the framework inlines only below 20,000 tokens — 80,000 characters at the four characters per token its eviction assumes — so the harness's 30,000-character budget gave away wording it could have served. On the parent (a311512) the retrieved answers carry 55 of the 85 charges the 50 LawBench val targets are made of (67%) where the whole memory carries 70 (82%), and 14 of the 100 samples have their exact target answer in the memory and not in the context (ex9 「赌博;开设赌场」, ex33 「拐骗儿童」, ex40 「生产、销售伪劣产品」 — the last two wrong in all nine runs). A second defect sat in the way the memory's longer answers are quoted: the composition quote names the memory's complete answer even when the memory writes the charge inside an answer that joins several charges, and the model then writes charges it never identified — ex0045/0 drew "the memory writes that charge only inside the complete answer 「过失致人死亡;破坏生产经营」" and answered 「过失致人死亡;破坏生产经营」 (/workspace/runs/b000c8efdc1973bb7b24cd9430e5f9a612f2bf24/LawBench/conversations/0045/sample-0.json), and the same shape turned ex12.1 and ex44.1 one run earlier (/workspace/runs/8b90b9c533d81d047bcfa360458b9b5b1f664fb9/LawBench/conversations/0012/sample-1.json). Measured offline over the 800 recorded first passes of the eight earlier runs, the quote change leaves 0 notices on a first pass that reproduces the target and alters 3 of the 283 notices, all three to a quote of the memory's own spelling of the charge. Modification: `retrieval.MAX_CHARS` 30000 -> 200000, so what is served is the memory itself in similarity order rather than the most similar slice of it; and `answer_conventions._compositions` takes the memory's joining separator and declines every answer that joins several charges, so such an answer contributes the charge's own quote and not its other charges. Results: {"evaluation_result": {"USPTO": 0.2, "Symptom2Disease": 0.87, "LawBench": 0.51, "average": 0.5267, "status": "partial"}, "message": "The expected effect did not occur; the mechanism was blocked before it reached the model. The smaller change is confirmed and the larger one is the reason: the intent to serve the whole memory overshot the framework's own tool-result ceiling, 97 of the 100 LawBench samples got a head-and-tail preview stub instead of the examples ('Tool result too large ... saved in the filesystem', /workspace/runs/ceeb3c6c371878d0818744024906d9acd941dc6a/LawBench/conversations/0014/sample-0.json), so the run is a test of a two-example context and not of the change: first passes fell to 21 of 100 from the parent's 37 while the check drew 58 notices against 30 and converted 28 against 15, LawBench scored 51/100 against 54, and the average fell 0.5456 -> 0.5267. The preview also emptied the text the composition quote is allowed to draw from, which is where the samples went: ex14.0/1 drew 'the memory writes it as 「窝藏」(1 occurrence)' and answered the fragment 「窝藏」 where the parent, reading the same first pass, quoted 「窝藏、包庇」 and scored both (conversations/0014/sample-0.json); ex36.0/1, ex27.0 and ex38.1 are the same loss one charge over. USPTO 0.2167 -> 0.20 and Symptom2Disease 0.88 -> 0.87 cannot be this change — their memories are 8,665 and 34,178 characters, no tool result of theirs was offloaded and 0 of their recorded first passes differ under the new code — they are the spread those runs have always shown."}

**Note**

# Evolution Notes

- Chosen from the parent's own evidence rather than from a new guess, and aimed where the
  parent's note pointed: the check has no reach left (of the 800 recorded first passes of the
  eight earlier runs, every prefix, suffix, sub-run and fragment match of an answer item
  against the memory's items fires on correct first passes at least as often as on wrong ones
  and lands on the target 0 times), while the memory the solver copies its wording from is
  still mostly hidden. On the parent (a311512) the retrieved context carries 55 of the 85
  charges the 50 LawBench val targets are made of (67%) against 70 (82%) for the whole memory,
  and 14 of the 100 samples have their exact target answer in the memory and not in the
  context ([[/workspace/runs/4383c6264deaf3410877e957b8f891f1f3da2936/LawBench/memory.json]]).
  The parent served 30,000 of the memory's 105,318 characters, and the framework's own ceiling
  on a tool result was assumed to be above that.

- Measured offline before evaluating, on those 800 first passes: the composition-quote change
  (skip the answers that join several charges) alters 3 of the 283 notices and leaves 0
  notices on a first pass that reproduces the target, in either version — the joined quotes it
  removes are the ones that cost samples in the runs (ex0045/0 「过失致人死亡;破坏生产经营」
  [[/workspace/runs/b000c8efdc1973bb7b24cd9430e5f9a612f2bf24/LawBench/conversations/0045/sample-0.json]],
  ex0044/1 「强奸;侮辱」
  [[/workspace/runs/8b90b9c533d81d047bcfa360458b9b5b1f664fb9/LawBench/conversations/0044/sample-1.json]]),
  and the single-charge quotes it keeps are the ones that help (ex0007/0 「虚开增值税专用发票、
  用于骗取出口退税、抵扣税款发票」). The budget change was expected to be the larger of the two
  and was not checked against the framework it runs in.

- The expected effect did not occur, and the reason is a ceiling the change crossed: the
  framework inlines a tool result only up to `tool_token_limit_before_evict` = 20,000 tokens,
  four characters per token, i.e. 80,000 characters
  ([[/opt/venv/lib/python3.11/site-packages/deepagents/middleware/filesystem.py]]:1650,
  :3212). A 105,316-character retrieval result is offloaded to `/large_tool_results/...` and
  replaced by a head-and-tail preview, so 97 of the 100 LawBench samples answered from about
  two examples instead of fifty: first passes fell to 21 of 100 against the parent's 37, the
  check drew 58 notices against 30 and converted 28 against 15, LawBench 54 -> 51 and the
  average 0.5456 -> 0.5267. The run therefore measures a two-example context, not the change
  ([[/workspace/runs/ceeb3c6c371878d0818744024906d9acd941dc6a/LawBench/conversations/0014/sample-0.json]]:
  the retrieval tool message is the offload stub, and its preview holds two of the memory's
  answers).

- The samples lost are the sharpest evidence that the ceiling, and not the quote rule, is what
  went wrong: the preview is also the text the composition quote is allowed to draw from, so
  the rule could no longer quote and fell back to the memory item on its own. ex14.0/1 drew
  "the memory writes it as 「窝藏」(1 occurrence)" and answered the fragment 「窝藏」; the parent,
  reading the identical first pass 「窝藏罪」, quoted 「窝藏、包庇」 and scored both
  ([[/workspace/runs/4383c6264deaf3410877e957b8f891f1f3da2936/LawBench/conversations/0014/sample-0.json]]
  against the candidate's same path). ex36.0/1, ex27.0 and ex38.1 are the same loss one charge
  over; 7 samples were lost and 4 gained, and the 4 include ex13.0, whose joined quote was
  suppressed exactly as intended but which the model then corrected anyway.

- Untouched and explained elsewhere: USPTO 0.2167 -> 0.20 and Symptom2Disease 0.88 -> 0.87 got
  0 offloaded tool results — their memories are 8,665 and 34,178 characters, under the ceiling —
  and 0 of their recorded first passes differ under the new code, so their movement is the
  spread this lineage has measured before (USPTO has been between 0.20 and 0.2833 across runs
  that never touched it). LawBench lost one further sample to a provider content_filter
  rejection.

- The limit this run establishes, and the next step it points at: the retrieval tool's output
  cannot exceed 80,000 characters on this framework, so the memory can be served only up to
  that bound — 75,000 characters is the safe budget, and on the same 50 val questions it serves
  129.1 of the 200 LawBench examples on average, 80.0% of the target charges (against 67% at
  30,000) and the exact target answer for 28 of the 50 (against 23), while staying under the
  ceiling for the other two tasks as well. Serving more requires either splitting the retrieval
  over several tool calls the model must be told to make, or raising
  `tool_token_limit_before_evict` where the agent is built. The composition-quote change itself
  is untested by this run and remains a candidate: it was measured offline as a strict
  improvement on the recorded corpus, and no sample in this run can be attributed to it.

## Round 10
- branch: `codex/inline-budget` | commit `bc19c512eb5b9e86cc09bd5cc3f28235b1452ad5` | tree `84fb7ecd4aa0f4a1ab2a71b3fec90e281f407964`
- score: average 0.5311111111111111 | USPTO 0.18333333333333332, Symptom2Disease 0.89, LawBench 0.52
- commit message: Issue: The examples the solver copies its answer wording from are read through one tool call whose result this framework inlines only below 20,000 tokens — four characters per token, i.e. 80,000 characters (/opt/venv/lib/python3.11/site-packages/deepagents/middleware/filesystem.py:926, :1650, :3213) — and the parent set `retrieval.MAX_CHARS` at 200,000, above that ceiling. On the parent (cadc26b) 97 of the 100 LawBench samples never saw the examples at all: the result was offloaded to `/large_tool_results/...` and replaced by a head-and-tail preview of two examples ("Tool result too large ... saved in the filesystem", /workspace/runs/ceeb3c6c371878d0818744024906d9acd941dc6a/LawBench/conversations/0014/sample-0.json), so that run measured a two-example context: first passes fell to 21 of 100 from the parent's 37, the check drew 58 notices against 30, and the average fell 0.5456 -> 0.5267. The bound the harness serves under is therefore not the harness's to choose — everything above it is a preview — and the previous run's intent to hand over the memory itself can only be carried out inside it. Modification: `retrieval.MAX_CHARS` 200000 -> 75000, the framework's inline limit with headroom, documented as such; what is served is unchanged in kind (the memory ranked by similarity, closest first, cut only where the framework would have cut it), but for the two memories that fit under the bound it is now the whole memory rather than a slice of it (USPTO 8,663 characters, Symptom2Disease 34,176), and for LawBench it is 133.6 of the 200 examples against 52.2, 80.0% of the target charges against 70.6%. Results: {"evaluation_result": {"USPTO": 0.1833, "Symptom2Disease": 0.89, "LawBench": 0.52, "average": 0.5311, "status": "partial"}, "message": "The expected effect did not occur, and its mechanism is separable from its cost. The ceiling was the defect and is fixed: 0 of the 100 LawBench results were offloaded against the parent's 97, the retrieved set is inlined whole at 74,940 characters, and the served text per sample rose 28,546 -> 72,976 characters. But the larger budget bought nothing measurable — the model reads the closest examples and ignores the rest — while it cost samples to the provider's content filter. On the samples that ran, the two runs are the same workload: the check drew 29 notices and converted 15 on the parent against 30 and 14 here, first passes 37 against 36, and the two samples gained (ex13.0, ex16.0) are samples the parent lost to content_filter rather than conversions (conversations/0013/sample-0.json). USPTO cannot have moved: its memory is 8,663 characters and is served identically under both bounds, so 11 of 60 against 13 is the spread those runs have always shown. What did follow from the change is the filter: the served text carries twice as much case text on the subjects the provider filters (16.9 -> 32.8 occurrences per sample) and the run drew 6 content_filter failures against the parent's 3 and the 2.1 the eleven runs average, each of which stays in the denominator as a wrong answer, so LawBench's 52 of 100 is 55.3% of the 94 samples that ran against the parent's 55.7% of 97. Average 0.5456 (a311512) -> 0.5267 (cadc26b) -> 0.5311."}

**Note**

# Evolution Notes

- Chosen from the parent's own evidence rather than from a new guess: the ceiling was the one
  thing the parent's change left untested and its failure was total. The parent's budget change
  had been measured as an improvement offline (80.0% of the target charges against 67%) and then
  never reached the model, because this framework inlines a tool result only below four
  characters per token of its 20,000-token eviction limit — 80,000 characters
  ([[/opt/venv/lib/python3.11/site-packages/deepagents/middleware/filesystem.py]]:926, :1650,
  :3213). The intent was to keep the parent's other half (the composition quote that declines the
  answers joining several charges) and put the budget at the largest the framework inlines,
  75,000: a memory that fits is then served whole and a larger one is cut only where the
  framework would have cut it. Offline over the same 50 val questions that is 133.6 of the 200
  LawBench examples against 52.2, 80.0% of the target charges against 70.6%, the exact target
  answer in context for 28 questions against 25, and the whole memory of the other two tasks at
  the same 30,000 ([[/workspace/runs/4383c6264deaf3410877e957b8f891f1f3da2936/LawBench/memory.json]]).

- The ceiling is fixed and is all that is fixed. No LawBench result was offloaded this run — 0 of
  100 samples against the parent's 97 — and the retrieved set arrives as one tool message of
  74,940 characters holding 138 examples
  ([[/workspace/runs/84fb7ecd4aa0f4a1ab2a71b3fec90e281f407964/LawBench/conversations/0014/sample-0.json]]),
  so the mean served text per sample went 28,546 -> 72,976 characters. Nothing else moved: the check
  drew 30 notices and converted 14 where the parent drew 29 and converted 15, and first passes were
  36 against 37. The check is provably insensitive to the budget it reads from — measured offline
  over the recorded first passes of four runs, moving the text the quote may be drawn from from the
  30,000-character context to the 75,000-character one gains and loses 0 notices — so this run
  tests the model's reading of the examples and nothing else.

- What the model does with the extra examples is nothing, because the ones a larger budget adds are
  the least similar and the copies it makes come from the top of the ranking: over the parent's 97
  first passes the answer the model writes is an example's answer at median rank 4, and 47 of its
  52 exact copies are inside the 52 examples the parent already served. The two samples gained
  (ex13.0, ex16.0) are samples the parent lost to a content filter rather than conversions
  ([[/workspace/runs/4383c6264deaf3410877e957b8f891f1f3da2936/LawBench/conversations/0013/sample-0.json]]),
  and the two lost on the same sample set are first-pass differences the check then worked on:
  ex7.0's first pass held one charge where the parent's held two, and the notice quoted the memory's
  complete answer for that one charge, which is how it finished
  ([[/workspace/runs/84fb7ecd4aa0f4a1ab2a71b3fec90e281f407964/LawBench/conversations/0007/sample-0.json]]
  against the same path in the parent).

- The cost of the extra text is the provider's content filter, and it is measurable: the served text
  of a sample carries twice as much case text on the subjects the filter reacts to (16.9 -> 32.8
  occurrences per sample of the vocabulary of such cases), and this run drew 6 content_filter
  failures against the parent's 3 and the 2.1 the eleven runs average, each of which stays in the
  denominator as a wrong answer ([[/workspace/runs/84fb7ecd4aa0f4a1ab2a71b3fec90e281f407964/results/summary.json]]).
  That is why LawBench reads 52 of 100: of the 94 samples that ran, 55.3% are correct against the
  parent's 55.7% of 97 — the same workload, three more samples the harness cannot reach.

- Untouched and explained: USPTO's memory is 8,663 characters and is served whole under both
  budgets, so its retrieval output is identical in the two runs and 0 of its 60 samples can differ
  under this change; 11 correct against 13 is the 0.1833-0.2833 spread the ten earlier runs have
  shown. Symptom2Disease's memory is 34,176 characters, of which the parent served 171.3 of 200
  examples and this run all 200; the 29 added are the least similar and the task moved 88 -> 89 of
  100. The composition-quote half of the parent's change is exercised here for the first time: 7
  notices carry a composition quote against the parent's 8, and where the parent named a joined
  answer (「非法采伐、毁坏国家重点保护植物;非法占用农用地」 for ex13.1, 「窝藏、包庇」 for ex14.1) the notice
  now names the charge's own spelling, both samples being correct in both runs; no sample here can
  be attributed to that rule. The limit this run leaves for the next step is that the budget is a
  bound and not a lever: what the solver gains from the memory is what the top of the ranking holds,
  and the rest is text the framework and the provider both charge for.

## Round 11
- branch: `codex/answer-form-repair` | commit `f071ba28b32bbf7dbef57c8d8947827fe7831363` | tree `8ccc11393d600b9e48147fab5c3c03829576e8fc`
- score: average 0.5133333333333333 | USPTO 0.15, Symptom2Disease 0.88, LawBench 0.51
- commit message: Issue: The answer the check compares with the memory's wording is only there when the model puts it in the object the task asks for, and a turn that ends without one is repaired by nothing: the runner's fallback converts the free-form reply with a separate no-think model call that never saw the case (/workspace/benchmark/runtime/worker.py:76, :158 — "Convert the following answer into a JSON object with exactly two string fields ... Copy the answer content unchanged"), which is measurably lossy exactly where the model had the answer in hand. On the parent (bc19c51) ex0020 answered a retrosynthesis question with "[DIAGNOSIS]No explicit final answer or diagnosis provided in the source text.[/DIAGNOSIS]" — the markup of the converter's own instructions wrapped around the converter's own commentary (/workspace/runs/84fb7ecd4aa0f4a1ab2a71b3fec90e281f407964/USPTO/conversations/0020/sample-0.json) — and ex0021 with the half-sentence "Looking at the examples for \"Heteroatom alkylation and arylation,\" I can see the pattern:" (conversations/0021/sample-0.json). The harness's own check reads `final_answer_field(text)`, which is empty for prose, so it returns nothing and the turn ends unchecked. Measured over the eleven recorded runs, 10 samples end that way — the reply carries no `final_answer` and none of the memory's wording anywhere in its text (6 USPTO, 3 Symptom2Disease, 1 LawBench) — and 9 of the 10 scored wrong. Modification: `answer_verification` — a second kind of repair on the same one-turn budget. A turn that ends with no `final_answer` field and no wording the memory writes anywhere in its text is asked for the answer object, with the answer it identified. Whether the reply already states an answer is read off the memory itself — its items and its complete answers, compared case-insensitively — so a reply that carries one of them is the answer already, written the way the memory writes it, and is left alone; that guard is what keeps the repair off the 88 Symptom2Disease and 3 LawBench replies that state their answer in the task's own markup, 72 of them right. Nothing else changed: the wording check, its quotes and the retrieval are the parent's. Results: {"evaluation_result": {"USPTO": 0.15, "Symptom2Disease": 0.88, "LawBench": 0.51, "average": 0.5133, "status": "partial"}, "message": "The expected effect did not occur, and this run could not have shown it: the new branch fired on nothing. Only Symptom2Disease and LawBench ended a turn without an answer object at all (5 samples and 1), every one of those replies carried the memory's wording in its text — a diagnosis, a charge — so the guard kept the check off them, and USPTO, where the converter's loss is worst, ended no turn that way; the harness therefore ran as the parent did and the difference is the spread. Average 0.5311 -> 0.5133 (USPTO 0.1833 -> 0.15, Symptom2Disease 0.89 -> 0.88, LawBench 0.52 -> 0.51); paired over the same examples USPTO is 3 samples gained against 5 lost, Symptom2Disease 0 against 1, LawBench 2 against 1, which is the order of the noise two runs of this harness show where nothing at all differs — a311512 and bc19c51 served USPTO the identical 8,663-character memory, whole under both bounds, and still disagreed on 10 of 60 samples, 6 one way and 4 the other. The run does settle where LawBench's remaining loss sits: 27 of the 59 target charges the parent's answers missed were written in a retrieved answer the model had read (28 of 57 here) and were not written anyway, and 12 of the 50 val examples need a charge no training answer writes at all, for which the check has no wording to quote. The 8 content_filter failures against the parent's 6 are not evidence about the harness: all 8 have exactly three messages (system, user, failed turn), so they fail on the first call, before any tool result exists, and cannot be caused by what the retrieval served."}

**Note**

# Evolution Notes

- The check the harness owns can only speak about an answer it can read, and the reading it
  does — `final_answer_field`, i.e. an object with a `final_answer` field — is not the only
  form the answer arrives in. A turn that ends without one is handed to the runner's
  fallback, a separate no-think model call with no case in front of it
  ([[/workspace/benchmark/runtime/worker.py]]:76, called at :158), and the parent's own run
  shows what that costs where the model had just worked the answer out: a retrosynthesis
  question answered with the converter's own markup around its own commentary
  ([[/workspace/runs/84fb7ecd4aa0f4a1ab2a71b3fec90e281f407964/USPTO/conversations/0020/sample-0.json]])
  and a heteroatom-alkylation question answered with the half-sentence the model had
  written about the examples
  ([[/workspace/runs/84fb7ecd4aa0f4a1ab2a71b3fec90e281f407964/USPTO/conversations/0021/sample-0.json]]).
  The change adds one repair for that turn: no `final_answer` field and none of the memory's
  wording anywhere in the text, and the model is asked for the answer object. Whether the
  reply already states an answer is decided from the memory itself — its items and its
  complete answers, compared case-insensitively — so the repair is off every reply that
  carries the memory's wording in plain words, which is what a Symptom2Disease answer
  ("[DIAGNOSIS]malaria[/DIAGNOSIS]") and a LawBench answer in the task's own markup both are.

- The intended effect did not occur, and the run could not have produced it: the branch
  fired on nothing. Replaying every recorded turn of the eleven earlier runs through the new
  decision put 10 samples in reach — 6 USPTO, 3 Symptom2Disease, 1 LawBench, value 9 of them
  wrong ([[/workspace/runs/4383c6264deaf3410877e957b8f891f1f3da2936/USPTO/conversations/0021/sample-0.json]],
  and the parent's two traces above) — but this run produced none of them: USPTO ended no
  turn without the object, and the 6 turns that did (5 Symptom2Disease, 1 LawBench) all
  carried the memory's wording in their text, so the guard kept the check off them. The
  harness therefore executed as the parent did, 27 wording notices against 30, and the score
  difference is the spread: average 0.5311 -> 0.5133, USPTO 0.1833 -> 0.15 (one sample of 60
  lost to a timeout), Symptom2Disease 0.89 -> 0.88, LawBench 0.52 -> 0.51. Paired over the
  same examples the candidate takes USPTO 3 samples and loses 5, takes Symptom2Disease 0 and
  loses 1, takes LawBench 2 and loses 1; the scale of that is on record inside the lineage —
  a311512 and bc19c51 served USPTO the identical 8,663-character memory, whole under both
  bounds, and still disagreed on 10 of 60 samples, 6 one way and 4 the other
  ([[/workspace/runs/4383c6264deaf3410877e957b8f891f1f3da2936/USPTO/conversations]],
  [[/workspace/runs/84fb7ecd4aa0f4a1ab2a71b3fec90e281f407964/USPTO/conversations]]).

- The 8 LawBench content_filter failures this run drew against the parent's 6 are not a
  property of the harness, and the parent's note reads its own 3 -> 6 the wrong way: every
  one of the 8 has exactly three messages — system, user, and the failed turn — so the
  request that was refused is the first one, carrying the case and nothing the harness
  retrieved
  ([[/workspace/runs/8ccc11393d600b9e48147fab5c3c03829576e8fc/LawBench/conversations/0002/sample-0.json]]).
  The served text cannot be the trigger, and the count moves between runs on samples that
  pass in other runs (ex0006 fails in three runs and passes in eight).

- Where the remaining LawBench loss actually sits, measured on both runs: of the target
  charges the answers missed, 27 of 59 (parent) and 28 of 57 (here) were written in a
  retrieved answer the model had read and were not written; and 12 of the 50 val examples
  need a charge no training answer writes at all (破坏电力设备, 重大劳动安全事故, 打击报复证人,
  走私、贩卖、运输、制造毒品, 伪造、变造金融票证, ...), for which the check has no wording to
  quote — the loss there is identification, not wording. The search that preceded this
  change measured and rejected the rules that would have reached for it, each on the 1074
  recorded LawBench first passes: a reply item that is a memory item with a piece deleted
  fires on 18 first passes that are already right; the memory's answer being a superset of
  the model's fires on 97; a charge the model mentions in its reasoning but does not write
  fires on 41 of the 362 right answers; the memory's co-occurrence with the charges already
  written puts a missing target charge first in 3 of 30; a second wording repair would find
  only 7 samples where the second quote lands; and relaxing the ending rule's "written as a
  charge of its own" guard buys 2 exact fixes in 1074 first passes (0 fires on the 50 val
  targets and the 143 memory answers, but too little to measure).

- The lead this run leaves is the turn the guard does suppress: this run's LawBench ex0046
  ended with the answer in the task's own markup inside a paragraph of prose —
  "[罪名]非法采伐国家重点保护植物罪<eoa>"
  ([[/workspace/runs/8ccc11393d600b9e48147fab5c3c03829576e8fc/LawBench/conversations/0046/sample-0.json]])
  — which the guard reads as "the memory's wording is in this text" and leaves alone, and
  which the converter then wraps into JSON unchanged. Read as an answer, that text draws the
  ending rule's quote of the memory's own 「非法采伐、毁坏国家重点保护植物」(1 occurrence), which
  is the target; reading the answer out of a reply rather than out of an object is the
  change that would reach it, and the same reading must not take the charges a reply's
  reasoning mentions for its answer (41 of the 362 right first passes do mention one).

## Round 12
- branch: `codex/retrieval-verification` | commit `921c06986dea35d021e7a932d15e855ace6cf12c` | tree `b51d7d5a29b630fb9527b066a5c1a0ade1313380`
- score: average 0.5366666666666666 | USPTO 0.15, Symptom2Disease 0.89, LawBench 0.57
- commit message: Issue: The wording the harness checks the answer against is read from a memory the model may never have opened, and nothing makes it open: `retrieve_examples` is offered and the prompt asks for it, but taking it is the model's choice, and the recorded runs show it declines often enough to matter. Measured over the twelve recorded runs, 176 of the 3,086 samples that ran to completion never consulted anything — no tool call, no tool result, a single model turn — 129 of USPTO's 718 (18%), 42 of LawBench's 1,169 (3.6%), 5 of Symptom2Disease's 1,199, and they are worse on every task: USPTO 18/129 = 14.0% against 141/589 = 23.9% for the samples that did read, LawBench 12/42 = 28.6% against 557/1,127 = 49.4%, Symptom2Disease 1/5 against 1,036/1,194 = 86.8%. The gap is not a property of the cases: paired within the same (example, sample) cell, the two modes write different answers in 36 of USPTO's 55 mixed cells and identical ones in only 3, and the cell is right only where the examples were read in 18 cells against 0 the other way (LawBench: 7 against 0). Reading the memory is what moves the answer, and it moves it onto the target. The check is downstream of that read — it quotes the memory back at the model — and when the turn has read nothing it quotes a memory the model never saw, since `answer_conventions.answer_notice`'s `seen` guard admits any quote when the text the model has read is empty. The parent's run has the shape on record: /workspace/runs/8ccc11393d600b9e48147fab5c3c03829576e8fc/USPTO/conversations/0004/sample-0.json is one model turn and no tool call, answered from the model's own prior about the chemistry.

**Note**

# Evolution Notes

- The change was chosen because reading the memory is the premise the whole check rests on and it was left to the model: 176 of the 3,086 completed samples across the twelve recorded runs never consulted anything, and they score 14% against 24% on USPTO, 29% against 49% on LawBench and 20% against 87% on Symptom2Disease. The intent was to spend one turn on making that read happen before the answer is checked or accepted, leaving the wording check, its quotes and the retrieval itself alone.
- The branch reached its population and changed nothing in it: the run's 15 no-tool samples (12 USPTO, 3 LawBench) were all sent back for the examples and all read them, and the 14 cells the parent also ran came out identical — 11 USPTO wrong in both, 3 LawBench right in both, none gained and none lost. [[/workspace/runs/b51d7d5a29b630fb9527b066a5c1a0ade1313380/USPTO/conversations/0019/sample-0.json]]
- Reading does move the answer, just not onto the target: the post-reading answer differs from the one the model was finishing with in 6 of the 15, and in three of those it reproduces exactly what the parent wrote when it had retrieved unprompted; in the other 9 the model re-emits its answer unchanged. The skipped samples are ones the model is confidently wrong about, so their deficit is a marker of hard cases rather than a cause the harness can remove. [[/workspace/runs/b51d7d5a29b630fb9527b066a5c1a0ade1313380/USPTO/conversations/0029/sample-1.json]] [[/workspace/runs/b51d7d5a29b630fb9527b066a5c1a0ade1313380/USPTO/conversations/0006/sample-1.json]]
- The scored rise (average 0.5133 -> 0.5367, LawBench 0.51 -> 0.57, the highest of the thirteen runs) is not attributable to the change: the branch touched 15 of the 249 scored samples, and the 234 it did not touch disagree between the two runs 7 gained against 4 lost, which is the run-to-run spread of identical code (a311512 and bc19c51 served USPTO the identical memory and still disagreed on 10 of 60). The population itself also varies run to run — 27 no-tool samples in the parent against 15 here, overlapping in only 3 cells — so one run bounds this mechanism from neither side. [[/workspace/runs/b51d7d5a29b630fb9527b066a5c1a0ade1313380/results/summary.json]]
- What the run does settle is where the remaining loss sits, and it is not wording: the branch's 12 USPTO samples had an answer already formed and none of them reached the target even after reading all 50 training examples, and the LawBench cells it fired on were already right in both runs. The check in `answer_conventions` is also at the limit of what the frozen memory can say — the val targets include charges no training answer writes at all (重大劳动安全事故, 破坏电力设备, 打击报复证人: 12 of the 50 examples), and there the check has no wording to quote. [[/workspace/runs/b51d7d5a29b630fb9527b066a5c1a0ade1313380/LawBench/conversations/0024/sample-0.json]]

## Round 13
- branch: `codex/consensus-draws` | commit `794d93ebe9a26d4b2fb5fc9d740471f08e5b8006` | tree `4b32c77ad6d053ba5a659c5ffad4a41250700043`
- score: average 0.5411111111111111 | USPTO 0.2833333333333333, Symptom2Disease 0.88, LawBench 0.46
- commit message: Issue: The answer the harness reports for a question is one draw of a distribution it never looks at. Two samples of the same question over the same frozen memory — same prompt, same examples, same configuration — agree on the answer in 24.0% of the questions whose answer is free text (388 completed pairs), 81.4% of those whose answer is a list of items (619) and 95.4% of those whose answer is a single item (649), and the same two samples disagree about whether the question was answered correctly in 14.7%, 9.0% and 2.5% of them. The runner draws two samples per question and the harness answers each of them once, so what is scored is a sample of that distribution rather than the model's own answer to the question: across the thirteen recorded runs one question of the free-text task was answered 16.2 different ways over its 26 draws, and 15 of its 30 questions were drawn right at least once and wrong at least once. Nothing in the harness addresses that: the reading turn, the wording check and the repair all act inside the draw the harness has already taken, and none of them takes a second look at a question the model has answered differently every time it was asked. What a second look would be worth is measurable offline over the 3,343 answers the thirteen runs hold — the answer five draws agree on is the right one for 27.9% of the free-text questions, 54.6% of the item-list questions and 88.0% of the single-item questions, against 21.6%, 49.5% and 86.7% for a single draw — and most of it is already there at three draws (25.2%, 52.1%, 88.0%).

**Note**

# Evolution Notes

- The change was chosen because every mechanism this harness has built so far acts inside a single draw of a question the model does not answer reproducibly: the reading turn and the wording check both operate on the one conversation the harness happened to take, and nothing in the lineage has ever taken a second one. Two samples of the same question over the same memory agree on the answer in 24.0% of the free-text questions (388 pairs), 81.4% of the item-list questions (619) and 95.4% of the single-item questions (649), and the offline mode of five draws over the 3,343 recorded answers is right 27.9%, 54.6% and 88.0% of the time against 21.6%, 49.5% and 86.7% for one draw — so the intent was to report the answer the draws agree on while leaving every other mechanism in place, each draw passing through the same reading turn, the same wording check and the same repair the single draw did.
- The mechanism ran and the vote is the reason the free-text task is where it is. Paired inside the run, the vote is right more often than the draws it was held among on all three tasks: USPTO 17/60 = 28.3% against 65/290 = 22.4%, LawBench 46/78 = 59.0% against 198/344 = 57.6%, Symptom2Disease 88/100 = 88.0% against 405/463 = 87.5%; 21 samples came out right where the draws were not all right against 9 that came out wrong where some draw carried the target. USPTO ex0000/sample-1 is the shape: four of its five draws wrote the target and one dropped a character from it, and the vote returned the four. [[/workspace/runs/4b32c77ad6d053ba5a659c5ffad4a41250700043/USPTO/conversations/0000/sample-1.json]] [[/workspace/runs/4b32c77ad6d053ba5a659c5ffad4a41250700043/results/summary.json]]
- The vote settles a question the draws split on, which is where the item-list task gained: LawBench ex0031/sample-0 had its four draws split over three different pairs of charges — 盗窃;妨害公务, 盗窃;破坏交通工具, and 盗窃;以危险方法危害公共安全 twice — and the vote took the pair written twice, which is the target; ex0007/sample-1 is the same with three of five draws on the target. [[/workspace/runs/4b32c77ad6d053ba5a659c5ffad4a41250700043/LawBench/conversations/0031/sample-0.json]] [[/workspace/runs/4b32c77ad6d053ba5a659c5ffad4a41250700043/LawBench/conversations/0007/sample-1.json]]
- The run lost 22 of LawBench's 100 samples to the provider, and they are in the denominator as wrong answers: every one of them is an `invalid_request` reading "Access denied, please make sure your account is in good standing ... overdue-payment", the denials begin at example 29 and run to the end of the task, and no run before this one has recorded a failure of that kind. The 78 samples that did run scored 59.0%, against the parent's 58.8% of 97, so the recorded LawBench score of 46/100 is the denials and not the change. [[/workspace/runs/4b32c77ad6d053ba5a659c5ffad4a41250700043/LawBench/conversations/0049/sample-0.json]]
- The cost that sits behind that failure is real and has to be read with it: five draws make 3,292 model calls and 51.7M input tokens for the run against the parent's 704 and 12.7M, and 1,844s of wall clock against 620s, which is five times the consumption on an account that stopped serving part-way through. A cheaper variant — three draws, or draws that share one retrieval — is not testable from this run, but the offline curve says three draws carry most of the gain (25.2%, 52.1%, 88.0%) and the next iteration should weigh that against the account's state.
- The single-item task is where the mechanism has nothing to do: 93 of its 100 samples had draws that were all identical, so the vote can only confirm what one draw already said, and the task moved 0.89 -> 0.88 (vote 88.0% against draws 87.5%). What the run does not settle is the residual it leaves everywhere else — the draws that were not taken, because a sample's 32 model calls ran out (USPTO had 8 samples with four draws and 1 with three) or because a draw was denied mid-question (LawBench's 78 samples hold 54 with five draws and 24 with fewer). [[/workspace/runs/4b32c77ad6d053ba5a659c5ffad4a41250700043/results/samples.jsonl]]

## Round 14
- branch: `codex/settled-draws` | commit `152cd1aad6f526fa156ecd4d74734b41d78cd11d` | tree `f940a4539b030a2578c9c9ac5dae166cc557869b`
- score: average 0.0 | USPTO 0.0, Symptom2Disease 0.0, LawBench 0.0
- commit message: Issue: The harness spends the same five draws on every question, whether the draws agree or not, and the vote is the only mechanism in it whose value still moves with what it is given. Over the answers the fourteen recorded runs hold — every val question of every task carries one recorded answer per run — the answer the most of k draws carry is the right one for 22.2% of the free-text questions (USPTO), 50.4% of the item-list questions (LawBench) and 86.7% of the single-item questions (Symptom2Disease) at one draw, 25.8%, 53.1% and 87.9% at three, 28.1%, 55.1% and 88.1% at five, and 29.7%, 55.7% and 88.0% at seven; the curve is still rising at five on the two tasks that are not already near their ceiling. The last run's own draws say the same on the subset of its samples whose draws the recorded vote reproduces (37 USPTO, 67 LawBench, 100 Symptom2Disease): one draw is right for 31.4%, 50.4% and 82.7% of them, three for 38.0%, 55.6% and 86.4%, five for 41.9%, 56.7% and 88.0%. But 88% of the free-text samples' draws disagree with each other, and there is nothing in the harness that lets a question whose draws disagree have more of them: the same five are taken whatever the five say, so the questions that would be settled by one draw and the questions that would be settled by ten are charged alike, and the 32-call budget of a question is spent either way. Modification: `consensus.py` — the draws are taken in rounds (4, 2, 2, up to `MAX_DRAWS = 8`) and stop as soon as the answer cannot change. Two cases are read off the draws themselves and not off the subject matter: four draws carrying the same answer are that answer already while four more are still available, because the four can tie them at best and a tie goes to the earliest draw, which is one of the four; and a leader more than the number of draws still available ahead of the answer behind it cannot be caught. Anything else — a question whose draws are split against each other — is what the later rounds are for. The vote itself is unchanged: plurality over the draws taken, the earliest breaking a tie, agreement read the way the memory's answers are read. The retrieval, the reading turn, the wording check and the repair are the parent's, and so is the answer a question gets wherever the vote is already decided, which the rounds were verified not to change: over all 4^8 = 65,536 answer sequences the staged vote returns exactly the vote over all eight draws whenever it stops early. Results: {"evaluation_result": null, "message": "No measurement was taken, and the run that was to take it could not: 0 of the 260 samples ran. The first attempt (manifest.json started_at 1789594827, finished_at 1789594883) had every sample refused by the provider — invalid_request, \"Access denied, please make sure your account is in good standing ... overdue-payment\", 60 of 60 USPTO, 100 of 100 Symptom2Disease, 100 of 100 LawBench, with 0 input and 0 output tokens recorded for all of them — and by that the runner printed {USPTO 0.0, Symptom2Disease 0.0, LawBench 0.0, average 0.0, status error}, which is the account and not the harness. Two further attempts (21:56, 22:21) returned that same saved summary without re-running, because a sample that fails is still counted as attempted and the summary is therefore rankable; clearing results/summary.json forced the fourth attempt (22:22), which failed before the provider was reached: every sample is `execution_error` \"bwrap: Can't bind mount /oldroot/etc/ld.so.cache on /newroot/etc/ld.so.cache: Unable to mount source on destination: No such file or directory\", the sandbox never starts, and /proc/self/mountinfo shows why — /etc/ld.so.cache is mounted from ext4 with the source path recorded as \"/etc/ld.so.cache//deleted\", so the file the sandbox binds was replaced on the host while the container held it open, and bwrap cannot bind a deleted inode. The sandbox command fails the same way outside the runner. The change is therefore recorded unevaluated; the next iteration has to re-run this tree (or a descendant of it) to obtain the effect, and should read the runner's reuse rule before it does — a summary from an all-failed run is rankable and will be served back unless the results directory is cleared."}

**Note**

# Evolution Notes

- The change was chosen because the vote is the one mechanism in this harness whose value
  still moves with what it is given, and the harness gives every question the same amount of
  it. Pooling the answers the fourteen recorded runs hold — one recorded answer per val
  question per run, ~13 per question — the answer the most of k draws carry is right for
  22.2% of the free-text questions (USPTO), 50.4% of the item-list questions (LawBench) and
  86.7% of the single-item questions (Symptom2Disease) at one draw, 25.8%, 53.1% and 87.9%
  at three, 28.1%, 55.1% and 88.1% at five and 29.7%, 55.7% and 88.0% at seven. The parent's
  own draws agree with the curve on the samples whose draws its recorded vote reproduces (37
  USPTO, 67 LawBench, 100 Symptom2Disease): 31.4%, 50.4% and 82.7% at one draw against
  41.9%, 56.7% and 88.0% at five. Yet the parent takes exactly five draws of every question,
  and its draws are split against each other in 53 of USPTO's 60 samples, 20 of LawBench's
  78 and 7 of Symptom2Disease's 100 — so the questions that one draw would settle and the
  questions that more draws would settle are charged the same five, against the same
  32-call budget of a question.
- The mechanism is rounds of draws that stop as soon as the answer cannot change: four
  draws carrying the same answer are that answer while four more are available (those four
  can tie them at best, and a tie goes to the earliest draw, which is one of them), and a
  leader more than the draws still available ahead of the next answer cannot be caught.
  Everything else — the vote, the reading turn, the wording check, the repair, the retrieval
  — is the parent's. The rounds were verified offline against the vote they replace: over
  all 4^8 = 65,536 answer sequences the staged vote returns exactly the plurality over all
  eight draws wherever it stops early, a draw that raises is dropped rather than failing the
  question, and a question no draw answers still raises.
- The evaluation measured nothing, so the effect is unmeasured. Every sample of the first
  attempt was refused by the provider before a single token came back — `invalid_request`,
  "Access denied, please make sure your account is in good standing ... overdue-payment", on
  all 260 samples, which the runner printed as average 0.0 with status error.
  [[/workspace/runs/f940a4539b030a2578c9c9ac5dae166cc557869b/results/summary.json]] The
  parent's run had the same account fail part-way through (its LawBench denials begin at
  example 29 and run to the end), so this is the same fault reaching the whole run.
- Two further attempts at 21:56 and 22:21 changed nothing and proved nothing: the runner
  serves back a saved summary when it is rankable, and an all-failed run is rankable, since
  a failed sample counts as attempted. Clearing `results/summary.json` forced a real fourth
  attempt, and it failed before the provider was reached — the sandbox cannot start at all:
  `bwrap: Can't bind mount /oldroot/etc/ld.so.cache on /newroot/etc/ld.so.cache: Unable to
  mount source on destination: No such file or directory` on every sample, and the same
  command fails outside the runner. `/proc/self/mountinfo` gives the cause: `/etc/ld.so.cache`
  is mounted from ext4 with its source recorded as `/etc/ld.so.cache//deleted`, so the file
  the sandbox binds was replaced on the host while the container held it mounted, and bwrap
  cannot bind a deleted inode. [[/workspace/runs/f940a4539b030a2578c9c9ac5dae166cc557869b/USPTO/conversations/0000/sample-0.json]]
- The first attempt's artifacts were copied to `/tmp/iter14-failed-run/` before the fourth
  attempt overwrote them; they are the only record of the provider denial. Two environment
  faults therefore sit between this candidate and a number: the account, which denied every
  call from 21:40 on, and the sandbox, which has not started since 22:22. Neither is a
  property of the change, and the next iteration has to re-run this tree (or a descendant of
  it) to obtain the effect — after clearing `results/`, since a failed run's summary is
  rankable and will otherwise be served back.

## Round 15
- no commit (round incomplete; tree `None`)
