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
from floorwise.core.connectors import inventory as connector_inventory_data, connector_kind
from floorwise.core.routing import NoRoute, Route, plan_route

NEW_DOOR_WIDTH_M = 0.9
MAX_RESULTS = 12


@dataclass
class Profile:
    """What we know about the person, so they never have to repeat it ("without asking twice")."""

    step_free: bool = False
    min_door_width_m: float | None = None
    location: str | None = None
    location_source: str | None = None


@dataclass
class Session:
    building: Building
    closed: set[str] = field(default_factory=set)
    profile: Profile = field(default_factory=Profile)
    events: list[dict] = field(default_factory=list)
    edits: list[dict] = field(default_factory=list)
    last_route: Route | None = None
    visual_results: dict[str, dict] = field(default_factory=dict)

    @classmethod
    def for_building(cls, building: Building) -> "Session":
        # Edits change the building; work on a copy so other sessions keep the original.
        session = cls(Building(copy.deepcopy(building.data), building.directory))
        session.default_start = main_entrance(session.building)
        return session

    default_start: str | None = None
    _undo: list = field(default_factory=list, repr=False)

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
            # An exact equipment type outranks substring matches (printer != 3d_printer).
            exact_types={t for t in R.asset_types(b) if R.normalise(t)==key}
            if not rooms and exact_types:
                rooms={a['space_id'] for a in b.assets.values() if a['type'] in exact_types}
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
            "unavailable_data": ["bookings", "live position", "seat capacity", "opening hours", "window geometry", "surveyed stair flights"],
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

    def publish_visual(self, kind: str, title: str, ids: list[str], measurements=None, rows=None, lines=None, warnings=None) -> dict:
        """Complete entity references go to the UI; the model receives only a compact summary."""
        import uuid
        b = self.building
        ids = list(dict.fromkeys(ids))
        entities = []
        for identifier in ids:
            entity = b.spaces.get(identifier) or b.assets.get(identifier) or b.openings.get(identifier)
            if entity:
                entities.append({'id': identifier, 'floor_id': entity['floor_id'],
                                 'kind': 'room' if identifier in b.spaces else 'asset' if identifier in b.assets else 'opening'})
        measurements=dict(measurements or {})
        values={r['id']:r.get('count',r.get('area_m2')) for r in rows or [] if 'id' in r and isinstance(r.get('count',r.get('area_m2')), (int,float))}
        if values and kind!='comparison':measurements['entity_values']=values
        result = {'id': uuid.uuid4().hex[:12], 'kind': kind, 'title': title, 'entities': entities,
                  'floor_ids': sorted({e['floor_id'] for e in entities}), 'measurements': measurements or {},
                  'rows': rows or [], 'lines': lines or [], 'warnings': warnings or [],
                  'provenance': 'Computed from supplied building data; current session edits apply.'}
        # Immutable grouped snapshots; list paging must not hold the chat's write lock.
        items = [b.assets[i] for i in ids if i in b.assets]
        if items:
            from collections import Counter
            grouped = Counter(a['space_id'] for a in items)
            result['room_rows'] = [{'id': sid, 'label': b.label(sid), 'floor_id': b.spaces[sid]['floor_id'],
                                    'count': count} for sid, count in sorted(grouped.items(), key=lambda p: (b.level(b.spaces[p[0]]['floor_id']), -p[1], p[0]))]
            result['item_rows'] = [{'id': a['id'], 'label': a['name'], 'room_id': a['space_id'],
                                   'floor_id': a['floor_id']} for a in items]
            result['measurements'] = {**result['measurements'], 'grouped': True, 'item_count': len(items), 'room_count': len(grouped)}
        self.visual_results[result['id']] = result
        while len(self.visual_results)>16:
            del self.visual_results[next(iter(self.visual_results))]
        self.emit('highlight', ids=ids)
        self.emit('visual_result', result={k:v for k,v in result.items() if k not in ('rows','room_rows','item_rows')}, total_rows=len(result['rows']))
        return result

    def result_page(self, result_id: str, offset: int = 0, limit: int = 25, view: str = 'default', room: str | None = None) -> dict:
        if offset<0 or not 1<=limit<=100:
            raise ValueError('offset must be nonnegative; limit must be 1 to 100')
        result = self.visual_results[result_id]
        if view not in ('default', 'rooms', 'items'): raise ValueError('Unknown result view')
        rows = result.get('room_rows', result['rows']) if view == 'rooms' else result.get('item_rows', result['rows']) if view == 'items' else result['rows']
        if room is not None:
            if view != 'items': raise ValueError('Room filtering requires item view')
            rows = [r for r in rows if r.get('room_id') == room]
        return {'id': result_id, 'total': len(rows), 'offset': offset,
                'rows': rows[offset:offset+limit],
                'next_offset': offset+limit if offset+limit<len(rows) else None}

    def search(self, query: str, floor: str | None = None, offset: int = 0, limit: int = 12) -> dict:
        b = self.building
        if offset<0 or not 1<=limit<=100:
            raise ValueError('offset must be nonnegative; limit must be 1 to 100')
        floor_id = R.resolve_floor(b, floor) if floor else None
        words = [w for w in R.normalise(query).split() if w]
        spaces, assets = [], []
        for entity in [*b.spaces.values(), *b.assets.values()]:
            text = R.normalise(f"{entity['name']} {entity.get('ref') or ''} {entity.get('room_type', '')} {entity['type']}")
            if (floor_id is None or entity['floor_id']==floor_id) and all(w in text or R._singular(w) in text for w in words):
                row = {'id': entity['id'], 'label': b.label(entity['id']) if entity['id'] in b.spaces else entity['name'],
                       'name': entity['name'], 'type': entity.get('room_type',entity['type']), 'floor_id': entity['floor_id'], 'floor': b.floor_name(entity['floor_id']),
                       'in': b.label(entity['space_id']) if 'space_id' in entity else None}
                (assets if 'space_id' in entity else spaces).append(row)
        rows = spaces+assets
        visual = self.publish_visual('matches', f'{len(rows)} matches for {query}', [r['id'] for r in rows], {'count': len(rows)}, rows)
        page=rows[offset:offset+limit]
        from collections import Counter
        grouped=Counter(b.assets[r['id']]['space_id'] for r in assets)
        return {'spaces': [r for r in page if r['id'] in b.spaces], 'assets': [r for r in page if r['id'] in b.assets],
                'total': len(rows), 'result_id': visual['id'], 'offset': offset,
                'next_offset': offset+limit if offset+limit<len(rows) else None,
                'grouped_by_room': [{'id': sid, 'label': b.label(sid), 'count': n} for sid,n in grouped.most_common(12)]}

    def connector_inventory(self, kind='stairs', floor=None, room=None):
        result=connector_inventory_data(self.building,kind,floor,room)
        visual=self.publish_visual('matches',f"{result['count']} mapped {result['kind']} connections",result['ids'],
                                   {k:v for k,v in result.items() if k not in ('ids','rows')},result['rows'])
        return {k:v for k,v in result.items() if k not in ('ids','rows')} | {'result_id':visual['id'],'connectors':result['rows'][:25],
                'rows_are_examples':len(result['rows'])>25,'total_connectors':len(result['rows'])}

    def count_items(self, item_type: str, floor: str | None = None, room: str | None = None, *, exact: bool = False) -> dict:
        if not exact and connector_kind(item_type):return self.connector_inventory(item_type,floor,room)
        from floorwise.core.analytics import count_items
        result = count_items(self.building, item_type, floor, room, inclusive=not exact)
        self.last_item_type=item_type
        maximum=max((r['count'] for r in result['per_room']),default=0)
        leaders=[r for r in result['per_room'] if r['count']==maximum]
        result.update(maximum_per_room=maximum,top_tie_count=len(leaders),leading_rooms=leaders[:5])
        visual = self.publish_visual('count', f"{result['count']} {item_type}", result['ids'],
                                     {k:v for k,v in result.items() if k not in ('ids','per_room')}, result['per_room'])
        return {k:v for k,v in result.items() if k not in ('ids','per_room')} | {'result_id': visual['id'], 'rooms': result['per_room'][:12]}

    def rank_by_items(self, item_type: str, floor: str | None = None, room_type: str | None = None, offset: int = 0, limit: int = 12) -> dict:
        if R.normalise(item_type) in ('all','everything','all items','all types'):
            return self.compare_item_leaders(floor)
        self.last_item_type=item_type
        from floorwise.core.analytics import rank_by_items
        if offset<0 or not 1<=limit<=100:
            raise ValueError('Invalid page; offset >= 0 and limit 1 to 100 required.')
        result = rank_by_items(self.building, item_type, floor, room_type)
        visual = self.publish_visual('ranking', f'Rooms ranked by {item_type}', [r['id'] for r in result['rows']],
                                     {**{k:v for k,v in result.items() if k!='rows'}, 'primary_ids':[r['id'] for r in result['rows'][:result['top_ties']]]}, result['rows'])
        return {k:v for k,v in result.items() if k!='rows'} | {'rows': result['rows'][offset:offset+limit], 'result_id': visual['id'],
                'next_offset': offset+limit if offset+limit<len(result['rows']) else None}

    def compare_item_leaders(self,floor=None,compare_floor=None):
        from floorwise.core.analytics import item_leaders
        result=item_leaders(self.building,floor,compare_floor)
        ids=list(dict.fromkeys(sid for row in result['rows'] for scope in row['scopes'] for sid in scope['leader_ids']))
        visual=self.publish_visual('comparison','Which places have the most of each item?',ids,
                                   {k:v for k,v in result.items() if k!='rows'},result['rows'])
        return {k:v for k,v in result.items() if k!='rows'} | {'result_id':visual['id'],
                'presentation':'Complete compact comparison table is visible. Each type has total, maximum and all tied leading places.'}

    def filter_rooms(self, requirements: list[dict], floor: str | None = None, room_type: str | None = None) -> dict:
        from floorwise.core.analytics import filter_rooms
        result = filter_rooms(self.building, requirements, floor, room_type)
        visual = self.publish_visual('matches', f"{result['count']} rooms match every requirement", [r['id'] for r in result['rows']],
                                     {'count': result['count'], 'requirements': result['requirements']}, result['rows'])
        from collections import Counter
        floors=Counter(r['floor_id'] for r in result['rows'])
        return result | {'rows': result['rows'][:12], 'result_id': visual['id'],
                         'rows_are_examples':len(result['rows'])>12,
                         'per_floor':[{'floor':self.building.floor_name(fid),'count':n} for fid,n in floors.items()],
                         'data_limits':['bookings, seat capacity and opening hours are unavailable; chair counts are not capacity']}

    def statistics(self, floor: str | None = None, room_type: str | None = None, group_by: str = 'floor') -> dict:
        from floorwise.core.analytics import statistics
        result = statistics(self.building, floor, room_type, group_by)
        visual = self.publish_visual('area', 'Room areas and totals', result['ids'],
                                     {k:v for k,v in result.items() if k not in ('ids','rows')}, result['rows'])
        return {k:v for k,v in result.items() if k not in ('ids','rows')} | {'rows': result['rows'][:12], 'result_id': visual['id']}

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
        self.publish_visual("area", b.label(space_id), [space_id], {"area_m2": round(geometry.area(b,space_id),2)}, [{"id": space_id,"label": b.label(space_id),"area_m2": round(geometry.area(b,space_id),2)}])
        return {
            "id": space_id, "name": s["name"], "type": s["room_type"], "floor": b.floor_name(s["floor_id"]),
            "area_m2": round(geometry.area(b, space_id), 2), "centre": [round(x, 2), round(y, 2), round(z, 2)],
            "doors": doors[:MAX_RESULTS], "door_count":len(doors), "door_examples_only":len(doors)>MAX_RESULTS,
            "connector_access":connector_inventory_data(b,room=space_id), "contents": contents,
            "shares_walls_with": [b.spaces[n]["name"] for n, _ in geometry.wall_neighbours(b, space_id)][:MAX_RESULTS],
            "above": b.label(above[0][0]) if above else None, "below": b.label(below[0][0]) if below else None,
        }

    def route(self, start: str, destination: str, via: list[str] | None = None, **constraint_args) -> dict:
        b = self.building
        self.last_route_request = (start, destination, via, dict(constraint_args))
        assumed = None
        if not start and (not self.profile.location or self.profile.location_source=='default'):
            if not self.default_start:
                return {"error": "Start unknown. Ask where the person is: offer 2-3 entrances or things they can see."}
            assumed = self.profile.location or self.default_start
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
                widening = fix.widen[0]
                self.emit("fix_preview", opening={**b.openings[widening.opening_id], "width_m": widening.to_m},
                          fix=asdict(fix), start=first, destination=last)
            return {"error": str(error), "without_extra_constraints_m": relaxed.length_m if relaxed else None, "why": asdict(fix)}
        self.last_route = route
        self.emit("route", route=route.to_dict())
        return {
            "from": b.label(stops[0]), "to": b.label(stops[-1]), "via": [b.label(s) for s in stops[1:-1]],
            "length_m": route.walk_m if route.walk_m is not None else route.length_m,
            "about_minutes": max(1, round((route.walk_m if route.walk_m is not None else route.length_m) / 1.2 / 60) + sum(s['kind'] == 'floor' for s in route.guide['steps'])), "constraints": route.constraints, "floors": [b.floor_name(f) for f in route.floors],
            "steps": route.steps, "spoken_overview": route.guide.get("spoken"), "walk_m": route.walk_m, "destination_basis":"marked room destination, not an equipment position", "distance_basis": "walking metres" if route.walk_m is not None else "route-model metres; walking preview unavailable",
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
        visual=self.publish_visual("reachability", f"{result['count']} reachable rooms", all_rooms, {"count": result["count"], "unreachable_ids": [s for s in all_rooms if s not in result["space_ids"]]}, [{"id": s,"label": b.label(s),"reachable": s in result["space_ids"]} for s in all_rooms])
        return {"result_id":visual["id"],"reachable_rooms": result["count"], "of_rooms_on_floor": len(all_rooms), "constraints": result["constraints"],
                "unreachable_examples": unreachable[:MAX_RESULTS]}

    def rank_rooms(self, floor: str, room_type: str) -> dict:
        b = self.building
        floor_id, room_type_id = R.resolve_floor(b, floor), R.resolve_room_type(b, room_type)
        members = ops.rooms_of_type(b, floor_id, room_type_id)
        ranked = sorted(((geometry.area(b, m), m) for m in members), reverse=True)
        visual=self.publish_visual("area", "Rooms ranked by area", members, {"total_area_m2": round(sum(a for a,_ in ranked),2)}, [{"id": m,"label": b.label(m),"area_m2": round(a,2)} for a,m in ranked])
        return {
            "floor": b.floor_name(floor_id), "room_type": room_type_id, "count": len(members),
            "total_area_m2": round(sum(a for a, _ in ranked), 2), "result_id":visual["id"],
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
        previous_walk = self.last_route.walk_m if self.last_route else None
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
        result = {"element": name, "id": element_id, "closed": closed, "all_closed": sorted(self.closed), "impact": impact}
        request = getattr(self, "last_route_request", None)
        self.last_route = None
        if request:
            start, target, via, kwargs = request
            result["route_update"] = self.route(start, target, via, **kwargs)
            current_walk = self.last_route.walk_m if self.last_route else None
            if previous_walk is not None and current_walk is not None:
                result['walking_change_m'] = round(current_walk-previous_walk,1)
        return result

    def closure_preview(self, element: str) -> dict:
        """What closing this place would do, without closing it (the UI asks before stranding rooms)."""
        element_id = self.element(element)
        was_closed = element_id in self.closed
        before = self.impact_snapshot()
        self.closed.add(element_id)
        try:
            impact = self.impact(before)
        finally:
            if not was_closed:
                self.closed.discard(element_id)
        b = self.building
        name = b.connectors[element_id]["name"] if element_id in b.connectors else b.label(element_id) if element_id in b.spaces else element_id
        return {"element": name, "id": element_id, "already_closed": was_closed, "impact": impact}

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
        self._insert_opening(door)
        self.edits.append({"op": "add_door", "door": door})
        self._undo.append(lambda: self._drop_opening(door["id"]))
        self.last_route = None
        self.emit("edit", op="add_door", door=door)
        return {"added": door["id"], "between": preview["between"], "impact": preview["impact"]}

    def _refresh(self, spaces=()) -> None:
        from floorwise.core.spacewalk import refresh_spaces
        from floorwise.core.walk import invalidate
        if spaces:
            refresh_spaces(self.building, spaces)
        invalidate(self.building)
        self.last_route = None

    def _insert_opening(self, door: dict) -> None:
        self.building.openings[door["id"]] = door
        self.building.data["openings"].append(door)
        self._refresh(door["space_ids"])

    def _drop_opening(self, opening_id: str) -> None:
        gone = self.building.openings.pop(opening_id, None)
        self.building.data["openings"][:] = [o for o in self.building.data["openings"] if o["id"] != opening_id]
        self._refresh(gone["space_ids"] if gone else ())

    def _door_between(self, first: str, second: str) -> str | None:
        """The opening that joins two named rooms (an opening id is accepted for either argument)."""
        b = self.building
        if first in b.openings and not second:
            return first
        a, c = self.space(first), self.space(second)
        found = [o["id"] for o in b.openings.values() if o["kind"] in ("door", "opening") and set(o["space_ids"]) == {a, c}]
        return found[0] if len(found) == 1 else (None if not found else found[0])

    def remove_door(self, first: str, second: str = "") -> dict:
        """Wall up a door or opening (by its id, or by the two rooms it joins)."""
        b = self.building
        opening_id = self._door_between(first, second)
        if opening_id is None:
            return {"error": "There is no door between those two rooms."}
        opening = b.openings[opening_id]
        if opening["kind"] == "entrance":
            return {"error": "That is a building entrance and cannot be removed."}
        before = self.impact_snapshot()
        self._drop_opening(opening_id)
        impact = self.impact(before)
        self.edits.append({"op": "remove_door", "door": opening})
        self._undo.append(lambda: self._insert_opening(opening))
        self.emit("edit", op="remove_door", door=opening, impact=impact)
        return {"removed": opening_id, "between": [b.label(s) for s in opening["space_ids"]], "impact": impact}

    def add_asset(self, name: str, kind: str, room: str) -> dict:
        """Put a new item (machine, desk, ...) in a room."""
        b = self.building
        space_id = self.space(room)
        from floorwise.core.graph import anchor

        x, y = anchor(b, space_id)
        number = 1 + sum(1 for edit in self.edits if edit["op"] == "add_asset")
        record = {"id": f"{b.spaces[space_id]['floor_id']}-A-new{number}", "name": name.strip() or kind, "category": "equipment",
                  "type": R.normalise(kind).replace(" ", "_") or "item", "space_id": space_id,
                  "floor_id": b.spaces[space_id]["floor_id"], "position": [round(x, 3), round(y, 3)], "source": "user"}
        b.assets[record["id"]] = record
        b.data["assets"].append(record)
        self.edits.append({"op": "add_asset", "asset": record})
        self._undo.append(lambda: self._drop_asset(record["id"]))
        self._refresh()
        self.emit("edit", op="add_asset", asset=record["id"], to=space_id)
        return {"added": record["name"], "id": record["id"], "in": b.label(space_id)}

    def _drop_asset(self, asset_id: str) -> None:
        self.building.assets.pop(asset_id, None)
        self.building.data["assets"][:] = [a for a in self.building.data["assets"] if a["id"] != asset_id]
        self._refresh()

    def remove_asset(self, asset: str) -> dict:
        b = self.building
        asset_id = self._asset_id(asset)
        if isinstance(asset_id, dict):
            return asset_id
        record = b.assets[asset_id]
        self._drop_asset(asset_id)
        self.edits.append({"op": "remove_asset", "asset": record})
        self._undo.append(lambda: (b.assets.__setitem__(record["id"], record), b.data["assets"].append(record), self._refresh()))
        self.emit("edit", op="remove_asset", asset=asset_id)
        return {"removed": record["name"], "from": b.label(record["space_id"])}

    def undo(self) -> dict:
        """Revert the most recent edit (door added/removed/widened, item moved/added/removed)."""
        if not self._undo or not self.edits:
            return {"error": "There is nothing to undo."}
        undone = self.edits.pop()
        self._undo.pop()()
        self.emit("edit", op="undo", undone=undone["op"])
        return {"undone": undone["op"], "remaining_edits": len(self.edits)}

    def _asset_id(self, asset: str):
        b = self.building
        if asset in b.assets:
            return asset
        match = next((a["id"] for a in b.assets.values() if R.normalise(a["name"]) == R.normalise(asset)), None)
        if match:
            return match
        found = self.search(asset)["assets"]
        if len(found) != 1:
            return {"error": f"Which item is '{asset}'?", "candidates": found[:8]}
        return found[0]["id"]

    def move_asset(self, asset: str, to: str) -> dict:
        b = self.building
        asset_id = self._asset_id(asset)
        if isinstance(asset_id, dict):
            return asset_id
        space_id = self.space(to)
        from floorwise.core.graph import anchor

        x, y = anchor(b, space_id)
        record = b.assets[asset_id]
        old = record["space_id"]
        previous = {k: record[k] for k in ("space_id", "floor_id", "position")}
        record.update(space_id=space_id, floor_id=b.spaces[space_id]["floor_id"], position=[round(x, 3), round(y, 3)])
        self.edits.append({"op": "move_asset", "asset": asset_id, "from": old, "to": space_id})
        self._undo.append(lambda: (record.update(previous), self._refresh()))
        from floorwise.core.walk import invalidate
        invalidate(self.building)
        self.last_route = None
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
            snapshots["your_needs"] = ops.distances_to_exit(self.building, replace(self.constraints(), outside="exits", extra_openings=extra))
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
        self._undo.append(lambda: (opening.__setitem__("width_m", old), self._refresh()))
        self.last_route = None
        self.emit("edit", **receipt)
        return receipt

    def weak_points(self, step_free: bool = True) -> list[dict]:
        from floorwise.core.resilience import chaos_test
        result = chaos_test(self.building, replace(self.constraints(step_free=step_free), outside="exits"))
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
            "distance_basis": "route-model metres including connector penalties, not physical walking distance",
            "of_rooms": sum(s in before for s in rooms), "cut_off_ids": cut_off,
            "cut_off_by_floor": [{"floor":b.floor_name(fid),"count":sum(b.spaces[s]['floor_id']==fid for s in cut_off),
                                  "total_rooms":sum(b.spaces[s]['floor_id']==fid for s in rooms)} for fid in b.floors
                                 if any(b.spaces[s]['floor_id']==fid for s in cut_off)],
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
