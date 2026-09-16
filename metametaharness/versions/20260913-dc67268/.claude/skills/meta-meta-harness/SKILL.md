---
name: meta-meta-harness
description: Auto-evolve a codebase against fixed validation.
---

# Self-evolution

Analyze evolution history, make one mechanism-level modification, run the benchmark once, audit the result, commit once with notes, then stop without further edits or reruns.

- Run binding comes from the task prompt.
- First action every round: read the full evaluation contract and follow it.

### Meta-Meta-Harness worldview

Self-evolution unfolds an evolution tree:

```text
H0 (root, baseline)
├── H1 ──┬── H3 ──┬── H5
│       │        └── H6
│       └── H4 ───── H7
└── H2
```

- Each node is one commit carrying `(code,  r_vec, evolution-story memory，notes)`.
- Each parent-child edge is one causal observation `(diff, Δr_vec)`.
- Multiple evolution steps create multiple branches that coexist as references.
- The whole tree is the accumulated cross-evolution memory and proposer state.

Analyze the tree and its diffs to decide what to evolve next; round numbers and
runner IDs are only labels.

## State

Harness git repois  the evolution graph:
- node = commit; lineage = commit parent
- commit message = issue/modification/results
- notes = the notes ref specified by the run binding, attached to the evaluated commit (bridge between the commit message and raw traces/files)
- traces = lowest-level evidence of actual run behavior

## Loop

do not skip any step, even if you are confident in your changes.

Follow this loop exactly; never deviation.

### Stage 0 — Cold start

No notes yet:
- run the existing harness
- attach notes to its commit
- back to Stage 1

**Output**: node with initial notes and traces.

### Stage 1 — Lineage analysis

- Read and analys the graph (codes diffs,commit messages, notes, scores，traces).
   First review the code diff and commit message for a quick understanding, then conduct a detailed analysis using the notes and traces.
  Use these commands to inspect the history and the parent-child change:
  `git -C <repo> log --branches --graph --decorate --oneline`
  `git -C <repo> show -s --format=fuller <commit>`
  `git -C <repo> notes --ref=<Notes ref> show <commit>`
  `git -C <repo> diff <parent-commit> <child-commit>`

- Select a strong or promising parent and one clear, solvable problem; do not default to the latest node or current `HEAD`.
- Choose one mechanism to address that problem. Do not repeatedly create similar children or keep focusing on the same problem after nearby directions have failed, unless new evidence supports a distinct hypothesis. Record the parent, mechanism, and expected effect as the sole direction for the round.

**Output**: three fixed items —
- parent node (and why)
- fixed direction of mechanism
- expected effect (what traces and scores should show)

### Stage 2 — Evolution

Create and switch to a branch from the selected parent, then implement the direction there:
`git -C <prompt-bound repository> switch -c <Branch-prefix><candidate-name> <parent-commit>`
Never commit on `main`.

**Output**:  changes to implement  the specific direction.

### Stage 3 — Validation

You can proceed to the next step only after completing the current step.

- **3.1 Run** the exact runner command yourself **exactly once per round** in one foreground Bash call and block until it fully completes. Never run it in the background or exit while it is running. **Regardless of the result — success, failure, regression, or infrastructure error — do NOT repeat, retry, or re-invoke Stage 3.1; one invocation per round is final.**
- **3.2 Audit** Audit traces and scores, determine whether the mechanism activated and worked, and fill the notes with cited findings.
- **3.3 Record** Create one template-compliant commit, then attach the note to that evaluated commit in Git:
  `git -C <prompt-bound repository> notes --ref=<Notes ref> add -m "<notes>" <evaluated-commit>`
  `<Notes ref>` is bound in the evaluation contract.

Stage only files you changed; never `add -A`.

**Output** (per run): a commit containing the benchmark result and its note.

## Templates (exact format required)

- Commit message: `references/commit-message-template.md`
- Notes: `references/notes-template.md`

## Constraints

- Each candidate must introduce a substantive mechanism change that addresses one clearly identified, evidence-supported problem.
- Run Git only with `git -C <prompt-bound repository> ...`.
- Inspect Git state only in the target repository.
