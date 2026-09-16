"""Experiment files, frozen candidates, task memories, and solver conversations."""

from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import tempfile
import time

import yaml

from benchmark.evaluate import load_task
from . import conversation, sandbox
from .errors import EvaluationError, classify_error

PROJECT = Path(__file__).resolve().parents[2]


def read_json(path):
    return json.loads(Path(path).read_text())


def write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")
    temporary.replace(path)


def directory_hash(directory):
    digest = hashlib.sha256()
    for path in sorted(Path(directory).rglob("*")):
        if path.is_symlink():
            raise ValueError("Candidate and memory files must not be symlinks")
        if path.is_file():
            digest.update(path.relative_to(directory).as_posix().encode() + b"\0")
            digest.update(hashlib.sha256(path.read_bytes()).digest())
    return digest.hexdigest()


def file_hash(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def load_config(path):
    path = Path(path).resolve()
    config = yaml.safe_load(path.read_text())
    config["dataset"]["root"] = str((path.parent / config["dataset"]["root"]).resolve())
    return config


def load_credentials(config):
    local_path = PROJECT / "config.local.yaml"
    local = yaml.safe_load(local_path.read_text()) if local_path.exists() else {}
    for section in ("solver", "proposer"):
        settings = config.get(section, {})
        key = (local or {}).get(section, {}).get("api_key")
        if key and settings.get("api_key_env"):
            os.environ[settings["api_key_env"]] = key


def open_experiment(name, config_path):
    if Path(name).name != name or name in {".", ".."}:
        raise ValueError("Experiment name must be a directory name")
    root = PROJECT / "runs" / name
    root.mkdir(parents=True, exist_ok=True)
    saved = root / "config.yaml"
    if not saved.exists():
        config = load_config(config_path)
        saved.write_text(yaml.safe_dump(config, allow_unicode=True, sort_keys=False))
    config = load_config(saved)
    load_credentials(config)
    for relative in ("candidates", "sessions", "results", "reports"):
        (root / relative).mkdir(parents=True, exist_ok=True)
    (root / "evolution_summary.jsonl").touch(exist_ok=True)
    if not (root / "pending_eval.json").exists():
        write_json(root / "pending_eval.json", {})
    return root, config


def open_candidate(root, config, source):
    source = Path(source).resolve()
    candidate = PROJECT / "harnesses" / root.name / source.name
    candidate.parent.mkdir(parents=True, exist_ok=True)
    if source != candidate and not candidate.exists():
        shutil.copytree(source, candidate, ignore=shutil.ignore_patterns("__pycache__", "*.pyc", ".git"))
    elif source != candidate and directory_hash(source) != directory_hash(candidate):
        raise ValueError("A different candidate already uses this name")
    manifest_path = root / "candidates" / candidate.name / "manifest.json"
    candidate_id = directory_hash(candidate)
    if manifest_path.exists():
        manifest = read_json(manifest_path)
        if manifest["candidate_id"] != candidate_id:
            raise ValueError("Submitted candidate changed; create a new candidate folder")
        if manifest["candidate_path"] != str(candidate):
            manifest["candidate_path"] = str(candidate)
            write_json(manifest_path, manifest)
    else:
        manifest = {
            "experiment": root.name, "name": candidate.name,
            "candidate_id": candidate_id, "candidate_path": str(candidate),
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        write_json(manifest_path, manifest)
    return {**manifest, "config": config}


def candidate_root(root, split="val"):
    return root / "candidates" if split == "val" else root / "test" / "candidates"


def results_root(root, split="val"):
    return root / "results" if split == "val" else root / "test" / "results"


def task_root(root, candidate, task, split="val"):
    return candidate_root(root, split) / candidate / task


def memory_path(root, candidate, task, split="val"):
    return task_root(root, candidate, task, split) / "memory.json"


def conversation_path(root, candidate, task, index, sample, split="val"):
    """``index`` is the example index; ``None`` names the memory-preparation conversation."""
    directory = "prepare" if index is None else f"{index:04d}"
    return task_root(root, candidate, task, split) / "conversations" / directory / f"sample-{sample}.json"


def workspace_path(root, candidate, task, index, sample, split="val"):
    """The kept workspace of one execution, next to its conversation file."""
    path = conversation_path(root, candidate, task, index, sample, split)
    return path.parent / f"sample-{sample}.tmp"


def read_conversations(root, candidate, task, split="val"):
    """The sample conversations of one candidate and task, keyed by (example, sample)."""
    rows = {}
    directory = task_root(root, candidate, task, split) / "conversations"
    for path in sorted(directory.glob("*/sample-*.json")):
        if path.parent.name == "prepare":
            continue
        row = read_json(path)
        rows[(row["example_index"], row["sample_index"])] = row
    return rows


def prepare_attempts(root, candidate, task, split="val"):
    directory = task_root(root, candidate, task, split) / "conversations" / "prepare"
    return sorted(directory.glob("sample-*.json"))


def write_conversation(root, candidate, task, index, sample, header, split="val"):
    write_json(conversation_path(root, candidate, task, index, sample, split), header)
    return header


def rebuild_index(root, split="val"):
    """`results/samples.jsonl` is derived: one line per sample, from the conversation headers."""
    path = results_root(root, split) / "samples.jsonl"
    lines = []
    for candidate in sorted(path for path in candidate_root(root, split).glob("*") if path.is_dir()):
        for task_dir in sorted(path for path in candidate.glob("*") if path.is_dir()):
            for file in sorted(task_dir.glob("conversations/*/sample-*.json")):
                if file.parent.name == "prepare":
                    continue
                row = read_json(file)
                row.pop("messages", None)
                row.pop("side_calls", None)
                lines.append(json.dumps(row, ensure_ascii=False))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(line + "\n" for line in lines))
    return path


def read_summary(root, candidate, split="val"):
    path = results_root(root, split) / "summary.json"
    return read_json(path).get(candidate) if path.exists() else None


def write_summary(root, candidate, result, split="val"):
    path = results_root(root, split) / "summary.json"
    saved = read_json(path) if path.exists() else {}
    saved[candidate] = result
    write_json(path, saved)
    return path


def prepare_task(root, manifest, task, gateway, split="val"):
    """Generate the frozen memory for one candidate and task, recording its conversation."""
    config = manifest["config"]
    memory = memory_path(root, manifest["name"], task, split)
    if memory.exists():
        return memory
    working = Path(tempfile.mkdtemp(prefix="metaharness-memory-"))
    try:
        train_path = working / "train.json"
        write_json(train_path, load_task(task, config)["train"])
        output = working / "memory"
        output.mkdir()
        request_path = working / "model.json"
        timeout = config["runtime"]["prepare_timeout_seconds"]
        token, job = gateway.register(timeout_seconds=timeout, max_calls=0)
        write_json(request_path, {
            "solver": config["solver"], "gateway_url": gateway.url, "gateway_token": token,
        })
        started = time.monotonic()
        try:
            result = sandbox.prepare(
                Path(manifest["candidate_path"]), train_path, output,
                config["dataset"]["num_epochs"], timeout, request_path,
            )
        finally:
            usage = job.finish()
        produced = output / "memory.json"
        status = result["status"]
        error = None
        if status != "ok" or not produced.exists():
            error = job.error or classify_error(
                "Memory preparation timeout" if status == "timeout" else result["stderr"] or "memory.json was not produced",
                patterns=config["solver"].get("error_patterns"),
            )
            status = "error" if status == "ok" else status
        folded = conversation.assemble(job.rows)
        write_conversation(root, manifest["name"], task, None, len(prepare_attempts(root, manifest["name"], task, split)), {
            "task": task, "candidate": manifest["name"], "split": split,
            "example_index": None, "sample_index": 0,
            "status": status, "error": error,
            "usage": usage, "elapsed_seconds": time.monotonic() - started,
            "memory_chars": produced.stat().st_size if produced.exists() else 0,
            "messages": folded["messages"], "side_calls": folded["side_calls"],
            "finish_reasons": folded["finish_reasons"], "truncated": folded["truncated"],
            "repair_turns": folded["repair_turns"], "retries": folded["retries"],
        }, split)
        if status != "ok":
            raise EvaluationError(error)
        memory.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(produced, memory)
        return memory
    finally:
        shutil.rmtree(working, ignore_errors=True)


def frozen_memory(root, candidate, task):
    """Test reuses the Val memory of the same frozen candidate, verified byte for byte."""
    source = memory_path(root, candidate, task, "val")
    if not source.exists():
        raise ValueError("Test requires the saved Val memory")
    memory = memory_path(root, candidate, task, "test")
    if memory.exists() and file_hash(memory) != file_hash(source):
        raise ValueError("Frozen Test memory changed")
    if not memory.exists():
        memory.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, memory)
    if file_hash(memory) != file_hash(source):
        raise ValueError("Frozen Test memory changed")
    return memory


def solve_question(root, manifest, task, split, index, sample, memory, input_text, gateway):
    """Run one sample in isolation and return its conversation header and raw response."""
    working = Path(tempfile.mkdtemp(prefix="metaharness-sample-"))
    try:
        workspace = working / "workspace"
        workspace.mkdir()
        token, job = gateway.register()
        started = time.monotonic()
        try:
            try:
                result = sandbox.solve(
                    Path(manifest["candidate_path"]), memory, workspace,
                    {
                        "input": input_text, "solver": manifest["config"]["solver"],
                        "gateway_url": gateway.url, "gateway_token": token,
                    },
                )
            except Exception as error:
                # 单题执行异常同样留下对话文件，由重试逻辑决定是否补跑
                result = {
                    "status": "error",
                    "error": classify_error(error, patterns=manifest["config"]["solver"].get("error_patterns")),
                }
        finally:
            usage = job.finish()
        stdout = result.pop("stdout", "")
        stderr = result.pop("stderr", "")
        response = None
        tool_calls = []
        context_chars = 0
        for line in stdout.splitlines():
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            if event.get("event") == "final":
                response = event["response"]
            elif event.get("event") == "tool_start":
                tool_calls.append(event["name"])
            elif event.get("event") == "tool_end":
                output = event["output"]
                context_chars += len(str(output.get("content", ""))) if isinstance(output, dict) else len(str(output))
        if response is None and result["status"] == "ok":
            result["status"] = "error"
        if result["status"] != "ok":
            result["error"] = result.get("error") or job.error or classify_error(
                "Solver timeout" if result["status"] == "timeout" else stderr or "Solver returned no final answer",
                patterns=manifest["config"]["solver"].get("error_patterns"),
            )
        folded = conversation.assemble(job.rows)
        conversation.save_workspace(
            workspace, workspace_path(root, manifest["name"], task, index, sample, split),
        )
        header = {
            "task": task, "candidate": manifest["name"], "split": split,
            "example_index": index, "sample_index": sample,
            "status": result["status"], "error": result.get("error"),
            "was_correct": False, "prediction": "", "target": "", "metric": {},
            "usage": usage, "elapsed_seconds": time.monotonic() - started,
            "memory_context_chars": context_chars,
            "tool_calls": tool_calls,
            "finish_reasons": folded["finish_reasons"], "truncated": folded["truncated"],
            "repair_turns": folded["repair_turns"], "retries": folded["retries"],
            "messages": folded["messages"], "side_calls": folded["side_calls"],
        }
        return header, response or ""
    finally:
        shutil.rmtree(working, ignore_errors=True)
