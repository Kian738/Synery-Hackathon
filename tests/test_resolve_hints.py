"""Rooms that share a name can be told apart in plain words, so the agent can ask one useful question."""
import pytest

from floorwise.core import resolve
from floorwise.core.model import Building
from floorwise.paths import DATA


def building():
    path = next(p for p in DATA.glob("*/osm-way37850565") if p.is_dir())
    return Building.load(path)


def test_nine_offices_with_one_name_each_get_a_different_hint():
    with pytest.raises(resolve.ResolveError) as raised:
        resolve.resolve_space(building(), "Büro (Floor 1)")
    hints = [c["hint"] for c in raised.value.candidates]
    assert len(hints) == 9 and all(hints) and len(set(hints)) == 9
    assert all(c["label"] == "Büro (Floor 1)" for c in raised.value.candidates)  # the label is unchanged; the hint is extra


def test_a_unique_name_is_resolved_without_any_question():
    b = building()
    unique = next(s for s in b.spaces.values() if sum(x["name"] == s["name"] and x["floor_id"] == s["floor_id"] for x in b.spaces.values()) == 1)
    assert resolve.resolve_space(b, f"{unique['name']} ({b.floor_name(unique['floor_id'])})").id == unique["id"]


def test_ask_choice_shows_two_to_four_options_and_refuses_a_free_text_question():
    from floorwise.agent.session import Session
    from floorwise.agent.tools import make_tools
    session = Session.for_building(building())
    ask = next(t for t in make_tools(session, allow_edits=False) if t.name == "ask_choice")
    ask.fn(question="Which Büro?", options=["next to Flur, with 4 desks", "top-right of the plan"])
    assert session.events[-1] == {"type": "choice", "question": "Which Büro?", "options": ["next to Flur, with 4 desks", "top-right of the plan"]}
    with pytest.raises(ValueError):
        ask.fn(question="Which?", options=["only one"])
    with pytest.raises(ValueError):
        ask.fn(question="Which?", options=["a", "b", "c", "d", "e"])
