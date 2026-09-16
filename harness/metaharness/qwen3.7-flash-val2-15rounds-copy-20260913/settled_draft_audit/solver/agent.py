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
from langchain.agents.middleware import AgentMiddleware, hook_config
from langchain_core.messages import HumanMessage

from tools import build_tools
from tools.retrieval import load_memory

SYSTEM_PROMPT = (
    "You are an agent that answers a question by grounding it in the frozen training"
    " references. Decide the answer from the facts of the question, then render it the way the"
    " references render theirs: whole reference units, never a fragment of one, with their exact"
    " spelling, separators and markup. A unit the reference vocabulary does not list can still be"
    " the right answer - what the references happen not to show is not a fact about the question"
    " - so never swap a correct unit for a listed one that merely looks related, and never drop"
    " one for being unlisted. Once you have decided, do not re-open the decision: call"
    " check_answer once on the draft, fix only what it reports as mechanically wrong, and if it"
    " reports nothing, submit the draft unchanged."
)
SKILL_PATH = "/harness/skills/answer-with-examples/SKILL.md"
SOLVER_PATH = "/harness/solver.md"
REFERENCE_CHARS = 15000
MAX_REFERENCES = 20

NUDGE = (
    "Before you submit: the draft has not been verified. Call check_answer once with your draft"
    " answer. It reports only mechanical problems - markup, structure, count, and units that are"
    " fragments or near-miss spellings of a reference unit. Fix those if it reports any, and if"
    " it reports none, submit this draft unchanged: a check that finds nothing is not a reason to"
    " reconsider the answer. Do not call it a second time over the same draft."
)
NUDGE_MARK = "the draft has not been verified"


class VerifyBeforeSubmit(AgentMiddleware):
    """Make the pre-submit check happen even when the model answers without one.

    The check is the only place a fragment, a near-miss spelling or a missing markup
    tag is caught, so it is worth one forced turn when the model reaches a final
    answer without ever calling the tool. It fires at most once: the marker in the
    injected message is what stops a second round, and the tool itself clears a draft
    it finds nothing wrong with, so a forced turn cannot turn into a re-decision.
    """

    @hook_config(can_jump_to=["model"])
    def after_model(self, state, runtime):  # noqa: ANN001, ANN201 - framework hook
        try:
            messages = state.get("messages") or []
            if not messages:
                return None
            last = messages[-1]
            if getattr(last, "tool_calls", None):
                return None
            if any(
                isinstance(getattr(message, "content", None), str)
                and NUDGE_MARK in message.content
                for message in messages
            ):
                return None
            for message in messages:
                for call in getattr(message, "tool_calls", None) or []:
                    if (call or {}).get("name") == "check_answer":
                        return None
            return {"messages": [HumanMessage(content=NUDGE)], "jump_to": "model"}
        except Exception:
            return None


def build_guide(memory: dict, input_text: str) -> str:
    """Brief the solver with the reference profile and the closest references."""
    from tools.memory_lib import MemoryView

    view = MemoryView(memory)
    if not view.examples:
        return ""
    return view.guide(input_text, reference_chars=REFERENCE_CHARS, max_references=MAX_REFERENCES)


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
    memory = load_memory()
    agent = create_deep_agent(
        model=model,
        tools=build_tools(input_text, memory),
        system_prompt=SYSTEM_PROMPT,
        middleware=[VerifyBeforeSubmit()],
        subagents=[],
        backend=backend,
    )
    prompt = Path(SOLVER_PATH).read_text().format(
        input=input_text,
        guide=build_guide(memory, input_text),
        skill=Path(SKILL_PATH).read_text().strip(),
    )
    return agent, prompt
