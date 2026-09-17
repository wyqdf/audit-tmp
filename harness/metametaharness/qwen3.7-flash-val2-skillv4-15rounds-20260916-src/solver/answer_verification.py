"""One repair turn when a final answer departs from the memory's answer wording.

A mistyped answer item is cheap to fix and expensive to lose, so the check does not
rewrite anything itself: it quotes the memory's own wording back to the model and lets
the model decide, once, whether to revise.
"""

from langchain.agents.middleware import AgentMiddleware
from langchain.agents.middleware.types import hook_config
from langchain_core.messages import AIMessage, HumanMessage

from answer_conventions import answer_notice, final_answer_field

MAX_REPAIRS = 1


class AnswerVerificationMiddleware(AgentMiddleware):
    """Compares the answer a model is about to finish with against the frozen memory.

    Fires at most `max_repairs` times per question, and never on a turn that still has
    tool calls to run, so the agent keeps its normal loop.
    """

    def __init__(self, profile: dict | None = None, max_repairs: int = MAX_REPAIRS):
        super().__init__()
        self.profile = profile or {}
        self.max_repairs = max_repairs
        self.repairs = 0

    @hook_config(can_jump_to=["model"])
    def after_model(self, state, runtime):
        try:
            return self._repair(state)
        except Exception:  # a failed check must never fail the question
            return None

    def _repair(self, state):
        if self.repairs >= self.max_repairs:
            return None
        messages = state.get("messages") or []
        message = messages[-1] if messages else None
        if not isinstance(message, AIMessage) or message.tool_calls:
            return None
        notice = answer_notice(self.profile, final_answer_field(_text(message)), _shown(messages))
        if not notice:
            return None
        self.repairs += 1
        return {"messages": [HumanMessage(content=notice)], "jump_to": "model"}


def _shown(messages: list) -> str:
    """The tool output the model has read, which is what a quote may be taken from."""
    return "\n".join(
        _text(message)
        for message in messages
        if getattr(message, "type", None) == "tool" or type(message).__name__ == "ToolMessage"
    )


def _text(message) -> str:
    content = message.content
    if isinstance(content, list):
        return "".join(
            part.get("text", "") if isinstance(part, dict) else str(part) for part in content
        )
    return content or ""
