"""Register business tools here. Initial candidate has only retrieval."""

from .retrieval import make_tool

TOOL_FACTORIES = [make_tool]


def build_tools(input_text: str):
    return [factory(input_text) for factory in TOOL_FACTORIES]
