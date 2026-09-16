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
    " references. Name every answer unit the question could support before you choose, and set"
    " a unit aside only for a factual reason: being absent from the reference vocabulary, or"
    " being less common there than another unit, is not one. Reuse whole reference units, never"
    " a fragment of one, with their exact spelling and answer shape. The answer is compared as"
    " an exact set of units: a unit that does not match the facts is wrong even when it is the"
    " more common one, a broader unit that covers the same facts is a different answer rather"
    " than a safer one, and the reference case closest to this question is the evidence for how"
    " this task names the situation it describes. Before submitting, verify the draft with"
    " check_answer, passing the candidate units you named in `considered`, and make the final"
    " answer reflect everything that call reports."
)
SKILL_PATH = "/harness/skills/answer-with-examples/SKILL.md"
SOLVER_PATH = "/harness/solver.md"
REFERENCE_CHARS = 15000
MAX_REFERENCES = 20

NUDGE = (
    "Before you submit: the draft has not been verified. Call check_answer once with your draft"
    " answer, and pass `considered` = the candidate units you named while deciding, comma"
    " separated, including the ones you set aside. Then work through everything it reports:"
    " every candidate it re-opens is either added to the answer or ruled out by a fact you can"
    " point to in the question, and every fragment or relative it flags is replaced by the whole"
    " reference unit the facts establish. Submit the final JSON only after that."
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
