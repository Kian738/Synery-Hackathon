"""Routes between buildings: indoor leg in A, outdoor leg between two entrances, indoor leg in B.

Every entrance of both buildings is a candidate. Indoor costs come from one Dijkstra per building (the judges'
route model, under the person's constraints: step-free, door width, closures), so a door the person cannot pass is
never offered. Outdoor cost is a pluggable provider (routing services on the server); without one, a straight
line times a per-mode detour is used and the result says so. The three costs, as door-to-door time, are minimised
together, not exit by exit.

Local metres to WGS84: each building's local frame is centred on its bounding box, so the anchor (lat, lon) is
the bbox centre, x points east and y north (checked against the OSM outlines of the dataset's OSM buildings).
Equirectangular, which is within centimetres of any projection at campus scale. The anchor is the weak point: a few
metres typically, tens of metres for large buildings. This module has no building-specific data: anchors are passed in."""

import math
import re
from collections.abc import Callable
from dataclasses import asdict, dataclass, field

from floorwise.core.graph import DOOR_PREFIX, Constraints, RouteGraph
from floorwise.core.model import OUTSIDE, Building
from floorwise.core.routing import NoRoute, Route, plan_route

METRES_PER_DEG_LAT = 111320.0
WALK_SPEED_M_S = 1.3  # indoors, always on foot
# Outdoor transport: (speed m/s, straight line to road distance). Speeds and detours are only used when no routing
# provider answers; a provider's own distance and duration replace them.
MODES: dict[str, tuple[float, float]] = {
    "foot": (WALK_SPEED_M_S, 1.3),
    "wheelchair": (1.0, 1.3),
    "bike": (4.2, 1.3),
    "car": (8.0, 1.5),
}
FALLBACK_PAIRS = 12  # distinct door pairs kept in reserve, in case the best ones cannot be walked
DIVERSITY_M = 15.0  # candidate pairs whose doors are all this close to a chosen pair add nothing to show


@dataclass(frozen=True)
class Anchor:
    lat: float
    lon: float


@dataclass(frozen=True)
class Entrance:
    opening_id: str
    space_id: str  # the room the entrance opens into
    floor_id: str
    x: float
    y: float
    step_free: bool
    width_m: float | None
    lat: float
    lon: float
    label: str


@dataclass
class Outdoor:
    distance_m: float
    duration_min: float
    polyline: list[list[float]]  # [[lon, lat], ...]
    steps: list[dict] = field(default_factory=list)
    estimated: bool = True
    provider: str = "straight-line estimate"
    mode: str = "foot"


OutdoorProvider = Callable[[Entrance, Entrance], Outdoor | None]


class NoCampusRoute(ValueError):
    pass


def frame_centre(building: Building) -> tuple[float, float]:
    points = [p for space in building.spaces.values() for p in space["polygon"]]
    xs, ys = [p[0] for p in points], [p[1] for p in points]
    return (min(xs) + max(xs)) / 2.0, (min(ys) + max(ys)) / 2.0


def to_geo(building: Building, anchor: Anchor, x: float, y: float) -> tuple[float, float]:
    cx, cy = frame_centre(building)
    lat = anchor.lat + (y - cy) / METRES_PER_DEG_LAT
    lon = anchor.lon + (x - cx) / (METRES_PER_DEG_LAT * math.cos(math.radians(anchor.lat)))
    return lat, lon


def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    a = math.sin((p2 - p1) / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(math.radians(lon2 - lon1) / 2) ** 2
    return 2 * 6371008.8 * math.asin(math.sqrt(a))


def entrances(building: Building, anchor: Anchor) -> list[Entrance]:
    result = []
    for opening in building.openings.values():
        if OUTSIDE not in opening["space_ids"]:
            continue
        space_id = next(s for s in opening["space_ids"] if s != OUTSIDE)
        x, y = opening["position"]
        lat, lon = to_geo(building, anchor, x, y)
        result.append(Entrance(opening["id"], space_id, opening["floor_id"], x, y, opening.get("step_free", True),
                               opening.get("width_m"), lat, lon,
                               f"Entrance into {building.label(space_id)}"))
    return result


def estimate_outdoor(first: Entrance, second: Entrance, mode: str = "foot") -> Outdoor:
    speed, detour = MODES[mode]
    metres = haversine_m(first.lat, first.lon, second.lat, second.lon) * detour
    return Outdoor(round(metres, 1), round(metres / speed / 60, 3),
                   [[first.lon, first.lat], [second.lon, second.lat]], mode=mode)


def door_costs(building: Building, constraints: Constraints, start: str | None) -> dict[str, float]:
    """opening id -> walking metres from start to that entrance door; every usable entrance when start is None."""
    graph = RouteGraph(building, constraints, keep=frozenset({start} if start else ()))
    if start is None:
        return {o["id"]: 0.0 for o in building.openings.values()
                if OUTSIDE in o["space_ids"] and DOOR_PREFIX + o["id"] in graph.graph}
    distances = graph.distances_from(start)
    return {o["id"]: distances[DOOR_PREFIX + o["id"]] for o in building.openings.values()
            if OUTSIDE in o["space_ids"] and DOOR_PREFIX + o["id"] in distances}


@dataclass
class Candidate:
    exit_a: Entrance
    entry_b: Entrance
    indoor_a_m: float
    outdoor: Outdoor
    indoor_b_m: float

    @property
    def total_m(self) -> float:
        return self.indoor_a_m + self.outdoor.distance_m + self.indoor_b_m

    @property
    def total_s(self) -> float:
        """Door to door in seconds: indoors on foot, outdoors by the chosen mode. The pairs are ranked by this."""
        return (self.indoor_a_m + self.indoor_b_m) / WALK_SPEED_M_S + self.outdoor.duration_min * 60


@dataclass
class IndoorLeg:
    building_id: str
    building_name: str
    from_space: str
    to_space: str
    distance_m: float
    route: dict
    door: Entrance  # the exit (first building) or entrance (second building) this leg uses
    trivial: bool = False  # the room already is the entrance's room: nothing to walk inside


@dataclass
class CampusPlan:
    first: IndoorLeg | None
    outdoor: Outdoor
    second: IndoorLeg | None
    exit_a: Entrance
    entry_b: Entrance
    total_m: float
    candidates_considered: int
    alternatives: list[dict]

    def to_dict(self) -> dict:
        return asdict(self)


def _pick_candidates(a_doors: dict[str, float], b_doors: dict[str, float], ents_a: dict[str, Entrance],
                     ents_b: dict[str, Entrance], top_k: int, mode: str) -> list[Candidate]:
    pairs = []
    for ida, da in a_doors.items():
        for idb, db in b_doors.items():
            outdoor = estimate_outdoor(ents_a[ida], ents_b[idb], mode)
            pairs.append(Candidate(ents_a[ida], ents_b[idb], da, outdoor, db))
    pairs.sort(key=lambda c: c.total_s)
    chosen: list[Candidate] = []
    for pair in pairs:
        near = any(
            haversine_m(pair.exit_a.lat, pair.exit_a.lon, c.exit_a.lat, c.exit_a.lon) < DIVERSITY_M
            and haversine_m(pair.entry_b.lat, pair.entry_b.lon, c.entry_b.lat, c.entry_b.lon) < DIVERSITY_M
            for c in chosen
        )
        if not near:
            chosen.append(pair)
        if len(chosen) >= top_k:
            break
    return chosen


def _extend_guide(route: Route, door: Entrance, name: str, door_first: bool) -> None:
    """The Navigator's step-by-step guide follows route.guide: make it begin at the entrance or end at the exit door,
    not at the room the entrance opens into."""
    steps = route.guide.get("steps")
    if not steps:
        return
    if door_first:
        first = steps[0]
        first["text"] = f"You have come in through the {name}. " + first["text"]
        first["short"] = f"in through the {name}"
        first["floor_id"], first["point"] = door.floor_id, [door.x, door.y]
        route.guide["spoken"] = f"Come in through the {name}. " + route.guide.get("spoken", "")
        route.steps = [step["text"] for step in steps]
        return
    last = steps[-1]
    last_point, same_floor = last.get("point"), last.get("floor_id") == door.floor_id
    to_door = math.dist(last_point, (door.x, door.y)) if last_point and same_floor else 0.0
    if last["kind"] == "arrive" and last["text"].startswith("You have arrived at"):
        steps.pop()  # already in the room that has the exit: nothing to announce before the door
    elif last["kind"] == "arrive":  # the room is not the destination: keep it as a waypoint on the way to the door
        last["kind"], last["icon"] = "walk", "straight"
        last["text"] = last["text"].replace(" You have arrived.", "")
        last["short"] = last["short"].replace("arrive at", "on to")
        route.guide["spoken"] = route.guide.get("spoken", "").replace("then arrive at", "then on to")
        last["text"] = re.sub(r" Continue about (\d+) m inside to the marked destination\.", r" Then continue about \1 m towards the exit.", last["text"])
    steps.append({"kind": "arrive", "icon": "arrive", "text": f"Walk to the {name}: that is your way out. You have reached the exit.",
                  "short": f"exit through the {name}", "metres": round(to_door, 1), "floor_id": door.floor_id,
                  "point": [door.x, door.y], "landmark": None, "space_id": door.space_id})
    route.guide["spoken"] = route.guide.get("spoken", "") + f" Then leave through the {name}."
    route.steps = [step["text"] for step in steps]


def _indoor_leg(building: Building, space_a: str, space_b: str, door: Entrance, door_m: float, constraints: Constraints,
                door_first: bool, humane: bool = True) -> IndoorLeg:
    """Route between two rooms of one building and append (or prepend) the entrance door itself.
    humane=False is the graph route without a drawn walking line, for places where furniture or geometry blocks one."""
    route: Route = plan_route(building, [space_a, space_b], constraints, humane=humane)
    if not humane:
        route.preview_available = False
        route.warnings.append("No validated walking line here (furniture or geometry blocks it); the room sequence is still correct.")
    door_point = {"floor_id": door.floor_id, "x": door.x, "y": door.y, "node": DOOR_PREFIX + door.opening_id}
    name = door.label.replace("Entrance into ", "entrance into ")
    if door_first:
        route.polyline.insert(0, {**door_point, "gap": False})
        route.steps.insert(0, f"Come in through the {name}.")
    else:
        route.polyline.append(door_point)
        route.steps.append(f"Leave through the {name}.")
    _extend_guide(route, door, name, door_first)
    route.length_m = round(door_m, 2)
    return IndoorLeg(building.id, building.info["name"], space_a, space_b, round(door_m, 1), route.to_dict(), door,
                     trivial=space_a == space_b)


def plan_campus(a: Building, a_anchor: Anchor, a_start: str | None, b: Building, b_anchor: Anchor, b_dest: str | None,
                constraints_a: Constraints = Constraints(), constraints_b: Constraints = Constraints(),
                outdoor: OutdoorProvider | None = None, top_k: int = 3, mode: str = "foot") -> CampusPlan:
    """a_start / b_dest are space ids, or None for "just get me from building A's exit to building B's door"."""
    ents_a = {e.opening_id: e for e in entrances(a, a_anchor)}
    ents_b = {e.opening_id: e for e in entrances(b, b_anchor)}
    a_doors = door_costs(a, constraints_a, a_start)
    b_doors = door_costs(b, constraints_b, b_dest)
    if not a_doors:
        raise NoCampusRoute(f"No usable exit from {a.info['name']}" + (f" ({'; '.join(constraints_a.describe())})" if constraints_a.describe() else ""))
    if not b_doors:
        raise NoCampusRoute(f"No usable entrance into {b.info['name']}" + (f" ({'; '.join(constraints_b.describe())})" if constraints_b.describe() else ""))
    pool = _pick_candidates(a_doors, b_doors, ents_a, ents_b, max(top_k, FALLBACK_PAIRS), mode)
    shortlist = pool[:top_k]
    refined = set()

    def refine(candidate: Candidate) -> None:  # a provider call costs time and quota: only pairs we actually consider
        if outdoor is not None and id(candidate) not in refined:
            refined.add(id(candidate))
            answer = outdoor(candidate.exit_a, candidate.entry_b)
            if answer is not None:
                candidate.outdoor = answer

    for candidate in shortlist:
        refine(candidate)
    shortlist.sort(key=lambda c: c.total_s)
    ordered = shortlist + pool[top_k:]
    # A pair can fail even when it looks best: furniture or geometry may block the drawn walk to one door. Try the next
    # pair, skipping doors whose room already failed on that side. If every pair fails, settle for the plain route.
    last_error: NoRoute | None = None
    best = first = second = None
    for humane in (True, False):
        bad_a: set[str] = set()
        bad_b: set[str] = set()
        for candidate in ordered:
            if candidate.exit_a.space_id in bad_a or candidate.entry_b.space_id in bad_b:
                continue
            refine(candidate)
            try:
                first_leg = None if a_start is None else _indoor_leg(a, a_start, candidate.exit_a.space_id, candidate.exit_a, candidate.indoor_a_m, constraints_a, False, humane)
            except NoRoute as error:
                bad_a.add(candidate.exit_a.space_id)
                last_error = error
                continue
            try:
                second_leg = None if b_dest is None else _indoor_leg(b, candidate.entry_b.space_id, b_dest, candidate.entry_b, candidate.indoor_b_m, constraints_b, True, humane)
            except NoRoute as error:
                bad_b.add(candidate.entry_b.space_id)
                last_error = error
                continue
            best, first, second = candidate, first_leg, second_leg
            break
        if best is not None:
            break
    if best is None:
        raise NoCampusRoute(str(last_error) if last_error else "No walkable way between these two places.")
    candidates = [best] + [c for c in shortlist if c is not best]
    alternatives = [{"exit": c.exit_a.label, "entrance": c.entry_b.label, "total_m": round(c.total_m, 1),
                     "outdoor_m": c.outdoor.distance_m, "minutes": round(c.total_s / 60, 1), "estimated": c.outdoor.estimated}
                    for c in candidates[1:]]
    return CampusPlan(first, best.outdoor, second, best.exit_a, best.entry_b, round(best.total_m, 1),
                      len(a_doors) * len(b_doors), alternatives)
