"""run_benchmark: one command from (building, questions) to answers, no manual steps.

  uv run run_benchmark <building_dir> <questions.json|jsonl|csv> <answers.json|answers.csv>
  uv run run_benchmark <split_dir>                              <answers.csv>   # every building's questions.jsonl

Questions may be a JSON list, {"questions": [...]}, JSON lines or CSV. Each entry needs an id and a text
(keys tried: id/question_id, question/text). Optional "constraints" ({"step_free": true, "closed": [...]})
are applied on top of what the text says. The output format follows the file extension: .csv gives
question_id,answer (the kit's submission format); .json gives one structured entry per question with the
full reply, the committed answer, the located item/room ids, the route as ordered node ids and its length."""

import argparse
import csv
import json
import sys
import time
from pathlib import Path

from floorwise.agent.answer import answer_with_trace, committed


def read_questions(path: Path) -> list[dict]:
    text = path.read_text(encoding="utf-8-sig")
    if path.suffix.lower() == ".csv":
        rows = list(csv.DictReader(text.splitlines()))
    elif path.suffix.lower() == ".jsonl":
        rows = [json.loads(line) for line in text.splitlines() if line.strip()]
    else:
        data = json.loads(text)
        rows = data.get("questions", data) if isinstance(data, dict) else data
    questions = []
    for row in rows:
        qid = row.get("id") or row.get("question_id")
        question = row.get("question") or row.get("text") or row.get("prompt")
        if not qid or not question:
            raise ValueError(f"question without id or text: {row}")
        questions.append({**row, "id": qid, "question": question})
    return questions


def structured(qid: str, reply: str, trace: dict) -> dict:
    result = trace.get("result") or {}
    kind = trace.get("kind")
    entry = {"id": qid, "kind": kind, "answer": committed(reply), "reply": reply}
    if kind in ("route", "tour"):
        entry["reachable"] = result.get("reachable", False)
        if result.get("reachable"):
            entry["length_m"] = result["length_m"]
            entry["route"] = result["space_path"]
            entry["route_elements"] = [e for leg in result["legs"] for e in leg["element_path"]]
            entry["legs"] = result["legs"]
    elif kind == "locate":
        entry["item_id"] = (result.get("asset_ids") or [None])[0]
        entry["item_ids"] = result.get("asset_ids", [])
        entry["room_id"] = result["matches"][0]["space_id"] if result.get("matches") else None
    elif kind in ("largest_room", "room_stacked"):
        entry["room_id"] = result.get("space_id")
        if "area_m2" in result:
            entry["value"] = result["area_m2"]
    elif kind == "errand":
        entry["length_m"] = result.get("total_m")
        entry["room_ids"] = [result.get("pickup_space_id"), result.get("target_space_id")]
    else:
        for key in ("count", "total_m2", "distance_m"):
            if key in result:
                entry["value"] = result[key]
    if trace.get("fallback"):
        entry["fallback"] = trace["fallback"]
    return entry


def jobs_for(source: Path, questions_file: Path | None) -> list[tuple[Path, dict]]:
    if questions_file is not None:
        return [(source, q) for q in read_questions(questions_file)]
    jobs = []
    for path in sorted(source.glob("*/questions.jsonl")) or sorted(source.glob("questions.jsonl")):
        jobs += [(path.parent, q) for q in read_questions(path)]
    return jobs


def main() -> None:
    parser = argparse.ArgumentParser(prog="run_benchmark", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("source", type=Path, help="building directory, or a split directory with one folder per building")
    parser.add_argument("paths", type=Path, nargs="+", help="[questions file] answers file (.csv or .json)")
    args = parser.parse_args()
    questions_file, output = (args.paths[0], args.paths[1]) if len(args.paths) == 2 else (None, args.paths[0])
    jobs = jobs_for(args.source, questions_file)
    if not jobs:
        sys.exit(f"no questions found for {args.source}")
    entries, started = [], time.time()
    for index, (building_dir, question) in enumerate(jobs, 1):
        constraints = question.get("constraints")
        if isinstance(constraints, str):
            constraints = json.loads(constraints) if constraints.strip().startswith("{") else None
        try:
            reply, trace = answer_with_trace(building_dir, question["question"], constraints)
        except Exception as error:  # noqa: BLE001 - one bad question must not stop the run
            reply, trace = f"Error: {error}\nAnswer: unknown", {"fallback": str(error)}
        entries.append(structured(question["id"], reply, trace))
        print(f"[{index}/{len(jobs)}] {question['id']}: {committed(reply)}", flush=True)
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.suffix.lower() == ".csv":
        with output.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.writer(handle)
            writer.writerow(("question_id", "answer"))
            writer.writerows((e["id"], e["reply"]) for e in entries)
    else:
        output.write_text(json.dumps({"answers": entries}, indent=1, ensure_ascii=False), encoding="utf-8")
    fallbacks = sum(1 for e in entries if e.get("fallback"))
    print(f"{len(entries)} answers -> {output} in {time.time() - started:.1f}s ({fallbacks} via fallback)")


if __name__ == "__main__":
    main()
