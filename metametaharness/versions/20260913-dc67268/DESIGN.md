# MetaMetaHarness 设计

日期：2026-09-10。状态：首版已实现，已执行三个任务各 8 题的 smoke；实测模型调用并发峰值 24。基线因 1 题超时、1 题内容审核拒绝而未完整成功，进化阶段尚未验证。

项目位置：`/home/yepeijie/workspace/mmharness/exp/TextClassification/metametaharness`。

## 1. 目标与参考

参考同级 `metaharness/`，建立使用 Git 管理候选演化树的 TextClassification 实验。沿用当前 benchmark、初始 harness、模型配置、数据划分、memory 生成、solver 隔离和完整轨迹记录；proposer 及其 Skill 沿用原 MetaMetaHarness 工作流。

移植以最小适配为原则：Skill、引用模板、加载方式和工作流尽量保持原样；其他组件只适配本项目必需的路径、完整 harness 候选接口、评测入口和版本关联。已有实现能够直接复用的部分直接移植。

核心是：**一个 commit 对应一个完整 harness，真实 Git parent 表达继承关系，评测产物按源码 tree hash 保存，并关联最终 commit。** proposer 根据整棵树选择父节点，修改一个机制，执行评测、分析结果，然后提交代码并附加 notes。

每类信息只维护一处：源码和演化关系由 Git 保存，分析由 commit message 和 notes 保存，客观分数由 benchmark 结果保存。`runs/` 只保留配置、评测产物和原始会话；需要比较历史成绩时，直接读取已有结果。

主要依据：

- 当前工程的 [README](/home/yepeijie/workspace/mmharness/exp/TextClassification/metaharness/README.md)、[外循环设计](/home/yepeijie/workspace/mmharness/exp/TextClassification/metaharness/desigen.md) 及核心实现。当前 `DESIGN.md` 是较早的 Deep Agents 迁移方案，不作为最新外循环流程。
- 直接移植仓库现有 [MetaMetaHarness 工作流](/home/yepeijie/workspace/mmharness/.claude/skill/skill.md)及引用模板，保持原文和提交顺序：分析历史、修改一个机制、前台评测一次、分析结果、commit 一次、附加 notes。必要的任务接口及路径写入领域合同和任务参数。唯一改动是 runner 打印的 scores 对象（`benchmark/run.py` 的 `scores_output`）：只留三个任务分数、平均分和评测状态，逐题明细不再出现在 stdout，只写进 `runs/<tree_hash>/results/`；commit message 模板本身保持原文。
- Meta-Harness 的公开[参考代码](https://github.com/stanford-iris-lab/meta-harness/blob/main/reference_examples/text_classification/meta_harness.py)作为评测及显式 Test 冻结流程的参考；本项目的 proposer 按 MetaMetaHarness 工作流直接运行 benchmark。

## 2. 目录与复用范围

```text
metametaharness/
├── DESIGN.md
├── README.md                         使用说明
├── config.yaml                       与对照实验一致的默认协议
├── config.local.example.yaml
├── config.local.yaml                 本地密钥，Git 忽略
├── pyproject.toml / uv.lock / .venv/
├── .claude/skills/meta-meta-harness/
│   ├── SKILL.md                      原 MetaMetaHarness Skill 的独立副本
│   └── references/                   原 commit、notes 模板，直接移植
├── adapters/                         沿用模型渠道适配
├── outerloop/
│   ├── meta_meta_harness.py           初始化、调用 proposer 及续跑
│   ├── proposer.py                    沿用调用、代理、请求与会话记录
│   ├── sandbox.py                     Git 工作区与证据挂载
│   └── prompt.md                      本轮参数、路径、分支及 runner 命令
├── benchmark/
│   ├── domainspecific.md              固定任务合同
│   ├── run.py / evaluate.py / answers.py
│   ├── runtime/                       固定模型接入、预算、隔离及轨迹
│   └── data/                          统一保存固定数据，沿用 MetaHarness 数据来源
├── harnesses/
│   ├── <实验名>/                     本实验唯一的 harness Git 仓库
│   │   ├── .git/                     全部候选 commit、分支和 notes
│   │   ├── prepare_memory.py
│   │   └── solver/                    agent、prompt、tools、skills
│   └── <其他实验名>/                 其他实验各自独立的 Git 仓库
└── runs/<实验名>/
    ├── config.yaml                   本实验的固定配置，proposer 只读
    ├── <tree_hash>/                  一次被评测的源码版本，目录名是它的完整 Git tree hash
    │   ├── manifest.json             本版本的 tree hash、真实 parent、评测配置、评测后补入的最终 commit
    │   ├── <任务>/
    │   │   ├── memory.json           prepare_memory.py 用 Train 生成的固定 memory，Val/Test 只读
    │   │   └── conversations/<题号>/sample-<k>.json
    │   │                             一个执行一份完整记录：表头统计 + messages 主线对话 + side_calls
    │   └── results/
    │       ├── samples.jsonl         一行一题，由各对话文件的表头拼成，proposer 的判断入口
    │       └── summary.json          本版本的各任务分数与汇总（average、rankable、status）
    ├── sessions/<轮次>/              proposer 本轮会话：prompt、逐次请求与响应、结构化事件、结果
    ├── finalized.json                显式 Test 时写入的冻结记录
    └── test/                         显式 Test 的候选、memory、结果与对话
```

`<题号>` 是题目在划分里的 `example_index`（四位补零，如 `0020`）；`sample-<k>` 是本次采样的序号（从 0 起）。

项目源码 Git 与候选 Git 分开：项目 Git 管理固定设施；`harnesses/<实验名>/` 本身就是该实验的 harness 仓库。proposer 始终在这个仓库里修改文件、创建分支和提交 commit，历史候选通过 Git 查看和切换，不为每个候选维护一个源码文件夹。候选仓库不保存数据、生成 memory、评测结果、密钥或 proposer 会话。

实现时复制当前 MetaHarness 的必要源码、依赖声明及数据文件，使用独立环境；不在运行时 import 同级实验，不复制其虚拟环境、Git 历史和运行产物。两种 outer loop 各自保留，不引入公共库改造。

数据统一放在 `benchmark/data/`，各实验只读使用。runner 按本实验保存的配置确定任务、seed 和 Train/Val/Test 样本数，沿用现有划分逻辑读取样本，不再向每个 `runs/` 复制数据。实验运行期间保持数据源固定。

proposer 按原工作流修改代码后直接运行 benchmark。runner 根据当前候选源码计算完整 Git tree hash，以该 hash 创建评测目录；计算时使用临时索引，不改变 proposer 的实际暂存区，也不要求提前暂存。baseline 使用其根 commit 的 tree hash。评测和分析完成后才按原工作流暂存改动、创建 commit 并附加 notes。同一源码版本的补跑沿用原目录，目录名在提交前后保持不变。benchmark 直接读取同一个 harness 仓库，源码历史由 Git 保存。

实验配置保存在 `runs/<实验名>/config.yaml`，每个 `runs/<实验名>/<tree_hash>/` 下的 memory、结果及轨迹都属于该源码版本；最终 commit 写入同目录的 manifest。proposer 完成分支、修改、评测、分析、提交和 notes；外循环负责初始化、调用 proposer 及确认本轮完成。

### 轨迹分层

轨迹只有两层，按"谁读、读多少"划分；同一份内容只保存一处。机制与 `../metaharness/desigen.md` 的「轨迹保存」一致，只有路径前缀不同。

| 层 | 位置 | 内容 | 读者 |
| --- | --- | --- | --- |
| 正文 | `conversations/` | 每个执行一份完整对话 | proposer、审计 |
| 索引 | `results/samples.jsonl` | 一行一题的统计字段 | proposer 的入口 |

**conversations：完整对话（正文的唯一权威）**

一个执行一个文件：`<tree_hash>/<任务>/conversations/<题号>/sample-<k>.json`。前半是判断用的表头，后半是对话正文。

```json
{
  "task": "USPTO", "example_index": 23, "sample_index": 1,
  "candidate": "baseline", "tree_hash": "…",

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

**results/samples.jsonl：候选级索引**

一行一题，由各对话文件的表头拼成，不含 `messages`。proposer 先读这张表定位异常样本，再打开对应候选的完整对话。proposer 挂载 `conversations/` 与 `results/`。

**sessions：proposer 轨迹**

每轮独立保存完整提示输入、模型实际收到的逐次请求、原始响应、工具调用及返回、最终输出和标准错误。

会话原始记录只保留结构化事件：`init`、`assistant`、`user`、`tool_progress`、`result`、`api_retry`、`vcs_state_changed`、`task_started`、`task_notification`。CLI 的 `thinking_tokens` 心跳逐 token 输出，实测 68 个会话共 348 万条、158 字节一条、占会话日志行数 99.4%，不保存；思考内容本身已在 `assistant` 事件和逐次请求中完整保留。`api_retry` 必须保留，重试次数是审计信号。

**不进轨迹的内容**：轨迹只保留完整对话（`messages`），逐 token 与逐包中间态一律丢弃：上游流式分包、CLI 的 `thinking_tokens` 心跳都不保存，只留解析后的完整文本与汇总用量。每次模型调用的耗时、状态码、重试次数也不单独保存，每题合计写在表头的 `usage`、`elapsed_seconds`、`retries`、`finish_reasons` 里，异常由 `status` 与 `error` 表达。非正常结束的执行同样生成对话文件，`messages` 为空，`error` 记 stderr 或错误分类。完整输入输出不截断。

## 3. 一轮如何执行

### 初始化与 baseline

1. 创建新实验，保存配置中的数据来源和划分参数，并记录 baseline 内容哈希及来源。通过 `--baseline` 指定完整候选目录，初始来源沿用 MetaHarness 的 baseline，仅复制源码。
2. 在 `harnesses/<实验名>/` 初始化全新 Git 仓库，创建 baseline 根 commit，`main` 固定指向该节点。
3. benchmark 直接使用当前仓库的 baseline 源码，生成训练 memory 并执行 Val；结果保存到 baseline tree hash 对应目录，分析附到已有 baseline commit 的 notes。baseline 不计入进化轮数。
4. baseline 未生成正式分数时停在准备阶段；续跑沿用现有逐题补评测规则，完成后才进入进化。

### 每个进化轮次

1. **分析历史**：proposer 读取领域合同、Git 图、commit message、notes 和评测结果；先用各 tree 目录下的 `results/samples.jsonl` 定位异常样本（错题、截断、调用异常），再打开对应候选的完整对话，从本实验已有评测及 notes 的 commit 中选择父版本，确定一个机制改动及预期效果。
2. **修改候选**：从选定 parent 建立 `codex/<机制名>` 分支，按原工作流修改完整 harness，此时不创建 commit。
3. **评测**：proposer 在一个前台 Bash 调用中直接运行 `benchmark/run.py`。runner 记录当前候选源码的 tree hash 及实际 parent，生成训练 memory 并执行一次正式 Val，产物直接写入 tree hash 目录。评测期间 proposer 前台等待，保持源码不变。
4. **分析结果**：proposer 读取分数和轨迹，分析改动是否生效、失败类别及副作用，整理结论和证据引用。
5. **提交并附 notes**：按原工作流只暂存本轮改动，使用原模板创建一个 commit：`Issue` 写问题，`Modification` 写实际改动，`Results` 的 `<runner stdout scores object>` 直接取 runner 在 stdout 打印的对象——**只有三个任务的准确率、平均分和本次评测状态，四位小数**，形如 `{"USPTO": 0.2333, "Symptom2Disease": 0.83, "LawBench": 0.53, "average": 0.5311, "status": "partial"}`（实测该对象 100 字节，完整 summary 2,610 字节）；其余信息全是文件侧，留在 `runs/<tree_hash>/results/summary.json` 与逐题结果里。随后将分析 notes 附到这个 commit。评测后不再修改源码。
6. **结束本轮**：外循环确认该 commit 的 tree 与被评测源码一致，真实 parent 与记录一致，将 commit 写入 manifest，确认 notes 已附加后进入下一轮。

所有已评测版本及其分支保留，低分版本的失败经验写入 notes。proposer 自行比较已有成绩并选择下一轮父版本。

## 4. 评测源码与 Git 版本绑定

**目录名使用源码的 tree hash，Git 节点使用提交后的 commit hash。** tree hash 在评测前即可确定；commit 包含父版本和提交说明，在完成评测、分析后才生成。

runner 先在 `/workspace/runs/<tree_hash>/manifest.json` 中记录 tree、parent 和评测配置。最终 commit 的 tree 和真实 parent 必须分别与记录一致，确认后补入 commit hash。版本不一致时保留证据并停在当前轮，分数以 benchmark 原始结果为准。

Git notes 使用 `refs/notes/evolution`，附在最终 commit 上，引用同一 tree hash 目录中的结果和轨迹。轮次只用于会话记录和进度计数，不维护额外的候选编号或 run_id，也不在提交后重命名评测目录。

## 5. 沙箱、评测入口与提示词

proposer 获得本实验的 harness Git 仓库、历史证据和可直接执行的固定 benchmark。沿用现有隔离机制，补充 benchmark 运行所需的只读代码、环境及本轮产物目录挂载。

### proposer 的两个提示词

system prompt 是固定三句，经 `--append-system-prompt` 追加到 Claude Code 默认系统提示词之后（`outerloop/proposer.py:20-24`）：

```text
You are an autonomous harness-evolution proposer. Complete exactly one candidate per
invocation by following the loaded Skill and evaluation contract. Modify only the bound
repository, finish the required result handoff, and do not start another candidate.
```

user prompt 是 `outerloop/prompt.md` 渲染 `{iteration}`、`{stage}`、`{continuation}` 的结果：

```text
Create one evaluated candidate node. Analyze evolution history, make one mechanism-level
modification, run benchmark once, audit and commit based on skill and domainspecific.

Round: {iteration}.

First action: Read Contract in full before any other tool call; it binds the Skill, the paths,
the branch prefix, the notes ref and the benchmark command.
Mandatory: follow the skill workflow exactly in order; never skip, merge, replace, or reorder any step.
Scope: repository source only.

{stage}
{continuation}
```

`{stage}` 第 0 轮是"评测既有 baseline 并在其原 commit 上补 notes、不新建 commit"，其余轮是"跑一轮进化"；`{continuation}` 只在续跑时非空。

**skill 不进系统提示词**：`--setting-sources ""` 关闭设置源，`SKILL.md` 以只读方式挂载在 `/workspace/.claude/skills/meta-meta-harness/`，由 proposer 按 user prompt 的指示自己读取；实测首轮第 5、6 次工具调用依次是 `Read SKILL.md` 与 `Read benchmark/domainspecific.md`。系统提示词只约束"一次一个候选、只改绑定仓库、做完交接即停"。

每轮的渲染结果落盘为 `sessions/<轮次>/prompt.md` 与 `sessions/<轮次>/input-<纳秒>.json`（内容为 `prompt`、`session_id`、`resume`）；不保存 skill 快照，skill 的版本由仓库 commit 决定。

### proposer 实际看到的文件

工作目录为 `/workspace/harness/`。实验名只用于宿主机管理；proposer 只看到当前实验，使用固定路径，每份文件只有一个访问路径。

```text
/
├── workspace/
│   ├── .claude/skills/meta-meta-harness/ 只读，proposer 工作流
│   │   ├── SKILL.md
│   │   └── references/                  commit、notes 模板
│   ├── harness/                         可写，当前实验唯一的 harness 仓库
│   │   ├── .git/                        commit、分支、notes
│   │   ├── prepare_memory.py
│   │   └── solver/
│   │       ├── agent.py
│   │       ├── solver.md
│   │       ├── tools/
│   │       └── skills/                  随 harness 演化的 solver 技能
│   ├── runs/                            当前实验的评测产物
│   │   ├── config.yaml                  只读，本实验固定配置
│   │   ├── <baseline_tree_hash>/        baseline 的评测产物
│   │   │   ├── manifest.json            tree hash、parent、评测配置、最终 commit
│   │   │   ├── <任务>/
│   │   │   │   ├── memory.json          该版本的固定 memory
│   │   │   │   └── conversations/<题号>/sample-<k>.json
│   │   │   │                            一个执行的完整记录：表头统计 + 对话
│   │   │   └── results/
│   │   │       ├── samples.jsonl        一行一题的索引
│   │   │       └── summary.json         各任务分数与汇总
│   │   ├── <candidate_tree_hash>/       该候选源码的评测产物
│   │   │   ├── manifest.json
│   │   │   ├── <任务>/
│   │   │   │   ├── memory.json
│   │   │   │   └── conversations/<题号>/sample-<k>.json
│   │   │   └── results/
│   │   │       ├── samples.jsonl
│   │   │       └── summary.json
│   │   └── <其他tree_hash>/             其他源码版本分别保存相同结构
│   └── benchmark/                       只读，直接执行固定评测
│       ├── run.py
│       ├── evaluate.py
│       ├── answers.py
│       ├── domainspecific.md            评测合同
│       ├── runtime/                     模型接入、隔离及轨迹代码
│       └── data/
│           ├── uspto/{train,val}.jsonl
│           ├── symptom_diagnosis/{train,val}.jsonl
│           └── crime_prediction/{train,val}.jsonl
└── tmp/                                 可写，临时工作文件
    └── claude-state/                    当前 proposer 会话运行状态
```

`/workspace/runs/` 只包含当前实验，内部按完整 tree hash 分目录。允许创建本轮新 hash 目录，已有候选目录只读；本轮目录可写，供 benchmark 保存产物。写入、读取及 notes 引用始终使用同一个路径。

MetaMetaHarness Skill 属于 proposer 的工作流，保留在 `.claude/skills/`；`benchmark/runtime/` 只放评测执行代码。Python、Git、Claude 及依赖所需的系统路径另外只读提供。实际数据仅提供 Train/Val 输入。

### 宿主机映射

以下 `P` 为本项目根目录，`E` 为实验名。只提供当前实验：产物根目录允许创建新的 hash 子目录，已完成候选逐个叠加只读挂载；配置只读，sessions 和 test 用空的只读目录遮蔽。

| 宿主机来源 | proposer 路径 | 权限 |
| --- | --- | --- |
| `P/harnesses/E/` | `/workspace/harness/` | 可写 |
| `P/runs/E/` | `/workspace/runs/` | 可创建本轮 hash 目录，按下述规则限制子路径 |
| `P/runs/E/config.yaml` | `/workspace/runs/config.yaml` | 只读 |
| `P/runs/E/<已完成tree_hash>/` | `/workspace/runs/<已完成tree_hash>/` | 逐个只读挂载 |
| `P/benchmark/` 中的代码、合同及 Train/Val 输入 | `/workspace/benchmark/` | 只读，Test 输入不挂载 |
| `P/.claude/skills/meta-meta-harness/` | `/workspace/.claude/skills/meta-meta-harness/` | 只读 |
| `P/runs/E/sessions/<本轮>/state/` | `/tmp/claude-state/` | 可写 |

源码 tree hash 由 benchmark 根据本轮工作区计算，直接在可写的产物根目录下创建对应目录。总分路径始终为 `/workspace/runs/<tree_hash>/results/summary.json`，Git notes 直接引用该路径。续跑时保留未完成版本的目录可写。

本轮任务参数给出使用上述固定路径的完整 benchmark 命令；runner 根据当前源码确定输出目录，proposer 无需传入实验名或候选编号。proposer 直接前台执行，等待完成，再读取分数和轨迹，最后提交及附加 notes。评测使用实验固定配置；其他实验、Test 和历史 proposer sessions 保持不可见。

memory 准备和 solver 隔离直接沿用 MetaHarness：准备只获得当前任务的训练数据；solver 只获得当前候选的求解代码、当前任务的固定 memory、单题输入及独立工作目录。Git 仓库及演化历史不提供给 solver。

### solver（agent）侧

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

**skill** 是 `solver/skills/answer-with-examples/SKILL.md` 全文，三行：

```text
1. Call `retrieve_examples` before answering.
2. Match the wording, format and level of detail of the examples' answers.
3. Reply as JSON: `{"reasoning": "[your reasoning]", "final_answer": "[your answer]"}`
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

## 6. 固定实验协议

本节只写规则，不写数值。模型、轮数、时限、并发、调用上限、采样次数、epoch、seed 与任务划分都是实验配置，创建实验时写入 `runs/<实验名>/config.yaml` 并固定，设计里不重复一遍。**设计约束只有一条：同一个实验内这些值不得中途更改，切换模型、划分或预算必须换新实验名。**

候选总分沿用 benchmark 返回的各任务准确率等权平均；失败题计入分母按错处理，任务的全部样本都执行过即生成正式准确率，全部任务都有正式准确率即生成候选总分与 `rankable`。memory 准备失败或受限运行（`--limit`、任务子集）只保留局部分数、完成率、工具返回文本字符数和错误明细。需要选取最优版本时直接比较完整结果，不维护独立前沿文件。

由于 benchmark 在 proposer 前台调用内运行，需要单独计时：**评测等待时间不计入 proposer 的活动预算**，评测继续受配置中的准备、单题及请求时限约束。前台 Bash 等待上限需覆盖评测，不能沿用包含 benchmark 的整进程超时。轨迹分别记录 proposer 活动时间、benchmark 时间及总墙钟时间。

memory 在 Val/Test 期间固定，只有准备阶段可写。

新实验使用同一份 baseline 源码与相同协议独立起跑，不读取 MetaHarness 的候选、分数、notes、失败经验和已有 memory。初始版本一致、搜索历史独立，才可以比较两种流程。

## 7. 续跑、结束与交付

续跑读取当前会话、Git 状态和 tree hash 目录中的结果：尚未评测则继续当前改动，评测中断则使用同一源码在原目录补齐，已有结果则继续分析、commit 及 notes，已经提交则只补齐版本关联和 notes。完整结束的版本不自动重跑。

完成指定轮数后停止，可在相同协议下追加轮数。切换模型、划分或预算使用新实验名，不覆盖原记录。

只有用户显式指定 Test 才冻结实验。从 harness Git 仓库按选定 commit 导出 Test 所用源码，根据其 tree hash 定位 Val 目录并复制其中的固定 memory，记录来源实验、轮次、tree、commit 和 Test 标识；全部产物放入 `test/<commit_hash>/`。Test 时 commit 已存在，可直接用其 hash 命名。不重新训练，也不向 proposer 反馈 Test 结果，冻结后的实验不再进化。

实现入口如下，运行前按 README 配置密钥：

```bash
.venv/bin/python -u outerloop/meta_meta_harness.py --run-name experiment_a --baseline /absolute/path/to/baseline --iterations 3
.venv/bin/python -u outerloop/meta_meta_harness.py --run-name experiment_a --iterations 6
.venv/bin/python -u outerloop/meta_meta_harness.py --run-name experiment_a --test-commits <baseline_sha> <candidate_sha>
```

`README.md` 在实现时说明配置更换、首次启动、原命令续跑、进度与结果位置，以及备份和恢复。备份必须同时保存 harness 仓库的工作区、全部 Git 对象及 refs/notes、runs 和配置，恢复时使用相同的固定数据源；清理实验必须同时处理对应候选 Git 与运行记录，不能只删日志。完成至少 5 轮的实验按 workspace 约定先备份。

进度保持简洁：proposer 只报阶段、具体活动、耗时和候选情况；benchmark 只报当前候选和最新分数。分析写入 commit message 和 notes，原始会话和执行细节保存在 sessions 与 traces。

首版已直接移植原 MetaMetaHarness Skill 与模板，复用当前 MetaHarness 的 benchmark 和 baseline，并适配路径、Git 结果关联、会话恢复及显式 Test。保持先评测并分析、再 commit 和 notes 的原顺序。使用方法见 README。
