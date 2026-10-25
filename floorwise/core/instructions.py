"""Directions people can follow (research: reports/Indoor wayfinding agent UX.md, section 3).

- Steps only at decision points: turns at doors into new areas, floor changes, leaving the building.
  Straight passes are merged into the next step ("straight through Main aisle H-B2 and H-B3").
- One salient landmark per step, scored on size, uniqueness nearby and closeness to the door, and seen
  from the doorway (it stands in one of the two spaces the door joins).
- A floor change is its own step: mode, direction, target floor, then where to head on exit.
- The room name and number confirm arrival.
- A spoken overview of at most 4 parts.

Output is structured (kind, icon, text, metres, floor, point) so the UI can draw icons and pan to steps,
and so evals can check the steps against the graph."""

import math
from dataclasses import asdict, dataclass

from floorwise.core.graph import DOOR_PREFIX, RouteGraph, anchor
from floorwise.core.model import OUTSIDE, Building

LANDMARK_RADIUS_M = 6.0
UNIQUENESS_RADIUS_M = 15.0
LANDMARK_CATEGORIES = {"machine", "equipment"}
MIN_SALIENCE = 0.35
WALKING_SPEED_MPS = 1.2


@dataclass
class Step:
    kind: str  # start | walk | floor | outside | arrive
    icon: str  # start | straight | left | right | back | lift | stairs | outside | arrive
    text: str
    short: str  # spoken form, <= ~15 words
    metres: float
    floor_id: str | None
    point: list[float] | None
    landmark: str | None = None
    space_id: str | None = None


def point_of(building: Building, graph: RouteGraph, node: str) -> tuple[str, float, float] | None:
    if node == OUTSIDE:
        return None
    if node.startswith(DOOR_PREFIX):
        opening_id = node[len(DOOR_PREFIX):]
        opening = building.openings.get(opening_id) or next(
            (o for o in graph.constraints.extra_openings if o["id"] == opening_id), None)
        return (opening["floor_id"], opening["position"][0], opening["position"][1])
    x, y = anchor(building, node)
    return (building.spaces[node]["floor_id"], x, y)


def turn_between(previous, here, following) -> str:
    heading_in = math.atan2(here[1] - previous[1], here[0] - previous[0])
    heading_out = math.atan2(following[1] - here[1], following[0] - here[0])
    delta = math.degrees((heading_out - heading_in + math.pi) % (2 * math.pi) - math.pi)
    if abs(delta) < 35:
        return "straight"
    if abs(delta) > 145:
        return "back"
    return "left" if delta > 0 else "right"


def salient_landmark(building: Building, opening: dict | None, floor_id: str, x: float, y: float) -> str | None:
    """Most salient machine or equipment visible from this doorway, or None."""
    visible_spaces = set(opening["space_ids"]) if opening else set()
    candidates = []
    for asset in building.assets.values():
        if asset["floor_id"] != floor_id or asset.get("category") not in LANDMARK_CATEGORIES:
            continue
        if visible_spaces and asset["space_id"] not in visible_spaces:
            continue
        distance = math.dist(asset["position"], (x, y))
        if distance > LANDMARK_RADIUS_M:
            continue
        footprint = asset.get("footprint") or {}
        size = min(1.0, (footprint.get("width_m", 0.5) * footprint.get("depth_m", 0.5)) / 6.0)
        same_type = sum(
            1 for other in building.assets.values()
            if other["type"] == asset["type"] and other["floor_id"] == floor_id
            and math.dist(other["position"], asset["position"]) <= UNIQUENESS_RADIUS_M
        )
        uniqueness = 1.0 / same_type
        closeness = 1.0 - distance / LANDMARK_RADIUS_M
        candidates.append((0.35 * size + 0.4 * uniqueness + 0.25 * closeness, asset))
    if not candidates:
        return None
    score, best = max(candidates, key=lambda item: item[0])
    return best["type"].replace("_", " ") if score >= MIN_SALIENCE else None


def _names(building: Building, space_ids: list[str]) -> str:
    names = [building.spaces[s]["name"] for s in space_ids]
    if len(names) <= 2:
        return " and ".join(names)
    return f"{names[0]}, {len(names) - 2} more and {names[-1]}"


def guide(building: Building, graph: RouteGraph, nodes: list[str], segments: dict | None = None) -> dict:
    """segments (optional): walking line per space-node index (floorwise.core.walk); used for metres and turns."""
    points = {node: point_of(building, graph, node) for node in nodes}
    segments = segments or {}
    steps: list[Step] = []
    start = nodes[0]
    if segments.get(0):
        points[start] = (points[start][0], *segments[0][0])
    steps.append(Step("start", "start", f"Start in {building.label(start)}.", f"From {building.spaces[start]['name']}.",
                      0.0, building.spaces[start]["floor_id"], list(points[start][1:]), space_id=start))
    # Distances run door to door (room anchors are graph artefacts, not where people walk).
    walked, passed = 0.0, []
    last = points[start]
    pending_core = None  # a lift/stair space we just walked into: merged into the floor step
    index = 1
    while index < len(nodes):
        previous, current = nodes[index - 1], nodes[index]
        edge = graph.edge_via(previous, current)
        element = edge["via"]
        here = points.get(current)
        if current.startswith(DOOR_PREFIX) and here and last and here[0] == last[0]:
            through = segments.get(index - 1)
            walked += _length(through) if through and len(through) > 1 else math.dist(here[1:], last[1:])
            last = here
        if element in building.connectors:
            connector = building.connectors[element]
            from_level = building.level(building.spaces[previous]["floor_id"])
            # Run along the connector as long as the route keeps using it.
            while index + 1 < len(nodes) and graph.edge_via(nodes[index], nodes[index + 1])["via"] == element:
                index += 1
            current = nodes[index]
            floor = building.spaces[current]["floor_id"]
            direction = "up" if building.level(floor) > from_level else "down"
            is_lift = connector["kind"] == "lift"
            lead = _lead(building, walked, passed, to=f"the {connector['name']}")
            pending_core = None
            exit_hint = ""
            if index + 2 < len(nodes) and nodes[index + 1].startswith(DOOR_PREFIX):
                after = nodes[index + 2]
                if after in building.spaces:
                    exit_hint = f" Leave toward {building.spaces[after]['name']}."
            verb = f"Take the {connector['name']} {direction}"
            if lead:  # the connector was just named in the lead: do not repeat it
                text = f"{lead}Take it {direction} to {building.floor_name(floor)}.{exit_hint}"
            else:
                text = f"{verb} to {building.floor_name(floor)}.{exit_hint}"
            steps.append(Step("floor", "lift" if is_lift else "stairs", text,
                              f"{connector['name']} {direction} to {building.floor_name(floor)}",
                              round(walked, 1), floor, list(points[current][1:]), space_id=current))
            walked, passed = 0.0, []
            last = points[current]
        elif current == OUTSIDE:
            steps.append(Step("outside", "outside", f"{_lead(building, walked, passed, to='the entrance')}Go outside.",
                              "go outside", round(walked, 1), None, None))
            walked, passed = 0.0, []
            last = None
        elif not current.startswith(DOOR_PREFIX):
            door_node = previous
            door = points.get(door_node)
            opening = building.openings.get(element) or next(
                (o for o in graph.constraints.extra_openings if o["id"] == element), None)
            space = building.spaces[current]
            is_last = index == len(nodes) - 1
            came_from_outside = index >= 2 and nodes[index - 2] == OUTSIDE
            turn = "straight"
            before = points.get(nodes[index - 2]) if index >= 2 else None
            after = points.get(nodes[index + 1]) if index + 1 < len(nodes) else None
            # Prefer the real walking line: last bend before the door, first bend after it.
            into, out_of = segments.get(index - 2), segments.get(index)
            if door and into and len(into) >= 2:
                before = (door[0], *_away(list(reversed(into)), door[1:]))
            if door and out_of and len(out_of) >= 2 and not is_last:
                after = (door[0], *_away(out_of, door[1:]))
            if door and before and after and before[0] == door[0] == after[0] and not came_from_outside:
                turn = turn_between(before[1:], door[1:], after[1:])
            elif door and before and before[0] == door[0] and is_last:
                turn = turn_between(before[1:], door[1:], points[current][1:])
            mergeable = turn == "straight" and not is_last and space["type"] in ("corridor", "hall") \
                and index + 2 < len(nodes) and nodes[index + 1].startswith(DOOR_PREFIX)
            if mergeable and not came_from_outside:
                passed.append(current)
                index += 1
                continue
            # Walking into a lift or stairwell only to ride it: say it once, in the floor step.
            next_is_connector = index + 1 < len(nodes) and graph.edge_via(current, nodes[index + 1])["via"] in building.connectors
            if space["type"] in ("lift", "stair") and next_is_connector:
                walked += _length(segments.get(index, []))
                index += 1
                continue
            if came_from_outside:
                last = door
            landmark = salient_landmark(building, opening, door[0], door[1], door[2]) if door else None
            target = "the entrance" if came_from_outside else ("the door" + (f" by the {landmark}" if landmark else ""))
            lead = _lead(building, walked, passed)
            if is_last:
                ref = f" ({space['ref']})" if space.get("ref") and space["ref"] not in space["name"] else ""
                inside = segments.get(index, [])
                interior = _length(inside)
                finish = f" Then {interior:.0f} m more to the marked spot." if interior >= 1 else ""
                text = f"{lead}Go through {target} into {space['name']}{ref}.{finish} You have arrived."
                steps.append(Step("arrive", "arrive", text, f"arrive at {space['name']}", round(walked + interior, 1),
                                  space["floor_id"], list(inside[-1]) if inside else list(points[current][1:]), landmark, current))
            else:
                then = {"left": ", then turn left", "right": ", then turn right", "back": ", then turn around"}.get(turn, "")
                text = f"{lead}Go through {target} into {space['name']}{then}."
                short = (f"{turn} into {space['name']}" if turn in ("left", "right") else f"into {space['name']}") + \
                    (f" at the {landmark}" if landmark else "")
                steps.append(Step("walk", turn if turn != "straight" else "straight", text, short, round(walked, 1),
                                  space["floor_id"], list(door[1:]) if door else None, landmark, current))
            walked, passed = 0.0, []
        index += 1
    if steps[-1].kind != "arrive":
        end = nodes[-1]
        steps.append(Step("arrive", "arrive", f"You have arrived at {building.label(end)}.",
                          f"arrive at {building.spaces[end]['name']}", 0.0, building.spaces[end]["floor_id"],
                          list(points[end][1:]), space_id=end))
    return {"steps": [asdict(s) for s in steps], "spoken": spoken(steps)}


def _away(points, door, minimum: float = 1.5):
    """First point along the walking line that is at least `minimum` metres from the door (stable heading)."""
    for p in points:
        if math.dist(p, door) >= minimum:
            return p
    return points[-1]


def _length(points) -> float:
    return sum(math.dist(points[i], points[i + 1]) for i in range(len(points) - 1))


def _lead(building: Building, metres: float, passed: list[str], to: str | None = None) -> str:
    if metres < 4 and not passed:
        return ""
    through = f" along {_names(building, passed)}" if passed else ""
    return f"Walk {metres:.0f} m{through}" + (f" to {to}" if to else "") + ". "


def spoken(steps: list[Step]) -> str:
    """Overview for voice: at most 4 parts (more overloads working memory), plus the size of the trip."""
    moves = [s for s in steps if s.kind in ("walk", "floor", "outside", "arrive")]
    total = sum(s.metres for s in steps)
    floors = sum(1 for s in steps if s.kind == "floor")
    minutes = max(1, round(total / WALKING_SPEED_MPS / 60) + floors)
    parts = [s.short.rstrip(".") for s in moves]
    if len(parts) > 4:
        parts = parts[:3] + [parts[-1]]
    trip = f"{len(moves)} steps, about {minutes} min" + (f", {floors} floor change{'s' if floors > 1 else ''}" if floors else "")
    sentence = ", then ".join(parts)
    return f"{trip}. {sentence[:1].upper()}{sentence[1:]}."
