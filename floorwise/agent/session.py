"""One user's live view of a building: closures, edits, the person's needs, and UI events.

Tools (for Claude) and the REST API (for the app) both go through this object, so what the agent does
and what the map shows can never disagree."""

import copy
from dataclasses import asdict, replace
import re
import itertools
from dataclasses import dataclass, field

from floorwise.core import geometry, ops
from floorwise.core import resolve as R
from floorwise.core.graph import Constraints
from floorwise.core.model import Building
from floorwise.core.routing import NoRoute, Route, plan_route

NEW_DOOR_WIDTH_M = 0.9
MAX_RESULTS = 12


@dataclass
class Profile:
    """What we know about the person, so they never have to repeat it ("without asking twice")."""

    step_free: bool = False
    min_door_width_m: float | None = None
    location: str | None = None


@dataclass
class Session:
    building: Building
    closed: set[str] = field(default_factory=set)
    profile: Profile = field(default_factory=Profile)
    events: list[dict] = field(default_factory=list)
    edits: list[dict] = field(default_factory=list)
    last_route: Route | None = None

    @classmethod
    def for_building(cls, building: Building) -> "Session":
        # Edits change the building; work on a copy so other sessions keep the original.
        session = cls(Building(copy.deepcopy(building.data), building.directory))
        session.default_start = main_entrance(session.building)
        return session

    default_start: str | None = None

    # ---------- helpers ----------

    def emit(self, kind: str, **payload) -> None:
        self.events.append({"type": kind, **payload})

    def space(self, mention: str) -> str:
        return R.resolve_space(self.building, mention).id

    def place(self, mention: str, near: str | None = None) -> str:
        """A space, the room an item stands in, or the nearest room with an item/room type.

        Ask-gate (research: ask only when candidates lead to materially different answers): if every
        candidate is in the same room, or we know where the person is, pick without asking and keep the
        alternatives in self.alternatives so the agent can mention them."""
        b = self.building
        self.alternatives = []
        if mention in b.assets:
            return b.assets[mention]["space_id"]
        try:
            return self.space(mention)
        except R.ResolveError as error:
            key = R.normalise(re.sub(r"^(the|a|an|nearest|closest)\s+", "", R.normalise(mention)))
            rooms = {a["space_id"] for a in b.assets.values() if R.normalise(a["name"]) == key}
            if key in ("exit", "entrance", "way out", "outside", "main entrance"):
                rooms = {s for o in b.openings.values() if "outside" in o["space_ids"] for s in o["space_ids"] if s != "outside"}
            if not rooms:
                rooms = {a["space_id"] for a in b.assets.values()
                         if key in R.normalise(a["name"]) or key in R.normalise(a["type"])}
            if not rooms:
                try:
                    rooms = {a["space_id"] for a in b.assets.values() if a["type"] == R.resolve_asset_type(b, key)}
                except R.ResolveError:
                    pass
            if not rooms:
                try:
                    room_type = R.resolve_room_type(b, key)
                    rooms = {s["id"] for s in b.spaces.values() if s["room_type"] == room_type}
                except R.ResolveError:
                    pass
            if len(rooms) == 1:
                return next(iter(rooms))
            if len(rooms) > 1 and near:
                from floorwise.core.graph import RouteGraph

                distances = RouteGraph(b, self.constraints(), keep=frozenset({near})).distances_from(near)
                ranked = sorted((distances[r], r) for r in rooms if r in distances)
                if ranked:
                    self.alternatives = [{"room": b.label(r), "walk_m": round(d)} for d, r in ranked[1:4]]
                    return ranked[0][1]
            if len(rooms) > 1:
                raise R.ResolveError(
                    f"'{mention}' is in {len(rooms)} rooms; where is the person, or which one?",
                    [{"id": r, "label": b.label(r)} for r in sorted(rooms)][:6],
                ) from error
            raise error

    def constraints(self, step_free: bool | None = None, min_door_width_m: float | None = None,
                    avoid: list[str] | None = None, avoid_stairs: bool = False, avoid_lifts: bool = False,
                    prefer_avoid: list[str] | None = None, closed: list[str] | None = None) -> Constraints:
        avoid_spaces, avoid_types = set(), set()
        for item in avoid or []:
            kind, value = self._avoid_target(item)
            (avoid_spaces if kind == "space" else avoid_types).add(value)
        soft = set()
        for item in prefer_avoid or []:
            soft.add(self._avoid_target(item)[1])
        closed_ids = set(self.closed) | {self.element(c) for c in closed or []}
        return Constraints(
            step_free=self.profile.step_free if step_free is None else step_free,
            min_width_m=min_door_width_m if min_door_width_m is not None else self.profile.min_door_width_m,
            closed=frozenset(closed_ids),
            avoid_spaces=frozenset(avoid_spaces),
            avoid_types=frozenset(avoid_types),
            no_stairs=avoid_stairs,
            no_lifts=avoid_lifts,
            soft_avoid_types=frozenset(soft),
            outside="none",  # people walk indoors; no free hop between entrances
        )

    def _avoid_target(self, item: str) -> tuple[str, str]:
        b = self.building
        try:
            return "type", R.resolve_room_type(b, item)
        except R.ResolveError:
            pass
        return "space", self.space(item)

    def element(self, mention: str) -> str:
        b = self.building
        if mention in b.connectors or mention in b.openings or mention in b.spaces:
            return mention
        try:
            return R.resolve_connector(b, mention)
        except R.ResolveError:
            return self.space(mention)

    # ---------- operations ----------

    def overview(self) -> dict:
        b = self.building
        floors = []
        for floor in sorted(b.floors.values(), key=lambda f: f["level"]):
            spaces = b.spaces_on(floor["id"])
            floors.append({"level": floor["level"], "name": floor["name"], "rooms": sum(1 for s in spaces if s["type"] == "room"),
                           "spaces": len(spaces)})
        return {
            "name": b.info["name"], "source": b.info["source"], "floors": floors,
            "stairs_and_lifts": [
                {"id": c["id"], "name": c["name"], "kind": c["kind"], "step_free": c.get("step_free", True),
                 "floors": [b.floor_name(f) for f in c["floor_ids"]]}
                for c in b.connectors.values()
            ],
            "entrances": [
                {"id": o["id"], "into": b.label(next(s for s in o["space_ids"] if s != "outside")),
                 "step_free": o.get("step_free", True), "width_m": o.get("width_m")}
                for o in b.openings.values() if "outside" in o["space_ids"]
            ],
            "room_types": sorted(R.room_types(b)),
            "closed": sorted(self.closed),
            "profile": self.profile.__dict__,
        }

    def search(self, query: str, floor: str | None = None) -> dict:
        b = self.building
        floor_id = R.resolve_floor(b, floor) if floor else None
        words = [w for w in R.normalise(query).split() if w]
        spaces, assets = [], []
        for s in b.spaces.values():
            text = R.normalise(f"{s['name']} {s.get('ref') or ''} {s['room_type']} {s['type']}")
            if (floor_id is None or s["floor_id"] == floor_id) and all(w in text or R._singular(w) in text for w in words):
                spaces.append({"id": s["id"], "name": s["name"], "type": s["room_type"], "floor": b.floor_name(s["floor_id"])})
        for a in b.assets.values():
            text = R.normalise(f"{a['name']} {a['type']}")
            if (floor_id is None or a["floor_id"] == floor_id) and all(w in text or R._singular(w) in text for w in words):
                assets.append({"id": a["id"], "name": a["name"], "type": a["type"], "in": b.label(a["space_id"])})
        if spaces or assets:
            self.emit("highlight", ids=[x["id"] for x in (spaces + assets)[:MAX_RESULTS]])
        return {"spaces": spaces[:MAX_RESULTS], "assets": assets[:MAX_RESULTS],
                "total": len(spaces) + len(assets)}

    def room_info(self, mention: str) -> dict:
        b = self.building
        space_id = self.place(mention)
        s = b.spaces[space_id]
        doors = [
            {"to": b.label(next((x for x in o["space_ids"] if x != space_id), space_id)), "width_m": o.get("width_m"),
             "kind": o["kind"], "step_free": o.get("step_free", True)}
            for o in b.openings.values() if space_id in o["space_ids"]
        ]
        contents = {}
        for a in b.assets.values():
            if a["space_id"] == space_id:
                contents[a["type"]] = contents.get(a["type"], 0) + 1
        above = geometry.stacked(b, space_id, "above")
        below = geometry.stacked(b, space_id, "below")
        x, y, z = geometry.centroid_3d(b, space_id)
        self.emit("highlight", ids=[space_id])
        return {
            "id": space_id, "name": s["name"], "type": s["room_type"], "floor": b.floor_name(s["floor_id"]),
            "area_m2": round(geometry.area(b, space_id), 2), "centre": [round(x, 2), round(y, 2), round(z, 2)],
            "doors": doors[:MAX_RESULTS], "contents": contents,
            "shares_walls_with": [b.spaces[n]["name"] for n, _ in geometry.wall_neighbours(b, space_id)][:MAX_RESULTS],
            "above": b.label(above[0][0]) if above else None, "below": b.label(below[0][0]) if below else None,
        }

    def route(self, start: str, destination: str, via: list[str] | None = None, **constraint_args) -> dict:
        b = self.building
        assumed = None
        if not start and not self.profile.location:
            if not self.default_start:
                return {"error": "Start unknown. Ask where the person is: offer 2-3 entrances or things they can see."}
            assumed = self.default_start
        first = self.place(start or self.profile.location or assumed)
        middle = []
        for stop in via or []:
            middle.append(self.place(stop, near=(middle or [first])[-1]))
        last = self.place(destination, near=(middle or [first])[-1])
        alternatives = self.alternatives
        stops = [first, *middle, last]
        constraints = self.constraints(**constraint_args)
        try:
            route = plan_route(b, stops, constraints, humane=True)
        except NoRoute as error:
            relaxed = None
            if constraints.describe():
                try:
                    relaxed = plan_route(b, stops, Constraints(closed=frozenset(self.closed)))
                except NoRoute:
                    pass
            from floorwise.core.fixes import smallest_fix
            fix = smallest_fix(b, first, last, constraints)
            if fix.verified:
                for widening in fix.widen:
                    self.emit("fix_preview", opening={**b.openings[widening.opening_id], "width_m": widening.to_m},
                              fix=asdict(fix), start=first, destination=last)
            return {"error": str(error), "without_extra_constraints_m": relaxed.length_m if relaxed else None, "why": asdict(fix)}
        self.last_route = route
        self.emit("route", route=route.to_dict())
        return {
            "from": b.label(stops[0]), "to": b.label(stops[-1]), "via": [b.label(s) for s in stops[1:-1]],
            "length_m": route.walk_m if route.walk_m is not None else route.length_m,
            "about_minutes": max(1, round((route.walk_m or route.length_m) / 1.2 / 60)), "constraints": route.constraints, "floors": [b.floor_name(f) for f in route.floors],
            "steps": route.steps, "spoken_overview": route.guide.get("spoken"), "walk_m": route.walk_m,
            **({"assumed_start": f"Start not given: assumed the main entrance, {b.label(assumed)}. Say so in one line."} if assumed else {}),
            **({"other_matches_further_away": alternatives} if alternatives else {}),
        }

    def reachable(self, start: str, floor: str, **constraint_args) -> dict:
        b = self.building
        start_id = self.place(start)
        floor_id = R.resolve_floor(b, floor)
        constraints = self.constraints(**constraint_args)
        result = ops.reachable_rooms_on_floor(b, start_id, floor_id, constraints)
        all_rooms = [s["id"] for s in b.spaces_on(floor_id) if s["type"] == "room"]
        unreachable = [b.spaces[s]["name"] for s in all_rooms if s not in result["space_ids"]]
        self.emit("highlight", ids=result["space_ids"])
        return {"reachable_rooms": result["count"], "of_rooms_on_floor": len(all_rooms), "constraints": result["constraints"],
                "unreachable_examples": unreachable[:MAX_RESULTS]}

    def rank_rooms(self, floor: str, room_type: str) -> dict:
        b = self.building
        floor_id, room_type_id = R.resolve_floor(b, floor), R.resolve_room_type(b, room_type)
        members = ops.rooms_of_type(b, floor_id, room_type_id)
        ranked = sorted(((geometry.area(b, m), m) for m in members), reverse=True)
        self.emit("highlight", ids=members)
        return {
            "floor": b.floor_name(floor_id), "room_type": room_type_id, "count": len(members),
            "total_area_m2": round(sum(a for a, _ in ranked), 2),
            "largest_first": [{"name": b.spaces[m]["name"], "id": m, "area_m2": round(a, 2)} for a, m in ranked[:MAX_RESULTS]],
        }

    def nearest(self, start: str, what: str, **constraint_args) -> dict:
        """Nearest room holding an item type, or nearest room of a type, by walking distance."""
        from floorwise.core.graph import RouteGraph

        b = self.building
        start_id = self.place(start)
        constraints = self.constraints(**constraint_args)
        distances = RouteGraph(b, constraints, keep=frozenset({start_id})).distances_from(start_id)
        try:
            asset_type = R.resolve_asset_type(b, what)
            targets = {a["space_id"] for a in b.assets.values() if a["type"] == asset_type}
            label = asset_type
        except R.ResolveError:
            room_type = R.resolve_room_type(b, what)
            targets = {s["id"] for s in b.spaces.values() if s["room_type"] == room_type}
            label = room_type
        ranked = sorted((distances[t], t) for t in targets if t in distances)
        if not ranked:
            return {"error": f"no reachable {label}", "constraints": constraints.describe()}
        return {"what": label, "nearest": [{"room": b.label(t), "id": t, "walk_m": round(d, 1)} for d, t in ranked[:5]],
                "constraints": constraints.describe()}

    def set_closed(self, element: str, closed: bool) -> dict:
        before = self.impact_snapshot()
        element_id = self.element(element)
        (self.closed.add if closed else self.closed.discard)(element_id)
        impact = self.impact(before)
        b = self.building
        if element_id in b.connectors:
            name = b.connectors[element_id]["name"]
        elif element_id in b.spaces:
            name = b.label(element_id)
        else:
            name = element_id
        self.emit("closure", id=element_id, closed=closed, impact=impact)
        return {"element": name, "id": element_id, "closed": closed, "all_closed": sorted(self.closed), "impact": impact}

    def door_preview(self, first: str, second: str) -> dict:
        b = self.building
        a, c = self.space(first), self.space(second)
        if b.spaces[a]["floor_id"] != b.spaces[c]["floor_id"]:
            return {"error": "A door can only join two spaces on the same floor."}
        position = geometry.wall_midpoint(b, a, c)
        if position is None:
            return {"error": f"{b.spaces[a]['name']} and {b.spaces[c]['name']} do not share a wall."}
        door = {"id": f"{b.spaces[a]['floor_id']}-O-new{len(self.edits) + 1}", "floor_id": b.spaces[a]["floor_id"],
                "space_ids": [a, c], "kind": "door", "position": [round(position[0], 3), round(position[1], 3)],
                "width_m": NEW_DOOR_WIDTH_M, "step_free": True, "synthetic": True}
        before = self.impact_snapshot()
        after = self.impact_snapshot(extra=(door,))
        impact = self.impact_diff(before, after)
        self.emit("preview_door", door=door, impact=impact)
        return {"door": door, "between": [b.label(a), b.label(c)], "impact": impact,
                "note": "Preview only. Call add_door with confirm=true after the person agrees."}

    def add_door(self, first: str, second: str) -> dict:
        preview = self.door_preview(first, second)
        if "error" in preview:
            return preview
        door = preview["door"]
        self.building.openings[door["id"]] = door
        self.building.data["openings"].append(door)
        self.edits.append({"op": "add_door", "door": door})
        self.emit("edit", op="add_door", door=door)
        return {"added": door["id"], "between": preview["between"], "impact": preview["impact"]}

    def move_asset(self, asset: str, to: str) -> dict:
        b = self.building
        asset_id = asset if asset in b.assets else next(
            (a["id"] for a in b.assets.values() if R.normalise(a["name"]) == R.normalise(asset)), None)
        if asset_id is None:
            found = self.search(asset)["assets"]
            if len(found) != 1:
                return {"error": f"Which item is '{asset}'?", "candidates": found[:8]}
            asset_id = found[0]["id"]
        space_id = self.space(to)
        from floorwise.core.graph import anchor

        x, y = anchor(b, space_id)
        record = b.assets[asset_id]
        old = record["space_id"]
        record.update(space_id=space_id, floor_id=b.spaces[space_id]["floor_id"], position=[round(x, 3), round(y, 3)])
        self.edits.append({"op": "move_asset", "asset": asset_id, "from": old, "to": space_id})
        self.emit("edit", op="move_asset", asset=asset_id, to=space_id)
        return {"moved": record["name"], "from": b.label(old), "to": b.label(space_id)}

    # ---------- change impact ----------

    def exit_distances(self, extra: tuple = ()) -> dict[str, float]:
        return ops.distances_to_exit(self.building, Constraints(closed=frozenset(self.closed), extra_openings=extra))

    def impact_snapshot(self, extra: tuple = ()) -> dict:
        general = Constraints(closed=frozenset(self.closed), extra_openings=extra)
        snapshots = {"general": ops.distances_to_exit(self.building, general),
                     "step_free": ops.distances_to_exit(self.building, replace(general, step_free=True))}
        if self.profile.min_door_width_m is not None:
            snapshots["your_needs"] = ops.distances_to_exit(self.building, replace(self.constraints(), outside="free", extra_openings=extra))
        return snapshots

    def impact_diff(self, before: dict, after: dict) -> dict:
        result = self._diff(before["general"], after["general"])
        for profile in ("step_free", "your_needs"):
            if profile in before:
                result[profile] = self._diff(before[profile], after[profile])
        return result

    def impact(self, before: dict) -> dict:
        return self.impact_diff(before, self.impact_snapshot())

    def widen_door(self, opening_id: str, width_m: float) -> dict:
        import math
        opening = self.building.openings.get(opening_id)
        if opening is None or not math.isfinite(width_m) or width_m <= 0 or width_m > 20:
            raise ValueError("Choose an existing opening and a width between 0 and 20 metres.")
        old = opening["width_m"]
        if width_m < old:
            raise ValueError("Widening cannot reduce an opening's width.")
        opening["width_m"] = width_m
        receipt = {"op": "widen_door", "opening": opening_id, "from": old, "to": width_m}
        self.edits.append(receipt)
        self.last_route = None
        self.emit("edit", **receipt)
        return receipt

    def weak_points(self, step_free: bool = True) -> list[dict]:
        from floorwise.core.resilience import chaos_test
        result = chaos_test(self.building, replace(self.constraints(step_free=step_free), outside="free"))
        items = result["critical"][:3]
        self.emit("weak_points", items=items, profile="step-free" if step_free else "general")
        self.emit("highlight", ids=list(dict.fromkeys(s for item in items for s in item["room_ids"])))
        return items

    def _diff(self, before: dict[str, float], after: dict[str, float]) -> dict:
        b = self.building
        rooms = [s for s in b.spaces if b.spaces[s]["type"] == "room"]
        cut_off = [s for s in rooms if s in before and s not in after]
        reconnected = [s for s in rooms if s not in before and s in after]
        longer = sorted(((after[s] - before[s], s) for s in rooms if s in before and s in after and after[s] - before[s] > 1), reverse=True)
        shorter = sorted(((before[s] - after[s], s) for s in rooms if s in before and s in after and before[s] - after[s] > 1), reverse=True)
        return {
            "of_rooms": sum(s in before for s in rooms), "cut_off_ids": cut_off,
            "reconnected_ids": reconnected,
            "rooms_cut_off_from_exits": [b.label(s) for s in cut_off][:MAX_RESULTS], "cut_off_count": len(cut_off),
            "rooms_reconnected": [b.label(s) for s in reconnected][:MAX_RESULTS],
            "longer_way_out_count": len(longer), "shorter_way_out_count": len(shorter),
            "most_affected": [{"room": b.label(s), "change_m": round(d, 1)} for d, s in itertools.islice(longer or shorter, 5)],
        }


def main_entrance(building: Building) -> str | None:
    """The space behind an entrance, preferring lobbies on the floor nearest the ground."""
    candidates = []
    for opening in building.openings.values():
        if "outside" not in opening["space_ids"]:
            continue
        space_id = next(s for s in opening["space_ids"] if s != "outside")
        space = building.spaces[space_id]
        rank = (0 if space["room_type"] == "lobby" else 1, abs(building.level(space["floor_id"])), space["type"] == "room")
        candidates.append((rank, space_id))
    return min(candidates)[1] if candidates else None
