"""Answer a request once per run, and end a run that keeps making the same one.

The tools the agent is given read a frozen memory: for as long as a run lasts,
the same request returns the same cases in the same order.  A request the run
has already made therefore carries nothing the run does not hold, and the
recorded runs measure what paying for it costs -- a run that asked the same two
questions back and forth spent 23 of its 32 model calls and 1.45 M input tokens
re-reading a slice it had already been shown, each call returning the same
cases, and it is the same content that makes the conversation long.

So the tool layer remembers what it has answered in this run.  The same request
is answered with its payload once, and a repeat is answered with a pointer to
what the run already holds instead of the payload again: the content is still
in the conversation, so nothing is taken away from the agent, and asking again
stops costing a copy of it.  The run itself is bounded on the same evidence --
a request that comes back beyond the bound has been answered over and over, so
the run is ended and the answer it has reached is the one it gives.

The bound is on *repeated requests*, not on calls: a run that asks new
questions is doing exactly the work the tools exist for and is never
interrupted here, and the tools this speaks about are the ones that answer from
the frozen memory -- a tool that writes a file or runs a command can do
something new on a second call and is left to the agent.
"""

import json

from langchain.agents.middleware import AgentMiddleware, hook_config
from langchain_core.messages import AIMessage

# A request asked this many times has already been answered twice over, and the
# answers cannot differ, so the run is not learning anything by asking again.
BOUND = 3

POINTER = (
    "This request has already been answered in this conversation -- {note} -- and these tools "
    "do not change within a run, so it can return nothing new: the same content is already in "
    "view above. Ask about something else, or answer the problem with the evidence in view."
)

CLOSED = (
    "This run was ended by the harness: the same request has come back {bound} times, and a "
    "request that has already been answered cannot return anything new. State the answer with "
    "the evidence already in view."
)


def request_key(name: str, arguments) -> str:
    """What makes two requests the same request: the tool and the arguments it was given."""
    if isinstance(arguments, str):
        try:
            arguments = json.loads(arguments)
        except ValueError:
            return f"{name}({arguments})"
    if isinstance(arguments, dict):
        arguments = {key: value for key, value in arguments.items() if value is not None}
    try:
        rendered = json.dumps(arguments, sort_keys=True, ensure_ascii=False)
    except (TypeError, ValueError):
        rendered = str(arguments)
    return f"{name}({rendered})"


def counts(messages, names) -> dict[str, int]:
    """How many times each request to ``names`` has been made in this run."""
    seen: dict[str, int] = {}
    for message in messages or ():
        for call in getattr(message, "tool_calls", None) or ():
            name = call.get("name")
            if names and name not in names:
                continue
            key = request_key(name, call.get("args") or {})
            seen[key] = seen.get(key, 0) + 1
    return seen


def closed(messages, names, bound: int = BOUND) -> bool:
    """True when some request has come back often enough that the run is not learning."""
    seen = counts(messages, names)
    return bool(seen) and max(seen.values()) >= bound


class Ledger:
    """The requests one run has been answered, and what each answer held."""

    def __init__(self):
        self._notes: dict[str, str] = {}

    def answered(self, key: str) -> bool:
        """True when the payload for this request is already in the conversation."""
        return key in self._notes

    def pointer(self, key: str) -> str:
        """What a repeated request is answered with instead of the payload again."""
        return POINTER.format(note=self._notes[key])

    def record(self, key: str, note: str) -> None:
        """Remember that this request was answered, and what the answer held."""
        self._notes[key] = note


class ProgressGuard(AgentMiddleware):
    """End a run that keeps asking a question it has already been answered.

    The count is read off the run's own messages, so a request is a repeat when
    the same tool was called with the same arguments again -- whether or not the
    tool layer answered it with a payload, and without any state of its own to
    keep in step with the conversation.  It is given the tools to bound rather
    than naming them here, so what it watches is exactly what this harness put
    in front of the agent.
    """

    def __init__(self, tools):
        super().__init__()
        self._names = frozenset(getattr(tool, "name", tool) for tool in tools)

    @hook_config(can_jump_to=["end"])
    def before_model(self, state, runtime):
        if not closed(state.get("messages", ()), self._names):
            return None
        return {
            "jump_to": "end",
            "messages": [AIMessage(content=CLOSED.format(bound=BOUND))],
        }
