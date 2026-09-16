"""Offline memory preparation: turns the training references into frozen memory.

The heavy lifting lives in ``solver/tools/memory_lib.py`` so that the solver and
the preparation step share exactly the same derivations. This script runs inside
the preparation sandbox with the candidate mounted read-only at ``/candidate``.
"""

import argparse
import importlib.util
import json
import sys
from pathlib import Path

LIBRARY = "/candidate/solver/tools/memory_lib.py"


def load_library(path: str = LIBRARY):
    if not Path(path).exists():
        path = str(Path(__file__).resolve().parent / "solver" / "tools" / "memory_lib.py")
    spec = importlib.util.spec_from_file_location("memory_lib", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules["memory_lib"] = module
    spec.loader.exec_module(module)
    return module


def prepare_memory(train: list[dict], epochs: int) -> dict:
    return load_library().build_memory(train, epochs)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--train", default="/input/train.json")
    parser.add_argument("--output", default="/output/memory.json")
    parser.add_argument("--epochs", type=int, default=1)
    args = parser.parse_args()
    train = json.loads(Path(args.train).read_text())
    memory = prepare_memory(train, args.epochs)
    Path(args.output).write_text(json.dumps(memory, ensure_ascii=False))
