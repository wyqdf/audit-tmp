"""Process-level isolation shared by retrieval, filesystem tools, and shell."""

import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import threading

PROJECT = Path(__file__).resolve().parents[2]
ACTIVE = set()
LOCK = threading.Lock()
STOPPING = threading.Event()


def stop_all():
    STOPPING.set()
    with LOCK:
        for process in list(ACTIVE):
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass


def base_command():
    command = [
        "bwrap", "--unshare-all", "--share-net", "--die-with-parent", "--new-session",
        "--cap-drop", "ALL", "--clearenv",
        "--proc", "/proc", "--dev", "/dev", "--tmpfs", "/tmp",
        "--ro-bind", "/usr", "/usr",
    ]
    for path in [Path("/bin"), Path("/sbin"), Path("/lib"), Path("/lib64")]:
        if path.is_symlink():
            command += ["--symlink", os.readlink(path), str(path)]
        elif path.exists():
            command += ["--ro-bind", str(path), str(path)]
    command += [
        "--ro-bind", sys.base_prefix, sys.base_prefix,
        "--ro-bind", str(Path(sys.prefix) / "lib"), "/opt/venv/lib",
        "--ro-bind", str(Path(sys.prefix) / "pyvenv.cfg"), "/opt/venv/pyvenv.cfg",
        "--dir", "/opt/venv/bin",
        "--symlink", str(Path(sys.executable).resolve()), "/opt/venv/bin/python",
        "--symlink", "python", "/opt/venv/bin/python3",
    ]
    for path in ["/etc/resolv.conf", "/etc/ssl/certs", "/etc/hosts", "/etc/ld.so.cache"]:
        if Path(path).exists():
            command += ["--ro-bind", path, path]
    for name, value in {
        "PATH": "/opt/venv/bin:/usr/bin:/bin",
        "HOME": "/tmp", "LANG": "C.UTF-8", "PYTHONNOUSERSITE": "1",
        "PYTHONDONTWRITEBYTECODE": "1", "TOKENIZERS_PARALLELISM": "false",
        "LANGSMITH_TRACING": "false",
    }.items():
        command += ["--setenv", name, value]
    return command


def execute(command, timeout, payload=None):
    with LOCK:
        if STOPPING.is_set():
            raise RuntimeError("Run interrupted")
        process = subprocess.Popen(
            command, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, start_new_session=True,
        )
        ACTIVE.add(process)
    try:
        stdout, stderr = process.communicate(
            json.dumps(payload, ensure_ascii=False) if payload is not None else None,
            timeout=timeout,
        )
        return {"status": "ok" if process.returncode == 0 else "error", "stdout": stdout, "stderr": stderr}
    except subprocess.TimeoutExpired:
        os.killpg(process.pid, signal.SIGKILL)
        stdout, stderr = process.communicate()
        return {"status": "timeout", "stdout": stdout, "stderr": stderr}
    except BaseException:
        os.killpg(process.pid, signal.SIGKILL)
        process.communicate()
        raise
    finally:
        with LOCK:
            ACTIVE.discard(process)


def prepare(candidate: Path, train: Path, output: Path, epochs: int, timeout: int, request_path: Path):
    request = json.loads(request_path.read_text())
    command = base_command() + [
        "--ro-bind", str(candidate), "/candidate",
    ]
    if (candidate / ".git").exists():
        command += ["--tmpfs", "/candidate/.git", "--remount-ro", "/candidate/.git"]
    command += [
        "--ro-bind", str(train), "/input/train.json",
        "--ro-bind", str(request_path), "/runtime/model.json",
        "--setenv", "MODEL_BASE_URL", request["gateway_url"],
        "--setenv", "MODEL_API_KEY", request["gateway_token"],
        "--setenv", "MODEL_NAME", request["solver"]["model"],
        "--bind", str(output), "/output", "--chdir", "/output",
        "/opt/venv/bin/python", "/candidate/prepare_memory.py", "--epochs", str(epochs),
    ]
    return execute(command, timeout)


def link_or_copy(source, target):
    """Hard-link when the two paths share a filesystem, otherwise copy."""
    try:
        os.link(source, target)
    except OSError:
        shutil.copyfile(source, target)


def harness_stage(candidate: Path, memory: Path, workspace: Path) -> Path:
    """Stage the harness tree the solver sees, with the frozen memory inside it.

    The solver mounts the harness read-only, so the memory cannot be bound into it
    directly: the mount point would have to be created inside a read-only filesystem.
    The stage hard-links the candidate's files (no data copied) and carries
    ``memory/memory.json``, so the sandbox binds one directory.
    """
    stage = workspace.parent / f".harness-{workspace.name}"
    shutil.rmtree(stage, ignore_errors=True)
    shutil.copytree(
        candidate / "solver", stage, copy_function=link_or_copy, symlinks=False,
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
    )
    memory_dir = stage / "memory"
    memory_dir.mkdir(parents=True, exist_ok=True)
    target = memory_dir / "memory.json"
    if target.exists():
        target.unlink()
    try:
        os.link(memory, target)
    except OSError:
        shutil.copyfile(memory, target)
    return stage


def solve(candidate: Path, memory: Path, workspace: Path, request: dict):
    stage = harness_stage(candidate, memory, workspace)
    try:
        command = base_command() + [
            "--ro-bind", str(stage), "/harness",
            "--bind", str(workspace), "/workspace",
            "--ro-bind", str(PROJECT / "benchmark" / "runtime" / "worker.py"), "/runtime/worker.py",
            "--chdir", "/workspace", "/opt/venv/bin/python", "/runtime/worker.py",
        ]
        return execute(command, request["solver"]["timeout_seconds"], request)
    finally:
        shutil.rmtree(stage, ignore_errors=True)
