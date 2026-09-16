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
from langchain_core.messages import AIMessage

from adjudication import adjudicate, answer_span
from answer_space import (
    answer_separators,
    build_index,
    canonicalize,
    complete_compound,
    edge_conventions,
    stored_answers,
    stored_values,
    trim_trailing,
    vocabulary,
)
from recovery import recover
from resolution import answer_field, resolve
from tools import build_guard, build_tools

SYSTEM_PROMPT = "You are an agent that answers a question by retrieving examples."
SKILL_PATH = "/harness/skills/answer-with-examples/SKILL.md"


class GroundedAgent:
    """Returns the agent's result with its answer spelled the way memory spells it."""

    def __init__(self, agent, model, index, problem):
        self._agent = agent
        self._model = model
        self._index = index
        self._problem = problem
        self._spellings = vocabulary()
        self._conventions = edge_conventions(stored_values())
        self._separators = answer_separators(stored_answers())

    def invoke(self, *args, **kwargs):
        try:
            result = self._agent.invoke(*args, **kwargs)
        except Exception:
            # The run died inside a model call, so there is no message to read
            # an answer out of: the harness answers the problem itself, with
            # the same evidence the agent would have retrieved.  When it can
            # produce no answer either, the run's own error stands.
            text = recover(self._model, self._problem)
            if text is None:
                raise
            answered = self._ground(resolve(text, self._model, self._problem))
            return {"messages": [AIMessage(content=answered)]}
        messages = list(result["messages"])
        content = messages[-1].content
        text = content if isinstance(content, str) else "".join(
            block if isinstance(block, str) else block.get("text", "")
            for block in (content or [])
        )
        grounded = self._ground(resolve(text, self._model, self._problem, messages))
        if grounded != text:
            messages[-1] = messages[-1].model_copy(update={"content": grounded})
        return {**result, "messages": messages}

    def _ground(self, message: str) -> str:
        """Spell the answer the way memory spells it, inside the answer field only.

        The rules speak about answers, so they run on the span the runner reads
        the answer from.  A message that carries no answer there is left as the
        agent wrote it.
        """
        span = answer_field(message)
        if span is None or not message[span[0] : span[1]].strip():
            return message
        adjudicated, _ = adjudicate(
            message,
            self._model,
            self._problem,
            self._index[0],
            self._spellings,
            self._separators,
        )
        start, end = answer_field(adjudicated) or (0, 0)
        if start >= end:
            return adjudicated
        answer = adjudicated[start:end]
        answer, _ = canonicalize(answer, self._index)
        answer, _ = trim_trailing(answer, self._index, self._conventions)
        answer, _ = complete_compound(answer, self._index)
        return adjudicated[:start] + answer + adjudicated[end:]

    def __getattr__(self, name):
        return getattr(self._agent, name)


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
    tools = build_tools(input_text)
    agent = create_deep_agent(
        model=model,
        tools=tools,
        system_prompt=SYSTEM_PROMPT,
        middleware=[build_guard(tools)],
        subagents=[],
        backend=backend,
    )
    prompt = Path("/harness/solver.md").read_text().format(
        input=input_text, skill=Path(SKILL_PATH).read_text().strip()
    )
    return GroundedAgent(agent, model, build_index(), input_text), prompt
