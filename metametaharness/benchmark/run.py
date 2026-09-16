"""Prepare or evaluate one candidate in an experiment."""

import argparse
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
import json
from pathlib import Path
import sys
import time

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from benchmark.evaluate import load_task, score, summarize
from benchmark.runtime.errors import EvaluationError, classify_error
from benchmark.runtime.gateway import Gateway
from benchmark.runtime.runs import (
    PROJECT, frozen_memory, git, load_config, load_credentials, memory_path, open_candidate,
    open_experiment, output_directory, prepare_attempts, prepare_task, read_conversations,
    read_json, read_summary, rebuild_index, solve_question, source_tree, write_conversation,
    write_json, write_summary,
)
from benchmark.runtime import sandbox


def evaluate_one(root, manifest, task, split, memory, index, sample, example, gateway):
    """Run one sample and write its conversation; failed samples are recorded the same way."""
    header, response = solve_question(
        root, manifest, task, split, index, sample, memory, example["input"], gateway,
    )
    graded = score(task, example, response, header["status"])
    header.update({
        "was_correct": graded["was_correct"],
        "prediction": graded["prediction"],
        "target": graded["target"],
        "metric": graded["metrics"],
    })
    return write_conversation(root, manifest, task, index, sample, header, split)


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


def evaluate_task(root, manifest, task, split, gateway, question_pool, limit=None, prepare_only=False, saved=None):
    config = manifest["config"]
    if saved and saved.get("rankable") and not prepare_only:
        return saved
    examples = load_task(task, config, split)
    samples = config["evaluation"][f"{split}_samples"]
    full_count = len(examples)
    if limit is not None:
        examples = examples[:limit]
    work = {
        (index, sample): example
        for index, example in enumerate(examples) for sample in range(samples)
    }
    attempt = len(prepare_attempts(root, manifest, task, split))
    memory = None
    if prepare_only:
        if split == "val":
            memory = prepare_task(root, manifest, task, gateway, split)
        return {"status": "prepared", "memory": str(memory) if memory else ""}
    rows = {key: row for key, row in read_conversations(root, manifest, task, split).items() if key in work}
    reused = sum(row["status"] == "ok" for row in rows.values())
    pending = [key for key in work if key not in rows or rows[key]["status"] != "ok"]
    attempts = config["runtime"].get("sample_attempts", config["runtime"].get("task_attempts", 2))
    preparation_error = None
    for _ in range(attempts):
        if not pending:
            break
        attempt += 1
        try:
            memory = (
                prepare_task(root, manifest, task, gateway, split) if split == "val"
                else frozen_memory(root, manifest, task)
            )
            preparation_error = None
            futures = [
                question_pool.submit(
                    evaluate_one, root, manifest, task, split, memory,
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
                sandbox.stop_all()
                raise
            pending = [key for key in pending if rows[key]["status"] != "ok" and rows[key]["error"]["retryable"]]
        except Exception as error:
            preparation_error = error.error if isinstance(error, EvaluationError) else classify_error(
                error, patterns=config["solver"].get("error_patterns"),
            )
            sandbox.STOPPING.clear()
            if not preparation_error["retryable"]:
                break
    predictions = [rows[key] for key in sorted(rows)]
    summary = task_summary(predictions, len(examples), samples, len(examples) < full_count, preparation_error)
    summary.update({"attempt": attempt, "reused_samples": reused})
    rebuild_index(root, manifest, split)
    return summary


def evaluate_candidate(root, config, candidate, split="val", tasks=None, limit=None, prepare_only=False, manifest=None):
    if split == "val" and (root / "finalized.json").exists():
        raise ValueError("Experiment was frozen for Test")
    if split == "test" and manifest is None:
        raise ValueError("Use outerloop/meta_meta_harness.py --test-commits for Test")
    manifest = manifest or open_candidate(root, config, candidate)
    output_root = output_directory(root, manifest, split)
    spec = {"limit": limit, "samples": config["evaluation"][f"{split}_samples"]}
    saved = read_summary(root, manifest, split) or {}
    if saved and saved.get("spec") != spec:
        raise ValueError("Evaluation size changed; use a new experiment")
    if saved and not prepare_only and (saved.get("rankable") or (split == "val" and manifest.get("commit"))):
        return saved
    manifest_path = output_root / "manifest.json"
    record = read_json(manifest_path)
    record["evaluation"] = {"started_at": time.time(), "finished_at": None}
    write_json(manifest_path, record)
    head = git(candidate, "rev-parse", "HEAD") if split == "val" else None
    try:
        result = _evaluate_candidate(root, config, manifest, split, tasks, limit, prepare_only, saved)
        if split == "val" and (source_tree(candidate) != manifest["tree"] or git(candidate, "rev-parse", "HEAD") != head):
            raise ValueError("Harness source or HEAD changed during evaluation")
        if not prepare_only:
            result["spec"] = spec
            write_summary(root, manifest, result, split)
        return result
    finally:
        record["evaluation"]["finished_at"] = time.time()
        write_json(manifest_path, record)


def _evaluate_candidate(root, config, manifest, split, tasks, limit, prepare_only, saved):
    tasks = tasks or config["dataset"]["tasks"]
    if any(task not in config["dataset"]["tasks"] for task in tasks):
        raise ValueError("Task is not enabled in the experiment configuration")
    print(f"benchmark 候选={manifest['name']} 最新分数=待评测", flush=True)
    sandbox.STOPPING.clear()
    with Gateway(config["solver"], config["runtime"]["model_concurrency"]) as gateway:
        with ThreadPoolExecutor(max_workers=config["runtime"]["parallel_questions"]) as question_pool:
            with ThreadPoolExecutor(max_workers=len(tasks)) as task_pool:
                futures = {
                    task: task_pool.submit(
                        evaluate_task, root, manifest, task, split, gateway, question_pool,
                        limit, prepare_only, saved.get("scores", {}).get(task),
                    )
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
        score_value = row.get("accuracy")
        graded = f"{score_value:.2%}" if score_value is not None else "无"
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
        memory = memory_path(root, manifest, task)
        if not memory.exists():
            parser.error("no frozen memory for this tree and task; run prepare first")
        with Gateway(config["solver"], config["runtime"]["model_concurrency"]) as gateway:
            header, _ = solve_question(
                root, manifest, task, "val", 0, 0, memory, args.input_file.read_text(), gateway,
            )
            result = write_conversation(root, manifest, task, 0, 0, header)
    else:
        result = evaluate_candidate(
            root, config, candidate, args.split, args.tasks, args.limit, args.command == "prepare",
        )
    print(json.dumps(scores_output(result) if args.command == "evaluate" else result, ensure_ascii=False), flush=True)
    return 0 if result["status"] in {"ok", "prepared"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
