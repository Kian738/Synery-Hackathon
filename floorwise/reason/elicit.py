"""Ask only what is needed. `missing` ranks every gap in a scenario by how much the answer depends on it;
`next_question` returns the one essential gap as a question with 2-4 options, or None.

A field that has a safe default is never essential: it is listed with its default marked as an assumption, so the
agent can state it instead of asking. A field without a safe default (where the hazard is) is essential."""

from dataclasses import dataclass

from floorwise.core.model import Building
from floorwise.reason import occupants
from floorwise.reason.types import ScenarioSpec


@dataclass(frozen=True)
class Option:
    value: str
    label: str
    assumption: bool = False  # the default the agent will use if the person does not choose


@dataclass(frozen=True)
class Question:
    field: str
    text: str
    options: tuple[Option, ...]
    importance: float  # 0..1: how strongly the answer depends on this field
    essential: bool  # no safe default exists


def _option(value: str, label: str, assumption: bool = False) -> Option:
    return Option(value, f"{label} (assumption)" if assumption else label, assumption)


HAZARDS = Question("hazards", "What is blocked or unsafe?", (
    _option("spaces", "One room or space"),
    _option("elements", "A door, stair or lift"),
    _option("floor", "A whole floor"),
), 1.0, True)

OBJECTIVE = Question("objective", "What should the plan optimise?", (
    _option("min_evacuation_time", "Everyone out as early as possible", assumption=True),
    _option("min_total_person_time", "The least total time spent inside, summed over everyone"),
), 0.3, False)

CAPACITIES = Question("capacities", "How many people can each door pass?", (
    _option("derive_from_width", "Work it out from each door's width", assumption=True),
    _option("rate_persons_per_s", "I give a rate in people per second"),
    _option("total_persons", "I give a maximum number of people"),
), 0.2, False)


def _occupants_question(has_seats: bool) -> Question:
    options = [_option("user", "I give the number of people per room"), _option("uniform", "The same number of people in every room")]
    if has_seats:
        return Question("occupants", "How many people are in the building?",
                        (_option("seats", "Estimate one person per seat", assumption=True), *options), 0.5, False)
    return Question("occupants", "How many people are in the building? This building lists no seats to estimate from.",
                    tuple(options), 0.9, True)


def missing(spec: ScenarioSpec, building: Building | None = None) -> list[Question]:
    """Gaps ranked by importance, most important first. Without a building, seat data is assumed to exist."""
    gaps = []
    if not spec.hazards:
        gaps.append(HAZARDS)
    given = spec.occupants
    seats = building is None or occupants.has_seat_data(building)
    if given is None or (not given.overrides and (given.source == "user" or (given.source == "seats" and not seats))):
        gaps.append(_occupants_question(seats))
    if spec.objective is None:
        gaps.append(OBJECTIVE)
    if not spec.capacities:
        gaps.append(CAPACITIES)
    return sorted(gaps, key=lambda gap: -gap.importance)


def next_question(spec: ScenarioSpec, building: Building | None = None) -> Question | None:
    return next((gap for gap in missing(spec, building) if gap.essential), None)
