# audit-tmp — MetaHarness / MetaMetaHarness 实验存档

两代 harness 自进化框架的代码与运行记录存档：外层循环代码、被进化的 harness 源码、以及各自最新一次多轮实验的完整记录（逐样本 traces + proposer 会话）。

## 目录

```
metametaharness/                    本代（MetaMetaHarness）：proposer + Skill 工作流
  outerloop/  benchmark/  adapters/  .claude/skills/meta-meta-harness/
  config.yaml  config.deepseek.yaml  DESIGN.md  README.md
  metametaharness.bundle            该仓库 git 历史
  runs/qwen3.7-flash-val2-skillv3-15rounds-20260916/

metaharness/                        上一代（MetaHarness）
  outerloop/  benchmark/  adapters/  .claude/  .agents/
  config*.yaml  DESIGN.md  desigen.md
  metaharness.bundle                该仓库 git 历史（41 个提交）
  runs/qwen3.7-flash-val2-15rounds-copy-20260913/

harness/
  metametaharness/
    qwen3.7-flash-val2-skillv3-15rounds-20260916.bundle   全部分支 + refs/notes/evolution
    HEAD/                                                末轮源码快照
  metaharness/
    qwen3.7-flash-val2-15rounds-copy-20260913.bundle      仓库 ref
    qwen3.7-flash-val2-15rounds-copy-20260913/            baseline 与各轮候选源码目录
```

## metametaharness 运行：`qwen3.7-flash-val2-skillv3-15rounds-20260916`

| 项 | 值 |
|---|---|
| 结束时间 | 2026-09-16 15:31 |
| 轮数 | 15 个候选（N1–N15）+ 1 次基线评测 |
| 任务 | USPTO（val 30）、Symptom2Disease（val 50）、LawBench（val 50），每题 2 采样 = 260 样本 |
| 平均分 | 基线 0.4311 → 最好 N13 `f3bef4a3` 0.5756；HEAD 为 N15 0.5478 |
| 谱系 | N1→N13 直线，N14、N15 均为 N13 的子节点，无合并提交 |
| 记录位置 | 每个候选一份 git note（`refs/notes/evolution`），随 bundle 保存 |

`runs/<run>/` 内容：`sessions/000…014`（15 个 proposer 会话：`conversation.jsonl`、`result.json`、部分含 `tool-results/`）；16 个 `<tree_hash>/`（`manifest.json`、`results/summary.json`、`results/samples.jsonl` 共 260 条逐样本判定、`<task>/conversations/*/sample-*.json` 逐题完整对话、`<task>/memory.json`）。

节点对照：基线 `f0b6817a`/`9f49dd72` 0.4311；N1 `913ebd45`/`57747d4b` 0.5244；N2 `02dcfc46`/`913109e9` 0.5211；N3 `d120469d`/`354e5e0a` 0.5611；N4 `28c00d83`/`2e2d9226` 0.5389；N5 `52669ee0`/`7074979c` 0.5122；N6 `72d9d015`/`3d5eaf15` 0.5556；N7 `3b572ccb`/`bf9c16fd` 0.5544；N8 `856cc92d`/`c1139da1` 0.5422；N9 `0e60b869`/`694c163a` 0.5500；N10 `be9427ba`/`64518426` 0.5656；N11 `ce5db05e`/`e4b5fa6f` 0.5533；N12 `55da8c0d`/`2cfc77c6` 0.5722；N13 `f3bef4a3`/`bf9c69ef` 0.5756；N14 `b56926c7`/`1f0bb7a0` 0.5311；N15 `0549be94`/`f2f87980` 0.5478。

## metaharness 运行：`qwen3.7-flash-val2-15rounds-copy-20260913`

| 项 | 值 |
|---|---|
| 轮数 | iteration 0（基线）–16，共 17 个候选 |
| 平均分 | 基线 0.4278 → 最高 iteration 16 = 0.5978（iteration 14 = 0.5944、12 = 0.5933） |
| 记录位置 | `evolution_summary.jsonl`（每候选一行：hypothesis、spec、scores、average）与 `reports/`（每轮一份说明） |

`runs/<run>/` 内容：`candidates/<name>/<task>/…`（逐题 trace 与 memory）、`results/`、`sessions/001…017`、`reports/`、`evolution_summary.jsonl`、`config.yaml`、`pending_eval.json`。

## 使用

```bash
# 恢复被进化仓库的完整历史与进化笔记（metametaharness）
git clone harness/metametaharness/qwen3.7-flash-val2-skillv3-15rounds-20260916.bundle mmh
git -C mmh log --branches --graph --oneline
git -C mmh notes --ref=refs/notes/evolution show f3bef4a3

# 复核任意节点的分数（metametaharness）
python3 -c "
import json
rows=[json.loads(l) for l in open('metametaharness/runs/qwen3.7-flash-val2-skillv3-15rounds-20260916/bf9c69efaa50709642cd760ec49d71e2743b8c5b/results/samples.jsonl')]
print(len(rows), sum(r['was_correct'] for r in rows)/len(rows))"

# 上一代的候选分数
python3 -c "
import json
for r in map(json.loads, open('metaharness/runs/qwen3.7-flash-val2-15rounds-copy-20260913/evolution_summary.jsonl')):
    print(r['iteration'], r['candidate_id'][:8], round(r['average'],4))"
```

## 说明

- 未包含两代的 `config.local.yaml`（含真实 API 密钥，均已被 `.gitignore` 排除）。全部上传内容已扫描 `sk-`/`ghp_`/`Bearer` 特征，未发现密钥。
- 两代代码目录上传的是各自工作区的当前状态，与其仓库最后一次提交的差异可用各自的 bundle 对比。
- 只包含上述两次实验，未包含 `runs/` 下的其他历史 run。
- metaharness 的候选源码位于其 `harnesses/<run>/`（每个候选一个目录，非 git 提交），已归档在 `harness/metaharness/<run>/`；metametaharness 的候选是 git 提交，见 bundle。
