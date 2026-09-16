"""Register business tools here. Initial candidate has only retrieval."""

from .progress import Ledger, ProgressGuard
from .retrieval import make_search_tool, make_tool

TOOL_FACTORIES = [make_tool, make_search_tool]


def build_tools(input_text: str):
    # One ledger per run: what the agent has already been answered holds for the
    # conversation it is in, and the tools it is given are the ones it asks.
    ledger = Ledger()
    return [factory(input_text, ledger) for factory in TOOL_FACTORIES]


def build_guard(tools) -> ProgressGuard:
    """The loop's bound, over the tools this harness builds.

    Every one of them answers from the same frozen memory, so a request that
    comes back to any of them can only be answered with what the run already
    holds.  The agent's other tools -- writing a file, running a command -- act
    on the world and are not bounded here.
    """
    return ProgressGuard(tools)
