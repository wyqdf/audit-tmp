# audit-tmp — MetaHarness / MetaMetaHarness 实验存档

两代 harness 自进化框架的代码与运行记录存档：外层循环代码、被进化的 harness 源码、以及各自最新一次多轮实验的完整记录（逐样本 traces + proposer 会话）。

## 目录

```
metametaharness/                    本代（MetaMetaHarness）：proposer + Skill 工作流
  outerloop/  benchmark/  adapters/  .claude/skills/meta-meta-harness/
  config.yaml  config.deepseek.yaml  DESIGN.md  README.md
  metametaharness.bundle            该仓库 git 历史
  versions/20260913-dc67268/        references + domainspecific 时代的外层代码快照
  versions/20260913-dc67268.SKILL-as-used.md   该 run 会话中实际读到的 SKILL.md
  versions/20260917-skillv4/        当前 Skill（单行 system/user prompt）的外层代码快照
  versions/20260917-skillv4.SKILL-as-used.md   该 run 会话中实际读到的 SKILL.md
  versions/20260917-skillv4.diff.patch         相对 dc67268 的未提交改动（1952 行）
  runs/qwen3.7-flash-val2-skillv4-15rounds-20260916/    当前 Skill，15 轮（并发 24）
  runs/qwen3.7-flash-val2-skillv4-15rounds-20260916-b/  同配置的第二份轨迹
  runs/qwen3.7-flash-val2-skillv3-15rounds-20260916/    Skill v3，15 轮
  runs/qwen3.7-flash-val2-skillv2-3rounds-20260915/     Skill v2（旧），14 个候选
  runs/qwen3.7-flash-val2-15rounds-copy-20260913/       references + domainspecific 时代，15 轮
  runs/*.log                        上述运行的 stdout 日志（有则收录）

metaharness/                        上一代（MetaHarness）
  outerloop/  benchmark/  adapters/  .claude/  .agents/
  config*.yaml  DESIGN.md  desigen.md
  metaharness.bundle                该仓库 git 历史（41 个提交）
  runs/qwen3.7-flash-val2-15rounds-copy-20260913/

harness/
  metametaharness/
    qwen3.7-flash-val2-skillv4-15rounds-20260916.bundle     全部分支 + refs/notes/evolution
    qwen3.7-flash-val2-skillv4-15rounds-20260916-src/       最佳节点（N5 `d8f5ef0a`）源码
    qwen3.7-flash-val2-skillv4-15rounds-20260916.notes.md   16 轮的 commit + 进化笔记全文
    qwen3.7-flash-val2-skillv4-15rounds-20260916-b.bundle   同上（第二份轨迹）
    qwen3.7-flash-val2-skillv4-15rounds-20260916-b-src/     最佳节点（N8 `b823e605`）源码
    qwen3.7-flash-val2-skillv4-15rounds-20260916-b.notes.md
    qwen3.7-flash-val2-skillv3-15rounds-20260916.bundle   全部分支 + refs/notes/evolution
    HEAD/                                                末轮源码快照
    qwen3.7-flash-val2-skillv2-3rounds-20260915.bundle   全部分支 + refs/notes/evolution
    qwen3.7-flash-val2-skillv2-3rounds-20260915-src/     末轮源码快照
    qwen3.7-flash-val2-15rounds-copy-20260913.bundle     全部分支 + refs/notes/evolution
    qwen3.7-flash-val2-15rounds-copy-20260913-src/       末轮源码快照
  metaharness/
    qwen3.7-flash-val2-15rounds-copy-20260913.bundle      仓库 ref
    qwen3.7-flash-val2-15rounds-copy-20260913/            baseline 与各轮候选源码目录
```

## metametaharness 运行：`qwen3.7-flash-val2-skillv4-15rounds-20260916` 与 `…-20260916-b`（同配置两份轨迹）

当前 Skill：system prompt 只有一行 `You are the proposer in a harness self-evolution process.`，user prompt 只有一行 `Run evolution iteration {iteration} using the meta-meta-harness skill at /workspace/.claude/skills/meta-meta-harness/SKILL.md.`，全部流程写进 `SKILL.md`（不再引用 `references/`，也不再提 `domainspecific`）。两份轨迹同配置、同 baseline、各 24 并发同时启动。

| 项 | A `…-20260916` | B `…-20260916-b` |
|---|---|---|
| 起止 | 09-16 23:57 → 09-17 08:02（末轮崩溃退出） | 09-16 23:57 → 09-17 05:50（跑完全部轮次退出） |
| 轮数 | 0–14 完成，N15 未提交 | 0–15 全部完成 |
| 平均分 | 基线 `9f49dd72`/`ea3b299c` 0.4367 → 最高 **N5 `d8f5ef0a` 0.5644** | 基线 `9f49dd72`/`3d84679d` 0.4367 → 最高 **N8 `b823e605` 0.5656** |
| 谱系 | 纯单链，14/14 轮接上一轮，无合并 | 纯单链，15/15 轮接上一轮，无合并 |
| 有效轮次 | N0–N12（N13 部分受损），N14 基建故障、N15 未完成 | N0–N12，N13–N15 作废 |

配置：`runtime.model_concurrency: 24`、`parallel_questions: 24`；`--iterations 15`（= 轮 0–15，共 16 轮）；baseline `metaharness/harnesses/glm53flash_10rounds/baseline`。`runs/<run>/` 内容与上一节相同（`sessions/000…015`、16 个 tree 的 `manifest.json`、`results/summary.json`、260 条 `results/samples.jsonl`、逐题 `sample-*.json`、`memory.json`）。

逐轮平均分（同一 baseline 的两份独立轨迹）：

| 轮 | 0 | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 | 9 | 10 | 11 | 12 | 13 | 14 | 15 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| A | .4367 | .4933 | .4989 | .5256 | .5344 | **.5644** | .5333 | .5333 | .5456 | .5267 | .5311 | .5133 | .5367 | .5411 | 0 | — |
| B | .4367 | .4522 | .4922 | .4978 | .4956 | .5144 | .4967 | .5122 | **.5656** | .5489 | .5367 | .5533 | .5511 | 0 | 0 | 0 |

分任务（轮 0 → 最好的有效轮）：A 的 USPTO 0.200→0.283、Symptom2Disease 0.800→0.890、LawBench 0.310→0.520（N12 达 0.570）；B 的 USPTO 0.150→0.267、Symptom2Disease 0.880→0.890、LawBench 0.280→0.540（N11/N12 达 0.590）。涨分几乎全部来自 LawBench。

节点对照（tree → commit → 均值 → 分支）：A 基线 `9f49dd72`/`ea3b299c` 0.4367；N1 `bca9cc83`/`d7b155f0` 0.4933；N2 `e2c96b80`/`3340e638` 0.4989；N3 `8b90b9c5`/`7628d2a1` 0.5256；N4 `3c5c61e1`/`e5d4cc50` 0.5344；N5 `37a3ebb7`/`d8f5ef0a` 0.5644；N6 `cd1bd0d4`/`3bb9672c` 0.5333；N7 `b000c8ef`/`5402cb12` 0.5333；N8 `4383c626`/`a311512c` 0.5456；N9 `ceeb3c6c`/`cadc26b5` 0.5267；N10 `84fb7ecd`/`bc19c512` 0.5311；N11 `8ccc1139`/`f071ba28` 0.5133；N12 `b51d7d5a`/`921c0698` 0.5367；N13 `4b32c77a`/`794d93eb` 0.5411；N14 `f940a453`/`152cd1aa` 0.0000；N15 无提交。
B 基线 `9f49dd72`/`3d84679d` 0.4367；N1 `b539c7be`/`13a6c63a` 0.4522；N2 `562ab087`/`419618e1` 0.4922；N3 `57a4d05c`/`49c9c67d` 0.4978；N4 `54fcbc30`/`e05c6f0d` 0.4956；N5 `7dacda0a`/`99acee1b` 0.5144；N6 `268efd93`/`7baad647` 0.4967；N7 `e16a2b19`/`ece44663` 0.5122；N8 `03d84c38`/`b823e605` 0.5656；N9 `0f46c28c`/`7f99ffff` 0.5489；N10 `32c01b54`/`9b04306a` 0.5367；N11 `744847db`/`0df22b3a` 0.5533；N12 `8f5a4844`/`b6060a91` 0.5511；N13 `f83d88b2`/`52a532fd` 0.0000；N14 `615d1db7`/`ae4fb7cb` 0.0000；N15 `7ad60114`/`c1a5a1ba` 0.0000。

**尾部 0 分与 A 的崩溃（不是候选的问题）**：09-17 05:24:59 起 solver 侧（阿里云百炼）账户欠费，样本报 `invalid_request: Access denied … #overdue-payment`，0 token、0 次模型调用；最后一条成功样本 05:25:41。此后 A 的 N13 有 22/260 条落在欠费（全部 LawBench，故 0.5411 被低估），N14 撞上另一个故障 `bwrap: Can't bind mount /oldroot/etc/ld.so.cache`（260/260 `execution_error`，评测 2 秒结束），N15 无提交 → `confirm_round` 不通过，进程抛 `RuntimeError: Round is incomplete` 退出；B 的 N13–N15 各 260/260 全部欠费。运行日志见 `runs/<run>.log`。

**谱系观察**：两条都是纯单链，每一轮都取上一轮作为父节点，从没回头用更早的强节点——A 的 N5（0.5644）和 B 的 N8（0.5656）在各自链上再没被用过。旧版 Skill 里的 `Select a strong or promising parent … do not default to the latest node or current HEAD` 在当前 `SKILL.md` 中已被删除；每轮 note 的第一条又都回到父节点 note 结尾的缺陷（如 A N6/N8 "Chosen from the parent's own evidence … the parent's note ended on …"），note 最后一条是新的 limit / next step（A 9/14 轮、B 14/15 轮如此收尾），形成接力式单链。

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

## metametaharness 运行：`qwen3.7-flash-val2-skillv2-3rounds-20260915`（旧 Skill）

| 项 | 值 |
|---|---|
| 会话 / 已评测候选 | 14 / 14 |
| 平均分 | 基线 `9f49dd72`（commit `804b98a9`）0.4378 → 最高 `c757e2f7`（commit `679e7deb`）0.6044 |
| 记录位置 | 每个候选一份 git note（`refs/notes/evolution`），随 bundle 保存 |
| 其他 | `killed-r5-005-1916`、`killed-r5-005-1943b` 为中途被杀的候选目录；根目录 `*.log` 为本次运行的 stdout |

候选平均分（按 tree → commit → 均值）：`9f49dd72`/`804b98a9` 0.4378；`53597ebc`/`adaed03b` 0.4522；`0d30915e`/`32b0dc34` 0.4967；`13b8664b`/`3a72aeca` 0.5156；`fb204702`/`d4199a22` 0.5467；`6baad5e0`/`40218c33` 0.5700；`fcc91464`/`b51ec0b0` 0.5722；`a5092674`/`7b3e5c81` 0.5756；`1542f6fc`/`5998feee` 0.5933；`0949fda6`/`f4201af7` 0.5956；`eda1e173`/`5e63b665` 0.5956；`87d68bc4`/`f45f2755` 0.5967；`113ff5bb`/`9df6a8e5` 0.5978；`c757e2f7`/`679e7deb` 0.6044。

## metametaharness 运行：`qwen3.7-flash-val2-15rounds-copy-20260913`（references + domainspecific 时代）

这一版的外层循环与现在不同：user prompt 要求先读 **Contract**（`skill + domainspecific`），`SKILL.md` 自身指向两个 references 模板，评测合同放在 `benchmark/domainspecific.md`。这些文件都收在 `versions/20260913-dc67268/` 快照里。

| 项 | 值 |
|---|---|
| 会话 / 候选（含基线） | 15 / 15 |
| 平均分 | 基线 `9f49dd72`（commit `f0ec3e90`）0.4011 → 最高 `8340000d`（commit `348dcbbc`）0.5833 |
| 依赖 | `SKILL.md` 引用 `references/commit-message-template.md`、`references/notes-template.md`；`benchmark/domainspecific.md` 为评测合同 |
| 与其他版本的区别 | 后续 Skill v2/v3 把评测合同并入 `SKILL.md`，不再引用 references 模板 |

候选平均分（tree → commit → 均值）：`9f49dd72`/`f0ec3e90` 0.4011；`8a4e7e02`/`97e9d517` 0.4444；`c40638ad`/`26687402` 0.5167；`554cf786`/`9e1b53e9` 0.5244；`84ec2cc2`/`b8b4c090` 0.5267；`91f82d64`/`bd858644` 0.5278；`b960408c`/`d58f5409` 0.5356；`83ed278a`/`76b74deb` 0.5367；`80a50a61`/`d7dab4e3` 0.5367；`b31e34da`/`a9d3480e` 0.5400；`4621bcdd`/`4131b187` 0.5511；`806c3bda`/`3c6c0d07` 0.5533；`24a695f6`/`e132497b` 0.5578；`5ac00dbb`/`459ed3dd` 0.5667；`8340000d`/`348dcbbc` 0.5833。

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
- 只包含上述六次实验，未包含 `runs/` 下的其他历史 run。
- `versions/20260913-dc67268/` 是外层仓库 `dc67268` 的完整快照；同名 run 实际读到的 `SKILL.md` 与提交版只差一句（`Select a strong or promising parent …` 末尾多 `Do not accumulate changes that had no effect.`），逐字还原在 `versions/20260913-dc67268.SKILL-as-used.md`。
- `versions/20260917-skillv4/` 是当前工作区（HEAD 仍为 `dc67268`，改动未提交）的完整快照，`20260917-skillv4.diff.patch` 是相对 `dc67268` 的 1952 行 diff（含 `SKILL.md` 重写、`outerloop/proposer.py` 的单行 system prompt、`outerloop/prompt.md` 的单行 user prompt），`20260917-skillv4.untracked.txt` 列出未跟踪文件；run 会话中实际读到的 SKILL 全文在 `20260917-skillv4.SKILL-as-used.md`。
- metaharness 的候选源码位于其 `harnesses/<run>/`（每个候选一个目录，非 git 提交），已归档在 `harness/metaharness/<run>/`；metametaharness 的候选是 git 提交，见 bundle。
