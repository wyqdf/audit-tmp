"""Resolve the answer the agent gave before the answer-space rules see it.

The runner reads the answer out of the ``final_answer`` field of the agent's
last message, and the rules that spell answers the way the frozen memory spells
them can only be trusted on text the harness knows is an answer.  A message
that carries no such field leaves those rules without a span to work on: they
fall back to the whole message, where they rewrite ordinary prose, and a
message whose answer is empty is returned as an empty answer.  This module
makes the answer exist first.  It finds the field, and when the agent did not
produce one it states the answer in the JSON object the task requires.

The statement is asked of the agent's own run rather than of a fresh call that
carries only the message's text.  The agent's last message is not the whole of
what it produced: its run holds the evidence it retrieved and its own reasoning
about the answer, and a call that sees only the concluding message re-derives
the answer from that message alone.  On the recorded samples that is not a
rewording but a second decision -- a message whose own last line names one
answer was returned with another, and the answers the agent had already reached
were lost ("pneumonia" for a message whose own final line reads
``[DIAGNOSIS]bronchial asthma[/DIAGNOSIS]``) -- so the answer is asked for
inside the run that holds it, and a run that cannot be continued falls back to
the single-message restatement this module has always used.
"""

from string import Template

from langchain_core.messages import HumanMessage

from adjudication import ANSWER_PATTERN

RESTATE = Template("""An agent worked on the problem below and its last message is quoted after it. That
message does not carry the answer in the JSON object the task requires.

## Problem

$problem

## The agent's last message

$message

State the answer as a single JSON object with exactly two string fields, "reasoning" and
"final_answer", as the task's own instructions require. If the message already holds an answer,
copy that answer unchanged -- keeping the markup the task asks the answer to carry -- into
"final_answer"; if it holds none, answer the problem yourself.

Reply with only the JSON object.""")

CONTINUE = """Your last message does not carry the answer in the JSON object the task requires. State
the answer as a single JSON object with exactly two string fields, "reasoning" and
"final_answer", as the task's own instructions require. If your last message already holds an
answer, copy that answer unchanged -- keeping the markup the task asks the answer to carry --
into "final_answer"; if it holds none, answer the problem yourself.

Reply with only the JSON object."""


def answer_field(text: str) -> tuple[int, int] | None:
    """Where the answer value sits inside the message, when the message carries it."""
    if not text:
        return None
    match = ANSWER_PATTERN.search(text)
    return (match.start(1), match.end(1)) if match else None


def resolved(text: str) -> bool:
    """True when the message already states a non-empty answer."""
    span = answer_field(text)
    return span is not None and bool(text[span[0] : span[1]].strip())


def _text(content) -> str:
    if isinstance(content, str):
        return content
    return "".join(
        block if isinstance(block, str) else block.get("text", "")
        for block in (content or [])
    )


def in_run(messages: list, model) -> str | None:
    """The answer asked for inside the agent's own messages, or None.

    The messages are the run as the agent lived it, so the model sees the same
    evidence and the same reasoning it answered from.  A call that fails, or
    that answers without the field, leaves the caller with nothing: the caller
    then asks the single-message restatement instead.
    """
    if not messages:
        return None
    try:
        response = model.invoke(list(messages) + [HumanMessage(content=CONTINUE)])
    except Exception:
        return None
    content = _text(getattr(response, "content", response))
    return content if resolved(content) else None


def resolve(text: str, model, problem: str, messages: list | None = None) -> str:
    """Return the agent's message with an answer in it, stated once if needed.

    The statement is an improvement to the message, never a condition for
    producing one: any failure leaves the agent's own text in place, and the
    run is asked first because it is the text that carries the answer.
    """
    if resolved(text):
        return text
    answered = in_run(messages, model)
    if answered is not None:
        return answered
    message = text.strip() or "(the agent produced no message)"
    try:
        response = model.invoke(RESTATE.substitute(problem=problem, message=message))
    except Exception:
        return text
    content = _text(getattr(response, "content", response))
    return content if resolved(content) else text
