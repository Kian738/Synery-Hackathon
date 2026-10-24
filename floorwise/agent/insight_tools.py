"""Read-only analytical tools and explicitly applied building interventions."""
from dataclasses import replace

from floorwise.core import ops, resolve
from floorwise.llm.tools import tool


def make_insight_tools(session, allow_edits=True):
    # Import lazily: tools.py registers this module after defining guarded.
    from floorwise.agent.tools import guarded

    @tool
    def find_places(room_type: str | None = None, floor: str | None = None, contains_item: str | None = None,
                    relative_to: str | None = None, relation: str | None = None) -> str:
        """Find rooms satisfying ALL descriptors, e.g. an office upstairs containing a coffee machine. relation is above/below relative_to; never guesses a missing feature."""
        def compute():
            b = session.building
            rooms = list(b.spaces.values())
            if room_type:
                kind = resolve.resolve_room_type(b, room_type)
                rooms = [s for s in rooms if s['room_type'] == kind]
            if floor:
                fid = resolve.resolve_floor(b, floor)
                rooms = [s for s in rooms if s['floor_id'] == fid]
            if contains_item:
                kind = resolve.resolve_asset_type(b, contains_item)
                holders = {a['space_id'] for a in b.assets.values() if a['type'] == kind}
                rooms = [s for s in rooms if s['id'] in holders]
            if relation:
                if relation not in ('above', 'below'):
                    raise ValueError('relation must be above or below')
                at = session.place(relative_to) if relative_to else session.profile.location
                if not at:
                    raise ValueError('A reference location is needed to interpret upstairs or downstairs.')
                level = b.level(b.spaces[at]['floor_id'])
                rooms = [s for s in rooms if (b.level(s['floor_id']) > level if relation == 'above' else b.level(s['floor_id']) < level)]
            matches = [{'id': s['id'], 'label': b.label(s['id'])} for s in rooms]
            session.emit('highlight', ids=[m['id'] for m in matches[:12]])
            return {'total': len(matches), 'matches': matches[:12], 'note': 'No room satisfies all descriptors.' if not matches else 'Choose a matching ID; distinct rooms may need clarification.'}
        return guarded(compute)()

    @tool
    def count_items(item_type: str, floor: str) -> str:
        """Exact count of an item type on a floor, without search-result truncation."""
        def compute():
            kind = resolve.resolve_asset_type(session.building, item_type)
            floor_id = resolve.resolve_floor(session.building, floor)
            return {"count": sum(a['type'] == kind and a['floor_id'] == floor_id for a in session.building.assets.values()),
                    "item_type": kind, "floor": session.building.floor_name(floor_id)}
        return guarded(compute)()

    @tool
    def shared_walls(room: str) -> str:
        """Count neighbouring rooms sharing at least 1 m of wall; excludes corridors, stairs and lifts."""
        return guarded(lambda: ops.shared_walls_count(session.building, session.space(room)))()

    @tool
    def distance_3d(room_a: str, room_b: str) -> str:
        """Exact straight-line distance between polygon centroids at floor elevations; not a walking route."""
        return guarded(lambda: ops.straight_line_3d(session.building, session.space(room_a), session.space(room_b)))()

    @tool
    def errand(start: str, item_type: str, target_room_type: str, floor: str, stairs_ok: bool = True) -> str:
        """Fetch the nearest item then visit the largest room of a type. Returns route-model metres, not walking metres."""
        def compute():
            b = session.building
            c = replace(session.constraints(), no_stairs=not stairs_ok, outside="free")
            result = ops.errand(b, session.place(start), resolve.resolve_asset_type(b, item_type),
                                resolve.resolve_floor(b, floor), resolve.resolve_room_type(b, target_room_type), c)
            return {**result, "distance_basis": "route-model metres including connector penalties"}
        return guarded(compute)()

    @tool
    def door_effect(room_a: str, room_b: str, on_floor: str) -> str:
        """Read-only benchmark-style what-if: number of rooms on a floor whose nearest exit improves by more than 1 m. Never edits the building."""
        return guarded(lambda: ops.what_if_door(session.building, session.space(room_a), session.space(room_b),
                                                resolve.resolve_floor(session.building, on_floor), constraints=session.constraints()))()

    @tool
    def weak_points(step_free: bool = True) -> str:
        """Simulate individual closures and rank the three largest groups by rooms losing exit access."""
        return guarded(session.weak_points)(step_free)

    @tool
    def apply_fix(opening_id: str, width_m: float) -> str:
        """Record an approved hypothetical door widening. Only after explicit agreement; does not perform physical work."""
        # Explicit tool arguments remain validated by the deterministic session operation.
        return guarded(session.widen_door)(opening_id, width_m)

    return [find_places, count_items, shared_walls, distance_3d, errand, door_effect, weak_points] + ([apply_fix] if allow_edits else [])
