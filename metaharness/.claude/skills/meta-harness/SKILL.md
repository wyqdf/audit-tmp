---
name: meta-harness
description: Run one iteration of harness evolution. Called by meta_harness.py or interactively via /meta-harness.
---

# Meta-Harness (Harness Evolution)

Run ONE iteration of harness evolution. Do all work in the main session — do NOT delegate to subagents.

The evolution object is the candidate harness folder (`harnesses/<name>/`): files inside it may change, nothing outside it. Everything in it is in scope — system prompt, user prompt, skills, tools, memory structure, retriever; new skills and tools may be added.

**You do NOT run benchmarks.** You analyze results + prediction traces and implement new systems. The outer loop (`meta_harness.py`) handles benchmarking separately.

## CRITICAL CONSTRAINTS

- You MUST evolve the whole harness every iteration.
- Do NOT write "the frontier is optimal" or "stop iterating", or abort early.
- Design exactly 1 candidate per iteration.
- Write only `harnesses/<new_name>/`, `reports/`, and `pending_eval.json`. Submit, then stop.
- Work in `/workspace`; use relative paths.

### Anti-overfitting rules

- **No dataset-specific hints.** Do not hardcode knowledge about specific datasets. Memory systems must be general-purpose.
- **Never mention dataset names** in system code, prompts, or comments.
- **General patterns are OK.** Rules like "prioritize recent errors" or "balance label coverage" are fine — they apply broadly.

## WORKFLOW

**Do ALL steps yourself in the main session.**

### Step 0: Post-eval reports (write if missing)

For each past iteration that has results in `history/evolution_summary.jsonl` but NO report in `reports/`, write one. Each report is **<=30 lines**: what changed, which datasets improved/regressed and why, and a takeaway for future iterations.

### Step 1: Analyze

Read the state files — `history/evolution_summary.jsonl` (what's been tried), `history/config.yaml` (datasets and baselines) — plus recent validation prediction and training/memory-preparation conversations under `history/candidates/<name>/<task>/conversations/` when needed. Then formulate 1 falsifiable hypothesis.

### Step 2: Implement

Copy any historical candidate from this experiment to a complete `harnesses/<name>/` directory, then make targeted modifications. Do not edit the submitted parent: copying keeps imports and proven patterns intact. Do not edit `history/config.yaml` to register candidates; the outer loop loads the directory submitted in `pending_eval.json`.

### Step 3: Write pending_eval.json

```json
{
  "iteration": <N>,
  "candidates": [
    {
      "name": "<snake_case_name>",
      "directory": "harnesses/<name>",
      "hypothesis": "<falsifiable claim>"
    }
  ]
}
```

Output: `CANDIDATES: <name>`, then exit.

## Harness Interface

Each candidate is a complete `harnesses/<name>/` directory containing `prepare_memory.py`, `solver/agent.py`, and its supporting files.

```python
# solver/agent.py
def build_agent(model, input_text, config):
    return agent, prompt
```

- Run `prepare_memory.py --epochs N`; read `/input/train.json` and write `/output/memory.json`.
- Generate memory only from training data; never embed Val answers in candidate code, prompts, or memory.
- Training model calls use the supplied fixed model gateway; memory is frozen after training and read-only while solving questions.
- Models, budgets, and runtime are fixed; the final JSON answer must contain `final_answer`.

## Directory Structure

Paths relative to `/workspace`:

- Candidates: `harnesses/` (submitted candidates are read-only)
- State: `history/config.yaml`, `history/evolution_summary.jsonl`
- Val results: `history/results/summary.json` (per task and candidate) and `history/results/samples.jsonl` (one line per sample); sampling follows `history/config.yaml` and all configured samples count toward the score
- Conversations: `history/candidates/<name>/<task>/conversations/` (validation predictions and training/memory preparation)
- Memory state: `history/candidates/<name>/<task>/memory.json`
- Data: `benchmark/data/` (read-only source splits; the fixed benchmark code is mounted next to it and Test inputs are not mounted)
- Reports: `reports/`
- Handoff: `pending_eval.json`
- Never exposed during evolution: test data, results, and traces

The benchmark retries failed questions without repeating successful ones. Use the recorded failure categories; partial scores are diagnostic, and only complete results qualify for ranking.

`history/evolution_summary.jsonl`, the traces above and recent training logs are the only history sources shipped in this trimmed repo.

## evolution_summary.jsonl Format

One JSON object per line, one line per evaluated candidate:

```json
{"iteration": 1, "name": "example_system", "average": 0.45, "status": "ok", "partial": false, "hypothesis": "..."}
```
