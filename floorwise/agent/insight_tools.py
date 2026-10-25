"""Read-only analytical tools and explicitly applied building interventions."""
from dataclasses import replace

from floorwise.core import ops, resolve
from floorwise.core.analytics import shared_wall_lines
from floorwise.llm.tools import tool
from floorwise.reason.report import resolve_exit, scenario_report


def make_insight_tools(session, allow_edits=True, exact_items=False):
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
            visual=session.publish_visual('matches', f'{len(matches)} matching rooms', [m['id'] for m in matches], {'count': len(matches)}, matches)
            return {'total': len(matches), 'result_id':visual['id'], 'matches': matches[:12], 'note': 'No room satisfies all descriptors.' if not matches else 'Choose a matching ID; distinct rooms may need clarification.'}
        return guarded(compute)()

    @tool
    def count_items(item_type: str, floor: str | None = None, room: str | None = None) -> str:
        """Complete computed count, optionally restricted to a floor or room, with per-floor breakdown. Matching item types and scope are returned explicitly."""
        return guarded(session.count_items)(item_type, floor, room, exact=exact_items)

    @tool
    def rank_rooms_by_items(item_type: str, floor: str | None = None, room_type: str | None = None, offset: int = 0, limit: int = 12) -> str:
        """Rank ALL rooms by item count, greatest first, including totals and number tied for first; optional floor and room type. Pages never affect the computed ranking."""
        return guarded(session.rank_by_items)(item_type, floor, room_type, offset, limit)

    @tool
    def filter_rooms(requirements: list[dict], floor: str | None = None, room_type: str | None = None) -> str:
        """Rooms satisfying EVERY requirement. Each requirement: {item_type: string, minimum: integer}. Example projector >=1 AND chairs >=8. Does not infer bookings or seat capacity."""
        return guarded(session.filter_rooms)(requirements, floor, room_type)

    @tool
    def aggregate_stats(floor: str | None = None, room_type: str | None = None, group_by: str = 'floor') -> str:
        """Complete room counts and polygon area totals grouped by floor or room_type. Not seating capacity."""
        return guarded(session.statistics)(floor, room_type, group_by)

    @tool
    def result_page(result_id: str, offset: int = 0, limit: int = 25) -> str:
        """Read another page of a previous complete visual result, without recomputing it."""
        return guarded(session.result_page)(result_id, offset, limit)

    @tool
    def capabilities() -> str:
        """State exactly what data is supplied and which queries are supported; never infer access rules or availability."""
        return '{"supported":["counts","room item rankings","compound contents","areas","routes","closures","shared walls","stacking","3D distance"],"unavailable":["bookings","live position","seat capacity","opening hours","window geometry","surveyed stair flights"]}'

    @tool
    def shared_walls(room: str) -> str:
        """Count neighbouring rooms sharing at least 1 m of wall; excludes corridors, stairs and lifts."""
        def compute():
            b=session.building; sid=session.space(room)
            result=ops.shared_walls_count(b,sid)
            neighbours=[n['space_id'] for n in result['neighbours']]
            session.publish_visual('shared_walls', 'Rooms sharing a qualifying wall', [sid,*neighbours], {'count':result['count']},
                                   [{'id':n,'label':b.label(n)} for n in neighbours], lines=shared_wall_lines(b,sid))
            return result
        return guarded(compute)()

    @tool
    def stacked_room(room: str, direction: str) -> str:
        """Room directly above or below, computed by maximum polygon overlap; shows the aligned floor slices."""
        def compute():
            if direction not in ('above','below'):raise ValueError('direction must be above or below')
            b=session.building;sid=session.space(room);result=ops.room_stacked(b,sid,direction)
            if 'error' in result:return result
            target=result['space_id']
            session.publish_visual('stacking',f'Room {direction} {b.label(sid)}',[sid,target],result,
                                   [{'id':target,'label':b.label(target),'overlap_m2':result['overlap_m2']}])
            return {'room':b.label(target),**result}
        return guarded(compute)()

    @tool
    def distance_3d(room_a: str, room_b: str) -> str:
        """Exact straight-line distance between polygon centroids at floor elevations; not a walking route."""
        def compute():
            from floorwise.core.geometry import centroid_3d
            b=session.building;a=session.space(room_a);c=session.space(room_b)
            result=ops.straight_line_3d(b,a,c)
            session.publish_visual('distance', 'Straight-line 3D measurement (not a walking route)', [a,c], result,
                                   lines=[{'a': list(centroid_3d(b,a)), 'b':list(centroid_3d(b,c))}])
            return result
        return guarded(compute)()

    @tool
    def errand(start: str, item_type: str, target_room_type: str, floor: str, stairs_ok: bool = True) -> str:
        """Fetch the nearest item then visit the largest room of a type. Returns route-model metres, not walking metres."""
        def compute():
            b = session.building
            c = replace(session.constraints(), no_stairs=not stairs_ok)
            result = ops.errand(b, session.place(start), resolve.resolve_asset_type(b, item_type),
                                resolve.resolve_floor(b, floor), resolve.resolve_room_type(b, target_room_type), c)
            if 'error' not in result:
                ids=[session.place(start),result['pickup_space_id'],result['target_space_id']]
                session.publish_visual('matches','Errand stops in order',ids,{},[{'id':sid,'label':b.label(sid),'stop':i+1} for i,sid in enumerate(ids)])
            return {**result, "distance_basis": "route-model metres including connector penalties"}
        return guarded(compute)()

    @tool
    def door_effect(room_a: str, room_b: str, on_floor: str) -> str:
        """Read-only benchmark-style what-if: number of rooms on a floor whose nearest exit improves by more than 1 m. Never edits the building."""
        def compute():
            b=session.building;a=session.space(room_a);c=session.space(room_b)
            result=ops.what_if_door(b,a,c,resolve.resolve_floor(b,on_floor),constraints=session.constraints())
            if 'error' in result:return result
            affected=[r['space_id'] for r in result['improved']]
            session.publish_visual('intervention','Hypothetical door: before / after exit distances',[a,c,*affected],
                                   {'count':result['count'],'proposed_opening':{'position':result['door_position'],'floor_id':b.spaces[a]['floor_id'],'space_ids':[a,c],'width_m':.9}},
                                   [{'id':r['space_id'],'label':b.label(r['space_id']),'before_m':r['before_m'],'after_m':r['after_m']} for r in result['improved']],
                                   warnings=['Hypothetical only. Distances include route-model connector penalties. No building edit applied.'])
            return result
        return guarded(compute)()

    @tool
    def weak_points(step_free: bool = True) -> str:
        """Simulate individual closures and rank the three largest groups by rooms losing exit access."""
        return guarded(session.weak_points)(step_free)

    @tool
    def apply_fix(opening_id: str, width_m: float) -> str:
        """Record an approved hypothetical door widening. Only after explicit agreement; does not perform physical work."""
        # Explicit tool arguments remain validated by the deterministic session operation.
        return guarded(session.widen_door)(opening_id, width_m)

    @tool
    def plan_scenario(hazard_rooms: list[str], audience: str = "safety_officer", responders: bool = True,
                      exit_limits: list[dict] | None = None) -> str:
        """Evacuation with a hazard in the named rooms: exact evacuation time, exits used, the bottleneck, a responder route that does not clash with evacuees, and verified door fixes. Every number is re-solved by checked steps; if a step cannot be answered the reply names it. Audience: occupant, safety_officer, builder or regulator. exit_limits caps an exit, for example [{"exit": "Main lobby", "max_people": 10}] when an entrance only takes 10 people; the rest are routed elsewhere. Also shows the result in the 3D twin."""
        def run():
            spaces = [resolve.resolve_space(session.building, room).id for room in hazard_rooms]
            spec = {"hazards": [{"spaces": spaces}], "responders": {"auto": responders},
                    "capacities": [{"element": resolve_exit(session.building, str(limit["exit"])), "kind": "total_persons",
                                    "value": int(limit["max_people"])} for limit in exit_limits or []]}
            report = scenario_report(session.building, "evacuation", {"spec": spec}, audience)
            session.emit("scenario_result", report=report, hazard=spaces[0])
            if report["evacuation"]:  # the per-step movement table is for the 3D replay, not for the model's context
                return {**report, "evacuation": {k: v for k, v in report["evacuation"].items() if k != "schedule"}}
            return report
        return guarded(run)()

    @tool
    def scenario_replay(action: str, seconds: int | None = None) -> str:
        """Control the evacuation replay in the twin after plan_scenario: action is play, pause, restart or seek (with seconds)."""
        if action not in ("play", "pause", "restart", "seek"):
            raise ValueError("action must be play, pause, restart or seek")
        session.emit("scenario_replay", action=action, seconds=seconds)
        return "ok"

    return [find_places, count_items, rank_rooms_by_items, filter_rooms, aggregate_stats, result_page, capabilities, shared_walls, stacked_room, distance_3d, errand, door_effect, weak_points, plan_scenario, scenario_replay] + ([apply_fix] if allow_edits else [])
