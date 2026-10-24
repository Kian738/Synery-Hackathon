"""Command-line benchmark runner and query interface for Talk to Your Building."""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

from agent import solve_question


def main() -> None:
    """CLI entrypoint for executing spatial queries and benchmark evaluations."""
    parser = argparse.ArgumentParser(
        prog="talk_to_your_building",
        description="Autonomous indoor spatial reasoning agent and benchmark solver.",
    )
    parser.add_argument(
        "--building-dir",
        type=Path,
        default=None,
        help="Path to building directory containing building.json",
    )
    parser.add_argument(
        "--question",
        type=str,
        default=None,
        help="Single question string to evaluate",
    )
    parser.add_argument(
        "--question-file",
        type=Path,
        default=None,
        help="Path to questions file (.jsonl or .csv)",
    )
    parser.add_argument(
        "--submission-csv",
        type=Path,
        default=None,
        help="Output path for submission CSV (question_id,answer)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Output path to save JSON results log",
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Enable verbose output",
    )

    args = parser.parse_args()

    # Case 1: Single question query
    if args.question:
        if not args.building_dir:
            print("Error: --building-dir is required when --question is specified", file=sys.stderr)
            sys.exit(1)
        if not args.building_dir.exists():
            print(f"Error: Building directory not found: {args.building_dir}", file=sys.stderr)
            sys.exit(1)

        reply = solve_question(args.building_dir, args.question)
        print(reply)
        return

    # Case 2: Batch evaluation from question file
    if args.question_file:
        if not args.question_file.exists():
            print(f"Error: Question file not found: {args.question_file}", file=sys.stderr)
            sys.exit(1)

        questions: list[dict] = []
        # Check if CSV or JSONL
        if args.question_file.suffix.lower() == ".csv":
            with open(args.question_file, mode="r", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    questions.append(row)
        else:
            with open(args.question_file, mode="r", encoding="utf-8") as f:
                for line in f:
                    if line.strip():
                        questions.append(json.loads(line))

        if args.verbose:
            print(f"Loaded {len(questions)} questions from {args.question_file}")

        replies: list[tuple[str, str]] = []
        log_entries: list[dict] = []

        base_search_dir = args.question_file.parent
        for q in questions:
            qid = q.get("id") or q.get("question_id", "unknown")
            q_text = q.get("question", "")
            building_id = q.get("building_id")

            # Determine building directory
            if args.building_dir:
                b_dir = args.building_dir
            elif building_id:
                # Look in same folder or parent folder
                candidates = [
                    base_search_dir / building_id,
                    base_search_dir.parent / building_id,
                    base_search_dir / "data" / "dev" / building_id,
                    base_search_dir / "data" / "test" / building_id,
                    Path.cwd() / "data" / "dev" / building_id,
                    Path.cwd() / "data" / "test" / building_id,
                ]
                b_dir = next((c for c in candidates if (c / "building.json").exists()), None)
                if not b_dir:
                    print(f"Warning: Building directory for '{building_id}' not found", file=sys.stderr)
                    b_dir = base_search_dir
            else:
                b_dir = base_search_dir

            reply = solve_question(b_dir, q_text)
            replies.append((qid, reply))
            log_entries.append({"question_id": qid, "question": q_text, "reply": reply})

            if args.verbose:
                print(f"[{qid}] -> {reply}")

        # Write submission CSV if requested
        if args.submission_csv:
            args.submission_csv.parent.mkdir(parents=True, exist_ok=True)
            with open(args.submission_csv, mode="w", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                writer.writerow(["question_id", "answer"])
                writer.writerows(replies)
            print(f"Saved submission CSV with {len(replies)} rows to {args.submission_csv}")

        # Write output log if requested
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            with open(args.output, mode="w", encoding="utf-8") as f:
                json.dump(log_entries, f, indent=2, ensure_ascii=False)
            print(f"Saved results log to {args.output}")

        if not args.submission_csv and not args.output:
            for qid, reply in replies:
                print(f"{qid}: {reply}")
        return

    parser.print_help()


if __name__ == "__main__":
    main()
