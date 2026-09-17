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

from middleware import Respelling
from tools import build_tools
from tools.retrieval import RETRY_CHARS

SYSTEM_PROMPT = "You are an agent that answers a question by retrieving examples."
SKILL_PATH = "/harness/skills/answer-with-examples/SKILL.md"

# The skill's steps are written for the tools that were built and for the listing
# those tools produce: a step that calls `check_answer`, or that sends the solver to
# the memory file for examples that were all listed, would describe a lookup that
# cannot return anything the solver does not already have.
MEMORY_STEP = {
    True: (
        "4. The examples above are the whole memory: every example it holds is listed,"
        " so there is nothing further to search for."
    ),
    False: (
        "4. If the closest examples do not cover the question, search the memory under"
        " `/harness/memory` yourself."
    ),
}
CHECK_STEP = {
    True: (
        "5. Draft your answer, then call `check_answer` with it. It compares every part of"
        " your draft with the answers the memory holds:\n"
        "   - `change: x -> y` — the memory writes that answer as `y`. Use `y` exactly.\n"
        "   - `not in memory: x` — the memory holds no answer written like `x`, so there is"
        " no spelling to copy from it: keep your own wording for that part, in the"
        " examples' style. The memory's silence says nothing about whether `x` is right."
    ),
    False: (
        "5. No example answers this question, so write the answer yourself, in the same"
        " style and format as the examples."
    ),
}


def render_skill(memory: dict) -> str:
    """The skill with the steps that match the tools the memory could support."""
    skill = Path(SKILL_PATH).read_text()
    return (
        skill
        .replace("[[memory_step]]", MEMORY_STEP[memory["complete_listing"]])
        .replace("[[check_step]]", CHECK_STEP[memory["check_answer"]])
    )


def make_agent(model, tools, config: dict, spelling):
    """One agent over the tools it was given and the memory's spelling of answers."""
    backend = LocalShellBackend(
        root_dir="/",
        virtual_mode=True,
        timeout=config["tool_timeout_seconds"],
        env={"PATH": os.environ["PATH"], "HOME": "/tmp", "PYTHONDONTWRITEBYTECODE": "1"},
    )
    return create_deep_agent(
        model=model,
        tools=tools,
        system_prompt=SYSTEM_PROMPT,
        middleware=[] if spelling is None else [Respelling(spelling)],
        subagents=[],
        backend=backend,
    )


class Attempts:
    """The agent, and the attempts a failed invocation earns.

    A sample whose invocation raises is scored as a wrong answer, so repeating it
    can only improve on what the run already has. The failures the runs record
    are the provider's — a refusal (`DataInspectionFailed`) of the call that
    carries the retrieved listing, which the runner does not retry — and the same
    sample is answered by every other run of the same harness, so the first
    repeat makes the same request again rather than a different one. The last
    attempt lists less of the memory, which is the part of the request a content
    inspection reads, and is the attempt left for a request that is refused
    whatever the state of the provider.
    """

    # The first attempt, the same request again, and one over a smaller listing.
    ATTEMPTS = 3

    def __init__(self, agent, smaller):
        self.agent = agent
        self.smaller = smaller

    def invoke(self, inputs, config=None):
        """The answer of the first attempt the provider accepts."""
        for attempt in range(self.ATTEMPTS):
            last = attempt == self.ATTEMPTS - 1
            agent = self.smaller() if last else self.agent
            try:
                return agent.invoke(inputs, config=config)
            except Exception:
                if last:
                    raise


def build_agent(model, input_text: str, config: dict):
    profile = HarnessProfile(
        general_purpose_subagent=GeneralPurposeSubagentProfile(enabled=False),
    )
    register_harness_profile("openai", profile)
    register_harness_profile(f"openai:{config['model']}", profile)
    tools, memory = build_tools(input_text)
    spelling = memory["spelling"]
    # The prompt names the tools the memory could support, and a repeated attempt
    # keeps the answer space and only shrinks the listing, so the skill the prompt
    # carries still describes what the repeated attempt can do.
    prompt = Path("/harness/solver.md").read_text().format(
        input=input_text, skill=render_skill(memory)
    )
    return (
        Attempts(
            make_agent(model, tools, config, spelling),
            lambda: make_agent(model, build_tools(input_text, RETRY_CHARS)[0], config, spelling),
        ),
        prompt,
    )
