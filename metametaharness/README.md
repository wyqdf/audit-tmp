# TextClassification MetaMetaHarness

每个实验使用一个独立 Git harness 仓库。proposer 按原 MetaMetaHarness Skill 分析历史、修改一个机制、前台评测、分析结果，再 commit 并附 notes。评测产物按源码 tree hash 保存，外循环在提交后确认 tree 与真实 parent，并关联 commit。

评测、模型接入、memory 准备和 solver 轨迹复用同级 MetaHarness 的实现，源码和数据已独立复制。原 Skill 与两份模板保持原文，通过任务 prompt 指定文件路径供 proposer 读取。

## 环境和配置

需要 Linux、Git、bubblewrap（`bwrap`）、Claude CLI 和 uv。独立 Python 环境使用已有依赖锁定文件：

```bash
cd /home/yepeijie/workspace/mmharness/exp/TextClassification/metametaharness
uv sync --locked
cp config.local.example.yaml config.local.yaml
```

在 `config.local.yaml` 填写 `solver.api_key` 和 `proposer.api_key`，或设置 `BAILIAN_API_KEY` 与 `PROPOSER_API_KEY`。本地密钥文件已被 Git 忽略。

默认 proposer 为 `deepseek-v4-flash`，solver 为开启 thinking 的 `qwen3.5-flash`；其余模型参数、三任务划分和预算沿用对照配置。新实验保存配置快照，续跑使用该快照。更换模型、数据或预算时使用新实验名。

三个任务并行评测，共享 `parallel_questions` 个题目执行槽位和 `model_concurrency` 个模型调用槽位，默认均为 24。显式缓存与 MetaHarness 同步，覆盖系统提示、题目及持续增长的对话历史。

## 创建和续跑

```bash
.venv/bin/python -u outerloop/meta_meta_harness.py --run-name experiment_a --iterations 3
```

默认从同级 `metaharness/harnesses/glm53flash_10rounds/baseline/` 复制初始源码，也可用 `--baseline /absolute/path/to/baseline` 指定完整 harness。不会复制已有实验的 Git 历史、分数、notes 或 memory。

创建后只有一个源码仓库：`harnesses/experiment_a/`。baseline 使用根 commit，评测和 notes 由 proposer 的 Stage 0 完成，不计入进化轮数；baseline 未生成正式分数则停留在该阶段。

重复启动命令即可续跑；追加轮数使用累计目标：

```bash
.venv/bin/python -u outerloop/meta_meta_harness.py --run-name experiment_a --iterations 6
```

中断后恢复原 Claude 会话和当前 Git 状态。未完成评测在相同 tree hash 目录补齐；已有结果则继续分析、提交和 notes。已结束的轮次直接跳过。每轮 proposer 的 7200 秒活动预算累计保存，benchmark 等待时间单独记录。

proposer 的工作目录固定为 `/workspace/harness`，只看到当前实验的 `/workspace/runs/<tree_hash>/`。已关联 commit 的历史产物只读；Test、其他实验和历史 proposer 会话不可访问。Skill 位于 `/workspace/.claude/skills/meta-meta-harness/`。

## 显式 Test

```bash
.venv/bin/python -u outerloop/meta_meta_harness.py --run-name experiment_a --test-commits <baseline_sha> <candidate_sha>
```

Test 只接受已有正式 Val 成绩（`rankable`）并关联 commit 的版本。它冻结实验，按所选 commit 导出源码并复制该版本的固定 Val memory，不重新训练。冻结后不能继续进化；再次指定 Test 可补齐未完成的题目。完成普通进化不会自动运行 Test 或冻结。

## 产物

```text
harnesses/<实验>/                 唯一候选 Git 仓库
runs/<实验>/
├── config.yaml                   固定配置及 baseline 来源
├── <tree_hash>/
│   ├── manifest.json             tree、parent、配置、计时及最终 commit
│   ├── <任务>/memory.json        固定训练 memory
│   ├── <任务>/conversations/     每题每次执行的完整对话，memory 生成阶段在 prepare/ 下
│   └── results/{samples.jsonl,summary.json}
├── sessions/<轮次>/
│   ├── conversation.jsonl       本轮 proposer 的完整交互记录（原生会话）
│   ├── tool-results/            过大的工具输出落盘的全文，会话里只留预览与指针
│   └── result.json              本轮结果、token 用量与耗时
├── finalized.json               显式 Test 后出现
└── test/<commit_hash>/           Test 源码、memory、结果、完整对话及来源
```

训练、验证和测试数据统一保存在 `benchmark/data/`；准备阶段所需的训练输入 JSON 临时生成，用完清除。分数与失败明细保留在 benchmark 结果中，分析保留在 commit message 和 `refs/notes/evolution` 中。

查看演化树可在 harness 仓库执行 `git log --graph --all --notes=refs/notes/evolution`。proposer 会话保留完整请求、响应和事件。计时与轮次完成状态位于对应 session 的 `result.json`。

已执行 `smoke24_cache_20260910_233401`：三个任务各 8 题，共 24 题，实测模型调用并发峰值为 24。基线有 22 题正常完成；USPTO 的 1 题重试后仍超时，LawBench 的 1 题被接口内容审核拒绝，因此未形成完整基线成绩，也未进入进化轮次。原始证据和 baseline notes 已保留。

本次已返回 usage 的请求中，输入 token 共 910,756，缓存命中 599,153，token 命中率为 65.8%。
