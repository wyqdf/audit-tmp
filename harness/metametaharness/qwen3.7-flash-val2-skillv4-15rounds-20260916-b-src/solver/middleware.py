"""The memory's spelling, applied to the answer the solver submits.

The skill asks the solver to copy an example's answer character for character and
`check_answer` reports the parts of a draft the memory writes differently, but the
answer that is scored is the last one the solver writes: over a val run of the task
whose answers carry a word ending the memory's examples drop, only 33 of its 100
samples called the check, and 9 of the 100 answers carried a part the memory spells
otherwise. The harness holds the same vocabulary and can read the reply, so the
correction is applied to the submitted answer rather than offered as a step the
solver may skip.
"""

import re

from langchain.agents.middleware import AgentMiddleware
from langchain_core.messages import AIMessage

# The answer field of the reply the runner scores, as a JSON string. The value is
# rewritten where it stands: an answer's spelling is made of the characters it
# holds, so the escapes around them are not part of it.
FIELD = re.compile(r'("final_answer"\s*:\s*")((?:[^"\\]|\\.)*)(")')


def respell_reply(content, space):
    """A reply with the memory's spelling written into its answer.

    The `final_answer` field is the answer the runner reads, so the rest of the
    reply is left as the solver wrote it. A reply without that field is wrapped
    into one unchanged, so its whole text is treated as the answer.
    """
    if isinstance(content, list):
        return [
            dict(block, text=respell_reply(block["text"], space))
            if isinstance(block, dict) and isinstance(block.get("text"), str)
            else block
            for block in content
        ]
    text = str(content)
    if not FIELD.search(text):
        return space.respell(text)
    return FIELD.sub(
        lambda field: f"{field.group(1)}{space.respell(field.group(2))}{field.group(3)}",
        text,
    )


class Respelling(AgentMiddleware):
    """Write the answer the solver submits the way the memory writes its answers."""

    def __init__(self, space):
        self.space = space

    def after_model(self, state, runtime):
        messages = state.get("messages") or []
        if not messages:
            return None
        message = messages[-1]
        # A message that calls a tool is a step in the work, not the answer to it.
        if not isinstance(message, AIMessage) or message.tool_calls:
            return None
        content = respell_reply(message.content, self.space)
        if content == message.content:
            return None
        return {"messages": [message.model_copy(update={"content": content})]}
