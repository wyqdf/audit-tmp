"""Original FewShotAll selection and formatting, exposed as a tool."""

import hashlib
import json
import random
from pathlib import Path

from langchain_core.tools import tool

MAX_CHARS = 30000
MAX_EXAMPLES = 9999


def make_tool(input_text: str):
    examples = json.loads(Path("/harness/memory/memory.json").read_text())["examples"]
    seed = int.from_bytes(hashlib.sha256(input_text.encode()).digest()[:8], "big")

    @tool
    def retrieve_examples() -> str:
        """Get the training Q/A examples to use when answering the current problem."""
        rng = random.Random(seed)
        if len(examples) > MAX_EXAMPLES:
            selected = rng.sample(examples, MAX_EXAMPLES)
        else:
            selected = list(examples[-MAX_EXAMPLES:])
            rng.shuffle(selected)
        parts = []
        total_chars = 0
        for example in selected:
            question = example.get("raw_question", example["input"])
            part = f"Q: {question}\nA: {example['target']}"
            if total_chars + len(part) > MAX_CHARS:
                break
            parts.append(part)
            total_chars += len(part) + 2
        return "\n\n".join(parts)

    return retrieve_examples
