"""Deep Agents candidate, loaded only inside the solver sandbox."""

import os
from pathlib import Path

from deepagents import (
    GeneralPurposeSubagentProfile,
    HarnessProfile,
    create_deep_agent,
    register_harness_profile,
)
from deepagents.backends import LocalShellBackend
from langchain_core.messages import AIMessage, HumanMessage

from passes import answer_field, conform, written_message
from tools import build_tools
from tools.retrieval import (
    block_budget,
    memory_answer_key,
    memory_joiner,
    memory_listed_strings,
    reduced_context,
)

SYSTEM_PROMPT = "You are an agent that answers a question by retrieving examples."
SKILL_PATH = "/harness/skills/answer-with-examples/SKILL.md"

# What a second attempt is offered of the example block, largest first. The call a provider
# refuses is the one carrying the whole block, so each attempt carries less of it and the
# last carries the answer key alone, which is what is left when no example can be delivered.
RECOVERY_CHARS = (8000, 2000, 0)


def message_text(content) -> str:
    """One message's content as plain text, whatever shape the provider returned it in."""
    if isinstance(content, list):
        content = "".join(
            block if isinstance(block, str) else block.get("text", "") for block in content
        )
    return content if isinstance(content, str) else ""


def recovery_prompt(case: str, context: str) -> str:
    """The problem, the memory's evidence for it, and the answer contract, in one call.

    The conversation answers this problem with the retrieval tool; this is the same question
    put to the same model with the examples already in hand, so an answer derived here is the
    answer the harness would have read from the conversation.
    """
    return (
        f"{case}\n\n"
        "Answer the problem above now, in the format it asks for, and put the answer itself\n"
        'inside the JSON object it asks for: {"reasoning": "...", "final_answer": "..."}.\n\n'
        "The examples and the answer key of this problem's memory are below, the closest\n"
        "precedents first. There is no tool to call and no further retrieval available.\n\n"
        f"{context}"
    )


class ConformedAgent:
    """The conversation plus the harness's own reading of the answer it produced.

    The conversation is left as it is -- it is the trace of what the solver retrieved and
    argued -- and the answer it produced is treated as a draft whose entries the harness
    writes the way the memory writes them before the sample is answered. What the list itself
    settles is written by the harness, and the model is asked only for what is left.
    """

    def __init__(self, agent, model, case: str, key: str, joiner: str, listed: tuple):
        self.agent = agent
        self.model = model
        self.case = case
        self.key = key
        self.joiner = joiner
        self.listed = listed

    def answer_from_memory(self, error):
        """The answer when the conversation produced none, or the conversation's own failure.

        A call the provider refuses costs the sample the whole conversation -- the lineage's
        refused samples carry no answer at all and count as wrong -- so the harness puts the
        problem to the model itself, with the memory's evidence cut to what the refused call
        can carry. Every attempt failing leaves the failure as it was.
        """
        readable = ""
        for chars in RECOVERY_CHARS:
            try:
                message = self.model.invoke([
                    HumanMessage(content=recovery_prompt(
                        self.case, reduced_context(self.case, chars),
                    ))
                ])
            except Exception:
                continue
            text = message_text(getattr(message, "content", ""))
            if not text.strip():
                continue
            if answer_field(text).strip():
                return {"messages": [AIMessage(content=text)]}
            # A reply that answers without the field it was asked for is still an answer: the
            # runner's own guard writes it into the schema, as it does for a conversation.
            readable = readable or text
        if readable:
            return {"messages": [AIMessage(content=readable)]}
        raise error

    def invoke(self, inputs, config=None):
        try:
            result = self.agent.invoke(inputs, config=config)
        except Exception as error:
            result = self.answer_from_memory(error)
        messages = result.get("messages") or []
        draft = message_text(getattr(messages[-1], "content", "")) if messages else ""
        # A memory whose answers are single strings has no name to write out in full: an
        # entry is the whole answer, and the check stays on the answer's own spelling.
        final = conform(self.model, self.case, self.key, draft, self.joiner, bool(self.joiner))
        written = final.strip() or draft
        whole, parts = self.listed
        # The entries the list does not carry are written the list's way by the list's own
        # endings, which is the one reading of them the frozen runs never leave to the model.
        written = written_message(written, whole, parts, self.joiner)
        if written.strip() and written != draft:
            result["messages"] = [*messages, AIMessage(content=written)]
        return result


def build_agent(model, input_text: str, config: dict):
    profile = HarnessProfile(
        general_purpose_subagent=GeneralPurposeSubagentProfile(enabled=False),
    )
    register_harness_profile("openai", profile)
    register_harness_profile(f"openai:{config['model']}", profile)
    backend = LocalShellBackend(
        root_dir="/",
        virtual_mode=True,
        timeout=config["tool_timeout_seconds"],
        env={"PATH": os.environ["PATH"], "HOME": "/tmp", "PYTHONDONTWRITEBYTECODE": "1"},
    )
    agent = create_deep_agent(
        model=model,
        tools=build_tools(input_text, block_budget(config.get("context_window"))),
        system_prompt=SYSTEM_PROMPT,
        middleware=[],
        subagents=[],
        backend=backend,
    )
    prompt = Path("/harness/solver.md").read_text().format(
        input=input_text, skill=Path(SKILL_PATH).read_text().strip()
    )
    return ConformedAgent(
        agent, model, input_text, memory_answer_key(), memory_joiner(), memory_listed_strings()
    ), prompt
