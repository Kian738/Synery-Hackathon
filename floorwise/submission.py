"""Validate the public-test output before publishing the organizer's two-file package."""

import csv
import json
from pathlib import Path

from floorwise.agent.answer import committed
from floorwise.cli import jobs_for


def validate_answers(data: dict, expected_ids: list[str]) -> list[dict]:
    entries = data.get("answers")
    if not isinstance(entries, list) or not entries:
        raise ValueError("Submission must contain a nonempty answers list")
    ids = [entry.get("id") for entry in entries]
    if len(set(expected_ids)) != len(expected_ids) or len(set(ids)) != len(ids):
        raise ValueError("Duplicate question IDs in questions or answers")
    if set(ids) != set(expected_ids):
        raise ValueError("Submission IDs do not exactly match the test questions")
    for entry in entries:
        answer, reply = entry.get("answer"), entry.get("reply")
        if (not isinstance(answer, str) or not answer.strip()
                or answer.strip().lower() in {"unknown", "none", "null"}
                or not isinstance(reply, str) or not reply.strip()
                or reply.startswith("Error:") or not entry.get("kind")):
            raise ValueError(f"Missing or unresolved answer: {entry.get('id')}")
        if committed(reply) != answer or not reply.rstrip().endswith("Answer: " + answer):
            raise ValueError(f"Answer/reply mismatch: {entry['id']}")
        if entry["kind"] in {"route", "tour"}:
            if entry.get("reachable") is True:
                route = entry.get("route")
                if not isinstance(route, list) or not route or answer != " -> ".join(route):
                    raise ValueError(f"Route/answer mismatch: {entry['id']}")
            elif entry.get("reachable") is not False or answer != "no route":
                raise ValueError(f"Invalid unreachable answer: {entry['id']}")
    return entries


def package_submission(root: Path, test_data: Path, candidate: Path) -> None:
    """Keep validation evidence outside SUBMISSION; retain the kit's legacy CSV too."""
    data = json.loads(candidate.read_text(encoding="utf-8"))
    expected = [q["id"] for _, q in jobs_for(test_data, None)]
    entries = validate_answers(data, expected)
    destination = root / "SUBMISSION"
    allowed = {"BENCHMARK.md", "answers.json"}
    if destination.exists() and any(p.name not in allowed or not p.is_file() for p in destination.iterdir()):
        raise ValueError("SUBMISSION must contain exactly BENCHMARK.md and answers.json; move extra files first")
    benchmark = (root / "BENCHMARK.md").read_text(encoding="utf-8")
    destination.mkdir(exist_ok=True)
    (destination / "answers.json").write_text(json.dumps(data, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    (destination / "BENCHMARK.md").write_text(benchmark, encoding="utf-8")
    legacy = root / "submissions" / "team_floorwise_test.csv"
    legacy.parent.mkdir(exist_ok=True)
    with legacy.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(("question_id", "answer"))
        writer.writerows((e["id"], e["reply"]) for e in entries)
    print(f"Validated {len(entries)}/{len(expected)} unique answers; SUBMISSION contains exactly the two required files.")
