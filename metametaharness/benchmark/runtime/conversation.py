"""Fold one execution's model calls into its single conversation record.

The conversation file is the only authoritative record of an execution: a header with the
per-sample statistics, then ``messages`` (the main line) and ``side_calls`` (independent
conversations the harness started after the main line's response). Files the harness left in
its writable workspace are kept next to the conversation when there are any. Per-call timing,
status codes, retry counts and upstream bytes are not kept anywhere else.
"""

import shutil
from pathlib import Path


def save_workspace(directory, destination):
    """Keep the files one execution left behind in its writable workspace.

    The workspace is a temporary directory that is removed once the conversation is written,
    so when it holds anything it is copied to ``destination`` (``sample-<k>.tmp`` next
    to the conversation file) instead; an empty workspace leaves nothing behind. The copy is
    byte for byte, so binary files survive unchanged.
    """
    root = Path(directory)
    if not root.is_dir() or not any(item.is_file() for item in root.rglob("*")):
        return None
    if destination.exists():
        shutil.rmtree(destination)
    shutil.copytree(root, destination, symlinks=True)
    return destination


def assistant_message(response):
    """The assistant turn of a response, in the shape the client would send it back."""
    choices = (response or {}).get("choices") or []
    if not choices:
        return None
    message = choices[0].get("message") or {}
    content = message.get("content")
    if not content and message.get("tool_calls"):
        # 线上格式：只发工具调用的轮次 content 是 null，不是空串
        content = None
    out = {"role": "assistant", "content": content}
    if message.get("reasoning_content"):
        out["reasoning_content"] = message["reasoning_content"]
    if message.get("tool_calls"):
        out["tool_calls"] = message["tool_calls"]
    return out


def _sent(row):
    return ((row.get("request") or {}).get("messages")) or []


def _is_prefix(short, line):
    return len(short) <= len(line) and all(left == right for left, right in zip(short, line))


def _carries(row):
    return bool(
        not row.get("error")
        and (row.get("status_code") or 0) < 400
        and assistant_message(row.get("response"))
    )


def assemble(rows):
    """Return the main line, the side conversations, and the call-level counters.

    The main line is the request carrying the most messages (it already contains every
    earlier turn's thinking, tool calls and tool returns) plus that call's response. Calls
    whose messages are a prefix of it are already inside it; anything left is an independent
    conversation the harness started, and is kept as a side call.
    """
    calls = [row for row in rows if _carries(row)]
    calls.sort(key=lambda row: len(_sent(row)), reverse=True)
    lines, folded = [], set()
    for index, row in enumerate(calls):
        if index in folded:
            continue
        line = list(_sent(row)) + [assistant_message(row["response"])]
        lines.append(line)
        for other in range(index + 1, len(calls)):
            if other not in folded and _is_prefix(_sent(calls[other]), line):
                folded.add(other)
    reasons = []
    for row in sorted(calls, key=lambda row: row.get("call_index") or 0):
        choices = (row.get("response") or {}).get("choices") or []
        if choices and choices[0].get("finish_reason"):
            reasons.append(choices[0]["finish_reason"])
    return {
        "messages": lines[0] if lines else [],
        "side_calls": lines[1:],
        "finish_reasons": reasons,
        "truncated": "length" in reasons,
        "repair_turns": sum(
            1 for row in calls
            if ((row.get("request") or {}).get("response_format") or {}).get("type") == "json_object"
        ),
        "retries": sum(1 for row in rows if (row.get("attempt") or 1) > 1),
    }
