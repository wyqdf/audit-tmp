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
from tools.memory_lib import MemoryView
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
# On a corpus the references measured to answer with molecular formulas that account for
# every heavy atom of the material the question states, the answer's elements are part of
# what is being asked, not a matter of style: one atom of the material no fragment carries
# means a fragment is missing. Corpora whose answers are words never see this sentence,
# because the measurement is what turns it on.
MATERIAL = (
    " The references answer with molecular formulas and their answers account for every"
    " heavy atom of the material the question states, so an element of that material no"
    " fragment of your answer carries means a fragment is missing."
)


def system_prompt(memory: dict) -> str:
    """The system prompt, with the answer-count rule and the material rule the profile measured."""
    profile = memory.get("profile") or {}
    one = bool(profile.get("single_unit"))
    material = MATERIAL if (profile.get("formula") or {}).get("enabled") else ""
    return PROMPT_HEAD + (UNITS_ONE if one else UNITS_SEVERAL) + material + PROMPT_TAIL


def render_skill(memory: dict) -> str:
    """The skill, with the decision step the profile's answer count calls for."""
    profile = memory.get("profile") or {}
    one = bool(profile.get("single_unit"))
    material = (
        " The references here answer with molecular formulas and account for every heavy atom\n"
        "   of the material the question states: a reaction's atoms all come from its\n"
        "   reactants, so an element of that material no fragment of your answer carries means\n"
        "   a fragment that supplies it is missing. `check_answer` reports the elements the\n"
        "   draft does not account for."
        if (profile.get("formula") or {}).get("enabled")
        else ""
    )
    skill = Path(SKILL_PATH).read_text().strip()
    return (
        skill.replace("%%DECISION%%", DECISION_ONE if one else DECISION_SEVERAL)
        .replace("%%REOPEN%%", REOPEN_ONE if one else REOPEN_SEVERAL)
        .replace("%%MATERIAL%%", material)
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
# answer quality recovers: the benchmark reads such a turn as an empty answer whatever it
# says, and the recorded runs contain turns that had already been checked and were then
# submitted with the JSON string left unclosed. The marker below makes the repair fire
# once per turn, and only when the reading the harness applies agrees with the benchmark's
# own extraction - checked against every recorded final turn of this harness family.
RESUBMIT = (
    "Your last message could not be read as a final answer: no JSON object with a"
    ' non-empty "final_answer" was found in it. Reply with the JSON object alone and'
    ' nothing after it - {"reasoning": "...", "final_answer": "..."} - closing the string'
    " and the object. Do not change the answer itself."
)
RESUBMIT_MARK = "could not be read as a final answer"
# On a corpus measured to answer with formulas that cover the material the question
# states, the harness can verify the submitted answer itself instead of asking the model
# to verify it: the elements of that material have to be in the answer, because a
# reaction's atoms all come from its reactants. A draft that fails that accounting is
# sent back once with the elements it is missing - a defect no reading of the question
# can talk away, unlike the surface notes the check also writes.
COVERAGE_MARK = "does not account for every element of the material"
COVERAGE_TURN = (
    "Your last answer does not account for every element of the material the question"
    " states, so it cannot be that material's reactants. Go back to the disconnection that"
    " produces the material, find the fragment that carries the missing element(s), and"
    " reply with the corrected JSON object"
    ' ({"reasoning": "...", "final_answer": "..."}). Keep the answer only if you can say'
    " which reference reagent supplies those elements without being listed."
)


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
    """Make the steps that must not be skipped happen: the check, the answer, and the material.

    The check is where a candidate unit that was quietly dropped comes back with the
    reference cases that answer it, so it is worth one forced turn when the model
    reaches a final answer without ever calling the tool. A turn whose text carries no
    readable ``final_answer`` is worth one turn too, since the benchmark scores it as
    empty whatever it says. And where the corpus was measured to answer with formulas
    that account for the material the question states, a submitted answer that does not
    account for it is sent back once with the elements it is missing: that one is
    computed here, so it does not depend on the model agreeing with a tool. Each fires at
    most once: the marker in the injected message is what stops a second round.
    """

    def __init__(self, coverage=None):  # noqa: ANN001 - callable set by build_agent
        self.coverage = coverage

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
            answer = read_answer(_content(last))
            if (
                (checked or nudged)
                and not answer
                and not any(RESUBMIT_MARK in text for text in texts)
            ):
                return {"messages": [HumanMessage(content=RESUBMIT)], "jump_to": "model"}
            if (
                (checked or nudged)
                and answer
                and self.coverage
                and not any(COVERAGE_MARK in text for text in texts)
            ):
                report = self.coverage(answer)
                if report:
                    return {
                        "messages": [HumanMessage(content=f"{COVERAGE_TURN}\n{report}")],
                        "jump_to": "model",
                    }
            if checked or nudged:
                return None
            return {"messages": [HumanMessage(content=NUDGE)], "jump_to": "model"}
        except Exception:
            return None


def build_guide(memory: dict, input_text: str) -> str:
    """Brief the solver with the reference profile and the closest references."""
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
    view = MemoryView(memory)

    def coverage(answer_text: str) -> str:
        """The elements the submitted answer does not account for, or an empty string."""
        problem, _ = view.coverage_report(answer_text, input_text)
        return problem

    agent = create_deep_agent(
        model=model,
        tools=build_tools(input_text, memory),
        system_prompt=system_prompt(memory),
        middleware=[VerifyBeforeSubmit(coverage)],
        subagents=[],
        backend=backend,
    )
    prompt = Path(SOLVER_PATH).read_text().format(
        input=input_text,
        guide=build_guide(memory, input_text),
        skill=render_skill(memory),
    )
    return agent, prompt
