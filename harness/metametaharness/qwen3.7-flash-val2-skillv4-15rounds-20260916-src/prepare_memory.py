"""Offline FewShotAll learning, run separately from the solver."""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "solver"))

from answer_conventions import build_profile


def prepare_memory(train: list[dict], epochs: int) -> dict:
    examples = []
    for _ in range(epochs):
        for item in train:
            example = {"input": item["input"], "target": item["target"]}
            if "raw_question" in item:
                example["raw_question"] = item["raw_question"]
            examples.append(example)
    return {
        "examples": examples,
        "answer_profile": build_profile([item["target"] for item in train]),
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--train", default="/input/train.json")
    parser.add_argument("--output", default="/output/memory.json")
    parser.add_argument("--epochs", type=int, default=1)
    args = parser.parse_args()
    train = json.loads(Path(args.train).read_text())
    Path(args.output).write_text(json.dumps(prepare_memory(train, args.epochs), indent=2))
