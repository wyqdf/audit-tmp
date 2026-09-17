---
name: meta-meta-harness
description: Evolve a harness using evolution history and benchmark feedback.
---

# Meta-Meta-Harness

## Overview

The harness is the code and resources in `/workspace/harness` used by the solver.

Each invocation completes one evolution iteration. **Lineage Analysis** selects a parent and plans an improvement from the evolution history. **Evolution** modifies the parent, evaluates the candidate once, and records the outcome for future iterations.

## Evolution Graph

The evolution graph is a directed acyclic graph (DAG) recording harness versions, evaluation evidence, and derivation history.

```text
N0 (root, baseline)
├── N1 ──┬── N3 ──┬── N5
│        │        └── N6
│        └── N4 ───── N7
└── N2
```

**Node:** An evaluated harness version recorded in a Git commit, with its associated results, notes, and traces.

- **Commit message:** An overview of the problem, the change, and the evaluation result.
- **Notes:** An explanation of the change and its observed effects, citing supporting traces. Attached to the evaluated commit under `refs/notes/evolution`.
- **Traces:** One file per evaluated sample, containing its conversation, prediction, reference answer, and execution outcome.

**Edge:** The parent–child commit link stored by Git. The source diff and change in `average` describe the evolution step.

## Baseline Initialization

The baseline is the root commit on `main`. If it has not been evaluated, switch to `main`, run the [Evaluation Runner](#evaluation-runner), and attach evolution notes to that commit.

```bash
git -C /workspace/harness switch main
```

Then proceed to Stage 1.

## Workflow

### Stage 1: Lineage Analysis

#### 1.1 Evolution History Analysis

Review the graph, commit messages, and scores to identify performance trends and relevant evolution steps. Inspect their diffs and notes; read traces when needed to investigate a problem or verify a finding.

```bash
# Evolution history
git -C /workspace/harness log --branches --graph --decorate --oneline

# Commit message and metadata, including tree and parent
git -C /workspace/harness show -s --format=raw <commit>

# Evolution notes
git -C /workspace/harness notes --ref=refs/notes/evolution show <commit>

# Changes from a non-root commit's parent
git -C /workspace/harness diff <commit>^ <commit>
```

The commit's `tree` field identifies `/workspace/runs/<tree-hash>/`, which contains `results/summary.json` and the traces shown in [Directory Structure](#directory-structure).

#### 1.2 Parent Harness Selection and Improvement Plan

Based on the history analysis, select a strong or promising evaluated commit as the parent. Choose one concrete problem, a mechanism to address it, and the expected observable effect.

### Stage 2: Evolution

#### 2.1 Modification

Create a branch from the selected parent and implement the planned change.

```bash
git -C /workspace/harness switch -c <candidate-name> <parent-commit>
```

#### 2.2 Evaluation

Evaluate the candidate once with the [Evaluation Runner](#evaluation-runner), in one foreground Bash call that waits for completion.

Inspect the result and relevant traces to determine whether the expected effect occurred. Record any execution failure alongside the available scores.

#### 2.3 Evolution Graph Update

Commit the evaluated source using the [Commit Message](#commit-message) template.

```bash
git -C /workspace/harness add -A && \
git -C /workspace/harness commit -F - <<'COMMIT_MESSAGE'
<commit message using the template below>
COMMIT_MESSAGE
```

Attach a note using the [Note](#note) template.

```bash
git -C /workspace/harness notes --ref=refs/notes/evolution add -F - HEAD <<'EVOLUTION_NOTE'
<note using the template below>
EVOLUTION_NOTE
```

End this invocation.

## Templates

### Commit Message

```text
Issue: <The concrete problem or motivation, supported by historical evidence when available>

Modification: <The mechanism or behavior actually changed>

Results: {"evaluation_result": <complete result JSON printed by the runner>, "message": "<Whether the expected effect occurred and briefly why>"}
```

If the runner produced no result, use `null` for `evaluation_result` and describe the failure in `message`.

### Note

```markdown
# Evolution Notes

- <Why the change was chosen and how it was intended to work>
- <Observed behavior and its relation to the result> [[<trace-or-file-path>]]
- <Additional finding or limitation> [[<trace-or-file-path>]]
```

Cite the supporting trace or file for each evidence-based finding.

## Constraints

- Call models only through the evaluation runner.
- Manually edit only files inside `/workspace/harness`. Once candidate evaluation starts, keep the harness source unchanged for the rest of this invocation.
- Do not hardcode dataset names, label names, or domain-specific keyword lists, or branch on dataset identity.

## Task

### Evolution Target

**Objective:** Maximize `average`, the equal-weight mean of Val accuracies across all benchmark tasks, using one general-purpose harness.

**Editable scope:** Everything in `/workspace/harness`, including system and user prompts, skills, tools, memory preparation and structure, and retrieval logic.

Train provides examples for preparing memory; the resulting memory is frozen for Val. Val scores and traces guide evolution; Test is evaluated separately afterward.

### Harness Interface

```text
prepare_memory.py    # the runner executes this script
solver/agent.py      # the runner calls build_agent(model, input_text, config)
```

### Evaluation Runner

Use this command for both the baseline and the candidate:

```bash
/opt/venv/bin/python -u /workspace/benchmark/run.py evaluate \
  --run-dir /workspace/runs \
  --candidate /workspace/harness
```

**Output example:**

```jsonc
{
  "USPTO": 0.2333,
  "Symptom2Disease": 0.83,
  "LawBench": 0.53,
  "average": 0.5311,        // Equal-weight mean of task accuracies
  "status": "partial"      // Whether evaluation completed normally, partially, or failed
}
```

### Directory Structure

```text
/workspace/
├── harness/                         # source to evolve
│   ├── prepare_memory.py            # memory preparation
│   └── solver/
│       └── agent.py                 # solver entry point
├── benchmark/
│   ├── run.py                       # evaluation runner
│   └── data/                        # task data
└── runs/
    └── <tree-hash>/                  # evaluated source tree hash
        ├── manifest.json            # evaluation metadata
        ├── <task>/
        │   ├── memory.json          # frozen training memory
        │   └── conversations/
        │       ├── prepare/         # memory preparation traces
        │       └── <index>/
        │           ├── sample-<k>.json  # conversation and outcome
        │           └── sample-<k>.tmp/  # files left in the sample workspace
        └── results/
            ├── samples.jsonl        # per-sample outcomes
            └── summary.json         # detailed evaluation statistics
```

**`results/summary.json` — selected fields:**

```jsonc
{
  "scores": {
    "<task>": {"accuracy": 0.7}
  },
  "average": 0.7,              // Equal-weight mean of task accuracies
  "status": "ok"               // Whether evaluation completed normally, partially, or failed
}
```

**One sample's trace** (`<task>/conversations/<index>/sample-<k>.json`):

```jsonc
{
  "prediction": "label A",     // Solver answer
  "target": "label B",         // Reference answer
  "was_correct": false,        // Whether the answer was marked correct
  "status": "ok",              // Sample execution status: ok, error, or timeout
  "error": null,               // Execution failure details, if any
  "messages": [                // Conversation, including tool interactions
    {"role": "user", "content": "input text"},
    {"role": "assistant", "content": "{\"final_answer\": \"label A\"}"}
  ],
  "side_calls": []             // Independent conversations started by the solver
}
```
