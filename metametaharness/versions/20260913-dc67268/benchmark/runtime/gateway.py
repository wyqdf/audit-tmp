"""Per-run model gateway: global concurrency, per-question budgets, full traces."""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import threading
import time
import uuid

import httpx

from .errors import classify_error


def merge_chunk(response, chunk):
    """Assemble an upstream stream into the solver's usual complete response."""
    for key in ("id", "created", "model", "system_fingerprint", "usage", "error"):
        if chunk.get(key) is not None:
            response[key] = chunk[key]
    response["object"] = "chat.completion"
    choices = response.setdefault("choices", [])
    for part in chunk.get("choices", []):
        index = part["index"]
        while len(choices) <= index:
            choices.append({
                "index": len(choices), "message": {"role": "assistant", "content": ""},
                "finish_reason": None,
            })
        choice = choices[index]
        if part.get("finish_reason") is not None:
            choice["finish_reason"] = part["finish_reason"]
        message = choice["message"]
        delta = part.get("delta") or {}
        for key in ("content", "reasoning_content", "refusal"):
            if delta.get(key) is not None:
                message[key] = message.get(key, "") + delta[key]
        for tool in delta.get("tool_calls") or []:
            calls = message.setdefault("tool_calls", [])
            while len(calls) <= tool["index"]:
                calls.append({"id": "", "type": "function", "function": {"name": "", "arguments": ""}})
            call = calls[tool["index"]]
            if tool.get("id"):
                call["id"] = tool["id"]
            for key, value in (tool.get("function") or {}).items():
                if value is not None:
                    call["function"][key] += value


@dataclass
class Job:
    directory: Path
    deadline: float
    max_calls: int
    calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    closed: bool = False
    error: dict | None = None
    lock: threading.Lock = field(default_factory=threading.Lock)

    def reserve(self):
        with self.lock:
            if self.closed or time.monotonic() >= self.deadline:
                self.error = classify_error("Question deadline exceeded")
                raise RuntimeError("Question deadline exceeded")
            if self.max_calls > 0 and self.calls >= self.max_calls:
                self.error = classify_error("Question model-call limit exceeded")
                raise RuntimeError("Question model-call limit exceeded")
            self.calls += 1
            return self.calls

    def record(self, row):
        with self.lock:
            usage = row.get("response", {}).get("usage") or {}
            self.input_tokens += usage.get("prompt_tokens", 0) or 0
            self.output_tokens += usage.get("completion_tokens", 0) or 0
            self.error = row.get("error")
            with (self.directory / "model_calls.jsonl").open("a") as handle:
                handle.write(json.dumps(row, ensure_ascii=False) + "\n")

    def finish(self):
        with self.lock:
            self.closed = True
            return {
                "model_calls": self.calls,
                "input_tokens": self.input_tokens,
                "output_tokens": self.output_tokens,
            }


class Gateway:
    def __init__(self, solver: dict, concurrency: int):
        self.solver = solver
        self.slots = threading.BoundedSemaphore(concurrency)
        self.jobs = {}
        self.client = httpx.Client(trust_env=False)
        self.max_retries = solver.get("max_retries", 0)
        self.retry_backoff = solver.get("retry_backoff_seconds", 5)
        self.api_key = os.environ.get(solver["api_key_env"], "local")
        gateway = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def send(self, status, content):
                body = json.dumps(content, ensure_ascii=False).encode()
                try:
                    self.send_response(status)
                    self.send_header("Content-Type", "application/json")
                    self.send_header("Content-Length", str(len(body)))
                    self.end_headers()
                    self.wfile.write(body)
                except (BrokenPipeError, ConnectionResetError):
                    pass

            def do_POST(self):
                if self.path != "/v1/chat/completions":
                    self.send(404, {"error": {"message": "Unknown endpoint"}})
                    return
                token = self.headers.get("Authorization", "").removeprefix("Bearer ")
                job = gateway.jobs.get(token)
                if job is None:
                    self.send(401, {"error": {"message": "Unknown question token"}})
                    return
                try:
                    payload = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                    call_id = job.reserve()
                except (ValueError, KeyError, RuntimeError) as error:
                    self.send(400, {"error": {"message": str(error)}})
                    return
                payload["model"] = gateway.solver["model"]
                payload["stream"] = True
                payload["stream_options"] = {**payload.get("stream_options", {}), "include_usage": True}
                payload["max_tokens"] = min(
                    payload.get("max_tokens", gateway.solver["max_tokens"]),
                    gateway.solver["max_tokens"],
                )
                started = time.monotonic()
                status = 502
                response = {}
                acquired = gateway.slots.acquire(timeout=max(0, job.deadline - started))
                try:
                    if not acquired or time.monotonic() >= job.deadline:
                        raise TimeoutError("Question deadline exceeded while queued")
                    attempts = gateway.max_retries + 1
                    for attempt in range(attempts):
                        if attempt:
                            call_id = job.reserve()
                        attempt_started = time.monotonic()
                        response = {}
                        raw_response = ""
                        chunks = []
                        first_chunk_seconds = None
                        try:
                            with gateway.client.stream(
                                "POST",
                                gateway.solver["api_base"].rstrip("/") + "/chat/completions",
                                headers={"Authorization": f"Bearer {gateway.api_key}"},
                                json=payload,
                                timeout=min(
                                    gateway.solver["request_timeout_seconds"],
                                    job.deadline - time.monotonic(),
                                ),
                            ) as upstream:
                                status = upstream.status_code
                                if status >= 400:
                                    upstream.read()
                                    raw_response = upstream.text
                                    try:
                                        response = upstream.json()
                                    except ValueError:
                                        response = {"error": {"message": "Upstream returned non-JSON content"}}
                                else:
                                    complete = False
                                    for line in upstream.iter_lines():
                                        if job.closed or time.monotonic() >= job.deadline:
                                            raise TimeoutError("Question deadline exceeded")
                                        if not line.startswith("data:"):
                                            continue
                                        data = line[5:].strip()
                                        if data == "[DONE]":
                                            complete = True
                                            break
                                        chunk = json.loads(data)
                                        if first_chunk_seconds is None:
                                            first_chunk_seconds = time.monotonic() - attempt_started
                                        chunks.append(line)
                                        merge_chunk(response, chunk)
                                    if not complete and not response.get("error"):
                                        raise httpx.RemoteProtocolError("Upstream stream ended before [DONE]")
                            retryable = status in {408, 429} or status >= 500 or (
                                response.get("error") and response["error"].get("type")
                                in {"ReadTimeout", "ConnectError", "ConnectTimeout", "ReadError"}
                            )
                        except (httpx.HTTPError, TimeoutError, ValueError) as error:
                            status = 502
                            response = {"error": {"message": str(error), "type": type(error).__name__}}
                            retryable = True
                        finally:
                            if chunks:
                                raw_response = "\n\n".join(chunks)
                            failure = classify_error(
                                response.get("error", {"message": f"HTTP {status}"}),
                                status, gateway.solver.get("error_patterns"),
                            ) if status >= 400 or response.get("error") else None
                            job.record({
                                "call_index": call_id, "attempt": attempt + 1,
                                "time": datetime.now(timezone.utc).isoformat(),
                                "elapsed_seconds": time.monotonic() - attempt_started,
                                "first_chunk_seconds": first_chunk_seconds,
                                "stream_chunks": len(chunks),
                                "status_code": status, "request": payload,
                                "response": response, "raw_response": raw_response,
                                "error": failure,
                            })
                        if not retryable or attempt == attempts - 1:
                            break
                        time.sleep(min(gateway.retry_backoff * (2 ** attempt), 60))
                except Exception as error:
                    response = {"error": {"message": str(error), "type": type(error).__name__}}
                    job.error = classify_error(error, patterns=gateway.solver.get("error_patterns"))
                finally:
                    if acquired:
                        gateway.slots.release()
                self.send(status, response)

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.server.daemon_threads = True
        self.url = f"http://127.0.0.1:{self.server.server_port}/v1"

    def __enter__(self):
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        return self

    def __exit__(self, *args):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()
        self.client.close()

    def register(self, directory: Path, timeout_seconds=None, max_calls=None):
        token = uuid.uuid4().hex
        job = Job(
            directory=directory,
            deadline=time.monotonic() + (timeout_seconds or self.solver["timeout_seconds"]),
            max_calls=self.solver["max_model_calls"] if max_calls is None else max_calls,
        )
        self.jobs[token] = job
        return token, job
