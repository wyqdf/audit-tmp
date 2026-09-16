# audit-tmp — MetaMetaHarness 15 轮实验存档

本仓库是 MetaMetaHarness 自进化实验的可审计存档：外层循环代码、被进化的 harness 仓库历史、以及最新一次 15 轮实验的完整运行记录。

## 目录

```
metametaharness/                 外层循环与评测代码（当前工作区状态）
  outerloop/                     proposer、沙箱、外层循环主体
  benchmark/                     评测 runner、runtime、数据集（train/val/test）
  .claude/skills/meta-meta-harness/   proposer 遵循的 Skill（约束与工作流）
  adapters/                      渠道请求适配
  config.yaml                    实验配置（任务、样本数、proposer 设置）
  config.deepseek.yaml           DeepSeek 通道配置（只引用环境变量名，无密钥）
  DESIGN.md / README.md          设计与使用说明
  metametaharness.bundle         该仓库的 git 历史（16 个提交）

harness/
  qwen3.7-flash-val2-skillv3-15rounds-20260916.bundle
                                 被进化的 harness 仓库：全部分支 + refs/notes/evolution
  HEAD/                          末轮源码快照（无 .git）

runs/qwen3.7-flash-val2-skillv3-15rounds-20260916/
  config.yaml                    本次 run 的配置
  sessions/000 … 014              15 个 proposer 会话
    conversation.jsonl           该轮的完整会话（首行即注入的 user prompt）
    result.json                  commit、tree、耗时、token、成本
    tool-results/                会话产生的工具输出
  <tree_hash>/                   每个被评测候选的产物（16 个，含基线）
    manifest.json                tree hash、commit、parent、评测时间
    results/summary.json         三任务分数
    results/samples.jsonl        260 条逐样本判定（评测的原始记录）
    <task>/conversations/…       逐题对话（模型实际收到的 prompt 与 block）
    <task>/memories/             该候选构建的 memory
```

## 本次实验

| 项 | 值 |
|---|---|
| run | `qwen3.7-flash-val2-skillv3-15rounds-20260916` |
| 结束时间 | 2026-09-16 15:31 |
| 轮数 | 15 个候选（N1–N15），另含 1 次基线评测 |
| 任务 | USPTO（val 30）、Symptom2Disease（val 50）、LawBench（val 50），每题 2 采样 = 260 样本 |
| 平均分 | 基线 0.4311 → 最好 N13 0.5756；HEAD 为 N15 0.5478 |
| 评测命令 | `/opt/venv/bin/python -u /workspace/benchmark/run.py evaluate --run-dir /workspace/runs --candidate /workspace/harness` |

节点与 commit 对应（`sessions/NN/result.json` 内亦有记录）：

| 节点 | commit | tree | mean |
|---|---|---|---|
| 基线 | `f0b6817a` | `9f49dd72` | 0.4311 |
| N1 | `913ebd45` | `57747d4b` | 0.5244 |
| N2 | `02dcfc46` | `913109e9` | 0.5211 |
| N3 | `d120469d` | `354e5e0a` | 0.5611 |
| N4 | `28c00d83` | `2e2d9226` | 0.5389 |
| N5 | `52669ee0` | `7074979c` | 0.5122 |
| N6 | `72d9d015` | `3d5eaf15` | 0.5556 |
| N7 | `3b572ccb` | `bf9c16fd` | 0.5544 |
| N8 | `856cc92d` | `c1139da1` | 0.5422 |
| N9 | `0e60b869` | `694c163a` | 0.5500 |
| N10 | `be9427ba` | `64518426` | 0.5656 |
| N11 | `ce5db05e` | `e4b5fa6f` | 0.5533 |
| N12 | `55da8c0d` | `2cfc77c6` | 0.5722 |
| N13 | `f3bef4a3` | `bf9c69ef` | 0.5756 |
| N14 | `b56926c7` | `1f0bb7a0` | 0.5311 |
| N15 | `0549be94` | `f2f87980` | 0.5478 |

进化谱系：N1→N13 为一条直线，N14 与 N15 均为 N13 的子节点，无合并提交。

## 使用

恢复被进化仓库的完整历史（含进化笔记）：

```bash
git clone harness/qwen3.7-flash-val2-skillv3-15rounds-20260916.bundle harness-repo
cd harness-repo
git log --branches --graph --oneline          # 15 个节点的谱系
git notes --ref=refs/notes/evolution show f3bef4a3   # 某节点的完整记录
```

逐样本复核任意节点的分数：

```bash
python3 - <<'PY'
import json
rows=[json.loads(l) for l in open('runs/qwen3.7-flash-val2-skillv3-15rounds-20260916/bf9c69efaa50709642cd760ec49d71e2743b8c5b/results/samples.jsonl')]
print(len(rows), sum(r['was_correct'] for r in rows)/len(rows))
PY
```

## 说明

- 未包含 `config.local.yaml`（该文件含真实 API 密钥，已被 `.gitignore` 排除）。`runs/` 与代码目录已扫描，未发现密钥或 token。
- `metametaharness/` 上传的是工作区当前状态，与仓库最后一次提交的差异见 `metametaharness.bundle` 中的 `dc67268`。
- `runs/` 与 `harness/` 只包含本次 15 轮实验，未包含同目录下其他历史 run。
