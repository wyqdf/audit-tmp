"""Retrieval of the training examples that bear on the current question.

The memory holds the training question/answer pairs, and the solver copies its answer
wording and composition from them, so the examples worth spending context on are the ones
closest to the question being asked. The pool is therefore ranked by a similarity over the
question text itself and the budget is filled from the top, instead of handing over an
arbitrary slice of the memory. The ranking is computed from the memory's own questions, so
the same code applies to any memory in the same format.
"""

import json
import math
import re
from collections import Counter
from pathlib import Path

from langchain_core.tools import tool

MAX_CHARS = 30000  # context the retrieved examples may take
NGRAM = 2  # characters per shingle: short enough for CJK, long enough to be specific


def _shingles(text: str) -> Counter:
    """The character shingles of a text, whitespace collapsed so wrapping does not matter."""
    text = re.sub(r"\s+", " ", (text or "").lower())
    return Counter(text[index : index + NGRAM] for index in range(max(0, len(text) - NGRAM + 1)))


def _document_frequency(counts: list[Counter]) -> Counter:
    frequency = Counter()
    for count in counts:
        frequency.update(count.keys())
    return frequency


def _weigh(count: Counter, frequency: Counter, documents: int) -> dict:
    """Weight a shingle count by how rare the shingle is across the memory's questions.

    A shingle no question contains can only be part of the question being asked, so it is
    given the largest weight; it matches nothing either way and leaves the ranking alone.
    """
    return {
        shingle: number * math.log(1 + (documents / frequency[shingle] if frequency[shingle] else 1e9))
        for shingle, number in count.items()
    }


def _cosine(left: dict, right: dict, right_norm: float) -> float:
    shared = left.keys() & right.keys()
    numerator = sum(left[shingle] * right[shingle] for shingle in shared)
    norm = math.sqrt(sum(value * value for value in left.values())) * right_norm
    return numerator / norm if norm else 0.0


def make_tool(input_text: str):
    examples = json.loads(Path("/harness/memory/memory.json").read_text())["examples"]
    questions = [example.get("raw_question", example["input"]) for example in examples]
    counts = [_shingles(question) for question in questions]
    frequency = _document_frequency(counts)
    vectors = [_weigh(count, frequency, len(counts)) for count in counts]
    norms = [math.sqrt(sum(value * value for value in vector.values())) for vector in vectors]
    asked = _weigh(_shingles(input_text), frequency, len(counts))
    # closest first; memory order breaks ties, so the same question always retrieves the
    # same examples in the same order.
    ranked = sorted(
        range(len(examples)),
        key=lambda index: (-_cosine(asked, vectors[index], norms[index]), index),
    )

    @tool
    def retrieve_examples() -> str:
        """Get the training Q/A examples to use when answering the current problem."""
        parts = []
        total_chars = 0
        for index in ranked:
            example = examples[index]
            question = example.get("raw_question", example["input"])
            part = f"Q: {question}\nA: {example['target']}"
            if total_chars + len(part) > MAX_CHARS:
                break
            parts.append(part)
            total_chars += len(part) + 2
        return "\n\n".join(parts)

    return retrieve_examples
