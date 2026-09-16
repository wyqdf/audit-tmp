"""The demonstrated examples, delivered with the question."""

import json
import re
from pathlib import Path

# The memory is the harness's whole evidence about the task, so the question carries it as
# it is: every demonstrated example, the ones closest to the question first.  What bounds
# it is the channel it travels in, and the channels do not have the same ceiling.  A tool
# result is taken off the conversation once it passes 20,000 tokens — 80,000 characters at
# four characters to the token — and replaced by a preview and a file path, so a memory
# past that size reaches the model as a handful of lines and a search problem; the question
# itself is only taken off past 50,000 tokens, 200,000 characters.  The set therefore
# travels with the question, sized to the room that channel has left once the question and
# the instructions are in it, so the model reads the demonstrations rather than paging for
# them, and a later attempt is a single model call instead of a fetch and an answer.  A
# provider may still refuse to read a request that carries as much as the channel allows,
# so the same set is also rendered at a fraction of that room, closest examples first.
DEMO_BUDGET_SHARE = 0.25
DEFAULT_CONTEXT_WINDOW = 128000
PROMPT_LIMIT_CHARS = 195000
MAX_EXAMPLES = 9999


def demo_budget(config: dict | None = None, question_chars: int = 0, share: float = 1.0) -> int:
    """How many characters of demonstrations the question leaves room for.

    The room the channel has is one thing and what the provider agrees to read is
    another, so the same budget is drawn on at a fraction of itself: a delivery that
    was refused is repeated with the closest examples that fit in ``share`` of it.
    """
    window = (config or {}).get("context_window") or DEFAULT_CONTEXT_WINDOW
    return int(min(window * DEMO_BUDGET_SHARE, PROMPT_LIMIT_CHARS - question_chars) * share)


def question_of(example: dict) -> str:
    """The question side of a demonstrated example."""
    return example.get("raw_question", example.get("input", ""))


def bigrams(text: str) -> set:
    text = re.sub(r"\s+", "", text or "")
    return {text[index:index + 2] for index in range(len(text) - 1)}


def closeness(question: str, example: dict) -> float:
    """How much wording the question and a demonstrated example share."""
    asked, shown = bigrams(question), bigrams(question_of(example))
    return len(asked & shown) / max(1, len(asked | shown))


def order_examples(question: str, examples: list[dict]) -> list[dict]:
    """The demonstrated examples, the ones closest to the question first."""
    return sorted(examples, key=lambda example: -closeness(question, example))


def render_demonstrations(input_text: str, config: dict | None = None, share: float = 1.0) -> str:
    """The demonstration set of the memory, rendered for the question to carry it.

    ``share`` is the fraction of the channel's room this rendering draws on, so every
    rendering is a prefix of the one before it: the same examples, in the same order
    by closeness, with the cut nearer or further down the list.
    """
    examples = json.loads(Path("/harness/memory/memory.json").read_text())["examples"]
    ordered = order_examples(input_text, examples)[:MAX_EXAMPLES]
    budget = demo_budget(config, len(input_text), share)
    parts = []
    total_chars = 0
    for example in ordered:
        part = f"Q: {question_of(example)}\nA: {example['target']}"
        if total_chars + len(part) > budget:
            break
        parts.append(part)
        total_chars += len(part) + 2
    if len(parts) == len(ordered):
        header = f"The complete demonstration set for this task ({len(parts)} examples):"
    else:
        header = (
            f"The {len(parts)} demonstrated examples closest to this question, out of "
            f"the {len(ordered)} the memory holds:"
        )
    return header + "\n\n" + "\n\n".join(parts)
