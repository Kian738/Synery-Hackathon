"""Risk check on the unseen split: the test questions have no gold, so look for the ways an answer could still be wrong.

Per test question, with no model call:
  parsed       the rules parse it (no LLM guess)
  one reading  the names resolve to exactly one meaning (an ambiguous name is scored against one of several readings)
  no near-tie  errand only: the nearest pickup beats the runner-up by more than 2%, so a tiny route-length difference
               cannot flip the committed room (the organisers score the route against best/yours with a 1% margin)
  known kind   the question kind exists in train/dev, where our answers are checked against gold
A pass is not a correctness proof; it removes the identified ways the unseen split could differ from train/dev.
Evidence chain: kit README (scoring, test has no gold) -> measured on test: 145/145 parsed, 0 ambiguous, 0 near-ties,
0 new kinds -> rule: this gate fails if a future parser or route-model change introduces any of them."""

import csv
import json

from eval.ledger import Ledger
from floorwise.agent.answer import load_building, parse
from floorwise.agent.spec import resolve_spec_all
from floorwise.core.graph import Constraints, RouteGraph
from floorwise.paths import DATA

NEAR_TIE = 0.02


def known_kinds() -> set[str]:
    kinds = set()
    for split in ("train", "dev"):
        for path in (DATA / split).glob("*/questions.jsonl"):
            kinds |= {json.loads(line)["kind"] for line in path.read_text(encoding="utf-8").splitlines() if line.strip()}
    return kinds


def check(row: dict, kinds: set[str]) -> tuple[bool, str]:
    if row["kind"] not in kinds:
        return False, "kind never seen in train/dev"
    building = load_building(str(DATA / "test" / row["building_id"]))
    spec, how = parse(building, row["question"])
    if spec is None:
        return False, "not parsed by rules"
    readings = resolve_spec_all(building, spec)
    if len(readings) != 1:
        return False, f"{len(readings)} readings"
    if row["kind"] == "errand":
        reading = readings[0]
        distance = RouteGraph(building, Constraints()).distances_from(reading["start"])
        holders = {a["space_id"] for a in building.assets.values() if a["type"] == reading["asset_type"]}
        ranked = sorted(distance[s] for s in holders if s in distance)
        if len(ranked) > 1 and (ranked[1] - ranked[0]) / max(ranked[0], 1e-9) < NEAR_TIE:
            return False, f"near-tie: best two pickups {ranked[0]:.2f} m and {ranked[1]:.2f} m"
    return True, ""


def main() -> None:
    kinds = known_kinds()
    rows = list(csv.DictReader((DATA / "test" / "questions.csv").open(encoding="utf-8-sig")))
    ledger = Ledger("unseen", {"split": "test"})
    for row in rows:
        try:
            ok, note = check(row, kinds)
        except Exception as error:  # noqa: BLE001  a crash is a failed check, reported with its type
            ok, note = False, f"{type(error).__name__}: {error}"[:160]
        ledger.record(id=row["question_id"], kind=row["kind"], source=row["building_id"].split("-")[0], correct=ok, note=note)
    summary = ledger.finish()
    if summary["correct"] != summary["total"]:
        raise SystemExit("unseen-split risk check found questions that could differ from train/dev")


if __name__ == "__main__":
    main()
