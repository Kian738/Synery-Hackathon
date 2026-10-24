#!/usr/bin/env python3
"""Universal CLI benchmark runner for indoor spatial reasoning evaluation.

Supports evaluating any unseen building directory or complete multi-building dataset
against questions in JSONL or CSV format, scoring with benchmark.score.score_reply,
and generating compliant submission CSV deliverables.

Usage:
    python benchmark_runner.py <building_dir_or_dataset> <questions_file> [--output <output_csv>]

Examples:
    # Evaluate dev dataset across all 138 questions with scoring:
    python benchmark_runner.py data/dev questions.jsonl

    # Evaluate single building:
    python benchmark_runner.py data/dev/proc-factory-dev-012 questions.jsonl

    # Run on test dataset and generate submission.csv:
    python benchmark_runner.py data/test data/test/questions.csv --output submission.csv
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
import time
from collections import Counter
from pathlib import Path
from typing import Any, Optional

from benchmark.score import score_reply
from spatial_engine.solver import answer


def load_benchmark_questions(
    target_path: Path, questions_spec: str
) -> list[tuple[Path, dict[str, Any]]]:
    """Load evaluation questions from JSONL or CSV across single or multiple buildings.

    Args:
        target_path: Building directory or root dataset split directory.
        questions_spec: File name (e.g. 'questions.jsonl') or path to questions file.

    Returns:
        List of (building_directory, question_dict) tuples.
    """
    questions: list[tuple[Path, dict[str, Any]]] = []

    # Case 1: questions_spec points directly to an existing file
    spec_path = Path(questions_spec)
    candidate_file = spec_path if spec_path.is_file() else (target_path / questions_spec)

    if candidate_file.is_file():
        if candidate_file.suffix.lower() == ".csv":
            with candidate_file.open("r", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    b_id = row.get("building_id", "")
                    bdir = target_path / b_id if (target_path / b_id).is_dir() else target_path
                    q_dict = {
                        "id": row.get("question_id", ""),
                        "building_id": b_id,
                        "kind": row.get("kind", ""),
                        "question": row.get("question", ""),
                    }
                    questions.append((bdir, q_dict))
            return questions

        elif candidate_file.suffix.lower() in (".jsonl", ".json"):
            bdir = target_path if (target_path / "building.json").is_file() else candidate_file.parent
            with candidate_file.open("r", encoding="utf-8") as f:
                for line in f:
                    if line.strip():
                        q = json.loads(line)
                        questions.append((bdir, q))
            return questions

    # Case 2: target_path is a dataset directory with building subdirectories
    pattern = f"*/{questions_spec}" if not questions_spec.startswith("*") else questions_spec
    for qpath in sorted(target_path.glob(pattern)):
        if qpath.is_file():
            bdir = qpath.parent
            with qpath.open("r", encoding="utf-8") as f:
                for line in f:
                    if line.strip():
                        q = json.loads(line)
                        questions.append((bdir, q))

    if not questions:
        # Check direct child
        direct_child = target_path / questions_spec
        if direct_child.is_file():
            with direct_child.open("r", encoding="utf-8") as f:
                for line in f:
                    if line.strip():
                        questions.append((target_path, json.loads(line)))

    return questions


def write_submission(output_path: Path, replies: list[tuple[str, str]]) -> None:
    """Write question replies to standardized two-column CSV for submission.

    Args:
        output_path: Target CSV file path.
        replies: List of (question_id, reply_text) tuples.
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["question_id", "answer"])
        for q_id, reply in replies:
            writer.writerow([q_id, reply])
    print(f"\n[benchmark_runner] Submission CSV written to: {output_path} ({len(replies)} rows)")


def print_scorecard(results: Counter[tuple[str, bool]], elapsed_sec: float) -> None:
    """Print structured scorecard showing accuracy breakdown across question kinds."""
    kinds = sorted({k for k, _ in results})
    total_correct = sum(c for (_, ok), c in results.items() if ok)
    total_count = sum(results.values())

    print("\n" + "=" * 70)
    print("             INDOOR SPATIAL BENCHMARK SCORECARD")
    print("=" * 70)
    print(f"{'Question Kind':<28} | {'Correct':<8} | {'Total':<6} | {'Accuracy':<8}")
    print("-" * 70)

    for kind in kinds:
        c = results[(kind, True)]
        w = results[(kind, False)]
        t = c + w
        acc = (c / t * 100.0) if t > 0 else 0.0
        print(f"{kind:<28} | {c:<8d} | {t:<6d} | {acc:6.1f}%")

    print("-" * 70)
    tot_acc = (total_correct / total_count * 100.0) if total_count > 0 else 0.0
    print(f"{'OVERALL (ALL KINDS)':<28} | {total_correct:<8d} | {total_count:<6d} | {tot_acc:6.1f}%")
    print("=" * 70)
    print(f"Total Questions Evaluated: {total_count}")
    print(f"Total Correct Answers    : {total_correct}")
    print(f"Execution Duration       : {elapsed_sec:.2f} seconds")
    print("=" * 70 + "\n")


def run_benchmark(
    target_path: Path,
    questions_file: str,
    output_csv: Optional[Path] = None,
    kinds: Optional[list[str]] = None,
    verbose: bool = False,
) -> int:
    """Execute benchmark evaluation across loaded questions.

    Args:
        target_path: Path to building or dataset directory.
        questions_file: Questions file name or path.
        output_csv: Optional path to save submission CSV.
        kinds: Optional list of question kinds to evaluate.
        verbose: If True, print detailed per-question output.

    Returns:
        0 if all scored questions passed (or evaluation succeeded), 1 otherwise.
    """
    questions = load_benchmark_questions(target_path, questions_file)
    if not questions:
        print(f"[benchmark_runner] ERROR: No questions found matching '{questions_file}' in '{target_path}'")
        return 1

    if kinds:
        questions = [item for item in questions if item[1].get("kind") in kinds]

    print(f"[benchmark_runner] Loaded {len(questions)} questions from {target_path}")

    results: Counter[tuple[str, bool]] = Counter()
    replies: list[tuple[str, str]] = []

    t0 = time.perf_counter()

    for idx, (bdir, q) in enumerate(questions, start=1):
        q_id = q.get("id") or q.get("question_id") or f"q_{idx}"
        q_text = q.get("question", "")
        ground_truth = q.get("answer")

        try:
            reply = answer(bdir, q_text)
        except Exception as err:
            print(f"[benchmark_runner] ERROR solving {q_id}: {err}")
            reply = f"Error: {err}"

        replies.append((q_id, reply))

        if ground_truth is not None:
            is_correct = score_reply(ground_truth, reply)
            kind = q.get("kind") or "unknown"
            results[(kind, is_correct)] += 1

            if verbose or not is_correct:
                status = "PASS" if is_correct else "FAIL"
                print(f"[{status}] {q_id:<28} {kind:<20} -> {reply}")
                if not is_correct:
                    print(f"       Expected: {ground_truth}")
        else:
            if verbose:
                print(f"[DONE] {q_id:<28} -> {reply}")

    elapsed = time.perf_counter() - t0

    if results:
        print_scorecard(results, elapsed)

    if output_csv is not None:
        write_submission(output_csv, replies)

    # If ground truth was present, return 0 only if 100% correct
    if results:
        wrong_count = sum(c for (_, ok), c in results.items() if not ok)
        return 0 if wrong_count == 0 else 1

    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="benchmark_runner",
        description="Universal CLI runner for Indoor Spatial Reasoning Benchmark",
    )
    parser.add_argument(
        "target_path",
        type=Path,
        help="Path to building directory (e.g. data/dev/proc-factory-dev-012) or dataset directory (e.g. data/dev)",
    )
    parser.add_argument(
        "questions_file",
        type=str,
        help="Questions file name (e.g. 'questions.jsonl') or full file path (e.g. 'data/test/questions.csv')",
    )
    parser.add_argument(
        "--output",
        "-o",
        type=Path,
        default=None,
        help="Path to save output submission CSV (e.g. submission.csv)",
    )
    parser.add_argument(
        "--kinds",
        nargs="+",
        default=None,
        help="Filter to specific question kinds",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Enable detailed per-question output",
    )
    args = parser.parse_args()

    return run_benchmark(
        target_path=args.target_path,
        questions_file=args.questions_file,
        output_csv=args.output,
        kinds=args.kinds,
        verbose=args.verbose,
    )


if __name__ == "__main__":
    sys.exit(main())
