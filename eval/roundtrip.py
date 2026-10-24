"""L3f: question-text round trip for the nine benchmark kinds, on EVERY building.

The Sunday building is unseen and its rooms may have names we have never parsed ("Büro", "Living room 3.25 (apartment 19)",
"Generic room N2146"). This suite takes the sentence frames of the train and dev benchmark questions (the mentions are cut out
using the gold inputs), fills them with entities of any other building (train, dev and test, 280 buildings), and checks that
the free rule parser plus the resolver recover exactly the entities that were put in. No answer is needed: the intended ids
are known by construction, so a miss is a parsing or linking bug, never a geometry question. Mentions whose label is not
unique in the building are not used (those are the diagnosed ambiguous names).

  uv run python -m eval.roundtrip --split dev --per-building 6
  uv run python -m eval.roundtrip --split train,dev,test --per-building 4     # every supplied building"""

import argparse
import random
import re

from eval.common import SPLITS, load_questions, source_of
from eval.ledger import Ledger
from floorwise.agent.parse_rules import parse_rules
from floorwise.agent.spec import resolve_spec_all
from floorwise.core.model import Building
from floorwise.paths import DATA

SPACE_SLOTS = ("start", "first", "second")


def floor_phrase(building: Building, floor_id: str) -> str:
    level = building.level(floor_id)
    return "the ground floor" if level == 0 else f"the basement {abs(level)}" if level < 0 else f"the floor {level}"


def harvest() -> list[dict]:
    """Sentence frames with {slots}, one per distinct frame text, taken from train and dev questions."""
    frames: dict[str, dict] = {}
    cache: dict[str, Building] = {}
    for directory, question in load_questions(["train", "dev"]):
        inputs = question.get("inputs")
        if not inputs or "question" not in question:
            continue
        building = cache.setdefault(str(directory), Building.load(directory))
        text, slots = question["question"], {}
        for slot in SPACE_SLOTS:
            if slot in inputs and building.label(inputs[slot]) in text:
                text = text.replace(building.label(inputs[slot]), "{" + slot + "}")
                slots[slot] = "space"
        if "floor_id" in inputs:
            match = re.search(r"the (?:ground floor|floor -?\d+|basement \d+)", text)
            if match:
                text = text.replace(match.group(0), "{floor}", 1)
                slots["floor"] = "floor"
        if "asset_type" in inputs:
            match = re.search(rf"\b{re.escape(inputs['asset_type'].replace('_', ' '))}s?\b", text)
            if match:
                text = text.replace(match.group(0), "{asset_type}", 1)
                slots["asset_type"] = "asset"
        if "room_type" in inputs:
            words = inputs["room_type"].replace("_", " ")
            match = re.search(rf"\b{re.escape(words)}s?\b", text)
            if match:
                text = text.replace(match.group(0), "{room_type}", 1)
                slots["room_type"] = "type"
        if "min_width" in inputs:
            width = f"{float(inputs['min_width']):.1f}"
            text = text.replace(width, "{width}")
            slots["width"] = "width"
        if "closed" in inputs:
            closed = cache[str(directory)].connectors.get(inputs["closed"], {}).get("name")
            if closed and closed in text:
                text = text.replace(closed, "{closed}")
                slots["closed"] = "connector"
        if "{" in text:
            frames.setdefault(text, {"kind": question["kind"], "text": text, "slots": slots})
    return list(frames.values())


def fill(frame: dict, building: Building, rng: random.Random) -> tuple[str, dict] | None:
    unique: dict[str, list[str]] = {}
    for sid in building.spaces:
        unique.setdefault(building.label(sid), []).append(sid)
    spaces = sorted(ids[0] for ids in unique.values() if len(ids) == 1 and building.spaces[ids[0]]["type"] in ("room", "hall"))
    floors = sorted(building.floors)
    types = sorted({s["room_type"] for s in building.spaces.values() if s["type"] in ("room", "hall")})
    asset_types = sorted({a["type"] for a in building.assets.values()})
    names: dict[str, list[str]] = {}
    for cid, connector in building.connectors.items():
        names.setdefault(connector["name"], []).append(cid)
    connectors = sorted(ids[0] for ids in names.values() if len(ids) == 1)
    slots, intended, text = frame["slots"], {}, frame["text"]
    for slot in [s for s in slots if slots[s] == "space"]:
        if len(spaces) < 3:
            return None
        sid = rng.choice([s for s in spaces if s not in intended.values()])
        intended[slot] = sid
        text = text.replace("{" + slot + "}", building.label(sid))
    if "floor" in slots:
        floor_id = rng.choice(floors)
        intended["floor_id"] = floor_id
        text = text.replace("{floor}", floor_phrase(building, floor_id))
    if "room_type" in slots:
        if not types:
            return None
        intended["room_type"] = rng.choice(types)
        text = text.replace("{room_type}", intended["room_type"].replace("_", " "))
    if "asset_type" in slots:
        if not asset_types:
            return None
        intended["asset_type"] = rng.choice(asset_types)
        text = text.replace("{asset_type}", intended["asset_type"].replace("_", " "))
    if "width" in slots:
        intended["min_width"] = rng.choice([0.9, 1.0, 1.1, 1.2, 1.6])
        text = text.replace("{width}", f"{intended['min_width']:.1f}")
    if "closed" in slots:
        if not connectors:
            return None
        intended["closed"] = rng.choice(connectors)
        text = text.replace("{closed}", building.connectors[intended["closed"]]["name"])
    return text, intended


def main() -> None:
    cli = argparse.ArgumentParser(prog="eval.roundtrip")
    cli.add_argument("--split", default="dev")
    cli.add_argument("--per-building", type=int, default=6)
    cli.add_argument("--seed", type=int, default=5)
    cli.add_argument("--limit", type=int, default=None)
    args = cli.parse_args()
    frames = harvest()
    ledger = Ledger("roundtrip", {"splits": args.split, "per_building": args.per_building, "seed": args.seed, "frames": len(frames)})
    paths = sorted(p for s in args.split.split(",") if s in SPLITS for p in (DATA / s).glob("*/building.json"))[: args.limit]
    for path in paths:
        building = Building.load(path.parent)
        rng = random.Random(f"{args.seed}:{building.id}")
        for index in range(args.per_building):
            frame = rng.choice(frames)
            made = fill(frame, building, rng)
            if made is None:
                continue
            text, intended = made
            spec = parse_rules(text)
            problem = ""
            readings = []
            if spec is None:
                problem = "the rule parser did not recognise the question"
            elif spec.kind != frame["kind"]:
                problem = f"parsed as {spec.kind}"
            else:
                try:
                    readings = resolve_spec_all(building, spec)
                except Exception as error:  # noqa: BLE001
                    problem = f"{type(error).__name__}: {error}"
            if not problem:
                got = readings[0] if len(readings) == 1 else {}
                wrong = {k: (got.get(k), v) for k, v in intended.items() if got.get(k) != v}
                problem = "" if not wrong and len(readings) == 1 else f"{len(readings)} readings; differing: {wrong}"
            ledger.record(id=f"{building.id}:{index}", kind=frame["kind"], source=source_of(building.id), building=building.id,
                          correct=not problem, problem=problem, question=text[:300])
    ledger.finish()


if __name__ == "__main__":
    main()
