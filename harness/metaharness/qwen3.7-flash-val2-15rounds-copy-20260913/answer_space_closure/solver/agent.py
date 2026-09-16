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

PROMPT_HEAD = (
    "You are an agent that answers a question by grounding it in the frozen training"
    " references."
)
# What to do with a unit the reference vocabulary does not list is a fact about the corpus,
# not a style: a corpus whose answers keep reusing the same units is enumerating the answers
# it accepts, and one whose answers keep introducing new units is showing examples of a
# vocabulary it never finishes listing. The profile states which of the two the references
# are, and the system prompt follows it, because "write the unit yourself" is the right
# instruction in the second case and an instruction to leave the answer space in the first.
VOCABULARY_OPEN = (
    " Name every answer unit the question could support before you choose, and set a unit aside"
    " only for a factual reason: being absent from the reference vocabulary is not one."
)
VOCABULARY_CLOSED = (
    " The profile states the set this task's answers are built from. Name the units the facts"
    " establish and answer with the one they establish; a unit from outside that set is a"
    " different answer rather than an alternative to one inside it, because on this task the"
    " references list the answers they accept rather than sampling a larger vocabulary."
)
PROMPT_TAIL = (
    " Reuse whole reference units, never a fragment of one, with their exact spelling and"
    " answer shape, and never substitute a listed unit for a correct one that merely looks"
    " related. When the question states the shared header of a question type in the references,"
    " that type is what its answer is measured against: how many parts its answers carry and"
    " which units they carry say whether a draft is complete, and a part count that type never"
    " uses for its cases is not a count this question can have. Before submitting, call"
    " check_answer once on the draft: it reports the count this question's own type answers with,"
    " the markup the question states, and the renderings the references prove about the draft's"
    " units; a draft it reports nothing about is submitted unchanged."
)


def system_prompt(memory: dict) -> str:
    """The system prompt, with the vocabulary rule the profile measured."""
    closed = bool((memory.get("profile") or {}).get("closed_vocabulary"))
    return PROMPT_HEAD + (VOCABULARY_CLOSED if closed else VOCABULARY_OPEN) + PROMPT_TAIL
SKILL_PATH = "/harness/skills/answer-with-examples/SKILL.md"
SOLVER_PATH = "/harness/solver.md"
REFERENCE_CHARS = 15000
MAX_REFERENCES = 20

NUDGE = (
    "Before you submit: the draft has not been verified. Call check_answer once with your draft"
    " answer. It reports the markup the question states, the answer count this question's own"
    " type uses, and how the references render each unit you used. Fix what it reports and submit"
    " the final JSON; if it reports nothing, submit this draft unchanged - a report with nothing"
    " in it is not a reason to reconsider the answer, and calling the check again over the same"
    " draft cannot tell you anything new."
)
NUDGE_MARK = "the draft has not been verified"


class VerifyBeforeSubmit(AgentMiddleware):
    """Make the pre-submit check happen even when the model answers without one.

    The check is where a draft's part count is held against the count this question's
    own type answers with, and where a unit the draft renders in its own words comes
    back as the whole unit the references use, so it is worth one forced turn when the
    model reaches a final answer without ever calling the tool. It fires at most once:
    the marker in the injected message is what stops a second round.
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
        system_prompt=system_prompt(memory),
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
