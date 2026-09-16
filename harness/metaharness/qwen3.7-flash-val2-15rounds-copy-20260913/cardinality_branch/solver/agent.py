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

# How many units an answer carries is a fact about the corpus, not a style: a corpus whose
# answers are always one unit is asking for a choice between the units, and one whose
# answers carry several is asking for the set the facts establish. The profile measures
# which of the two the references are, and the prompt follows it, because "add every unit
# the facts establish" is the right instruction in the second case and an instruction to
# leave the answer space in the first.
PROMPT_HEAD = (
    "You are an agent that answers a question by grounding it in the frozen training"
    " references."
)
UNITS_SEVERAL = (
    " Name every answer unit the question could support before you choose, and set"
    " a unit aside only for a factual reason: being absent from the reference vocabulary is not"
    " one."
)
UNITS_ONE = (
    " Every reference answer is a single unit, so this task's answer is one unit: name the"
    " units the question could support, then answer with the single one the facts establish."
    " A second unit is a different answer rather than a more complete one, and a draft that"
    " carries two units is wrong even when one of them is right."
)
PROMPT_TAIL = (
    " Reuse whole reference units, never a fragment of one, with their exact spelling and"
    " answer shape, and never substitute a listed unit for a correct one that merely looks"
    " related. Before submitting, verify the draft with check_answer, passing the candidate"
    " units you named in `considered`, and fix everything that call reports."
)
DECISION_SEVERAL = (
    "4. Decide by naming candidates first. Write down every unit the question could support,\n"
    "   including the ones you are about to set aside, and for each one ask which fact\n"
    "   establishes it or rules it out. A unit may only be set aside for a factual reason -\n"
    '   "the references never use it" and "it is not in the reference unit list" are not\n'
    "   factual reasons. A missing unit and an extra unit both count as wrong, so be complete\n"
    "   and precise, and check the answer length the profile reports for the question type you\n"
    "   are answering."
)
DECISION_ONE = (
    "4. Decide by naming candidates first, then choosing between them. Write down every unit\n"
    "   the question could support, including the ones you are about to set aside, and for\n"
    "   each one ask which fact establishes it and which fact rules it out. A unit may only be\n"
    '   set aside for a factual reason - "the references never use it" and "it is not in the\n'
    '   reference unit list" are not factual reasons. This task\'s answers are one unit, so\n'
    "   the answer is the single unit the facts establish: when two candidates both look\n"
    "   supported, the one that explains the facts the other cannot is the answer, and the one\n"
    "   that leaves a distinctive fact unexplained is not. Covering a fact your choice leaves\n"
    "   out means replacing it with the unit that covers it, never appending a second unit."
)
REOPEN_SEVERAL = (
    "Fix everything it flags, including any candidate you cannot rule out\n"
    "   with a fact, then call it again on the corrected draft."
)
REOPEN_ONE = (
    "Fix everything it flags. When it re-opens a candidate you set aside, either a fact\n"
    "   rules it out and your draft stands, or the facts establish it and it takes the place\n"
    "   of the unit you drafted - an answer carrying both is not this task's answer."
)


def system_prompt(memory: dict) -> str:
    """The system prompt, with the answer-count rule the profile measured."""
    one = bool((memory.get("profile") or {}).get("single_unit"))
    return PROMPT_HEAD + (UNITS_ONE if one else UNITS_SEVERAL) + PROMPT_TAIL


def render_skill(memory: dict) -> str:
    """The skill, with the decision step the profile's answer count calls for."""
    one = bool((memory.get("profile") or {}).get("single_unit"))
    skill = Path(SKILL_PATH).read_text().strip()
    return skill.replace("%%DECISION%%", DECISION_ONE if one else DECISION_SEVERAL).replace(
        "%%REOPEN%%", REOPEN_ONE if one else REOPEN_SEVERAL
    )
SKILL_PATH = "/harness/skills/answer-with-examples/SKILL.md"
SOLVER_PATH = "/harness/solver.md"
REFERENCE_CHARS = 15000
MAX_REFERENCES = 20

NUDGE = (
    "Before you submit: the draft has not been verified. Call check_answer once with your draft"
    " answer, and pass `considered` = the candidate units you named while deciding, comma"
    " separated, including the ones you set aside. Then submit the final JSON. Change your"
    " answer only if the check output gives you a factual reason to."
)
NUDGE_MARK = "the draft has not been verified"


class VerifyBeforeSubmit(AgentMiddleware):
    """Make the pre-submit check happen even when the model answers without one.

    The check is where a candidate unit that was quietly dropped comes back with the
    reference cases that answer it, so it is worth one forced turn when the model
    reaches a final answer without ever calling the tool. It fires at most once: the
    marker in the injected message is what stops a second round.
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
        skill=render_skill(memory),
    )
    return agent, prompt
