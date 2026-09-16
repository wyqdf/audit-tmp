"""MetaHarness evolution: one proposal, external Val, and an accumulated archive."""

import argparse
import json
import os
from pathlib import Path
import shutil
import sys

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from benchmark.run import evaluate_candidate
from benchmark.runtime.runs import PROJECT, open_experiment, read_json, write_json
from outerloop.proposer import run_agent


def read_history(root):
    latest = {}
    for line in (root / "evolution_summary.jsonl").read_text().splitlines():
        if line.strip():
            row = json.loads(line)
            latest[row["iteration"]] = row
    return [latest[iteration] for iteration in sorted(latest)]


def append_result(root, history, iteration, proposal, result, tasks):
    entry = {**proposal, **result, "iteration": iteration}
    with (root / "evolution_summary.jsonl").open("a") as handle:
        handle.write(json.dumps(entry, ensure_ascii=False) + "\n")
    history[:] = [row for row in history if row["iteration"] != iteration]
    history.append(entry)
    pending = read_json(root / "pending_eval.json")
    if pending.get("iteration") == iteration:
        write_json(root / "pending_eval.json", {})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-name", required=True)
    parser.add_argument("--config", type=Path, default=PROJECT / "config.yaml")
    parser.add_argument("--iterations", type=int)
    parser.add_argument("--baseline", type=Path)
    parser.add_argument("--test-candidates", nargs="+")
    args = parser.parse_args()
    root, config = open_experiment(args.run_name, args.config)
    harnesses = PROJECT / "harnesses" / args.run_name
    harnesses.mkdir(parents=True, exist_ok=True)
    if args.test_candidates:
        for name in args.test_candidates:
            if Path(name).name != name:
                parser.error("Test candidate must be a candidate name")
            evaluate_candidate(root, config, harnesses / name, split="test")
        return 0
    if (root / "finalized.json").exists():
        parser.error("Experiment is frozen after explicit Test; use a new experiment")
    iterations = args.iterations if args.iterations is not None else config["evolution"]["iterations"]
    if iterations < 0:
        parser.error("iterations must be nonnegative")
    for section in ("solver", "proposer") if iterations else ("solver",):
        variable = config[section]["api_key_env"]
        if not os.environ.get(variable):
            parser.error(f"Set {variable}, or {section}.api_key in config.local.yaml")
    baseline = harnesses / "baseline"
    if not baseline.exists():
        if not args.baseline:
            parser.error("Provide --baseline for a new experiment")
        shutil.copytree(
            args.baseline.resolve(), baseline,
            ignore=shutil.ignore_patterns("__pycache__", "*.pyc", ".git"),
        )
    history = read_history(root)
    if not any(row["iteration"] == 0 and row.get("rankable") for row in history):
        result = evaluate_candidate(root, config, baseline)
        append_result(
            root, history, 0,
            {"name": "baseline", "hypothesis": "Initial baseline"},
            result, config["dataset"]["tasks"],
        )
    for iteration in range(1, iterations + 1):
        if any(row["iteration"] == iteration for row in history):
            continue
        pending = read_json(root / "pending_eval.json")
        if not pending:
            run_agent(root, harnesses, iteration, config["proposer"], len(config["dataset"]["tasks"]))
            pending = read_json(root / "pending_eval.json")
        candidates = pending.get("candidates", [])
        if pending.get("iteration") != iteration or len(candidates) != 1:
            raise ValueError("Proposer must hand off exactly one candidate for this iteration")
        proposal = candidates[0]
        name = proposal["name"]
        candidate = harnesses / name
        if Path(name).name != name or candidate.resolve().parent != harnesses.resolve():
            raise ValueError("Candidate must be a folder in this experiment")
        if not candidate.is_dir() or any(row["name"] == name for row in history):
            raise ValueError("Candidate must be a new complete folder")
        result = evaluate_candidate(root, config, candidate)
        append_result(root, history, iteration, proposal, result, config["dataset"]["tasks"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
