# Domain Reference — Text Classification


## 0. Target

Maximize the equal-weight average accuracy across the three tasks with one general-purpose
harness.

Evaluation is offline: each task prepares its memory from Train once, the memory is frozen
for Val and Test, and Val/Test labels are never fed back to the harness. Data lives under
`/workspace/benchmark/data/`; only Train and Val inputs are visible during evolution.


## 1. Interface

The evolution object is the harness folder `/workspace/harness`: files inside it may
change, nothing outside it. Everything in it is in scope — system prompt, user prompt,
skills, tools, memory structure, retriever; new skills and tools may be added. It MUST
contain:

```text
prepare_memory.py
solver/agent.py        # with supporting prompts, tools and skills
```

`prepare_memory.py` runs in an isolated process before evaluation:

```bash
python prepare_memory.py --epochs N
```

- Read training examples from `/input/train.json`.
- Write `/output/memory.json` and any additional memory files under `/output`.
- Use the supplied fixed model through `MODEL_BASE_URL`, `MODEL_API_KEY`, `MODEL_NAME`;
  its settings are in `/runtime/model.json`.
- Preparation sees only the current task's training examples; the result is copied
  read-only to the solver as `/harness/memory`.

The solver entry point is:

```python
def build_agent(model, input_text, config):
    # Factory: build the agent and prompt the benchmark invokes per question.
    return agent, prompt
```

The agent runs at COLD START and must return JSON containing `final_answer`. It sees
`/harness` (its own code and the frozen memory, read-only) and a writable `/workspace`; the
current example arrives as `input_text`.

Limits per question: 32 model calls, 420 s deadline, 120 s per tool call, 90 s per model
request; memory preparation: 900 s. Exceeding the question deadline is recorded as
`timeout`.


## 2. Runner output

The runner writes one directory per evaluated source tree and prints one JSON object: the
three task accuracies, their mean and the evaluation status, each rounded to four decimals.

```json
{"USPTO": 0.2333, "Symptom2Disease": 0.83, "LawBench": 0.53, "average": 0.5311, "status": "partial"}
```

- Each task value is that task's validation accuracy; a failed sample stays in the
  denominator and counts as wrong.
- `average` = arithmetic mean of the three task accuracies; use it as the aggregate
  comparison score.
- `status` is `ok` when every sample of all three tasks ran, `partial` when only some ran,
  and `error` when none did.
- Only a complete three-task run counts as a result to compare: `rankable` is false for a
  partial run or a run restricted with `--limit`.
- Everything else the runner computes — `rankable`, per-task `completion_rate` and
  `successful_accuracy`, `memory_context_chars`, error counts — is written to
  `results/summary.json` on disk and is not printed.

### 2.1 Mandatory benchmark invocation

Run the benchmark with this command, unchanged, for both baseline and candidate:

```bash
/opt/venv/bin/python -u /workspace/benchmark/run.py evaluate \
  --run-dir /workspace/runs \
  --candidate /workspace/harness
```

Do not substitute another repository/interpreter or invoke the benchmark modules directly.
If the runner did not launch (wrong path/interpreter/workspace), fix the invocation and
retry once; otherwise the single invocation is final. Only the runner's written summary
and its printed scores are authoritative.


## 3. Trace

Per evaluation, under the run evidence directory from the run binding:

```text
<run-dir>/<source-tree>/
├── manifest.json                     # evaluated tree, actual parent, config, timing
├── <task>/memory.json                # frozen training memory for this source
├── <task>/conversations/<index>/
│   ├── sample-<k>.json               # one execution: header statistics, messages, side_calls
│   └── sample-<k>.tmp/               # what the harness left in /workspace, only when non-empty
├── <task>/conversations/prepare/     # memory preparation conversations
└── results/
    ├── samples.jsonl                 # one line per sample, built from the conversation headers
    └── summary.json                  # complete runner result
```

Read `results/samples.jsonl` first: one line per sample with `task`, `tree_hash`, `split`,
`example_index`, `sample_index`, `status`, `error`, `was_correct`, `prediction`, `target`,
`metric`, `usage` (`model_calls`, `input_tokens`, `output_tokens`), `elapsed_seconds`,
`memory_context_chars`, `tool_calls`, `finish_reasons`, `truncated`, `repair_turns` and
`retries`. The matching conversation file holds the main line in `messages` and any
independent conversations in `side_calls`; a writable workspace the harness left files in
is kept beside it as `sample-<k>.tmp/`. It is the only trace, there is no per-call or
per-token record.

The evidence root is `/workspace/runs`; each evaluation lives in
`/workspace/runs/<source-tree>/`. Keep the source unchanged during and after evaluation.
Commit each candidate on a `codex/<candidate-name>` branch and attach the note to
`refs/notes/evolution`, using the templates in
`/workspace/.claude/skills/meta-meta-harness/references/` and the order the Skill
specifies; the controller matches the commit's tree and actual parent against this
directory and requires its note before the round counts as finished.


## 4. Requirements

### 4.1 Anti-overfitting

- No dataset names, label names, or domain-specific keyword lists in candidate code,
  prompts, comments, class names, or function names.
- No branching on which dataset is running.
- A candidate that would behave differently if the datasets were renamed is overfit —
  rewrite it.
- Parameter-only variants do not count as candidates: changing pool size, retrieval
  count, similarity threshold, context budget, ranking weights, or prompt wording with
  otherwise-identical logic.
