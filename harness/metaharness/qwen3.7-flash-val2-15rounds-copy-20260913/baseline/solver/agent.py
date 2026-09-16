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

from tools import build_tools

SYSTEM_PROMPT = "You are an agent that answers a question by retrieving examples."
SKILL_PATH = "/harness/skills/answer-with-examples/SKILL.md"


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
        tools=build_tools(input_text),
        system_prompt=SYSTEM_PROMPT,
        middleware=[],
        subagents=[],
        backend=backend,
    )
    prompt = Path("/harness/solver.md").read_text().format(
        input=input_text, skill=Path(SKILL_PATH).read_text().strip()
    )
    return agent, prompt
