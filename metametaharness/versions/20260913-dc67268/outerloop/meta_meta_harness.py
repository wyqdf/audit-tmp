"""Evolve one Git harness repository using the original MetaMetaHarness workflow."""

import argparse
import io
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import tarfile
import time
import uuid

import yaml

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from benchmark.run import evaluate_candidate
from benchmark.runtime import sandbox
from benchmark.runtime.runs import PROJECT, git, open_experiment, read_json, source_tree, write_json
from outerloop.proposer import run_agent

NOTES_REF = "refs/notes/evolution"
DEFAULT_BASELINE = PROJECT.parent / "metaharness/harnesses/glm53flash_10rounds/baseline"


def initialize(root, config, source):
    repo = PROJECT / "harnesses" / root.name
    if (repo / ".git").is_dir():
        return repo
    source = source.resolve()
    if not (source / "prepare_memory.py").is_file() or not (source / "solver/agent.py").is_file():
        raise ValueError("Baseline must contain prepare_memory.py and solver/agent.py")
    shutil.copytree(source, repo, ignore=shutil.ignore_patterns(".git", "__pycache__", "*.pyc"))
    git(repo, "init", "-b", "main")
    git(repo, "config", "user.name", "MetaMetaHarness")
    git(repo, "config", "user.email", "metametaharness@localhost")
    git(repo, "config", "notes.displayRef", NOTES_REF)
    with (repo / ".git/info/exclude").open("a") as handle:
        handle.write("\n__pycache__/\n*.pyc\n")
    git(repo, "add", "--", ".")
    git(repo, "commit", "-m", "Issue: Establish the baseline\n\nModification: Import the initial harness source\n\nResults: Baseline evaluation pending.")
    config["baseline"] = {
        "source": str(source), "commit": git(repo, "rev-parse", "HEAD"),
        "tree": git(repo, "rev-parse", "HEAD^{tree}"),
    }
    (root / "config.yaml").write_text(yaml.safe_dump(config, allow_unicode=True, sort_keys=False))
    return repo


def has_notes(repo, commit):
    result = subprocess.run(
        ["git", "-C", str(repo), "notes", f"--ref={NOTES_REF}", "show", commit],
        capture_output=True, text=True,
    )
    return result.returncode == 0 and bool(result.stdout.strip())


def confirm_round(root, repo, config, iteration, state):
    baseline = config["baseline"]["commit"]
    if git(repo, "rev-parse", "main") != baseline:
        raise ValueError("main must remain at the baseline root commit")
    commits = set(git(repo, "rev-list", "--branches").splitlines())
    added = commits - set(state["commits_before"])
    if iteration == 0:
        if added:
            raise ValueError("Baseline evaluation must not create a candidate commit")
        commit = baseline
    else:
        if not added:
            return False
        if len(added) != 1:
            raise ValueError("Each evolution round must create exactly one commit")
        commit = added.pop()
        if not git(repo, "branch", "--show-current").startswith("codex/"):
            raise ValueError("Candidate branches must use codex/")
    if git(repo, "rev-parse", "HEAD") != commit:
        raise ValueError("The evaluated commit must be the current HEAD")
    tree = git(repo, "rev-parse", f"{commit}^{{tree}}")
    parents = git(repo, "show", "-s", "--format=%P", commit).split()
    parent = parents[0] if len(parents) == 1 else None
    if (iteration == 0 and parents) or (iteration > 0 and len(parents) != 1):
        raise ValueError("Candidates must have exactly one actual Git parent")
    manifest_path = root / tree / "manifest.json"
    summary_path = root / tree / "results/summary.json"
    if not manifest_path.exists() or not summary_path.exists():
        return False
    manifest = read_json(manifest_path)
    if manifest["tree"] != tree or manifest["parent"] != parent or manifest["config"] != config:
        raise ValueError("Commit tree, parent or protocol does not match the evaluated source")
    if source_tree(repo) != tree:
        raise ValueError("Source changed after evaluation; keep the evidence and resolve this round")
    if iteration > 0:
        parent_tree = git(repo, "rev-parse", f"{parent}^{{tree}}")
        parent_manifest = root / parent_tree / "manifest.json"
        if parent not in state["commits_before"] or not parent_manifest.exists():
            raise ValueError("Parent must be an already evaluated commit from this experiment")
        if read_json(parent_manifest).get("commit") != parent or not has_notes(repo, parent):
            raise ValueError("Parent must have its evaluation association and notes")
    if iteration == 0 and not read_json(summary_path).get("rankable"):
        return False
    if not has_notes(repo, commit):
        return False
    manifest["commit"] = commit
    write_json(manifest_path, manifest)
    state.update({"completed": True, "commit": commit, "tree": tree})
    write_json(root / "sessions" / f"{iteration:03d}" / "result.json", state)
    return True


def run_test(root, config, repo, references):
    candidates = []
    for reference in references:
        commit = git(repo, "rev-parse", "--verify", f"{reference}^{{commit}}")
        tree = git(repo, "rev-parse", f"{commit}^{{tree}}")
        manifest = read_json(root / tree / "manifest.json")
        summary = read_json(root / tree / "results/summary.json")
        if manifest.get("commit") != commit or not summary.get("rankable"):
            raise ValueError("Test requires an associated commit with complete successful Val")
        candidates.append((commit, tree, manifest))
    frozen_path = root / "finalized.json"
    frozen = read_json(frozen_path) if frozen_path.exists() else {"started_at": time.time(), "commits": []}
    frozen["commits"] = list(dict.fromkeys(frozen["commits"] + [commit for commit, _, _ in candidates]))
    frozen["status"] = "started"
    write_json(frozen_path, frozen)
    for commit, tree, val_manifest in candidates:
        output = root / "test" / commit
        candidate = output / "harness"
        if not candidate.exists():
            archive = subprocess.run(
                ["git", "-C", str(repo), "archive", "--format=tar", commit],
                capture_output=True, check=True,
            ).stdout
            candidate.mkdir(parents=True)
            with tarfile.open(fileobj=io.BytesIO(archive)) as files:
                files.extractall(candidate, filter="data")
        manifest_path = output / "manifest.json"
        if manifest_path.exists():
            manifest = read_json(manifest_path)
        else:
            iteration = next(
                int(path.parent.name) for path in (root / "sessions").glob("*/result.json")
                if read_json(path).get("commit") == commit
            )
            manifest = {
                "tree": tree, "commit": commit, "parent": val_manifest["parent"], "config": config,
                "source_experiment": root.name, "source_iteration": iteration,
                "val_directory": tree, "split": "test", "created_at": time.time(),
            }
            write_json(manifest_path, manifest)
        runtime_manifest = {**manifest, "name": commit, "candidate_id": tree, "candidate_path": str(candidate)}
        result = evaluate_candidate(root, config, candidate, split="test", manifest=runtime_manifest)
        print(json.dumps(result, ensure_ascii=False), flush=True)
    complete = all(
        (root / "test" / commit / "results/summary.json").exists()
        and read_json(root / "test" / commit / "results/summary.json").get("rankable")
        for commit in frozen["commits"]
    )
    frozen.update({"status": "complete" if complete else "partial", "updated_at": time.time()})
    write_json(frozen_path, frozen)
    return 0 if complete else 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-name", required=True)
    parser.add_argument("--config", type=Path, default=PROJECT / "config.yaml")
    parser.add_argument("--baseline", type=Path, default=DEFAULT_BASELINE)
    parser.add_argument("--iterations", type=int)
    parser.add_argument("--test-commits", nargs="+")
    args = parser.parse_args()
    root, config = open_experiment(args.run_name, args.config)
    if args.test_commits:
        repo = PROJECT / "harnesses" / args.run_name
        return run_test(root, config, repo, args.test_commits)
    if (root / "finalized.json").exists():
        parser.error("Experiment is frozen after explicit Test; use a new experiment")
    iterations = args.iterations if args.iterations is not None else config["evolution"]["iterations"]
    if iterations < 0:
        parser.error("iterations must be nonnegative")
    for section in ("solver", "proposer"):
        variable = config[section]["api_key_env"]
        if not os.environ.get(variable):
            parser.error(f"Set {variable}, or {section}.api_key in config.local.yaml")
    repo = initialize(root, config, args.baseline)
    for iteration in range(iterations + 1):
        session = root / "sessions" / f"{iteration:03d}"
        session.mkdir(parents=True, exist_ok=True)
        state_path = session / "result.json"
        if state_path.exists():
            state = read_json(state_path)
        else:
            state = {
                "session_id": str(uuid.uuid4()),
                "commits_before": git(repo, "rev-list", "--branches").splitlines(),
                "completed": False,
            }
            write_json(state_path, state)
        if state.get("completed") or confirm_round(root, repo, config, iteration, state):
            continue
        state = run_agent(root, repo, iteration, config)
        if not confirm_round(root, repo, config, iteration, state):
            stage = "Baseline is incomplete" if iteration == 0 else "Round is incomplete"
            raise RuntimeError(f"{stage}; resume the same experiment to finish evaluation, commit or notes")
    return 0


def interrupt(signum, frame):
    raise KeyboardInterrupt


if __name__ == "__main__":
    signal.signal(signal.SIGTERM, interrupt)
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        sandbox.stop_all()
        raise SystemExit(130)
