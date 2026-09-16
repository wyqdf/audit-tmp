"""One isolated proposal, with full HTTP requests, responses, and native sessions."""

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import importlib
import json
import os
from pathlib import Path
import signal
import subprocess
import threading
import time
import uuid

import httpx

from benchmark.runtime.runs import git, read_json, write_json
from .sandbox import build_sandbox, child_environment

# Mirrors the autonomous-proposer system prompt used by the reference runs.
SYSTEM_PROMPT = (
    "You are an autonomous harness-evolution proposer. Complete exactly one candidate "
    "per invocation by following the loaded Skill and evaluation contract. Modify only "
    "the bound repository, finish the required result handoff, and do not start another candidate."
)


class TraceProxy:
    def __init__(self, settings, session):
        self.settings = settings
        self.adapt_request = None
        if settings.get("request_adapter"):
            module, function = settings["request_adapter"].split(":", 1)
            self.adapt_request = getattr(importlib.import_module(module), function)
        self.directory = session / "requests"
        self.directory.mkdir(exist_ok=True)
        self.counter = len(list(self.directory.glob("*.request.json")))
        self.lock = threading.Lock()
        self.token = uuid.uuid4().hex
        self.api_key = os.environ[settings["api_key_env"]]
        self.client = httpx.Client(timeout=settings["timeout_seconds"])
        proxy = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_POST(self):
                token = self.headers.get("x-api-key") or self.headers.get("Authorization", "").removeprefix("Bearer ")
                if token != proxy.token:
                    self.send_error(401)
                    return
                body = self.rfile.read(int(self.headers["Content-Length"]))
                with proxy.lock:
                    proxy.counter += 1
                    stem = proxy.directory / f"{proxy.counter:06d}"
                stem.with_suffix(".request.json").write_bytes(body)
                upstream = json.loads(body)
                if proxy.adapt_request:
                    upstream = proxy.adapt_request(upstream)
                upstream_body = json.dumps(upstream, ensure_ascii=False).encode()
                stem.with_suffix(".upstream_request.json").write_bytes(upstream_body)
                started = time.time()
                headers = {
                    name: self.headers[name]
                    for name in ("content-type", "anthropic-version", "anthropic-beta")
                    if self.headers.get(name)
                }
                headers["x-api-key"] = proxy.api_key
                headers["Authorization"] = "Bearer " + proxy.api_key
                status = 502
                error = None
                try:
                    with proxy.client.stream(
                        "POST", proxy.settings["api_base"].rstrip("/") + self.path,
                        headers=headers, content=upstream_body,
                    ) as response:
                        status = response.status_code
                        self.send_response(status)
                        self.send_header("Content-Type", response.headers.get("content-type", "application/json"))
                        self.end_headers()
                        with stem.with_suffix(".response.txt").open("wb") as record:
                            connected = True
                            for chunk in response.iter_bytes():
                                record.write(chunk)
                                record.flush()
                                if connected:
                                    try:
                                        self.wfile.write(chunk)
                                        self.wfile.flush()
                                    except (BrokenPipeError, ConnectionResetError):
                                        connected = False
                except Exception as exc:
                    error = f"{type(exc).__name__}: {exc}"
                    payload = json.dumps({"type": "error", "error": {"type": "api_error", "message": error}}).encode()
                    if not stem.with_suffix(".response.txt").exists():
                        stem.with_suffix(".response.txt").write_bytes(payload)
                        try:
                            self.send_response(502)
                            self.send_header("Content-Type", "application/json")
                            self.end_headers()
                            self.wfile.write(payload)
                        except (BrokenPipeError, ConnectionResetError):
                            pass
                finally:
                    write_json(stem.with_suffix(".meta.json"), {
                        "path": self.path, "status": status, "started_at": started,
                        "elapsed_seconds": time.time() - started, "error": error,
                    })

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.server.daemon_threads = True
        self.url = f"http://127.0.0.1:{self.server.server_port}"

    def __enter__(self):
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        return self

    def __exit__(self, *args):
        self.server.shutdown()
        self.server.server_close()
        self.client.close()
        self.thread.join()


def benchmark_time(root, started, now):
    elapsed = 0.0
    running = None
    for path in root.glob("*/manifest.json"):
        manifest = read_json(path)
        interval = manifest.get("evaluation", {})
        begin = interval.get("started_at", 0)
        if begin < started:
            continue
        end = interval.get("finished_at")
        elapsed += max(0.0, min(end or now, now) - begin)
        if end is None:
            running = manifest["tree"]
    return elapsed, running


def run_agent(root, harness, iteration, config):
    settings = config["proposer"]
    session = root / "sessions" / f"{iteration:03d}"
    state_path = session / "result.json"
    state = read_json(state_path)
    previous_activity = state.get("activity_seconds", 0.0)
    previous_benchmark = state.get("benchmark_seconds", 0.0)
    previous_wall = state.get("wall_seconds", 0.0)
    if previous_activity >= settings["timeout_seconds"]:
        raise TimeoutError("This round has exhausted its proposer activity budget")
    resume = any((session / "state").rglob(f"{state['session_id']}.jsonl"))
    stage = (
        "Stage 0: evaluate the existing baseline and attach notes to its existing commit; do not create a new commit. "
        "An incomplete baseline remains in Stage 0 on continuation."
        if iteration == 0 else "Run one evolution iteration of the original Skill."
    )
    prompt = (Path(__file__).parent / "prompt.md").read_text().format(
        iteration=iteration, stage=stage,
        continuation=(
            "Continue this same round from its saved session, Git state and evaluation evidence. "
            "If evaluation finished, continue with analysis, commit and notes; if already committed, only complete missing notes. "
            "If evaluation was interrupted, resume the same source in its existing output directory."
            if resume else ""
        ),
    )
    (session / "prompt.md").write_text(prompt)
    progress = {"action": "分析：读取工作流和领域合同", "candidate": git(harness, "rev-parse", "--short", "HEAD"), "result": None}
    invocation = str(time.time_ns())
    code = None
    with TraceProxy(settings, session) as proxy:
        command = build_sandbox(root, harness, session, config) + [
            "/sandbox-bin/claude", "--dangerously-skip-permissions",
            "--setting-sources", "", "--append-system-prompt", SYSTEM_PROMPT, "--print", prompt,
            "--output-format", "stream-json", "--verbose", "--model", settings["model"],
            "--tools", "Read,Glob,Grep,Edit,Write,Bash",
            "--resume" if resume else "--session-id", state["session_id"],
        ]
        write_json(session / f"input-{invocation}.json", {"prompt": prompt, "session_id": state["session_id"], "resume": resume})
        with (session / "events.jsonl").open("a") as events, (session / "stderr.txt").open("a") as stderr:
            started = time.time()
            process = subprocess.Popen(
                command, env=child_environment(proxy.url, proxy.token, config),
                stdout=subprocess.PIPE, stderr=stderr, text=True, start_new_session=True,
            )

            def record():
                for line in process.stdout:
                    events.write(line)
                    events.flush()
                    try:
                        event = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if event.get("type") == "result":
                        progress["result"] = event
                    if event.get("type") != "assistant":
                        continue
                    for block in event.get("message", {}).get("content", []):
                        if block.get("type") != "tool_use":
                            continue
                        name = block["name"]
                        value = block.get("input", {})
                        detail = value.get("file_path") or value.get("path") or value.get("description") or value.get("pattern") or name
                        phase = "写候选" if name in {"Write", "Edit"} else "分析" if name in {"Read", "Grep", "Glob"} else "执行步骤"
                        progress["action"] = f"{phase}：{str(detail)[:160]}"

            def save_timing():
                now = time.time()
                benchmark, running = benchmark_time(root, started, now)
                wall = now - started
                state.update({
                    "activity_seconds": previous_activity + max(0.0, wall - benchmark),
                    "benchmark_seconds": previous_benchmark + benchmark,
                    "wall_seconds": previous_wall + wall,
                    "result": progress["result"],
                })
                write_json(state_path, state)
                return running

            reader = threading.Thread(target=record, daemon=True)
            reader.start()
            last_report = 0.0
            try:
                while True:
                    running = save_timing()
                    if time.time() - last_report >= 30:
                        if running:
                            progress["candidate"] = running
                            scores = []
                            for task in config["dataset"]["tasks"]:
                                path = root / running / "results" / task / "summary.json"
                                if path.exists():
                                    row = read_json(path)
                                    accuracy = row.get("accuracy")
                                    if accuracy is not None:
                                        scores.append(f"{task}={accuracy:.2%}")
                            print(f"benchmark 候选={running} 最新分数={', '.join(scores) or '待评测'}", flush=True)
                        else:
                            print(f"proposer 轮次={iteration} {progress['action']} 耗时={state['activity_seconds']:.0f}s 候选={progress['candidate']}", flush=True)
                        last_report = time.time()
                    if state["activity_seconds"] >= settings["timeout_seconds"]:
                        raise TimeoutError("Proposer exceeded its cumulative activity time limit")
                    try:
                        code = process.wait(timeout=1)
                        break
                    except subprocess.TimeoutExpired:
                        pass
            except BaseException as error:
                write_json(session / f"error-{invocation}.json", {"error": str(error)})
                raise
            finally:
                if process.poll() is None:
                    os.killpg(process.pid, signal.SIGKILL)
                    process.wait()
                reader.join()
                process.stdout.close()
                save_timing()
    result = progress["result"]
    if code or result is None or result.get("is_error"):
        raise RuntimeError(f"Proposer failed; see {session}")
    return state
