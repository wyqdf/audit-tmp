"""Experiment files, frozen candidates, task memories, and solver traces."""

from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import time

import yaml

from benchmark.evaluate import load_task
from . import sandbox
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


def load_config(path):
    return yaml.safe_load(Path(path).read_text())


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
    (root / "sessions").mkdir(exist_ok=True)
    return root, config


def git(repo, *args, env=None):
    return subprocess.run(
        ["git", "-C", str(repo), *args], env=env, check=True,
        capture_output=True, text=True,
    ).stdout.strip()


def source_tree(repo):
    with tempfile.TemporaryDirectory(prefix="harness-index-") as temporary:
        environment = {**os.environ, "GIT_INDEX_FILE": str(Path(temporary) / "index")}
        git(repo, "read-tree", "HEAD", env=environment)
        git(repo, "add", "-A", "--", ".", env=environment)
        return git(repo, "write-tree", env=environment)


def open_candidate(root, config, source):
    source = Path(source).resolve()
    tree = source_tree(source)
    head = git(source, "rev-parse", "HEAD")
    baseline = head == git(source, "rev-parse", "main") and tree == git(source, "rev-parse", "main^{tree}")
    parent = None if baseline else head
    manifest_path = root / tree / "manifest.json"
    if manifest_path.exists():
        manifest = read_json(manifest_path)
        if manifest["config"] != config:
            raise ValueError("Evaluation configuration changed; use a new experiment")
        if manifest["parent"] != parent and manifest.get("commit") != head:
            raise ValueError("This source tree already belongs to a different evaluated lineage")
    else:
        manifest = {
            "tree": tree, "parent": parent, "config": config,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        write_json(manifest_path, manifest)
    return {**manifest, "name": tree, "candidate_id": tree, "candidate_path": str(source)}


def output_directory(root, manifest, split):
    return root / manifest["tree"] if split == "val" else root / "test" / manifest["commit"]


def prepare_task(root, manifest, task, gateway, trace):
    candidate_root = root / manifest["tree"]
    memory = candidate_root / "memories" / task
    ready = candidate_root / "results" / task / "memory_manifest.json"
    if ready.exists():
        if directory_hash(memory) != read_json(ready)["memory_id"]:
            raise ValueError("Frozen memory changed")
        return memory
    trace = trace / f"execution-{time.time_ns()}"
    trace.mkdir(parents=True, exist_ok=True)
    output = trace / "memory"
    output.mkdir(exist_ok=True)
    config = manifest["config"]
    timeout = config["runtime"]["prepare_timeout_seconds"]
    token, job = gateway.register(trace, timeout_seconds=timeout, max_calls=0)
    request = {
        "solver": config["solver"], "gateway_url": gateway.url, "gateway_token": token,
    }
    request_path = trace / "model.json"
    write_json(request_path, request)
    try:
        with tempfile.TemporaryDirectory(prefix="harness-train-") as temporary:
            train = Path(temporary) / "train.json"
            write_json(train, load_task(task, config, "train"))
            train_id = hashlib.sha256(train.read_bytes()).hexdigest()
            result = sandbox.prepare(
                Path(manifest["candidate_path"]), train, output,
                config["dataset"]["num_epochs"], timeout, request_path,
            )
    finally:
        write_json(trace / "usage.json", job.finish())
    (trace / "stdout.txt").write_text(result["stdout"])
    (trace / "stderr.txt").write_text(result["stderr"])
    if result["status"] != "ok" or not (output / "memory.json").exists():
        error = job.error or classify_error(
            "Memory preparation timeout" if result["status"] == "timeout" else result["stderr"] or "memory.json was not produced",
            patterns=config["solver"].get("error_patterns"),
        )
        write_json(trace / "result.json", {"status": result["status"], "error": error})
        raise EvaluationError(error)
    write_json(trace / "result.json", {"status": "ok"})
    shutil.copytree(output, memory, dirs_exist_ok=True)
    write_json(ready, {
        "candidate_id": manifest["candidate_id"], "task": task,
        "memory_id": directory_hash(memory),
        "train_id": train_id,
        "epochs": config["dataset"]["num_epochs"],
    })
    return memory


def solve_question(manifest, memory, sample_directory, input_text, gateway):
    sample_directory.mkdir(parents=True, exist_ok=True)
    workspace = sample_directory / "workspace"
    workspace.mkdir(exist_ok=True)
    token, job = gateway.register(sample_directory)
    started = time.monotonic()
    try:
        result = sandbox.solve(
            Path(manifest["candidate_path"]), memory, workspace,
            {
                "input": input_text, "solver": manifest["config"]["solver"],
                "gateway_url": gateway.url, "gateway_token": token,
            },
        )
    finally:
        usage = job.finish()
    stdout = result.pop("stdout")
    (sample_directory / "events.jsonl").write_text(stdout)
    stderr = result.pop("stderr")
    (sample_directory / "stderr.txt").write_text(stderr)
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
        result["error"] = job.error or classify_error(
            "Solver timeout" if result["status"] == "timeout" else stderr or "Solver returned no final answer",
            patterns=manifest["config"]["solver"].get("error_patterns"),
        )
    result.update({
        "input": input_text, "response": response or "", "usage": usage,
        "tool_calls": tool_calls, "memory_context_chars": context_chars,
        "elapsed_seconds": time.monotonic() - started,
        "candidate_id": manifest["candidate_id"], "memory_id": directory_hash(memory),
    })
    return result
