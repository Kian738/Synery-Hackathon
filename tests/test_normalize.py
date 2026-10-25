"""Chatter, dictation and typos are cleaned only when the exact wording does not parse; names are never edited."""
import pytest

from floorwise.agent.normalize import clean_question, has_chatter
from floorwise.agent.parse_rules import parse_rules

ROUTE = "How do I get from Office 2.21 (Floor 2) to Meeting room 0.45 (Ground floor)?"


@pytest.mark.parametrize("wrapped", [
    f"Hi, could you help me? {ROUTE} Thank you!",
    f"um so {ROUTE[0].lower() + ROUTE[1:]}",
    f"Kurze Frage: {ROUTE}",
    f"Please {ROUTE[0].lower() + ROUTE[1:]} Thanks!",
])
def test_chatter_is_stripped_and_the_question_parses_to_the_same_route(wrapped):
    assert has_chatter(wrapped)
    spec = parse_rules(clean_question(wrapped))
    assert spec.kind == "route" and spec.start == "Office 2.21 (Floor 2)" and spec.destination == "Meeting room 0.45 (Ground floor)"


def test_dataset_wording_is_untouched():
    assert not has_chatter(ROUTE)
    assert parse_rules(ROUTE).start == "Office 2.21 (Floor 2)"


def test_dictated_question_gets_its_floors_and_sentence_break_back():
    said = "stairs is closed for maintenance how do i get from generic room 101 floor 1 to generic room k20 basement 2"
    spec = parse_rules(clean_question(said))
    assert spec.closed == "Stairs" and spec.start == "generic room 101 (floor 1)" and spec.destination == "generic room k20 (basement 2)"
    tour = parse_rules(clean_question("starting at office 302 floor 3 visit office 019 ground floor then toilet 326 floor 3 in this order what is the route"))
    assert tour.kind == "tour" and len(tour.stops) == 3


def test_count_question_keeps_its_floor_outside_brackets():
    assert "(" not in clean_question("how many fire extinguisher items are on the ground floor")


def test_function_word_typos_are_fixed_but_names_are_not():
    assert clean_question("Where is teh shower?") == "Where is the shower?"
    assert "Form 12" in clean_question("How do I get from Form 12 (Floor 1) to Lab (Floor 2)?")
