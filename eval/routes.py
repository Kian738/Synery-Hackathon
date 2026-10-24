"""L0: the route model and simple operators against every warm-up answer (questions_basic.jsonl).

Uses the gold ids from the answers (warm-up lines carry no 'inputs'), so this tests the core only:
route lengths must match to the centimetre, locate/count exactly."""

import argparse
from functools import lru_cache

from eval.common import load_questions, source_of
from eval.ledger import Ledger
from floorwise.core.graph import Constraints
from floorwise.core.model import Building
from floorwise.core.routing import NoRoute, plan_route

TOLERANCE_M = 0.01


@lru_cache(maxsize=64)
def building_at(directory: str) -> Building:
    return Building.load(directory)


def check(building: Building, question: dict) -> tuple[bool, str]:
    kind, answer = question["kind"], question["answer"]
    if kind == "locate":
        asset = building.assets[answer["asset_id"]]
        return asset["space_id"] == answer["space_id"], ""
    if kind == "count":
        level = answer["floor_level"]
        count = sum(
            1 for asset in building.assets.values()
            if asset["type"] == answer["asset_type"] and building.level(asset["floor_id"]) == level
        )
        return count == answer["count"], f"got {count}"
    constraints = Constraints(
        step_free=kind == "route_step_free",
        closed=frozenset({answer["closed_element_id"]}) if answer.get("closed_element_id") else frozenset(),
    )
    if kind == "tour":
        stops = answer["stops"]
    else:
        stops = [answer["from_space_id"], answer["to_space_id"]] if "from_space_id" in answer else None
    if answer.get("reachable") is False:
        if stops is None:
            return True, "unreachable (no ids to check)"
        try:
            route = plan_route(building, stops, constraints)
            return False, f"found {route.length_m} but expected unreachable"
        except NoRoute:
            return True, ""
    try:
        route = plan_route(building, stops, constraints)
    except NoRoute as error:
        return False, str(error)
    return abs(route.length_m - answer["optimal_length_m"]) <= TOLERANCE_M, f"got {route.length_m} want {answer['optimal_length_m']}"


def main() -> None:
    parser = argparse.ArgumentParser(prog="eval.routes")
    parser.add_argument("--split", default="train,dev")
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args()
    ledger = Ledger("routes", {"splits": args.split})
    for directory, question in load_questions(args.split.split(","), "questions_basic.jsonl"):
        ok, note = check(building_at(str(directory)), question)
        ledger.record(id=question["id"], kind=question["kind"], source=source_of(question["building_id"]), correct=ok, note=note)
        if not ok and args.verbose:
            print("BAD", question["id"], question["kind"], note)
    ledger.finish()


if __name__ == "__main__":
    main()
