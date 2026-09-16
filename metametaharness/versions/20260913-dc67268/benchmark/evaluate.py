"""Selected baseline splits and scoring; this module stays outside the solver."""

from .answers import extract_json_field
from pathlib import Path
import random

from .data import constants, loaders
from .data.api import _with_context, _balanced_subsample
from .data.evaluators import get_evaluator


def load_task(task: str, config: dict, split: str):
    dataset = config["dataset"]
    data_root = Path(__file__).resolve().parents[1] / dataset["root"]
    constants.MCE_DATA_PATH = loaders.MCE_DATA_PATH = str(data_root)
    count = dataset.get("overrides", {}).get(task, {}).get(f"num_{split}", dataset[f"num_{split}"])
    loader = loaders.load_mce_dataset if task in constants.MCE_TASKS else loaders.load_transfer_dataset
    examples = _with_context(loader(task, split=split))
    if count > len(examples):
        raise ValueError(f"Requested too many {split} examples for {task}")
    if task in constants.MCE_TASKS:
        random.Random(dataset["seed"]).shuffle(examples)
        return examples[:count]
    return _balanced_subsample(examples, count, seed=dataset["seed"])


def score(task: str, example: dict, response: str, status: str):
    prediction = extract_json_field(response, "final_answer")
    result = get_evaluator(task)(prediction, example["target"])
    if isinstance(result, dict):
        correct, metrics = result["was_correct"], result.get("metrics", {})
    else:
        correct, metrics = bool(result), {}
    return {
        "prediction": prediction,
        "target": example["target"],
        "was_correct": bool(correct) and status == "ok",
        "metrics": metrics,
    }


def summarize(rows: list[dict], examples: int):
    correct = sum(row["was_correct"] for row in rows)
    f1_values = [row["metrics"]["f1"] for row in rows if "f1" in row["metrics"]]
    tp = sum(row["metrics"].get("tp", 0) for row in rows)
    fp = sum(row["metrics"].get("fp", 0) for row in rows)
    fn = sum(row["metrics"].get("fn", 0) for row in rows)
    return {
        "accuracy": correct / len(rows) if rows else 0.0,
        "correct": correct,
        "total": len(rows),
        "num_examples": examples,
        "aggregation": "sample_mean",
        "avg_f1": sum(f1_values) / len(f1_values) if f1_values else None,
        "micro_f1": (2 * tp / (2 * tp + fp + fn) if 2 * tp + fp + fn else 0.0) if f1_values else None,
        "failed_samples": sum(row["status"] != "ok" for row in rows),
        "model_calls": sum(row["usage"]["model_calls"] for row in rows),
        "input_tokens": sum(row["usage"]["input_tokens"] for row in rows),
        "output_tokens": sum(row["usage"]["output_tokens"] for row in rows),
    }
