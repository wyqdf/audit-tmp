"""One isolated proposal, with the native session and its conversation events kept."""

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import importlib
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import threading
import time
import uuid

import httpx

from benchmark.runtime.runs import git, read_json, write_json
from .sandbox import build_sandbox, child_environment

# Role-only system prompt, following the reference proposer prompts, which state the role and
# leave the constraints to the skill: SIA "You are a meta-agent. Your task is to create a target
# agent which can execute a task."; Proteus "You are an agent that can inspect and change its own
# harness — the set of files it wakes up with each episode."; RHO "You are the proposer in an
# end-to-end harness search loop."; Meta-Harness injects the whole SKILL.md instead.
SYSTEM_PROMPT = (
    "You are the proposer in a harness self-evolution process."
)


def spill_directory(transcript):
    """Where the CLI parks tool output too large to keep in the transcript itself."""
    return transcript.parent / transcript.stem / "tool-results"


def copy_spills(source, destination):
    """Copy the spilled tool outputs, and nothing else, into ``destination``."""
    spills = sorted(source.glob("*.txt")) if source.is_dir() else []
    if not spills:
        return
    destination.mkdir(parents=True, exist_ok=True)
    for spill in spills:
        shutil.copyfile(spill, destination / spill.name)


def keep_conversation(session):
    """Keep the CLI's own session transcript as the round's conversation record.

    The CLI writes it inside a working state directory next to shell snapshots and tool-result
    spills; the transcript survives as ``conversation.jsonl`` and oversize tool output as
    ``tool-results/`` beside it. The returned path is where the transcript has to go back
    before a resumed run.
    """
    state = session / "state"
    projects = state / "projects"
    transcripts = sorted(projects.glob("*/*.jsonl")) if projects.is_dir() else []
    relative = None
    if transcripts:
        source = max(transcripts, key=lambda path: path.stat().st_size)
        relative = source.relative_to(state).as_posix()
        shutil.copyfile(source, session / "conversation.jsonl")
        copy_spills(spill_directory(source), session / "tool-results")
    shutil.rmtree(state, ignore_errors=True)
    return relative


def usage_totals(*events):
    """Token, cost and turn counters of the CLI result events, summed over a resumed round."""
    totals = {
        "usage": {
            "input_tokens": 0, "output_tokens": 0,
            "cache_creation_input_tokens": 0, "cache_read_input_tokens": 0,
        },
        "cost_usd": 0.0, "num_turns": 0, "duration_api_ms": 0,
    }
    for event in events:
        if not event:
            continue
        usage = event.get("usage") or {}
        for key in totals["usage"]:
            totals["usage"][key] += usage.get(key, 0)
        totals["cost_usd"] += event.get("total_cost_usd") or 0.0
        totals["num_turns"] += event.get("num_turns", 0)
        totals["duration_api_ms"] += event.get("duration_api_ms", 0)
    return totals


def conversation_event(line):
    """One CLI event to keep, with its parsed form; thinking heartbeats are dropped."""
    try:
        event = json.loads(line)
    except json.JSONDecodeError:
        return line, None
    if event.get("type") == "system" and event.get("subtype") == "thinking_tokens":
        return None, None
    return line, event


class UpstreamProxy:
    """Forward the proposer's API calls to the configured upstream endpoint.

    The CLI is pointed at this proxy, the real key is injected here and the optional request
    adapter runs on the way through. Nothing is recorded: the round keeps its conversation
    events instead of per-call requests and responses.
    """

    def __init__(self, settings):
        self.settings = settings
        self.adapt_request = None
        if settings.get("request_adapter"):
            module, function = settings["request_adapter"].split(":", 1)
            self.adapt_request = getattr(importlib.import_module(module), function)
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
                upstream = json.loads(body)
                if proxy.adapt_request:
                    upstream = proxy.adapt_request(upstream)
                upstream_body = json.dumps(upstream, ensure_ascii=False).encode()
                headers = {
                    name: self.headers[name]
                    for name in ("content-type", "anthropic-version", "anthropic-beta")
                    if self.headers.get(name)
                }
                headers["x-api-key"] = proxy.api_key
                headers["Authorization"] = "Bearer " + proxy.api_key
                try:
                    with proxy.client.stream(
                        "POST", proxy.settings["api_base"].rstrip("/") + self.path,
                        headers=headers, content=upstream_body,
                    ) as response:
                        self.send_response(response.status_code)
                        self.send_header("Content-Type", response.headers.get("content-type", "application/json"))
                        self.end_headers()
                        connected = True
                        for chunk in response.iter_bytes():
                            if connected:
                                try:
                                    self.wfile.write(chunk)
                                    self.wfile.flush()
                                except (BrokenPipeError, ConnectionResetError):
                                    connected = False
                except Exception as exc:
                    payload = json.dumps({
                        "type": "error",
                        "error": {"type": "api_error", "message": f"{type(exc).__name__}: {exc}"},
                    }).encode()
                    try:
                        self.send_response(502)
                        self.send_header("Content-Type", "application/json")
                        self.end_headers()
                        self.wfile.write(payload)
                    except (BrokenPipeError, ConnectionResetError):
                        pass

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
    previous_result = state.get("result")
    previous_activity = state.get("activity_seconds", 0.0)
    previous_benchmark = state.get("benchmark_seconds", 0.0)
    previous_wall = state.get("wall_seconds", 0.0)
    if previous_activity >= settings["timeout_seconds"]:
        raise TimeoutError("This round has exhausted its proposer activity budget")
    resume = (session / "conversation.jsonl").exists() and bool(state.get("session_file"))
    if resume:
        # 会话记录搬回了轮次目录，恢复前先放回 CLI 期望的位置
        restored = session / "state" / state["session_file"]
        restored.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(session / "conversation.jsonl", restored)
        copy_spills(session / "tool-results", spill_directory(restored))
    stage = (
        "Stage 0: evaluate the existing baseline and attach notes to its existing commit; do not create a new commit. "
        "An incomplete baseline remains in Stage 0 on continuation."
        if iteration == 0 else ""
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
    progress = {"action": "分析：读取 Skill", "candidate": git(harness, "rev-parse", "--short", "HEAD"), "result": None}
    with UpstreamProxy(settings) as proxy:
        command = build_sandbox(root, harness, session, config) + [
            "/sandbox-bin/claude", "--dangerously-skip-permissions",
            "--setting-sources", "", "--append-system-prompt", SYSTEM_PROMPT, "--print", prompt,
            "--output-format", "stream-json", "--verbose", "--model", settings["model"],
            "--tools", "Read,Glob,Grep,Edit,Write,Bash",
            "--resume" if resume else "--session-id", state["session_id"],
        ]
        started = time.time()
        process = subprocess.Popen(
            command, env=child_environment(proxy.url, proxy.token, config),
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, start_new_session=True,
        )
        code = None

        def record():
            for line in process.stdout:
                _, event = conversation_event(line)
                if event is None:
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

        def complain():
            for line in process.stderr:
                progress["stderr"] = (progress.get("stderr", "") + line)[-4000:]

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
        listener = threading.Thread(target=complain, daemon=True)
        reader.start()
        listener.start()
        last_report = 0.0
        try:
            while True:
                running = save_timing()
                if time.time() - last_report >= 30:
                    if running:
                        progress["candidate"] = running
                        path = root / running / "results" / "summary.json"
                        scores = []
                        if path.exists():
                            saved = read_json(path)
                            for task in config["dataset"]["tasks"]:
                                accuracy = (saved.get("scores", {}).get(task) or {}).get("accuracy")
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
            progress["error"] = str(error)
            raise
        finally:
            if process.poll() is None:
                os.killpg(process.pid, signal.SIGKILL)
                process.wait()
            reader.join()
            listener.join()
            process.stdout.close()
            process.stderr.close()
            state["session_file"] = keep_conversation(session) or state.get("session_file")
            state.update(usage_totals(previous_result, progress["result"]))
            state["error"] = progress.get("error")
            save_timing()
    if progress.get("error") or code or progress["result"] is None or progress["result"].get("is_error"):
        raise RuntimeError(f"Proposer failed; see {session}")
    return state
