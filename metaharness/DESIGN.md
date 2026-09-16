TextClassification 的 Deep Agents 迁移方案

日期：2026-09-08。状态：首版代码已实现，三个任务的基线 memory 已生成于 runs/baseline。已完成本地 agent 构建和文件挂载检查，确认子 agent 工具关闭、memory 只读、生成代码和旧实验目录不可见。当前 solver 已切换为 DeepSeek V4 Flash，并跑通 USPTO 验证集第一题：答案正确，耗时 47.18 秒，共 3 次模型调用。运行方式和结果位置见 README.md。

在 `/home/yepeijie/workspace/mmharness/exp/TextClassification` 将 fewshot_all 基线移植到 Deep Agents，作为后续进化起点。保留基础工具，关闭子 agent，只接入一个检索业务工具。通过文件系统隔离，将当前任务的 memory 挂载到 harness 内。

首版采用 Deep Agents SDK，保留文件操作、规划、上下文管理和技能加载能力；脚本在隔离进程内执行。显式关闭框架默认的通用子 agent，同时不注册同步、异步或动态子 agent，移除对应的委派工具。仅传入空子 agent 列表不能关闭默认通用子 agent，需要同时设置框架提供的关闭选项。[关闭子 agent 的方式](https://docs.langchain.com/oss/python/deepagents/subagents#running-without-subagents)

1. 初始行为

   保留原来的离线训练环节，作为求解前的 memory 生成阶段。runner 负责按原配置选择当前任务的训练数据并调度，harness 负责按原学习逻辑生成 memory 内容。收到一道评测题后，创建独立的隔离进程和求解会话，挂载已生成的该任务 memory，agent 获取示例、完成回答。评测器沿用原来的答案解析和计分方式，保留原数据划分和采样配置。

   fewshot_all 的原学习逻辑是依次保存训练样例的 `input`、正确答案 `target`，以及存在时的 `raw_question`，最后序列化为 `{"examples": [...]}`。这一步不调用模型。首版直接迁移这段逻辑，并保持原训练顺序和 epoch 语义。[原学习及保存实现](/home/yepeijie/workspace/mmharness/exp/testclassification/official/5.6-sol-D/text_classification/agents/fewshot_memory.py:106)

   生成阶段也在隔离进程中执行：只提供当前任务的训练数据、当前候选中的 memory 生成代码和可写的输出目录。生成完成后，将输出目录冻结；求解阶段只读挂载生成结果和求解代码。生成入口由 runner 调用，其源码不挂载给 solver。

   同一候选、任务、训练划分、seed 和生成配置对应一份 memory，各道题及其重复采样复用该只读快照。生成逻辑或输入改变时重新生成。memory 保存原学习逻辑收集的全部示例，字符预算仅在检索工具格式化返回内容时生效。

   求解路径为：题目 → Deep Agents → 检索工具读取已挂载的 memory → 收到 Q/A 示例 → 输出原格式答案。提示中要求回答前获取示例，后续工具和文件操作由单个 solver 自主执行。

2. 检索工具

   初始只注册一个自定义业务工具 `retrieve_examples()`，绑定当前题目，从沙箱内固定路径 `/harness/memory/memory.json` 读取当前任务的训练示例，返回原来拼入 prompt 的 Q/A 文本。宿主机 memory 来源由外部 runner 决定，工具不接收数据集名称或宿主机文件路径。

   用户已确定按 [fewshot_all.py](/home/yepeijie/workspace/mmharness/exp/testclassification/official/5.6-sol-D/text_classification/agents/fewshot_all.py) 及其父类 [fewshot_memory.py](/home/yepeijie/workspace/mmharness/exp/testclassification/official/5.6-sol-D/text_classification/agents/fewshot_memory.py) 原样移植，保留 30,000 字符上限。这份基线收集训练示例并按原顺序规则拼接，没有独立的语义相关性检索器。

   工具复用原来的示例数量、基于题目生成的确定性随机顺序、原始问题优先的 Q/A 格式，以及字符截断规则。当前这份代码实际限制是 30,000 字符，注释中的 50k 不作为实现依据。

   工具内部首版直接封装上述示例组织逻辑。以后可以修改检索实现、扩充参数或注册新业务工具，初始候选保持一个业务工具。

3. Solver prompt

   保存为候选目录中的独立文本文件，保留原题目输入、根据示例解题的指令，以及以下输出格式：

   ```json
   {"reasoning": "[your reasoning]", "final_answer": "[your answer]"}
   ```

   将原来的内嵌示例占位改为从工具获取示例的说明，新增一句：

   ```text
   Use retrieve_examples to obtain the examples before answering.
   ```

   分类模板仍作为任务消息传入，Deep Agents 的基础工具说明由框架组装。首版就是基线移植：沿用原分类指令和示例组织逻辑，将示例的交付方式改为工具结果，因此完整消息序列和推理调用次数会发生变化。

4. 目录与职责

   实现结构如下：

   ```text
   /home/yepeijie/workspace/mmharness/exp/TextClassification/
   ├── DESIGN.md
   ├── README.md                 使用方式、配置和评测协议
   ├── pyproject.toml            依赖及固定版本
   ├── config.yaml               模型、数据、并发、每题预算
   ├── run.py                    单题和批量评测入口
   ├── benchmark/                固定的执行设施、数据加载、答案解析和评分适配
   │   └── runtime/              模型接入、隔离进程、挂载、调用统计
   ├── harness/                  整体保存、加载和进化的候选
   │   ├── prepare_memory.py      原离线学习逻辑，仅在生成阶段执行
   │   └── solver/                求解阶段挂载到沙箱内 /harness
   │       ├── agent.py           组装 Deep Agents
   │       ├── solver.md          分类 prompt
   │       ├── tools/
   │       │   ├── __init__.py    明确注册业务工具
   │       │   └── retrieval.py   原 fewshot_all 示例获取逻辑
   │       ├── skills/            初始为空，可容纳技能及辅助脚本
   │       └── memory/            沙箱内挂载点，候选中为空
   └── runs/                     任务 memory 快照、候选快照、每题工作区和记录
   ```

   直接使用 Deep Agents 的组装和技能能力；业务工具用一个明确的注册列表接入。生成逻辑与求解部分一同保存在候选中，用于版本管理和后续进化；运行时按阶段分别挂载。solver 直接读取 memory 产物，不依赖生成入口。外围运行入口负责数据和评测。

5. 技能与后续进化

   每个技能使用标准目录格式，包含 `SKILL.md`，可附带脚本和参考文件。每个新求解会话从当前候选快照发现技能，按需读取。首版技能目录为空，并接通实际加载机制。[技能加载机制](https://docs.langchain.com/oss/python/deepagents/skills)

   后续进化的单位是整个 harness 目录，包括入口、memory 生成逻辑、prompt、tools 和 skills。每一轮可以继承已有技能继续修改，也可以组合、删除技能或增加工具；一次候选评测绑定整个目录的固定版本。

   Solver 的当题工作文件保存在独立临时目录。它产生的技能草稿可以随执行记录输出，由后续进化决定是否纳入下一版候选。评测期间不把某道题产生的文件自动传播给其他题。

   技能目录必须被实际加载进 agent；仅创建文件夹不构成技能能力。生成、筛选和继承技能属于后续进化流程，首版先提供可运行的初始候选及其评测接口。

6. 运行和评测边界

   模型接入改用能够保留完整多轮消息、工具定义和工具调用结果的聊天模型客户端。旧的字符串输入、字符串输出封装不直接作为 agent 的模型接口。模型和 API 地址通过配置传入；如沿用已查看的 NVIDIA 网关，使用非流式请求，该网关当前拒绝 streaming 请求。上游模型是否完整支持工具调用仍是实现接入时需要确认的事项。

   每道题及其重复采样使用新的隔离进程、会话和工作区。采用 bubblewrap 为整个 solver 进程建立独立文件系统视图，并隔离进程视图；检索工具、文件工具和脚本执行都在该视图内运行。[隔离和挂载机制](https://github.com/containers/bubblewrap)

   挂载约定如下，沙箱内路径在所有任务中保持一致：

   | 来源 | 沙箱内位置 | 权限 |
   | --- | --- | --- |
   | 本轮冻结候选的 `harness/solver/` 子目录，含求解入口、prompt、tools、skills | `/harness` | 只读 |
   | 当前任务的 memory 输出目录，初始包含 `memory.json` | `/harness/memory` | 求解阶段只读 |
   | 当前题目、当前采样独有的工作目录 | `/workspace` | 可读写 |
   | 必要的解释器、依赖和运行组件 | 对应运行时路径 | 只读 |
   | 当前隔离进程的临时空间 | `/tmp` | 独立、可读写 |

   memory 生成阶段使用独立挂载：生成入口挂到 `/prepare/prepare_memory.py`（只读），当前任务的训练样例挂到 `/input/train.json`（只读），当前候选、当前任务独有的输出目录挂到 `/output`（可写）。两阶段复用必要运行依赖；生成阶段结束后，求解阶段只将该输出目录只读挂到 `/harness/memory`，不挂载生成代码及原始训练输入文件。

   求解阶段只挂载 `harness/solver/` 子目录，不挂载包含 `prepare_memory.py` 的完整候选目录。

   例如运行 USPTO 时，runner 只将 USPTO 的 memory 输出目录挂到 `/harness/memory`，检索工具读取其中的 `memory.json`；换任务时替换该目录的挂载来源。其他任务的 memory、完整数据目录、验证和测试答案、benchmark 源码、旧实验目录及宿主机 workspace 不挂载。单题输入由 runner 传入，正确答案留在外部评分。

   挂载点中的 memory 是训练示例数据，与 skills 中可继承的方法分开保存。检索工具读取该文件，基础文件工具也能访问该任务的挂载内容。运行时工作文件和技能草稿写入 `/workspace`，不修改冻结的 harness 或训练 memory。

   使用同一隔离进程约束所有文件访问。Deep Agents 的普通本地 shell 后端仅设置工作目录，本身不限制 shell 访问宿主机其他路径，因此文件隔离由外部进程沙箱落实。[后端说明](https://docs.langchain.com/oss/python/deepagents/backends)

   每题预算先采用较宽松的暂定值：最多 32 次模型调用，总超时 900 秒（15 分钟）。在 `config.yaml` 中分别配置 `solver.max_model_calls` 和 `solver.timeout_seconds`，模型、API 地址和全局调用并发也通过配置提供。用户已明确这些参数可以后续调整，当前无需继续定值。

   全部 solver 调用共享全局模型并发限制并计入用量。记录完整模型消息、工具调用与返回、技能读取、最终答案、得分、耗时和 token 用量，结果绑定候选版本及当前任务 memory 快照。

首版交付范围是：单 solver 的 Deep Agents 基线移植、一个沿用原行为的示例检索工具、原分类 prompt 的最小适配、已接通的空技能目录、按任务挂载 memory 的文件隔离，以及原评测流程的接入和使用说明。后续进化可直接围绕整个 harness 目录开展。
