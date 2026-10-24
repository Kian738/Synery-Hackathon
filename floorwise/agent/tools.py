"""The agent's tools: thin, typed wrappers around Session, provider-neutral (floorwise.llm.tools).
Results are compact JSON; errors become is_error tool results with candidates, so the model can ask
the person instead of guessing."""

import json

from floorwise.llm.tools import ToolFailure as ToolError
from floorwise.llm.tools import tool as beta_tool

from floorwise.agent.session import Session
from floorwise.core.resolve import ResolveError
from floorwise.core.routing import NoRoute


def as_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def guarded(function):
    def call(*args, **kwargs):
        try:
            result = function(*args, **kwargs)
        except ResolveError as error:
            raise ToolError(as_json({"error": str(error), "candidates": error.candidates[:8]})) from error
        except (NoRoute, ValueError, KeyError) as error:
            raise ToolError(str(error)) from error
        if isinstance(result, dict) and "error" in result:
            raise ToolError(as_json(result))
        return as_json(result)

    return call


def make_tools(session: Session, allow_edits: bool = True) -> list:
    @beta_tool
    def building_overview() -> str:
        """Floors, stairs and lifts, entrances, room types, current closures and what we know about the person."""
        return guarded(session.overview)()

    @beta_tool
    def search(query: str, floor: str | None = None) -> str:
        """Find rooms and things (furniture, machines, equipment) by name, room number or type.

        Args:
            query: Words to look for, e.g. "3d printer", "2.03", "toilet", "coffee machine", "press".
            floor: Optional floor, e.g. "ground floor", "floor 2", "basement 1".
        """
        return guarded(session.search)(query, floor)

    @beta_tool
    def room_info(room: str) -> str:
        """Facts about one room: area, centre (x, y, elevation), doors with widths, contents, rooms sharing a
        wall, and the rooms directly above and below.

        Args:
            room: Room name with floor, e.g. "Office 0.29 (Ground floor)", a room number, or an item name.
        """
        return guarded(session.room_info)(room)

    @beta_tool
    def find_route(
        destination: str,
        start: str | None = None,
        via: list[str] | None = None,
        step_free: bool | None = None,
        min_door_width_m: float | None = None,
        avoid: list[str] | None = None,
        prefer_avoid: list[str] | None = None,
        avoid_stairs: bool = False,
        avoid_lifts: bool = False,
    ) -> str:
        """Shortest walking route with turn-by-turn steps and metres; draws it on the map.

        Args:
            destination: Where they want to go: room name/number, an item ("the 3D printer") or a kind of room ("toilet"); the nearest match is chosen.
            start: Where the person is: room name/number or an item name. Omit if remembered.
            via: Places to visit in order on the way (multi-stop tour).
            step_free: True for wheelchair, pram, trolley, crutches or "no stairs". Omit to use the person's profile.
            min_door_width_m: Every door must be at least this wide (wide loads).
            avoid: Rooms or room types the route must never enter, e.g. ["production_zone", "Lab 0.12"].
            prefer_avoid: Rooms or room types to avoid if reasonably possible (soft), e.g. quiet routes.
            avoid_stairs: Do not use staircases (lifts allowed).
            avoid_lifts: Do not use lifts.
        """
        return guarded(session.route)(
            start, destination, via, step_free=step_free, min_door_width_m=min_door_width_m, avoid=avoid,
            prefer_avoid=prefer_avoid, avoid_stairs=avoid_stairs, avoid_lifts=avoid_lifts,
        )

    @beta_tool
    def reachable_rooms(start: str, floor: str, step_free: bool | None = None, min_door_width_m: float | None = None) -> str:
        """How many rooms on a floor can be reached from a start room under constraints (closures apply).

        Args:
            start: Start room (e.g. the entrance lobby).
            floor: Floor to count rooms on.
            step_free: Only step-free connections (no stairs or steps; lifts fine).
            min_door_width_m: Every door passed must be at least this wide.
        """
        return guarded(session.reachable)(start, floor, step_free=step_free, min_door_width_m=min_door_width_m)

    @beta_tool
    def rank_rooms(floor: str, room_type: str) -> str:
        """All rooms of one type on a floor, largest first, with areas and the total area.

        Args:
            floor: e.g. "floor 1".
            room_type: e.g. "meeting room", "office", "kitchen".
        """
        return guarded(session.rank_rooms)(floor, room_type)

    @beta_tool
    def nearest(start: str, what: str, step_free: bool | None = None) -> str:
        """Nearest rooms (by walking distance) that hold an item type or are of a room type.

        Args:
            start: Where the person is.
            what: An item type ("fire extinguisher", "coffee machine") or room type ("toilet").
            step_free: Only step-free connections.
        """
        return guarded(session.nearest)(start, what, step_free=step_free)

    @beta_tool
    def remember_person(step_free: bool | None = None, min_door_width_m: float | None = None, location: str | None = None) -> str:
        """Remember the person's needs and location for every later answer (so they never repeat themselves).

        Args:
            step_free: They need step-free routes (wheelchair, crutches, pram, trolley).
            min_door_width_m: They move something this wide.
            location: Where they are now (room name or number).
        """
        profile = session.profile
        if step_free is not None:
            profile.step_free = step_free
        if min_door_width_m is not None:
            profile.min_door_width_m = min_door_width_m
        if location is not None:
            try:
                profile.location = session.place(location)
            except ResolveError as error:
                raise ToolError(as_json({"error": str(error), "candidates": error.candidates[:8]})) from error
        session.emit("profile", profile=profile.__dict__)
        return as_json(profile.__dict__)

    tools = [building_overview, search, room_info, find_route, reachable_rooms, rank_rooms, nearest, remember_person]

    if allow_edits:

        @beta_tool
        def set_closed(element: str, closed: bool) -> str:
            """Close or reopen a lift, staircase, door or room; returns which rooms lose or regain a way out.

            Args:
                element: e.g. "Lift 1", "the east lift", "Office staircase", a room name.
                closed: True to close, False to reopen.
            """
            return guarded(session.set_closed)(element, closed)

        @beta_tool
        def add_door(first_room: str, second_room: str, confirm: bool = False) -> str:
            """Add a door in the middle of the wall two rooms share. With confirm=false it only previews the
            change and its effect; call again with confirm=true once the person agrees.

            Args:
                first_room: Room name/number.
                second_room: Neighbouring room on the same floor.
                confirm: Apply the edit (true) or just preview it (false).
            """
            if confirm:
                return guarded(session.add_door)(first_room, second_room)
            return guarded(session.door_preview)(first_room, second_room)

        @beta_tool
        def move_item(item: str, to_room: str) -> str:
            """Record that a machine or item now stands in another room ("the drum is now in 0.21").

            Args:
                item: Item name, e.g. "Steel drum 0.14-A" or "the 3D printer".
                to_room: Room it is now in.
            """
            return guarded(session.move_asset)(item, to_room)

        tools += [set_closed, add_door, move_item]
    return tools
