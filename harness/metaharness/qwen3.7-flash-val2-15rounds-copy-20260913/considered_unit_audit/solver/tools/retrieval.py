"""Tools over the frozen reference memory: retrieve, grep and answer checks."""

import json
from pathlib import Path

from langchain_core.tools import tool

from .memory_lib import MemoryView

MEMORY_PATH = "/harness/memory/memory.json"


def load_memory(path: str = MEMORY_PATH) -> dict:
    try:
        return json.loads(Path(path).read_text())
    except (OSError, json.JSONDecodeError):
        return {}


def build_tools(input_text: str, memory: dict | None = None):
    view = MemoryView(memory if memory is not None else load_memory())

    @tool
    def retrieve_examples(query: str = "", limit: int = 10) -> str:
        """Return training reference cases ranked by similarity to a query.

        Args:
            query: what to look for; leave empty to rank against the current question.
            limit: how many reference cases to return (1-20).
        """
        try:
            size = max(1, min(int(limit), 20))
        except (TypeError, ValueError):
            size = 10
        return view.render_references(query.strip() or input_text, limit=size, per_reference=900)

    @tool
    def search_examples(keyword: str, limit: int = 8) -> str:
        """Grep the training references for a keyword or regular expression.

        Args:
            keyword: text or regular expression to look for in questions and answers.
            limit: how many matching reference cases to return (1-20).
        """
        try:
            size = max(1, min(int(limit), 20))
        except (TypeError, ValueError):
            size = 8
        indexes = view.keyword_search(keyword.strip(), limit=size)
        if not indexes:
            return f"No reference case matches {keyword!r}."
        return view.render(indexes, per_reference=900)

    @tool
    def check_answer(draft_answer: str, considered: str = "") -> str:
        """Check a draft answer against the reference profile before finalizing.

        Reports shape, markup and unit-surface problems, and re-opens the candidate
        units you named while deciding but left out of the draft, with the reference
        cases that answer each of them, so a unit is only set aside for a factual
        reason. Also re-opens reference units that share an edge with a unit of your
        draft (the same unit said more or less specifically).

        Args:
            draft_answer: the answer exactly as it would be submitted.
            considered: every unit you named while deciding, comma separated, including
                the ones you set aside (just the units, not the surrounding reasoning).
        """
        return view.check(draft_answer, input_text, considered)

    return [retrieve_examples, search_examples, check_answer]
