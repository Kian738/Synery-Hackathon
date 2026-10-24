"""Release packaging must reject incomplete or contradictory outputs."""
import json
import csv

import pytest

from floorwise.submission import package_submission, validate_answers


def entry(qid="q1", answer="2"):
    return {"id": qid, "kind": "count", "answer": answer, "reply": f"Computed.\nAnswer: {answer}"}


@pytest.mark.parametrize("entries,ids", [
    ([entry()], ["q1", "q2"]),
    ([entry(), entry()], ["q1"]),
    ([entry()], ["q1", "q1"]),
    ([entry(answer="unknown")], ["q1"]),
    ([{**entry(), "reply": "Answer: 3"}], ["q1"]),
    ([{**entry(), "kind": None}], ["q1"]),
    ([{**entry(), "kind": "route", "reachable": True, "route": ["a", "b"]}], ["q1"]),
    ([{**entry(answer="no route"), "kind": "route"}], ["q1"]),
])
def test_reject_invalid_release(entries, ids):
    with pytest.raises(ValueError):
        validate_answers({"answers": entries}, ids)


def test_package_exact_files_and_legacy_consistency(tmp_path):
    building = tmp_path / "data" / "building"
    building.mkdir(parents=True)
    (building / "questions.jsonl").write_text(json.dumps({"id": "q1", "question": "Count rooms"}), encoding="utf8")
    candidate = tmp_path / "candidate.json"
    candidate.write_text(json.dumps({"answers": [entry()]}), encoding="utf8")
    (tmp_path / "BENCHMARK.md").write_text("Reproduce with fw bench", encoding="utf8")
    package_submission(tmp_path, tmp_path / "data", candidate)
    package = tmp_path / "SUBMISSION"
    assert {p.name for p in package.iterdir()} == {"BENCHMARK.md", "answers.json"}
    assert (package / "BENCHMARK.md").read_text() == "Reproduce with fw bench"
    with (tmp_path / "submissions" / "team_floorwise_test.csv").open(newline="", encoding="utf8") as handle:
        assert list(csv.DictReader(handle)) == [{"question_id": "q1", "answer": entry()["reply"]}]
    (package / "extra.txt").write_text("Keep this user file")
    with pytest.raises(ValueError, match="exactly"):
        package_submission(tmp_path, tmp_path / "data", candidate)
    assert (package / "extra.txt").read_text() == "Keep this user file"
