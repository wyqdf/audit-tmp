# MetaHarness 外循环设计

本文记录目标目录和流程，作为后续实现依据。

项目根目录为 `/home/yepeijie/workspace/mmharness/exp/TextClassification/metaharness`，Git 历史、环境、配置、候选及运行产物一并存放在此目录。

模型、轮数、采样次数等运行参数全部由各实验的 `config.yaml` 指定，设计里不写具体值；密钥单独放在 Git 忽略的 `config.local.yaml` 或环境变量中。

## 设计依据

- 外循环参考 `exp/testclassification/official/5.6-sol-D/text_classification` 的 MetaHarness：每轮生成一个候选，外部执行评测，积累全部候选与反馈。
- `/home/yepeijie/DeepTaxon-Tri-mmharness/outerloop/proposer/invoke.py` 仅作为挂载隔离方法的参考，不沿用其进化流程。
- official 的一个候选是一个文件；本项目的一个候选是一个完整 harness 目录，包含 memory 生成和求解逻辑。
- 候选按实验组织。proposer 可以读取本实验所有历史候选，自行选择基础方案并创建新候选。
- proposer 的 skill 保留 official 的进化流程、方法约束和固定路径；skill 不注入系统提示词，proposer 自己读，system prompt 只写最小角色定义，user prompt 只提供本轮参数，避免重复说明。solver 的提示词策略由 harness 进化决定。

## 目标目录

```text
metaharness/
├── .claude/skills/meta-harness/SKILL.md  proposer 的进化工作流，参考 official
├── outerloop/
│   ├── meta_harness.py              外循环入口与调度
│   ├── proposer.py                  调用 proposer，接收候选交接
│   ├── sandbox.py                   proposer 的挂载隔离
│   └── prompt.md                    本轮 user prompt 模板
├── benchmark/
│   ├── run.py                       单个候选的准备、评测入口
│   ├── evaluate.py                  评分与汇总
│   ├── runtime/                     固定执行环境、模型接入和预算
│   └── data/                        数据与固定划分逻辑
├── harnesses/
│   └── <实验名>/
│       ├── baseline/
│       │   ├── prepare_memory.py
│       │   └── solver/
│       │       ├── agent.py
│       │       ├── solver.md
│       │       ├── tools/
│       │       └── skills/
│       ├── candidate_001/           完整 harness 目录
│       └── candidate_002/
└── runs/
    └── <实验名>/
        ├── config.yaml              本实验的固定配置：模型、预算、数据划分、采样次数
        ├── candidates/<候选>/<任务>/
        │   ├── memory.json          该候选的 prepare_memory.py 用 Train 生成的固定 memory
        │   └── conversations/<题号>/
        │       ├── sample-<k>.json  一个执行一份完整记录：表头统计 + messages 主线对话 + side_calls
        │       └── sample-<k>.tmp/  有 tmp 文件时保留
        ├── sessions/<轮次>/
        │   ├── conversation.jsonl   本轮 proposer 的完整交互记录（原生会话）
        │   ├── tool-results/        过大的工具输出落盘的全文，会话里只留预览与指针
        │   └── result.json          本轮结果、token 用量与耗时
        ├── results/
        │   ├── samples.jsonl        一行一题，由各对话文件的表头拼成，proposer 的判断入口
        │   └── summary.json         各任务分数与汇总
        ├── reports/                 每轮分析报告
        ├── pending_eval.json        待评测候选及改进假设
        ├── evolution_summary.jsonl  历次候选、假设与评测结果
        ├── finalized.json           仅显式运行 Test 时创建，记录冻结状态
        └── test/                    仅显式运行 Test 时创建，存放全部 Test 产物
```

`<题号>` 是题目在划分里的 `example_index`（四位补零，如 `0020`）；`sample-<k>` 是本次采样的序号（从 0 起）。

`harnesses/<实验名>/` 集中存放该实验的所有候选代码；`runs/<实验名>/` 集中存放对应的运行状态和产物。两处使用同一个实验名和候选名关联。

数据统一放在 `benchmark/data/`，各实验只读使用；runner 按本实验配置确定任务、seed 和样本数，从源划分切片读取，不向 `runs/` 复制。实测 7 个实验各自展开的划分逐字节相同，复制没有信息量。

每个候选包含完整代码，可以独立准备 memory 和执行求解，不依赖其他候选目录。候选提交评测后固定，后续改动生成新候选目录。

## 执行流程

1. **初始化实验**：固定模型、预算、数据划分和采样次数，保存初始候选 `baseline`。
2. **基线评测**：使用训练集生成各任务 memory，再执行 Val，保存轨迹、分数和初始最优记录。
3. **分析历史**：proposer 先读 `history/results/samples.jsonl` 定位异常样本（错题、截断、调用异常），再打开对应候选的完整对话，阅读本实验历史候选、结果和相关轨迹，补充已完成轮次的分析报告，提出本轮改进假设。
4. **生成候选**：proposer 自行选择历史基础方案，生成一个新的完整 harness 目录。通过 `pending_eval.json` 交接候选名、目录、基础方案和改进假设。
5. **外部评测**：proposer 结束后，外循环固定候选，交给 benchmark 使用训练集生成 memory，再用固定 memory 执行 Val。验证阶段不更新 memory。
6. **积累反馈**：保存候选、memory、分数和完整轨迹，追加进化历史，进入下一轮。所有已评测候选保留。
7. **中断续跑**：只有完整成功的 baseline 才跳过；不完整 baseline 先补齐失败或缺失题目，成功任务和成功题保持复用。补 baseline 不清空其他轮次的候选交接。已有候选交接时从评测继续，不重新提案；其他已归档失败候选留给 proposer 分析，不自动逐个补跑。
8. **默认结束**：完成指定进化轮数后停止，保留 Val 结果；不自动运行 Test，也不自动冻结实验，可以继续追加进化轮次。

**可选 Test**：只有用户单独显式触发才运行，先冻结实验，再使用选定候选各任务在 Val 阶段已保存的 memory 执行 Test，不重新训练或生成 memory。Test 数据副本、所用 memory 的副本、结果和轨迹统一保存在 `test/` 下，不进入 proposer 反馈；该实验不再继续进化。

每轮严格生成一个候选。外循环不强制指定总分最高的候选作为唯一基础，proposer 根据整个实验的历史选择改进方向。

## 训练与执行限制

本节只写规则，不写数值：轮数、时限、并发、采样次数、epoch、seed、模型与任务划分都由各实验的 `config.yaml` 在起跑时固定，设计里不重复一遍。

- **memory 生成对齐 official**：允许候选使用固定的模型接入，在训练集输入和标签上生成或整理 memory；是否调用模型由候选实现决定。生成 epoch 数取自配置；生成完成后固定 memory，Val/Test 只读使用。
- **失败题重试**：每次评测调用中，每题每个采样最多执行 `runtime.sample_attempts` 次。复用历史成功结果，后续批次只执行失败或缺失样本；自动重试限于临时故障。显式续跑为仍未成功的样本重新分配本次尝试预算，既有轨迹不覆盖。此处已改为逐题重试，不再采用原先整任务重跑的口径。
- **错误分类**：超时、连接失败、限流和上游服务错误可自动重试；内容审核、鉴权、请求错误、调用预算耗尽和候选执行错误记录具体原因，不作相同输入的自动重试。渠道错误匹配词配置在 `solver.error_patterns`，不写入核心渠道判断。memory 准备失败单独记录。
- **分数与完成状态**：候选总分沿用 benchmark 返回的各任务准确率等权平均；失败题计入分母按错处理，任务的全部样本都执行过即生成正式准确率，全部任务都有正式准确率即生成候选总分与 `rankable`。memory 准备失败或受限运行（`--limit`、任务子集）只保留局部分数、完成率、工具返回文本字符数和错误明细。需要选取最优版本时直接比较完整结果，不维护独立前沿文件。逐题明细仍分别记录 `successful_samples`、`expected_samples`、`completion_rate`、`successful_accuracy`、`errors` 和 `error_counts`；baseline 补评测追加历史记录，旧记录仍保留。
- **重复调用**：由 harness 进化修正重复读取 memory 等无进展行为；固定 runtime 继续执行已有总调用预算，不增加重复工具调用早停策略。
- **proposer 时限**：每轮的活动时间上限取自配置，超时结束该轮 proposer 进程，保留完整会话记录。
- **版本比较**：沿用 official 的准确率与上下文长度比较；文件夹 harness 的上下文长度统计每次求解中工具返回文本的字符数。

## 挂载边界

以下是挂载映射。以实验 `exp_a`、当前第 `003` 轮为例，宿主机项目根目录记为：

```text
P = /home/yepeijie/workspace/mmharness/exp/TextClassification/metaharness
```

### proposer

proposer 的工作目录固定为 `/workspace`。它看到的项目内容如下，仅对应当前实验 `exp_a`。`history/` 集中提供该实验的配置、历史和评测记录。

提示词组织对齐 metametaharness：**skill 不注入系统提示词**，`--setting-sources ""` 关闭设置源，skill 以只读方式挂载在 `/workspace/.claude/skills/meta-harness/`，由 proposer 按 user prompt 的指示自己读取全文。system prompt 只有一个最小角色定义，user prompt 提供轮次、数据集数、offline 模式，并指明第一件事是读 skill。固定路径只在 skill 正文里定义；skill 正文直接移植 official，仅适配文件夹接口、隔离路径及已确认的评测规则，不加入测试或复查步骤。skill 快照与每轮完整输入保存在 sessions 备查。

system prompt（`outerloop/proposer.py`）：

```text
You are an autonomous harness-evolution proposer. Complete exactly one candidate per invocation
by following the loaded Skill and evaluation contract. Modify only the bound harness directory,
finish the required result handoff, and do not start another candidate.
```

user prompt 是 `outerloop/prompt.md` 渲染 `{iteration}`、`{num_datasets}` 的结果：

```text
Run iteration {iteration} of the evolution loop. There are {num_datasets} datasets.
Produce exactly 1 candidate directory this iteration.

Current mode is offline: all examples stored in memory are ground truth.
```

开头另有一行强制动作，要求先完整读 skill 再做任何工具调用（对应 metametaharness 的 `First action: Read Contract in full …`）：

```text
First action: read the meta-harness skill in full at
/workspace/.claude/skills/meta-harness/SKILL.md before any other tool call.
```

两边都不含具体路径，路径只在 skill 正文里定义。三份输入都不单独落盘：system prompt 从命令行传入，skill 由 proposer 自己读，user prompt 就在会话记录的第一行。

```text
/workspace/
├── harnesses/                      当前实验的全部候选
│   ├── baseline/                   只读
│   ├── candidate_001/              只读
│   ├── candidate_002/              只读
│   └── <本轮新候选>/               proposer 创建，可写
├── benchmark/                      只读，固定评测代码与源划分
│   ├── run.py                      评测入口
│   ├── evaluate.py                 计分
│   ├── answers.py                  答案解析
│   ├── runtime/                    沙箱、gateway 代理与轨迹写入
│   └── data/
│       ├── *.py                    划分与评测逻辑
│       └── <数据集>/{train,val}.jsonl  源划分；Test 输入不挂载
├── history/                        只读
│   ├── config.yaml
│   ├── evolution_summary.jsonl
│   ├── candidates/<候选>/<任务>/    固定 memory 与完整对话
│   └── results/                     samples.jsonl 索引与分数汇总
├── reports/                        可写
├── pending_eval.json               可写，本轮候选交接
└── .claude/skills/meta-harness/    只读，skill 全文，proposer 自己读

/tmp/claude-state/                  可写，CLI 运行时的会话工作目录，轮次结束只留 conversation.jsonl 与 tool-results/
```

实际映射关系如下。`P` 表示上面的宿主机绝对路径；表中每项单独挂载，不把整个实验运行目录挂进去。

| 宿主机来源 | proposer 内路径 | 权限 |
| --- | --- | --- |
| `P/harnesses/exp_a/` | `/workspace/harnesses/` | 可写，用于创建本轮新候选 |
| `P/harnesses/exp_a/<已提交候选>/` | `/workspace/harnesses/<已提交候选>/` | 逐个叠加只读挂载，固定历史代码 |
| `P/benchmark/` 下的 `*.py`、`*.md` | `/workspace/benchmark/` | 只读，评测入口与计分代码 |
| `P/benchmark/runtime/` | `/workspace/benchmark/runtime/` | 只读，沙箱、gateway 与轨迹写入 |
| `P/benchmark/data/*.py` | `/workspace/benchmark/data/` | 只读，划分与评测逻辑，不含数据集本体 |
| `P/benchmark/data/<数据集>/{train,val}.jsonl` | `/workspace/benchmark/data/<数据集>/` | 只读，源划分；Test 输入不挂载 |
| `P/runs/exp_a/config.yaml` | `/workspace/history/config.yaml` | 只读 |
| `P/runs/exp_a/evolution_summary.jsonl` | `/workspace/history/evolution_summary.jsonl` | 只读 |
| `P/runs/exp_a/candidates/` | `/workspace/history/candidates/` | 只读，各候选的固定 memory 与训练/验证阶段完整对话 |
| `P/runs/exp_a/results/` | `/workspace/history/results/` | 只读，仅训练/验证阶段的结果与 `samples.jsonl` 索引 |
| `P/runs/exp_a/reports/` | `/workspace/reports/` | 可写 |
| `P/runs/exp_a/pending_eval.json` | `/workspace/pending_eval.json` | 可写 |
| `P/.claude/skills/meta-harness/` | `/workspace/.claude/skills/meta-harness/` | 只读，skill 全文，proposer 的第一件事就是读它 |
| `P/runs/exp_a/sessions/003/state/` | `/tmp/claude-state/` | 可写，保存当前原始会话状态 |

例如，proposer 创建 `/workspace/harnesses/candidate_003/solver/agent.py`，实际写入的是宿主机 `P/harnesses/exp_a/candidate_003/solver/agent.py`。读取 `/workspace/history/candidates/candidate_002/`，读到的是本实验该候选固定 memory 与完整对话。

本轮完整输入输出由外部记录到 `P/runs/exp_a/sessions/003/`，供用户查看。proposer 只获得本轮的指令文件和独立可写的 `state/` 运行状态；历史 `sessions/` 不挂载，也不作为后续轮次的输入。

另提供 Claude、Python 所需的固定系统环境和临时目录。宿主机项目根目录、其他实验、完整原始数据目录、`outerloop/` 源码、Test 输入和 `test/` 都不挂载。评测代码只读挂载，供 proposer 阅读计分与答案解析逻辑；模型、隔离、调用预算和评分仍由外部固定设施控制，proposer 按 skill 的约定不自行运行评测，评测由外循环执行。

### solver

solver 沿用现有隔离方式，工作目录为 `/workspace`。每道题的每次采样使用独立进程和工作目录。除 Python 和系统依赖外，它看到的目录如下：

```text
/
├── harness/                 只读，当前候选的 solver 文件夹
│   ├── agent.py
│   ├── solver.md
│   ├── tools/
│   ├── skills/
│   └── memory/              只读，当前候选、当前任务的固定 memory
│       └── memory.json
├── workspace/               可写，本题本次采样独立
├── runtime/
│   └── worker.py            只读，固定启动代码
└── tmp/                     可写，临时文件
```

按目标实验目录，以候选 `candidate_003` 的 Val 评测为例：

| 宿主机来源 | solver 内路径 | 权限 |
| --- | --- | --- |
| `P/harnesses/exp_a/candidate_003/solver/` | `/harness/` | 只读 |
| `P/runs/exp_a/candidates/candidate_003/<任务>/memory.json` | `/harness/memory/` | 只读，单独挂载当前任务的 memory |
| 本题本次采样的独立工作目录，执行结束删除，非空时整份保存在对话旁 | `/workspace/` | 可写 |
| `P/benchmark/runtime/worker.py` | `/runtime/worker.py` | 只读 |
| 沙箱内临时目录 | `/tmp/` | 可写 |

Test 使用 Val 阶段已保存的 memory 副本，solver 内仍映射到 `/harness/memory/`。求解期间不能修改候选代码或 memory。

当前问题直接作为输入传入，不挂载完整评测数据或当前题标准答案。其他候选、`prepare_memory.py`、历史评测记录、proposer 会话和评分代码都不挂载。

#### agent：候选侧的装配

固定运行时只认一个入口（`worker.py` 动态加载 `/harness/agent.py`）：

```python
def build_agent(model, input_text, config) -> tuple[agent, prompt]
```

框架是 deepagents 0.7.13 的 `create_deep_agent`，执行在 langgraph 1.2.11；模型客户端由固定运行时注入，候选拿不到密钥。baseline 的装配就是这个文件（43 行）：

```python
# baseline/solver/agent.py
SYSTEM_PROMPT = "You are an agent that answers a question by retrieving examples."
SKILL_PATH = "/harness/skills/answer-with-examples/SKILL.md"


def build_agent(model, input_text: str, config: dict):
    profile = HarnessProfile(
        general_purpose_subagent=GeneralPurposeSubagentProfile(enabled=False),
    )
    register_harness_profile("openai", profile)
    register_harness_profile(f"openai:{config['model']}", profile)
    backend = LocalShellBackend(
        root_dir="/", virtual_mode=True, timeout=config["tool_timeout_seconds"],
        env={"PATH": os.environ["PATH"], "HOME": "/tmp", "PYTHONDONTWRITEBYTECODE": "1"},
    )
    agent = create_deep_agent(
        model=model, tools=build_tools(input_text), system_prompt=SYSTEM_PROMPT,
        middleware=[], subagents=[], backend=backend,
    )
    prompt = Path("/harness/solver.md").read_text().format(
        input=input_text, skill=Path(SKILL_PATH).read_text().strip()
    )
    return agent, prompt
```

**system prompt** 只有一句：

```text
You are an agent that answers a question by retrieving examples.
```

**user prompt** 由 `solver/solver.md` 渲染，模板只有两个占位符：

```text
{input}

{skill}
```

**skill** 是 `solver/skills/answer-with-examples/SKILL.md` 全文，四行：

```text
1. Call `retrieve_examples` before answering.
2. If the examples do not cover the question, search the memory under `/harness/memory` yourself.
3. Match the wording, format and level of detail of the examples' answers.
4. Reply as JSON: `{"reasoning": "[your reasoning]", "final_answer": "[your answer]"}`
```

**tools** 只有一个，在 `solver/tools/retrieval.py` 里用 `@tool` 定义，`build_tools(input_text)` 装配，闭包捕获当题输入；模型看到的说明就是 docstring：

```python
@tool
def retrieve_examples() -> str:
    """Get the training Q/A examples to use when answering the current problem."""
```

它把固定 memory 里的训练样例用输入哈希作种子打乱，按 `Q: …\nA: …` 拼接并截到 30,000 字（`MAX_CHARS = 30000`、`MAX_EXAMPLES = 9999`），没有参数。

**middleware 是空的**（`middleware=[]`），**subagents 也是空的**，`HarnessProfile` 只关掉了通用子 agent，没有关 deepagents 自带的工具——所以 `ls` / `read_file` / `write_file` / `edit_file` / `delete` / `glob` / `grep` / `execute` / `task` 在 baseline 里全部可用。

**实测一次 baseline 求解**（USPTO `0023/sample-1`）：system 一句，user prompt 1,958 字（题目 + 三行 skill + 运行时追加的 FINAL OUTPUT REQUIREMENT），2 次调用，消息数 2 → 4。

**运行时收尾**：`answer_guard` 打开时给 user prompt 末尾追加（`worker.py:143-150`）：

```text
FINAL OUTPUT REQUIREMENT (mandatory, overrides anything else): Your final message MUST be a
single JSON object with exactly two string fields, "reasoning" and "final_answer". Put the
answer itself (keeping any required markup such as [DIAGNOSIS]...[/DIAGNOSIS]) inside
"final_answer". Output nothing outside the JSON object.
```

答案取 `result["messages"][-1].content`；不是合格 JSON 时用一次 no-think 的 `json_object` 调用重包；最后打 `{"event": "final", "response": …}`，评测侧只认这一行。

可进化的是候选目录内的 `agent.py`、`solver.md`、`tools/`、`skills/`、`prepare_memory.py`；`worker.py`、沙箱挂载、gateway 代理、评分、模型与调用预算在候选之外。

## 轨迹保存

轨迹只有两层，按"谁读、读多少"划分。**同一份内容只保存一处**：正文进对话，每题一行统计进索引。

**不保存任何逐 token 的记录。** 上游流式分包（每 token 一个 JSON 帧）和 CLI 的 `thinking_tokens` 心跳（每 token 一条 158 字节事件）都是传输中间态，只保留解析后的完整文本与汇总用量。判断标准很直接：单条记录只承载一个 token 的信息量。

| 层 | 位置 | 内容 | 读者 |
| --- | --- | --- | --- |
| 正文 | `conversations/` | 每个执行一份完整对话 | proposer、审计 |
| 索引 | `results/samples.jsonl` | 一行一题的统计字段 | proposer 的入口 |

### conversations：完整对话（正文的唯一权威）

一个执行一个文件：`<候选>/<任务>/conversations/<题号>/sample-<k>.json`。前半是判断用的表头，后半是对话正文。

```json
{
  "task": "USPTO", "example_index": 23, "sample_index": 1, "split": "val",
  "candidate": "baseline", "error": null,

  "status": "ok", "was_correct": true,
  "prediction": "CCOC(=O)c1cc(OC(F)(F)C(F)Cl)ccc1C.O=C1CCC(=O)N1Br",
  "target": "CCOC(=O)c1cc(OC(F)(F)C(F)Cl)ccc1C.O=C1CCC(=O)N1Br",
  "metric": {"jaccard_similarity": 1.0},

  "usage": {"model_calls": 2, "input_tokens": 10550, "output_tokens": 644},
  "elapsed_seconds": 8.26, "memory_context_chars": 8663,

  "tool_calls": ["retrieve_examples"],
  "finish_reasons": ["tool_calls", "stop"],
  "truncated": false, "repair_turns": 0, "retries": 0,

  "messages": [
    {
      "role": "system",
      "content": "You are an agent that answers a question by retrieving examples."
    },
    {
      "role": "user",
      "content": "You are an expert organic chemist specializing in retrosynthesis analysis. …题目 1,958 字，末尾接着三行 skill 与运行时的 FINAL OUTPUT REQUIREMENT…"
    },
    {
      "role": "assistant",
      "content": "I'll retrieve the training examples first.",
      "tool_calls": [
        {
          "id": "call_00_ET_WSZaOMyOirD…",
          "type": "function",
          "function": {"name": "retrieve_examples", "arguments": "{}"}
        }
      ]
    },
    {
      "role": "tool",
      "tool_call_id": "call_00_ET_WSZaOMyOirD…",
      "content": "Q: Context: The reaction type is Heterocycle formation.\nInput: c1ccc(-c2nc(CCCCCCc3nnn[nH]3)oc2-c2ccccc2)cc1\nAnswer: \nA: …\n\n…训练样例共 8,663 字…"
    },
    {
      "role": "assistant",
      "content": "{\"reasoning\": \"Product analysis: CCOC(=O)c1cc(OC(F)(F)C(F)Cl)ccc1CBr …\", \"final_answer\": \"CCOC(=O)c1cc(OC(F)(F)C(F)Cl)ccc1C.O=C1CCC(=O)N1Br\"}",
      "reasoning_content": "…该轮思考 777 字…"
    }
  ],

  "side_calls": []
}
```

`messages` 是主线对话，字段沿用线上格式，不改名：

| 字段 | 说明 |
| --- | --- |
| `role` | `system` / `user` / `assistant` / `tool` |
| `content` | 该轮正文；只发工具调用的轮次为 `null` |
| `reasoning_content` | 该轮思考，沿用模型字段名，不改名为 `reasoning` |
| `tool_calls[].id`、`type`、`function.name`、`function.arguments` | 工具调用；`arguments` 是 JSON 字符串，不是对象 |
| `tool_call_id` | 仅 `tool` 消息，与 `tool_calls[].id` 配对 |

上面的值是实测的 baseline 执行（`USPTO/0023/sample-1`）：2 次调用串成一条对话，消息数 2 → 4，`finish_reasons` 是 `tool_calls` 和 `stop`。机制在一轮里同时发多个工具调用时，每个调用对应一条 `tool` 消息，顺序与 `tool_calls` 一致。

拼接规则：**主线取消息数最多的那次请求**（它已包含此前每一轮的思考、工具调用及返回），再补上该次请求的响应；响应之后由机制额外发起的独立调用（例如把同一题独立作答多次的机制，其余几次各自是一条完整对话）放入 `side_calls`，不混入主线。表头字段用于判断是否值得读这个文件，正文用于判断机制是否生效。

`/workspace` 是本次执行的临时工作目录，写完对话即删除；结束时目录非空的话，整份目录原样保存在对话文件旁边（`sample-<k>.tmp/`），目录为空时不建任何目录。solver 落在对话之外的中间文件，只有这一处保留。

### results/samples.jsonl：候选级索引

一行一题，由各对话文件的表头拼成，不含 `messages`。proposer 先读这张表定位异常样本，再打开对应候选的完整对话。

### 不进轨迹的内容

轨迹只保留完整对话（`messages`），逐 token 与逐包中间态一律丢弃：上游流式分包、CLI 的 `thinking_tokens` 心跳都不保存，只留解析后的完整文本与汇总用量。每次模型调用的耗时、状态码、重试次数也不单独保存，每题合计写在表头的 `usage`、`elapsed_seconds`、`retries`、`finish_reasons` 里，异常由 `status` 与 `error` 表达。非正常结束的执行同样生成对话文件，`messages` 为空，`error` 记 stderr 或错误分类。完整输入输出不截断。

### memory 生成轨迹

memory 生成按候选、任务保存，走同一套分层：生成阶段的对话进 `<候选>/<任务>/conversations/`，生成结果固定保存为 `<候选>/<任务>/memory.json`。

### sessions：proposer 轨迹

每轮只留这一份交互记录和它的结果：`conversation.jsonl` 是 CLI 的原生会话记录，第一行就是发下去的 prompt，其后是每一轮 assistant 输出、工具调用及返回，续跑读的正是它；`result.json` 是本轮的结果事件、耗时、错误，以及 token 用量、成本、轮次与 API 耗时（续跑的话按各次调用累计，metametaharness 还含续跑状态）。

会话之外的中间态一律不留：逐次请求与上游原始响应和会话里的 `assistant`、`user` 条目重复；CLI 的 `thinking_tokens` 心跳逐 token 输出，实测占原始事件行数 99.6%（单轮 17 MB 级），而思考内容本身已经在 assistant 输出里；过大的工具输出 CLI 会落盘、会话里只留一段预览和指针，这些全文随 `tool-results/` 一起保留；shell 快照、配置备份和标准错误在轮次结束后删除。实测一轮 `conversation.jsonl` 约 1.3 MB、`result.json` 几 KB，改前是 120–136 MB。

完整输入输出不截断；终端进度和简短分析报告不能代替原始轨迹。

## 进度输出

- proposer 阶段：当前阶段、具体分析内容或正在写的候选、耗时和候选情况。
- benchmark 阶段：当前候选、任务、成功样本数、成功题准确率和错误类别；结束后同时输出正式总分是否可用及各任务局部成绩。
