"""Prepare or evaluate one candidate in an experiment."""

import argparse
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
import json
from pathlib import Path
import shutil
import sys
import time

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from benchmark.evaluate import load_task, score, summarize
from benchmark.runtime.errors import EvaluationError, classify_error
from benchmark.runtime.gateway import Gateway
from benchmark.runtime.runs import (
    PROJECT, open_candidate, open_experiment, output_directory, prepare_task, read_json,
    solve_question, write_json, load_config, load_credentials, source_tree, git, directory_hash,
)
from benchmark.runtime import sandbox


def evaluate_one(root, manifest, task, split, memory, trace, index, sample, example, gateway):
    directory = trace / f"{index:04d}" / f"sample-{sample}"
    result_path = directory / "result.json"
    if result_path.exists():
        row = read_json(result_path)
        if row["status"] == "ok":
            return row
    execution = directory / f"execution-{time.time_ns()}"
    try:
        row = solve_question(manifest, memory, execution, example["input"], gateway)
        if row["status"] == "ok":
            row.update(score(task, example, row["response"], row["status"]))
    except Exception as error:
        row = {
            "status": "error", "input": example["input"], "response": "",
            "error": classify_error(error, patterns=manifest["config"]["solver"].get("error_patterns")),
            "usage": {"model_calls": 0, "input_tokens": 0, "output_tokens": 0},
        }
    row.update({
        "task": task, "split": split, "example_index": index, "sample_index": sample,
        "trace_dir": str(execution.relative_to(root)),
    })
    write_json(result_path, row)
    return row


def cached_predictions(root, task_trace, split, patterns):
    rows = {}
    attempts = sorted(task_trace.glob("attempt-*"), key=lambda path: int(path.name.split("-")[1]))
    for attempt in attempts:
        for path in (attempt / split).glob("*/sample-*/result.json"):
            row = read_json(path)
            key = (row["example_index"], row["sample_index"])
            if row["status"] != "ok" and not row.get("error"):
                stderr = root / row["trace_dir"] / "stderr.txt"
                message = "Previous solver execution failed"
                if stderr.exists():
                    with stderr.open("rb") as handle:
                        handle.seek(max(0, stderr.stat().st_size - 4096))
                        message = handle.read().decode(errors="replace") or message
                row["error"] = classify_error(message, patterns=patterns)
            if key not in rows or rows[key]["status"] != "ok" or row["status"] == "ok":
                rows[key] = row
    return rows, int(attempts[-1].name.split("-")[1]) if attempts else 0


def task_summary(rows, examples, samples, limited, preparation_error=None):
    good = [row for row in rows if row["status"] == "ok"]
    expected = examples * samples
    complete = len(good) == expected and preparation_error is None
    summary = summarize(good, examples)
    successful_accuracy = summary["accuracy"] if good else None
    errors = [
        {"example_index": row["example_index"], "sample_index": row["sample_index"], **row["error"]}
        for row in rows if row["status"] != "ok"
    ]
    missing = expected - len(rows)
    # Failed samples stay in the denominator and count as wrong answers; the task score
    # only requires that every sample was attempted.
    scored = preparation_error is None and expected > 0 and missing == 0
    summary.update({
        "status": "ok" if complete else "partial" if good else "error",
        "accuracy": summary["correct"] / expected if scored else None,
        "successful_accuracy": successful_accuracy,
        "successful_samples": len(good), "expected_samples": expected,
        "completion_rate": len(good) / expected if expected else 1.0,
        "failed_samples": len(errors), "missing_samples": missing,
        "errors": errors, "error_counts": dict(Counter(error["type"] for error in errors)),
        "partial": limited,
        "rankable": scored and not limited,
        "memory_context_chars": sum(row["memory_context_chars"] for row in good) / len(good) if good else 0,
    })
    if preparation_error:
        summary["preparation_error"] = preparation_error
    return summary


def evaluate_task(root, manifest, task, split, gateway, question_pool, limit=None, prepare_only=False):
    config = manifest["config"]
    output_root = output_directory(root, manifest, split)
    result_root = output_root / "results" / task
    result_root.mkdir(parents=True, exist_ok=True)
    summary_path = result_root / "summary.json"
    spec = {"limit": limit, "samples": config["evaluation"][f"{split}_samples"]}
    spec_path = result_root / "spec.json"
    if spec_path.exists() and read_json(spec_path) != spec:
        raise ValueError("Evaluation size changed; use a new experiment")
    write_json(spec_path, spec)
    if summary_path.exists() and not prepare_only:
        saved = read_json(summary_path)
        if saved.get("rankable"):
            return saved
    state_path = result_root / "attempt.json"
    task_trace = output_root / "traces" / task
    task_trace.mkdir(parents=True, exist_ok=True)
    examples = load_task(task, config, split)
    if split == "test":
        source = root / manifest["tree"] / "memories" / task
        val_summary = root / manifest["tree"] / "results" / task / "summary.json"
        if not val_summary.exists() or read_json(val_summary)["status"] != "ok":
            raise ValueError("Test requires the saved memory and successful Val result")
        memory = output_root / "memories" / task
        memory_id = read_json(val_summary.parent / "memory_manifest.json")["memory_id"]
        if directory_hash(source) != memory_id:
            raise ValueError("Frozen Val memory changed")
        if not memory.exists():
            shutil.copytree(source, memory)
        if directory_hash(memory) != memory_id:
            raise ValueError("Frozen Test memory changed")
    full_count = len(examples)
    if limit is not None:
        examples = examples[:limit]
    work = {(index, sample): example for index, example in enumerate(examples) for sample in range(spec["samples"])}
    rows, attempt = cached_predictions(root, task_trace, split, config["solver"].get("error_patterns"))
    rows = {key: row for key, row in rows.items() if key in work}
    reused = sum(row["status"] == "ok" for row in rows.values())
    pending = [key for key in work if key not in rows or rows[key]["status"] != "ok"]
    attempts = config["runtime"].get("sample_attempts", config["runtime"].get("task_attempts", 2))
    preparation_error = None
    for _ in range(attempts):
        if not pending and not prepare_only:
            break
        attempt += 1
        write_json(state_path, {"attempt": attempt, "status": "running"})
        trace = task_trace / f"attempt-{attempt}"
        trace.mkdir(parents=True, exist_ok=True)
        try:
            if split == "val":
                memory = prepare_task(root, manifest, task, gateway, trace / "prepare")
            preparation_error = None
            if prepare_only:
                return {"status": "prepared", "memory": str(memory)}
            futures = [
                question_pool.submit(
                    evaluate_one, root, manifest, task, split, memory, trace / split,
                    index, sample, work[(index, sample)], gateway,
                )
                for index, sample in pending
            ]
            try:
                for future in as_completed(futures):
                    row = future.result()
                    rows[(row["example_index"], row["sample_index"])] = row
                    good = [item for item in rows.values() if item["status"] == "ok"]
                    latest = f"{sum(item['was_correct'] for item in good) / len(good):.2%}" if good else "待评测"
                    failure = f" 错误={row['error']['type']}" if row["status"] != "ok" else ""
                    print(f"benchmark 候选={manifest['name']} 任务={task} 成功={len(good)}/{len(work)} 成功题准确率={latest}{failure}", flush=True)
            except BaseException:
                for future in futures:
                    future.cancel()
                raise
            predictions = [rows[key] for key in sorted(rows)]
            with (trace / "predictions.jsonl").open("w") as handle:
                for row in predictions:
                    handle.write(json.dumps(row, ensure_ascii=False) + "\n")
            pending = [key for key in pending if rows[key]["status"] != "ok" and rows[key]["error"]["retryable"]]
        except Exception as error:
            preparation_error = error.error if isinstance(error, EvaluationError) else classify_error(
                error, patterns=config["solver"].get("error_patterns"),
            )
            write_json(trace / "error.json", {"attempt": attempt, "error": preparation_error})
            if not preparation_error["retryable"]:
                break
    predictions = [rows[key] for key in sorted(rows)]
    predictions_path = task_trace / "predictions.jsonl"
    with predictions_path.open("w") as handle:
        for row in predictions:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
    summary = task_summary(predictions, len(examples), spec["samples"], len(examples) < full_count, preparation_error)
    summary.update({"attempt": attempt, "reused_samples": reused, "predictions": str(predictions_path.relative_to(root))})
    write_json(summary_path, summary)
    write_json(state_path, {"attempt": attempt, "status": summary["status"], "error_counts": summary["error_counts"]})
    return summary


def evaluate_candidate(root, config, candidate, split="val", tasks=None, limit=None, prepare_only=False, manifest=None):
    if split == "val" and (root / "finalized.json").exists():
        raise ValueError("Experiment was frozen for Test")
    if split == "test" and manifest is None:
        raise ValueError("Use outerloop/meta_meta_harness.py --test-commits for Test")
    manifest = manifest or open_candidate(root, config, candidate)
    output_root = output_directory(root, manifest, split)
    summary_path = output_root / "results" / "summary.json"
    if summary_path.exists() and not prepare_only:
        saved = read_json(summary_path)
        if saved.get("rankable") or (split == "val" and manifest.get("commit")):
            return saved
    manifest_path = output_root / "manifest.json"
    record = read_json(manifest_path)
    record["evaluation"] = {"started_at": time.time(), "finished_at": None}
    write_json(manifest_path, record)
    head = git(candidate, "rev-parse", "HEAD") if split == "val" else None
    try:
        result = _evaluate_candidate(root, config, manifest, split, tasks, limit, prepare_only)
        if split == "val" and (source_tree(candidate) != manifest["tree"] or git(candidate, "rev-parse", "HEAD") != head):
            raise ValueError("Harness source or HEAD changed during evaluation")
        if not prepare_only:
            write_json(summary_path, result)
        return result
    finally:
        record["evaluation"]["finished_at"] = time.time()
        write_json(manifest_path, record)


def _evaluate_candidate(root, config, manifest, split, tasks, limit, prepare_only):
    tasks = tasks or config["dataset"]["tasks"]
    if any(task not in config["dataset"]["tasks"] for task in tasks):
        raise ValueError("Task is not enabled in the experiment configuration")
    print(f"benchmark 候选={manifest['name']} 最新分数=待评测", flush=True)
    sandbox.STOPPING.clear()
    with Gateway(config["solver"], config["runtime"]["model_concurrency"]) as gateway:
        with ThreadPoolExecutor(max_workers=config["runtime"]["parallel_questions"]) as question_pool:
            with ThreadPoolExecutor(max_workers=len(tasks)) as task_pool:
                futures = {
                    task: task_pool.submit(evaluate_task, root, manifest, task, split, gateway, question_pool, limit, prepare_only)
                    for task in tasks
                }
                try:
                    scores = {task: future.result() for task, future in futures.items()}
                except BaseException:
                    for future in futures.values():
                        future.cancel()
                    sandbox.stop_all()
                    raise
    if prepare_only:
        return {"name": manifest["name"], "scores": scores, "status": "prepared"}
    full_tasks = set(tasks) == set(config["dataset"]["tasks"])
    complete = full_tasks and all(row["status"] == "ok" for row in scores.values())
    # A task keeps its score when every sample was attempted, so a failed sample lowers
    # the mean instead of voiding the whole candidate.
    scored = full_tasks and all(row.get("accuracy") is not None for row in scores.values())
    partial = not full_tasks or any(row.get("partial", False) for row in scores.values())
    result = {
        "name": manifest["name"], "candidate_id": manifest["candidate_id"], "split": split,
        "scores": scores, "status": "ok" if complete else "partial" if any(row.get("total", 0) for row in scores.values()) else "error",
        "average": sum(row["accuracy"] for row in scores.values()) / len(scores) if scored else None,
        "partial": partial,
        "rankable": scored and not partial,
        "successful_samples": sum(row.get("successful_samples", row.get("total", 0) if row["status"] == "ok" else 0) for row in scores.values()),
        "expected_samples": sum(row.get("expected_samples", row.get("total", 0)) for row in scores.values()),
    }
    result["completion_rate"] = result["successful_samples"] / result["expected_samples"] if result["expected_samples"] else 0.0
    latest = f"{result['average']:.2%}" if scored else "未形成完整成绩"
    print(f"benchmark 候选={manifest['name']} 最新分数={latest}", flush=True)
    for task, row in scores.items():
        accuracy = row.get("successful_accuracy")
        local = f"{accuracy:.2%}" if accuracy is not None else "无"
        score = row.get("accuracy")
        graded = f"{score:.2%}" if score is not None else "无"
        print(f"  {task}: 成功={row.get('successful_samples', row.get('total', 0))}/{row.get('expected_samples', row.get('total', 0))} 计分准确率={graded} 成功题准确率={local} 错误={row.get('error_counts', {})}", flush=True)
    return result


def scores_output(result: dict) -> dict:
    """The object printed for the caller: the task accuracies, their mean, and the run status.

    Everything else the runner computes stays in ``results/summary.json`` and the per-task
    result files; callers that need completion rates, error counts or prediction paths read
    them from there.
    """
    payload = {}
    for task, row in result.get("scores", {}).items():
        score = row.get("accuracy") if isinstance(row, dict) else None
        payload[task] = None if score is None else round(score, 4)
    average = result.get("average")
    payload["average"] = None if average is None else round(average, 4)
    payload["status"] = result.get("status")
    return payload


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["prepare", "evaluate", "solve"])
    location = parser.add_mutually_exclusive_group(required=True)
    location.add_argument("--run-name")
    location.add_argument("--run-dir", type=Path)
    parser.add_argument("--config", type=Path, default=PROJECT / "config.yaml")
    parser.add_argument("--candidate", type=Path)
    parser.add_argument("--task", "--tasks", nargs="+", dest="tasks")
    parser.add_argument("--split", choices=["val", "test"], default="val")
    parser.add_argument("--limit", type=int)
    parser.add_argument("--input-file", type=Path)
    args = parser.parse_args()
    if args.run_dir:
        root = args.run_dir.resolve()
        config = load_config(root / "config.yaml")
        load_credentials(config)
        candidate = args.candidate or PROJECT / "harness"
    else:
        root, config = open_experiment(args.run_name, args.config)
        candidate = args.candidate or PROJECT / "harnesses" / args.run_name
    candidate = candidate.resolve()
    if args.command == "solve":
        if not args.input_file or not args.tasks or len(args.tasks) != 1:
            parser.error("solve requires one task and an input file")
        manifest = open_candidate(root, config, candidate)
        task = args.tasks[0]
        trace = root / manifest["tree"] / "traces" / task / "solve" / str(time.time_ns())
        with Gateway(config["solver"], config["runtime"]["model_concurrency"]) as gateway:
            memory = root / manifest["tree"] / "memories" / task
            result = solve_question(manifest, memory, trace, args.input_file.read_text(), gateway)
            write_json(trace / "result.json", result)
    else:
        result = evaluate_candidate(
            root, config, candidate, args.split, args.tasks, args.limit, args.command == "prepare",
        )
    print(json.dumps(scores_output(result) if args.command == "evaluate" else result, ensure_ascii=False), flush=True)
    return 0 if result["status"] in {"ok", "prepared"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
