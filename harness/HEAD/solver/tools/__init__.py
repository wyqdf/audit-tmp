"""Register business tools here. Initial candidate has only retrieval."""

from .retrieval import MAX_CHARS, make_tool

TOOL_FACTORIES = [make_tool]


def build_tools(input_text: str, max_chars: int = MAX_CHARS):
    return [factory(input_text, max_chars) for factory in TOOL_FACTORIES]
