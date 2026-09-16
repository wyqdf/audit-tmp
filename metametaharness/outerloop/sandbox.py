"""Expose one harness repository and its evaluation evidence."""

import math
import os
from pathlib import Path
import shutil

from benchmark.runtime.runs import PROJECT, read_json
from benchmark.runtime.sandbox import base_command


def build_sandbox(root, harness, session, config):
    claude = shutil.which("claude")
    if not claude:
        raise FileNotFoundError("The proposer requires the claude CLI")
    state = session / "state"
    state.mkdir(exist_ok=True)
    command = base_command()
    command.remove("--clearenv")
    mounts = [
        (Path(claude).resolve(), "/sandbox-bin/claude", False),
        (harness, "/workspace/harness", True),
        (root, "/workspace/runs", True),
        (root / "config.yaml", "/workspace/runs/config.yaml", False),
    ]
    for path in sorted(root.glob("*/manifest.json")):
        if read_json(path).get("commit"):
            mounts.append((path.parent, f"/workspace/runs/{path.parent.name}", False))
    benchmark = PROJECT / "benchmark"
    for path in sorted(benchmark.iterdir()):
        if path.is_file() and path.suffix in {".py", ".md"}:
            mounts.append((path, f"/workspace/benchmark/{path.name}", False))
    mounts.append((benchmark / "runtime", "/workspace/benchmark/runtime", False))
    for path in sorted((benchmark / "data").glob("*.py")):
        mounts.append((path, f"/workspace/benchmark/data/{path.name}", False))
    data_root = PROJECT / config["dataset"]["root"]
    data_target = Path("/workspace") / config["dataset"]["root"]
    for directory in sorted(data_root.iterdir()):
        if directory.is_dir():
            for split in ("train", "val"):
                path = directory / f"{split}.jsonl"
                if path.exists():
                    mounts.append((path, str(data_target / directory.name / path.name), False))
    mounts.extend([
        (PROJECT / ".claude/skills/meta-meta-harness", "/workspace/.claude/skills/meta-meta-harness", False),
        (state, "/tmp/claude-state", True),
    ])
    for source, target, writable in mounts:
        command += ["--bind" if writable else "--ro-bind", str(source.resolve()), target]
    for name in ("sessions", "test"):
        (root / name).mkdir(exist_ok=True)
        target = f"/workspace/runs/{name}"
        command += ["--tmpfs", target, "--remount-ro", target]
    command += [
        "--dir", "/tmp/home", "--setenv", "HOME", "/tmp/home",
        "--setenv", "CLAUDE_CONFIG_DIR", "/tmp/claude-state",
        "--setenv", "PATH", "/sandbox-bin:/opt/venv/bin:/usr/bin:/bin",
        "--chdir", "/workspace/harness",
    ]
    return command


def child_environment(url, token, config):
    # Cover preparation and the fixed benchmark's serial task batches.
    dataset, runtime, solver = config["dataset"], config["runtime"], config["solver"]
    benchmark_limit = 0
    for task in dataset["tasks"]:
        count = dataset.get("overrides", {}).get(task, {}).get("num_val", dataset["num_val"])
        batches = math.ceil(count * config["evaluation"]["val_samples"] / runtime["parallel_questions"])
        benchmark_limit += runtime["sample_attempts"] * (
            runtime["prepare_timeout_seconds"] + batches * solver["timeout_seconds"]
        )
    timeout_ms = str(int((benchmark_limit + config["proposer"]["timeout_seconds"]) * 1000))
    environment = {
        "ANTHROPIC_BASE_URL": url,
        "ANTHROPIC_API_KEY": token,
        solver["api_key_env"]: os.environ[solver["api_key_env"]],
        "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC": "1",
        "CLAUDE_CODE_DISABLE_BACKGROUND_TASKS": "1",
        "BASH_DEFAULT_TIMEOUT_MS": timeout_ms,
        "BASH_MAX_TIMEOUT_MS": timeout_ms,
        "DISABLE_AUTOUPDATER": "1",
        "DISABLE_TELEMETRY": "1",
        "NO_PROXY": "127.0.0.1,localhost",
    }
    # The Claude Code driver sends this value as the request's thinking effort.
    effort = config["proposer"].get("effort")
    if effort:
        environment["CLAUDE_CODE_EFFORT_LEVEL"] = str(effort)
    return environment
