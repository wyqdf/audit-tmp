---
name: meta-meta-harness
description: Auto-evolve a harness using evolution history and benchmark feedback.
---

# Meta-Meta-Harness

## world view

Self-evolution unfolds an evolution graph:

```text
N0 (root, baseline)
├── N1 ──┬── N3 ──┬── N5
│        │        └── N6
│        └── N4 ───── N7
└── N2
```

**node:** each commit of the harness: the harness code, its evaluation results, and the records below. Its parent is the commit it was derived from.

- **commit message:** an overview of the node. `Issue` states the problem or motivation, `Modification` states the mechanism or behavior changed, and `Results` records the complete evaluation result and whether the expected effect was achieved.
- **notes:** a summary of the changes made and their impact. It captures the reasoning and mechanism behind the evolution step, summarizes the observed behavior, and cites the original traces. Notes are attached to the evaluated commit under `refs/notes/evolution`.
- **traces:** the raw trajectory of evaluation, one file per sample: its conversation and outcome.

**edge:** the parent→child link: the code diff and the score change between the two nodes.

**evolution graph:** a directed acyclic graph (DAG) of nodes.

## Baseline Initialization

When there are no notes yet:

- Run the baseline using the command in [Evaluation Runner](#evaluation-runner).
- Attach notes to its commit.
- Proceed to Stage 1.

## Workflow

### Stage 1: Lineage Analysis

#### 1.1 Evolution History analysis

Obtain an overview of the evolution history from the graph, code differences, commit messages, and the evaluation results.
Then investigate a specific problem using the notes and traces of the relevant evolution steps.

Use these commands to inspect the history and parent-child changes:

```bash
git -C /workspace/harness log --branches --graph --decorate --oneline
git -C /workspace/harness show -s --format=raw <commit>
git -C /workspace/harness notes --ref=refs/notes/evolution show <commit>
git -C /workspace/harness diff <parent-commit> <child-commit>
```

#### 1.2 Parent Harness Selection and Improvement Plan

Select a strong or promising node as the parent node, then decide how to improve it based on the history analysis. 
Choose one clear, solvable problem and a mechanism to address it.

### Stage 2: Evolution

#### 2.1 Modification

Create and switch to a branch from the parent node, then implement the improvement to produce the candidate:

```bash
git -C /workspace/harness switch -c <candidate-name> <parent-commit>
```

#### 2.2 Evaluation

Evaluate the candidate using the command in [Evaluation Runner](#evaluation-runner) in one foreground Bash call, blocking until it fully completes, to obtain its evaluation result.

#### 2.3 Evolution Graph Update

Commit the candidate using the commit message template:

```bash
git -C /workspace/harness add -A && git -C /workspace/harness commit -F <commit-message-file>
```

Attach a note summarizing the changes and their impact to the evaluated commit:

```bash
git -C /workspace/harness notes --ref=refs/notes/evolution add -m "<notes>" <evaluated-commit>
```

## Template

### commit message

```text
Issue: <State the concrete problem or motivation, grounded in historical evidence when available>

Modification: <State what mechanism or behavior was actually changed>

Results: {"evaluation_result": <the complete evaluation result>, "message": "<whether the expected effect was achieved and briefly why>"}
```

### Note

```markdown
# Notes for <evaluated commit SHA>

Example note entries:
- <concise evolution reasoning and mechanism summary>
- <trace-derived summary of the run's behavior and important patterns> [[<trace/file ref>]]
- <additional important finding or analysis> [[<trace/file ref>]]
- ...
```

Rules:

- Summarize the reasoning, changes, and main findings from the evaluation.
- Cite the relevant traces or files for evidence-based findings.

## Constraints

- Do not call any model except through the evaluation runner.
- Change only files inside `/workspace/harness`, and keep the source unchanged during and after evaluation.
- Do not hardcode dataset names, label names, or domain-specific keyword lists, or branch on dataset identity.
- Do not feed Val/Test labels back to the harness.

## Task

### Evolution Target

Maximize the equal-weight average accuracy across the three tasks with one general-purpose harness.

The evolution object is the harness folder `/workspace/harness`. Everything in it is in scope — system prompt, user prompt, skills, tools, memory structure, retriever; new skills and tools may be added.

Evaluation is offline: each task prepares its memory from Train once, and the memory is frozen for Val and Test. Only Train and Val inputs are visible during evolution.

Train supplies memory and retrieval examples. Val supplies the evaluation results and feedback used during evolution. Test is evaluated separately after evolution.

### harness Interface

```text
prepare_memory.py    # the runner executes this script
solver/agent.py      # the runner calls build_agent(model, input_text, config)
```

### Evaluation Runner

Evaluate both baseline and candidate with this command:

```bash
/opt/venv/bin/python -u /workspace/benchmark/run.py evaluate \
  --run-dir /workspace/runs \
  --candidate /workspace/harness
```

The evaluation result reports Val accuracy for each task, their mean (`average`), and the status:

```json
{"USPTO": 0.2333, "Symptom2Disease": 0.83, "LawBench": 0.53, "average": 0.5311, "status": "partial"}
```

### Directory Structure

```text
/workspace/
├── harness/                         # harness source to evolve
│   ├── prepare_memory.py            # memory preparation
│   └── solver/
│       └── agent.py                 # solver entry point, with supporting resources
├── benchmark/
│   ├── run.py                       # evaluation runner
│   └── data/                        # task data
└── runs/                            # evaluation evidence
    └── <tree-hash>/                 # the evaluated commit's tree hash
        ├── manifest.json            # tree hash, actual parent, config, timing
        ├── <task>/
        │   ├── memory.json          # frozen training memory for this tree
        │   └── conversations/
        │       ├── prepare/         # memory preparation traces
        │       └── <index>/
        │           ├── sample-<k>.json  # one trace: conversation and outcome
        │           └── sample-<k>.tmp/  # non-empty files left in /workspace
        └── results/
            ├── samples.jsonl        # one line per trace
            └── summary.json         # the complete evaluation result
```

**`results/summary.json` — the evaluation result:**

```jsonc
{
  "scores": {
    "<task>": {"accuracy": 0.7} // Accuracy for each task; <task> is its name
  },
  "average": 0.7,              // Equal-weight mean of task accuracies
  "rankable": true             // Whether this result can be used to compare versions
}
```

**`<task>/conversations/<index>/sample-<k>.json` — one trace:**

```jsonc
{
  "prediction": "label A",    // Solver answer
  "target": "label B",        // Reference answer
  "was_correct": false,       // Whether the evaluator marked the answer correct
  "status": "ok",             // Execution status: ok, error, or timeout
  "error": null,              // Execution failure details, if any
  "messages": [               // the trace's conversation, including tool interactions
    {"role": "user", "content": "input text"}, // role: speaker; content: message text
    {"role": "assistant", "content": "{\"final_answer\": \"label A\"}"}
  ],
  "side_calls": []            // Independent conversations started by the solver
}
```
