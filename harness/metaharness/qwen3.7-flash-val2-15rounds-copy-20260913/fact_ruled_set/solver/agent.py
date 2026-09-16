"""Deep Agents candidate, loaded only inside the solver sandbox."""

import json
import os
import re
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
# leave the answer space in the first. A corpus that carries several units *from a
# vocabulary* is a third case, and the measured one: replayed over its own recorded run,
# the units its answers were missing had been named by the solver in 12 of 61 cases and
# were ruled out in the rest by reasons about the law ("another unit covers this conduct",
# "that unit is the more specific one") rather than by facts of the question, so the
# prompt names those non-reasons where the decision is made rather than only where a
# named candidate comes back.
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
# The remaining loss on the multi-unit corpus is one-sided: every wrong answer there is a
# missing unit, and where the check re-opened a candidate the solver had named it kept the
# draft for a reason about the corpus rather than about the question. So the candidates the
# solver names are made binding - a named candidate the draft does not carry is a defect,
# and the check writes out the answer that would carry it, which leaves the solver a
# comparison instead of a formatting decision.
PROMPT_TAIL = (
    " Reuse whole reference units, never a fragment of one, with their exact spelling and"
    " answer shape, and never substitute a listed unit for a correct one that merely looks"
    " related. Before submitting, verify the draft with check_answer, passing the candidate"
    " units you named in `considered`: a candidate that call reports as not carried is a"
    " defect of the draft, and only a fact of the question rules it out - the vocabulary not"
    " listing it, the references usually answering with one unit, and another unit covering"
    " the same acts do not. Fix everything that call reports."
)
DECISION_SEVERAL = (
    "4. Decide by naming candidates first. Write down every unit the question could support,\n"
    "   including the ones you are about to set aside, and for each one ask which fact\n"
    "   establishes it or rules it out. A unit may only be set aside for a factual reason -\n"
    '   "the references never use it" and "it is not in the reference unit list" are not\n'
    "   factual reasons. A missing unit and an extra unit both count as wrong, so be complete\n"
    "   and precise, and decide the count from the facts rather than from the count the\n"
    "   references happen to use most often."
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
    "Fix everything it flags. A candidate it reports as not\n"
    "   carried goes into the answer unless a fact of the question rules it out, and the\n"
    "   written-out form it gives is what to submit; then call it again on the corrected draft."
)
REOPEN_ONE = (
    "Fix everything it flags. A candidate it reports as not carried is either ruled out by a\n"
    "   fact of the question, and your draft stands, or the facts establish it and the\n"
    "   written-out form it gives replaces the unit you drafted - an answer carrying both is\n"
    "   not this task's answer."
)
# The third case: a corpus whose answers carry one unit or several, all of them drawn from
# the vocabulary the references use. There the loss is one-sided - replayed over the
# recorded run, every wrong answer of that corpus was missing a unit and none carried an
# extra one - and the missing units are not a retrieval problem (the units are in the
# material the solver is shown for most of the cases, and the reference cases that answer
# them are the ones the vocabulary already ranks first). The reasons the solver records for
# leaving them out are about the law rather than about the facts: the conduct is fully
# evaluated by another unit, the other unit is the more specific one, the two names are one
# offence. Those are reasons about how offences are counted, not facts the question states,
# and they are exactly what the corpus does *not* do: it answers with the several units its
# judgments establish. So the decision step is where they are named, not only the check.
UNITS_SET = (
    " This task's answers are a set of reference units - the units the facts establish - and"
    " one course of conduct can establish more than one of them, so neither a missing unit"
    " nor an extra one is safe. Name every answer unit the question could support before you"
    " choose, and set a unit aside only for a fact of the question: a reason about the law"
    " rather than about the facts - another unit covering the same conduct, that unit being"
    " the more specific one, the conduct being fully evaluated by the unit you drafted - does"
    " not set a unit aside."
)
DECISION_SET = (
    "4. Decide the set by naming candidates first. Write down every unit the question could\n"
    "   support, including the ones you are about to set aside, and for each one write the\n"
    "   fact of the question that establishes it or rules it out; a unit you cannot rule out\n"
    "   with a quoted fact belongs to the answer, so an answer you could have extended is a\n"
    "   defect and so is an answer you extended without one. Reasons about the law rather\n"
    "   than about the facts do not rule a unit out: that another unit covers the same\n"
    "   conduct, that the other unit is the more specific one, that the conduct is fully\n"
    '   evaluated by the unit you drafted, that the references never use it, and that the\n'
    "   reference unit list does not contain it. A missing unit and an extra unit both count\n"
    "   as wrong, so decide the count from those facts and not from the count the references\n"
    "   happen to use most often."
)
REOPEN_SET = (
    "Fix everything it flags. A candidate it reports as not carried goes into the answer\n"
    "   unless a fact of the question rules it out, and the written-out form it gives is what\n"
    "   to submit; the units your draft already carries stay, because the answer is the set of\n"
    "   units no fact rules out."
)
SHAPE_SET = (
    " This task's answer is the set of those units that no fact of the question rules out,"
    " and one course of conduct can establish several of them."
)


def branch_of(memory: dict) -> str:
    """Which of the three answer shapes the profile measured: one unit, a set, or free.

    ``one``   - every reference answer is a single unit, so the answer is a choice.
    ``set``   - the answers are units from a vocabulary and often several of them.
    ``free``  - the answers are free-form, so the vocabulary rules do not apply.
    """
    profile = memory.get("profile") or {}
    if profile.get("single_unit"):
        return "one"
    return "set" if profile.get("label_like") else "free"


def system_prompt(memory: dict) -> str:
    """The system prompt, with the answer-shape rule the profile measured."""
    branch = branch_of(memory)
    return PROMPT_HEAD + {"one": UNITS_ONE, "set": UNITS_SET}.get(branch, UNITS_SEVERAL) + PROMPT_TAIL


def render_skill(memory: dict) -> str:
    """The skill, with the decision step the profile's answer shape calls for."""
    branch = branch_of(memory)
    skill = Path(SKILL_PATH).read_text().strip()
    return (
        skill.replace(
            "%%DECISION%%",
            {"one": DECISION_ONE, "set": DECISION_SET}.get(branch, DECISION_SEVERAL),
        )
        .replace("%%REOPEN%%", {"one": REOPEN_ONE, "set": REOPEN_SET}.get(branch, REOPEN_SEVERAL))
        .replace("%%SHAPE%%", SHAPE_SET if branch == "set" else "")
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
# A turn that ends with no answer the harness can read is the one failure no amount of
# answer quality recovers: the recorded runs contain a sample whose final JSON string was
# never closed, so the answer it had already checked twice was read as empty and scored
# zero. The marker below makes the repair fire once.
RESUBMIT = (
    "Your last message could not be read as a final answer: no JSON object with a"
    ' non-empty "final_answer" was found in it. Reply with the JSON object alone and'
    ' nothing after it - {"reasoning": "...", "final_answer": "..."} - closing the string'
    " and the object. Do not change the answer itself."
)
RESUBMIT_MARK = "could not be read as a final answer"


def read_answer(text) -> str:
    """The ``final_answer`` a response text yields, or an empty string.

    The reading has to accept what the benchmark accepts, because a guard that is
    stricter would repair answers that were going to score anyway, and one that is
    laxer would miss the answer that never arrived.
    """
    if not isinstance(text, str) or '"final_answer"' not in text:
        return ""
    try:
        data = json.loads(text)
        if isinstance(data, dict):
            return str(data.get("final_answer") or "")
    except json.JSONDecodeError:
        pass
    for match in re.finditer(r"```(?:json)?\s*([\s\S]*?)\s*```", text):
        try:
            data = json.loads(match.group(1))
            if isinstance(data, dict):
                return str(data.get("final_answer") or "")
        except json.JSONDecodeError:
            pass
    for start, character in enumerate(text):
        if character != "{":
            continue
        depth, position, in_string = 1, start + 1, False
        while position < len(text) and depth > 0:
            current = text[position]
            if current == '"' and text[position - 1] != "\\":
                in_string = not in_string
            elif not in_string:
                depth += 1 if current == "{" else (-1 if current == "}" else 0)
            position += 1
        if depth:
            continue
        candidate = re.sub(r",\s*([\]}])", r"\1", text[start:position])
        try:
            data = json.loads(candidate)
            if isinstance(data, dict):
                return str(data.get("final_answer") or "")
        except json.JSONDecodeError:
            pass
    matches = re.findall(r'"final_answer"\s*:\s*"([^"]*)"', text)
    return matches[-1] if matches else ""


def _content(message) -> str:
    content = getattr(message, "content", None)
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return " ".join(
            str(part.get("text") or "") for part in content if isinstance(part, dict)
        )
    return ""


class VerifyBeforeSubmit(AgentMiddleware):
    """Make the two steps that must not be skipped happen: the check, and the answer.

    The check is where a candidate unit that was quietly dropped comes back with the
    reference cases that answer it, so it is worth one forced turn when the model
    reaches a final answer without ever calling the tool. A turn whose text carries no
    readable ``final_answer`` is worth one turn too, since that answer scores zero
    whatever it says. Each fires at most once: the marker in the injected message is
    what stops a second round.
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
            texts = [_content(message) for message in messages]
            checked = any(
                (call or {}).get("name") == "check_answer"
                for message in messages
                for call in getattr(message, "tool_calls", None) or []
            )
            nudged = any(NUDGE_MARK in text for text in texts)
            if (
                (checked or nudged)
                and not read_answer(_content(last))
                and not any(RESUBMIT_MARK in text for text in texts)
            ):
                return {"messages": [HumanMessage(content=RESUBMIT)], "jump_to": "model"}
            if checked or nudged:
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
