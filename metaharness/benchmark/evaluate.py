"""Selected baseline splits and scoring; this module stays outside the solver."""

from .answers import extract_json_field
from .data import constants, loaders
from .data.api import load_dataset_splits_3way
from .data.evaluators import get_evaluator


def load_task(task: str, config: dict):
    dataset = config["dataset"]
    constants.MCE_DATA_PATH = dataset["root"]
    loaders.MCE_DATA_PATH = dataset["root"]
    sizes = {name: dataset[name] for name in ["num_train", "num_val", "num_test"]}
    sizes.update(dataset.get("overrides", {}).get(task, {}))
    train, val, test, _ = load_dataset_splits_3way(
        task, **sizes, shuffle_seed=dataset["seed"],
    )
    return {"train": train, "val": val, "test": test}


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
    def metric(row):
        return row.get("metric") or {}

    correct = sum(row["was_correct"] for row in rows)
    f1_values = [metric(row)["f1"] for row in rows if "f1" in metric(row)]
    tp = sum(metric(row).get("tp", 0) for row in rows)
    fp = sum(metric(row).get("fp", 0) for row in rows)
    fn = sum(metric(row).get("fn", 0) for row in rows)
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
