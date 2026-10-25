"""Plugs the exact evacuation solver (floorwise.evacuation) into the engine's evacuation operators.

Importing this module replaces the placeholders, so a plan such as the evacuation template runs end to end:
hazard -> people -> exact evacuation -> bottleneck -> responder route -> door fix, each step checked."""

from dataclasses import replace

from floorwise import evacuation as ev
from floorwise.reason import occupants as occupancy
from floorwise.reason.operators import REGISTRY
from floorwise.reason.types import Abstain, ScenarioSpec, World


# Assumption, not a measurement: people already inside the hazard space get this long to leave, then it is closed.
# Without it a fire at t=0 would count its own occupants as trapped, which is not what the scenario asks.
DEFAULT_ESCAPE_S = 30.0
# Interactive answers must arrive in seconds on any building size: each search checks its likeliest candidates first and stops
# after this compute time (at least one candidate is always checked). The result says when a search was cut short.
RESPONDER_BUDGET_S = 6.0
DOOR_BUDGET_S = 10.0


def _hazards(world: World, spec: ScenarioSpec) -> list[ev.Hazard]:
    """The scenario's hazards with their start times, plus anything already closed in this world."""
    found = [ev.Hazard(spaces=h.spaces, elements=h.elements, from_s=h.start_s or 0.0,
                       escape_s=DEFAULT_ESCAPE_S if h.escape_s is None else h.escape_s) for h in spec.hazards]
    named = {i for h in spec.hazards for i in (*h.spaces, *h.elements)}  # already carried, with their own escape window
    spaces = tuple(sorted(i for i in world.closed if i in world.building.spaces and i not in named))
    elements = tuple(sorted(i for i in world.closed if i not in world.building.spaces and i not in named))
    return found + ([ev.Hazard(spaces=spaces, elements=elements)] if spaces or elements else [])


def _occupants(occupants) -> ev.Occupants:
    return ev.Occupants.explicit(dict(occupants.by_space), label=f"{occupants.source} estimate")


def _capacities(spec: ScenarioSpec) -> list[ev.Capacity]:
    return [ev.Capacity(c.element, c.kind, c.value) for c in spec.capacities]


def _evacuate(world, occupants, spec):
    if not occupants.total:
        raise Abstain("no occupants: the building has no seat-type assets and none were given")
    return ev.evacuate(world.building, _occupants(occupants), _hazards(world, spec), _capacities(spec))


def _bottleneck(world, evacuation):
    return evacuation.bottleneck


def _responder_route(world, spec, evacuation):
    wanted = spec.responders
    target = (wanted.target if wanted and wanted.target else None) or next(
        (s for h in spec.hazards for s in h.spaces), None)
    if target is None:
        raise Abstain("responders need a target space, and the scenario names no hazard space")
    entrances = None if not wanted or wanted.auto else wanted.entrances
    plan = ev.with_responders(world.building, _people(world, spec),
                              _hazards(world, spec), _capacities(spec), responders=ev.Responders(target, entrances, budget_s=RESPONDER_BUDGET_S))
    if plan.status == "no_route":
        raise Abstain("no responder route reaches the target from a usable entrance")
    return plan


def _people(world: World, spec: ScenarioSpec) -> ev.Occupants:
    return _occupants(occupancy.build(world.building, spec.occupants))


def _door_candidates(world, evacuation, bottleneck):
    return evacuation  # candidates are generated and pruned against the min cut inside best_door


def _best_door(world, candidates, spec, evacuation):
    occupants = _people(world, spec)
    plan = ev.best_doors(world.building, occupants, _hazards(world, spec), _capacities(spec), budget_s=DOOR_BUDGET_S)
    if not plan.fixes:
        raise Abstain("no door or widening shortens the evacuation")
    return plan


for name, function in {"evacuate": _evacuate, "bottleneck": _bottleneck, "responder_route": _responder_route,
                       "door_candidates": _door_candidates, "best_door": _best_door}.items():
    REGISTRY.register(replace(REGISTRY.get(name), fn=function, doc=""), replace=True)
