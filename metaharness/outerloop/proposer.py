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

from benchmark.runtime.runs import write_json
from .sandbox import build_sandbox, child_environment


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


def run_agent(root, harnesses, iteration, settings, num_datasets):
    session = root / "sessions" / f"{iteration:03d}"
    session.mkdir(parents=True, exist_ok=True)
    state_path = session / "result.json"
    previous_result = read_json(state_path).get("result") if state_path.exists() else None
    system_prompt = (
        "You are an autonomous harness-evolution proposer. Complete exactly one candidate per"
        " invocation by following the loaded Skill and evaluation contract. Modify only the bound"
        " harness directory, finish the required result handoff, and do not start another candidate."
    )
    prompt = (Path(__file__).parent / "prompt.md").read_text().format(
        iteration=iteration, num_datasets=num_datasets,
    )
    progress = {"action": "分析历史", "candidate": "尚未交接", "result": None}
    started = time.monotonic()
    with UpstreamProxy(settings) as proxy:
        command = build_sandbox(root, harnesses, session) + [
            "/sandbox-bin/claude", "--dangerously-skip-permissions",
            "--setting-sources", "", "--append-system-prompt", system_prompt,
            "--print", prompt, "--output-format", "stream-json", "--verbose",
            "--model", settings["model"], "--tools", "Read,Glob,Grep,Edit,Write,Bash",
        ]
        process = subprocess.Popen(
            command, env=child_environment(proxy.url, proxy.token, settings),
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
                    phase = "写候选" if name in {"Write", "Edit"} and "/harnesses/" in str(detail) else "分析" if name in {"Read", "Grep", "Glob"} else "执行步骤"
                    progress["action"] = f"{phase}：{str(detail)[:160]}"

        def complain():
            for line in process.stderr:
                progress["stderr"] = (progress.get("stderr", "") + line)[-4000:]

        reader = threading.Thread(target=record, daemon=True)
        listener = threading.Thread(target=complain, daemon=True)
        reader.start()
        listener.start()
        try:
            while True:
                elapsed = time.monotonic() - started
                pending = root / "pending_eval.json"
                try:
                    proposal = json.loads(pending.read_text())
                    candidates = proposal.get("candidates", [])
                    if candidates:
                        progress["candidate"] = candidates[0]["name"]
                except (ValueError, KeyError):
                    pass
                print(
                    f"proposer 轮次={iteration} {progress['action']} "
                    f"耗时={elapsed:.0f}s 候选={progress['candidate']}", flush=True,
                )
                remaining = settings["timeout_seconds"] - elapsed
                if remaining <= 0:
                    raise TimeoutError("Proposer exceeded its configured time limit")
                try:
                    code = process.wait(timeout=min(30, remaining))
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
            keep_conversation(session)
            result = progress["result"]
            error = progress.get("error")
            if error is None and (code or result is None or result.get("is_error")):
                error = progress.get("stderr", "").strip() or f"proposer exited with code {code}"
            write_json(state_path, {
                "error": error, "elapsed_seconds": time.monotonic() - started, "result": result,
                **usage_totals(previous_result, result),
            })
    if progress.get("error") or code or progress["result"] is None or progress["result"].get("is_error"):
        raise RuntimeError(f"Proposer failed; see {session}")
