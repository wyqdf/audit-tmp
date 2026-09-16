"""Mount only this experiment's candidates and allowed records."""

import os
from pathlib import Path
import shutil

from benchmark.runtime.runs import PROJECT
from benchmark.runtime.sandbox import base_command


def build_sandbox(root, harnesses, session):
    claude = shutil.which("claude")
    if not claude:
        raise FileNotFoundError("The proposer requires the claude CLI")
    state = session / "state"
    state.mkdir(exist_ok=True)
    command = base_command()
    command.remove("--clearenv")
    mounts = [
        (Path(claude).resolve(), "/sandbox-bin/claude", False),
        (harnesses, "/workspace/harnesses", True),
        (state, "/tmp/claude-state", True),
    ]
    for candidate in sorted(harnesses.iterdir()):
        if candidate.is_dir() and (root / "candidates" / candidate.name / "manifest.json").exists():
            mounts.append((candidate, f"/workspace/harnesses/{candidate.name}", False))
    for name in ("config.yaml", "evolution_summary.jsonl", "candidates", "results"):
        mounts.append((root / name, f"/workspace/history/{name}", False))
    for path in sorted((PROJECT / "benchmark").iterdir()):
        if path.is_file() and path.suffix in {".py", ".md"}:
            mounts.append((path, f"/workspace/benchmark/{path.name}", False))
    mounts.append((PROJECT / "benchmark" / "runtime", "/workspace/benchmark/runtime", False))
    for path in sorted((PROJECT / "benchmark" / "data").glob("*.py")):
        mounts.append((path, f"/workspace/benchmark/data/{path.name}", False))
    for directory in sorted((PROJECT / "benchmark" / "data").iterdir()):
        if directory.is_dir():
            for split in ("train", "val"):
                source = directory / f"{split}.jsonl"
                if source.exists():
                    mounts.append((source, f"/workspace/benchmark/data/{directory.name}/{source.name}", False))
    mounts.append((PROJECT / ".claude" / "skills" / "meta-harness", "/workspace/.claude/skills/meta-harness", False))
    mounts.extend([
        (root / "reports", "/workspace/reports", True),
        (root / "pending_eval.json", "/workspace/pending_eval.json", True),
    ])
    for source, target, writable in mounts:
        for parent in reversed(Path(target).parents):
            if parent != Path("/"):
                command += ["--dir", str(parent)]
        command += ["--bind" if writable else "--ro-bind", str(source.resolve()), target]
    command += [
        "--dir", "/tmp/home", "--setenv", "HOME", "/tmp/home",
        "--setenv", "CLAUDE_CONFIG_DIR", "/tmp/claude-state",
        "--setenv", "PATH", "/sandbox-bin:/opt/venv/bin:/usr/bin:/bin",
        "--chdir", "/workspace",
    ]
    return command


def child_environment(url, token, settings):
    environment = {
        "ANTHROPIC_BASE_URL": url,
        "ANTHROPIC_API_KEY": token,
        "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC": "1",
        "DISABLE_AUTOUPDATER": "1",
        "DISABLE_TELEMETRY": "1",
        "NO_PROXY": "127.0.0.1,localhost",
    }
    # The Claude Code driver sends this value as the request's thinking effort.
    effort = settings.get("effort")
    if effort:
        environment["CLAUDE_CODE_EFFORT_LEVEL"] = str(effort)
    return environment
