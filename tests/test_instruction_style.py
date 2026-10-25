"""Directions read clearly: short sentences, no repeated names inside a step, every step has an icon and a distance."""
import re

import pytest

from floorwise.core.graph import Constraints
from floorwise.core.model import Building
from floorwise.core.routing import NoRoute, plan_route
from floorwise.paths import DATA

BUILDINGS = [("test", "proc-campus-test-013"), ("dev", "proc-factory-dev-003"), ("dev", "proc-campus-dev-000")]
MAX_WORDS_PER_SENTENCE = 24


def routes():
    for split, name in BUILDINGS:
        building = Building.load(DATA / split / name)
        rooms = [s for s, v in building.spaces.items() if v["type"] == "room"]
        for i in range(0, min(len(rooms) - 1, 24), 3):
            try:
                yield building, plan_route(building, [rooms[i], rooms[-1 - i]], Constraints(), humane=True)
            except NoRoute:
                continue


def test_steps_are_short_unrepeated_and_complete():
    seen = 0
    for building, route in routes():
        for step in route.guide["steps"]:
            seen += 1
            assert step["icon"] and step["text"][0].isupper() and step["text"].rstrip().endswith((".", ")"))
            assert step["metres"] >= 0
            for sentence in re.split(r"(?<=[.!?])\s+", step["text"]):
                assert len(sentence.split()) <= MAX_WORDS_PER_SENTENCE, sentence
            sentences = [x.strip().lower() for x in re.split(r"(?<=[.!?])\s+", step["text"]) if x.strip()]
            assert len(sentences) == len(set(sentences)), step["text"]
            if step["kind"] == "floor":
                name = step["short"].split(" up ")[0].split(" down ")[0]
                assert step["text"].count(name) <= 1, step["text"]
        assert route.guide["spoken"]
    assert seen > 30


def test_the_benchmark_answer_line_does_not_depend_on_step_wording():
    from floorwise.agent.answer import answer

    building = Building.load(DATA / "dev" / "proc-factory-dev-003")
    rooms = [s for s, v in building.spaces.items() if v["type"] == "room"]
    reply = answer(DATA / "dev" / "proc-factory-dev-003", f"How do I get from {building.label(rooms[0])} to {building.label(rooms[5])}?")
    assert "Answer:" in str(reply)
