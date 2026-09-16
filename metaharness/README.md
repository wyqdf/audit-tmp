# MetaHarness

以文件夹为候选的 MetaHarness 外循环。proposer 每轮读取当前实验历史，提交一个新候选；benchmark 在外部生成训练 memory 并执行 Val。保留全部候选、分数和完整轨迹。

项目整体位于 `TextClassification/metaharness/`，包含独立 Git 历史、虚拟环境、本地配置及已有实验。

## 配置

模型、接口、预算、并发和轮数统一放在 [config.yaml](/home/yepeijie/workspace/mmharness/exp/TextClassification/metaharness/config.yaml)：

- solver 沿用 Qwen 3.5 Flash 的思考配置。
- proposer 为 `deepseek-v4-flash`，使用官方 Anthropic 兼容接口 `https://api.deepseek.com/anthropic`；思考强度由 `proposer.effort` 控制（经 `CLAUDE_CODE_EFFORT_LEVEL` 传给 Claude Code），当前为 `max`。
- 渠道适配独立放在 `adapters/`，通过 `proposer.request_adapter` 配置；核心只加载适配器并保留原始请求、转换后的请求和响应。当前 DeepSeek 接口直接接收原始请求，不配置适配器。
- 默认进化 3 轮，不含 baseline；proposer 每轮最多 7200 秒。
- Val 每题采样 2 次、Test 每题采样 1 次，任务准确率等权平均。
- 每次评测调用中，每道题的每个采样最多执行 `runtime.sample_attempts` 次，默认 2 次；成功题直接复用，只对临时故障导致的失败题自动重试。
- 错误区分为超时、连接失败、限流、上游服务错误、内容审核、鉴权、请求错误、调用预算耗尽及候选执行错误。渠道特有的错误匹配词放在 `solver.error_patterns`，核心不写渠道判断。内容审核、调用预算耗尽和候选执行错误不做相同输入的自动重试。
- 每个任务分别保存完成率、成功题准确率及失败明细。失败题计入分母按错处理：只要全部样本都执行过就生成正式准确率和候选总分；使用 `--limit` 或任务子集时只保留局部分数，不参与候选排名。

密钥通过配置中指定的环境变量提供，或填写本地 `config.local.yaml`：

```yaml
solver:
  api_key: "填写 solver 密钥"
proposer:
  api_key: "填写 proposer 密钥"
```

`config.local.yaml` 已被 Git 忽略。实验创建后保存固定配置；改变 solver、数据或预算时使用新实验名。

## 启动

```bash
cd /home/yepeijie/workspace/mmharness/exp/TextClassification/metaharness
.venv/bin/python -u outerloop/meta_harness.py --run-name glm53flash_3rounds --baseline harnesses/glm53flash_10rounds/baseline
```

初始候选从 `harnesses/glm53flash_10rounds/baseline/` 复制到当前实验目录。新建其他实验时，通过 `--baseline /absolute/path/to/candidate` 指定起始候选。用 `--iterations` 设置累计进化轮数，重复同一命令即可续跑；已交接候选从评测继续。

只有已生成正式分数的 baseline 才自动跳过。续跑时，baseline 已成功的任务和题目保持复用，只补失败或未完成的部分；本次补评测重新获得每题最多 2 次的预算。补 baseline 不清除后续轮次的待评测候选。其他已归档失败候选保留给 proposer 分析，不在续跑时逐个自动重跑。

单独评测一个候选：

```bash
.venv/bin/python benchmark/run.py evaluate --run-name glm53flash_3rounds --candidate harnesses/glm53flash_3rounds/baseline --split val
```

默认完成进化后停止，允许以后追加轮次。只有以下显式命令才运行 Test：

```bash
.venv/bin/python outerloop/meta_harness.py --run-name glm53flash_3rounds --test-candidates baseline candidate_name
```

Test 先冻结实验，使用选定候选在 Val 阶段保存的 memory，产物全部进入实验的 `test/`。冻结后不能在同一实验继续进化。

## 候选与隔离

- `harnesses/<实验>/<候选>/`：完整候选目录，包含 `prepare_memory.py` 和 `solver/`。提交后固定，后续修改使用新目录。
- `outerloop/`：外循环入口、proposer 调用和挂载隔离。
- `benchmark/run.py`：单个候选的准备、评测、单题求解入口。
- `benchmark/runtime/`：固定的隔离、模型接入、调用预算和轨迹记录。

memory 生成只获得训练输入和标签，允许使用固定模型。模型接入通过 `MODEL_BASE_URL`、`MODEL_API_KEY`、`MODEL_NAME` 提供，生成参数在 `/runtime/model.json`。默认训练 1 个 epoch，生成后固定；训练调用受准备阶段时限约束。

proposer 只看到当前实验的候选和允许的历史记录。历史候选、memory、分数和 solver 轨迹只读；新候选、报告和交接文件可写。历史 proposer sessions 不提供给它。

proposer 直接移植 official 的 [.claude/skills/meta-harness/SKILL.md](/home/yepeijie/workspace/mmharness/exp/TextClassification/metaharness/.claude/skills/meta-harness/SKILL.md)，只适配文件夹候选、隔离路径及已确认的评测规则。skill 不注入系统提示词：用 `--setting-sources ""` 关闭设置源，skill 以只读方式挂载进沙箱，system prompt 只有一个最小角色定义，proposer 按 user prompt 的指示自己读取全文；[outerloop/prompt.md](/home/yepeijie/workspace/mmharness/exp/TextClassification/metaharness/outerloop/prompt.md) 沿用 official 的轮次、候选数量及 offline 说明，将候选适配为文件夹，开头一行要求先读完 skill 再做任何工具调用。固定路径只在 skill 中定义。

solver 只看到当前候选的求解代码、当前任务的固定 memory、独立工作目录和固定启动代码。当前题输入通过消息传入，完整评测数据和标准答案不挂载。详细目录与映射见 [desigen.md](/home/yepeijie/workspace/mmharness/exp/TextClassification/metaharness/desigen.md)。

重复读取相同 memory 等无进展行为由 harness 进化修正，固定 runtime 保留原调用预算，不新增重复调用早停规则。

## 运行产物

`runs/<实验>/` 下：

- `config.yaml`：固定配置；数据划分直接从 `benchmark/data/` 按配置切片读取，不复制到实验目录。
- `candidates/<候选>/manifest.json`：候选身份；`<任务>/memory.json`：固定训练 memory。
- `candidates/<候选>/<任务>/conversations/<题号>/sample-<k>.json`：一次执行的完整记录（表头统计 + `messages` 主线 + `side_calls`；工作目录非空时旁边多一个 `sample-<k>.tmp/`），内存生成阶段的对话放在同目录的 `prepare/` 下。轨迹只有这一处正文，不保存逐 token、逐包或逐次调用的中间态。
- `results/summary.json`：各候选各任务的分数、完成率与错误明细；`results/samples.jsonl`：由各对话文件的表头拼成的一行一题索引。
- `sessions/<轮次>/`：`conversation.jsonl` 是本轮 proposer 的完整交互记录（CLI 原生会话，第一行是 user prompt），`tool-results/` 是过大工具输出的落盘全文，`result.json` 是本轮结果、耗时、错误，以及 token 用量、成本与轮次。逐次请求、上游原始响应、thinking 心跳、shell 快照和标准错误都不保存。
- `reports/`、`pending_eval.json`：分析报告和下一候选交接。
- `evolution_summary.jsonl`：完整历史。

baseline 补评测会追加同一轮的新结果，保留旧记录；需要比较历史成绩时直接读 `evolution_summary.jsonl` 与 `results/summary.json`，不维护独立前沿文件。

前沿沿用 official 的准确率与上下文长度比较方式；此处的上下文长度统计 solver 工具返回文本的字符数，以适配多轮工具求解。只对全部任务都生成正式分数的候选排名。

进度输出：proposer 显示阶段、具体活动、耗时和候选；benchmark 显示候选与最新分数。原始记录不截断，运行产物不提交 Git。
