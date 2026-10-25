"""Routing between buildings: POST /api/campus/route.

Indoor legs and the choice of entrances come from floorwise.core.campus (deterministic). The outdoor leg asks
OpenRouteService first (ORS_API_KEY, base URL ORS_API_URL, default api.heigit.org), then the public OSRM routers of
routing.openstreetmap.de (no key), then falls back to a straight-line estimate that the response labels as such.
Modes: foot, wheelchair, bike, car. Only the pruned few entrance pairs are sent out, and answers are cached."""

import os
from typing import Literal

import httpx
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from floorwise.agent.session import Session
from floorwise.core import campus
from floorwise.core.resolve import ResolveError
from server.georef import GEOREF

router = APIRouter()
_cache: dict[tuple, campus.Outdoor] = {}
_ors_refused: str | None = None  # set when ORS rejects the key, so we stop calling it for this process

ORS_PROFILES = {"foot": "foot-walking", "wheelchair": "wheelchair", "bike": "cycling-regular", "car": "driving-car"}
OSRM_INSTANCES = {"foot": "routed-foot", "wheelchair": "routed-foot", "bike": "routed-bike", "car": "routed-car"}
USER_AGENT = "floorwise-hackathon/1.0 (student project)"

Mode = Literal["foot", "wheelchair", "bike", "car"]


class CampusRouteRequest(BaseModel):
    from_building: str
    to_building: str
    from_room: str | None = None
    to_room: str | None = None
    min_door_width_m: float | None = None
    mode: Mode = "foot"


def _maneuver_text(step: dict) -> str:
    maneuver, name = step["maneuver"], step.get("name") or ""
    kind, modifier = maneuver.get("type", ""), maneuver.get("modifier", "")
    onto = f" onto {name}" if name else ""
    if kind == "depart":
        return f"Head {modifier or 'out'}{onto}".strip()
    if kind == "arrive":
        return "You have reached the entrance"
    if kind in ("turn", "end of road", "fork", "on ramp", "off ramp"):
        return f"Turn {modifier}{onto}".strip() if modifier else f"Continue{onto}"
    if kind in ("roundabout", "rotary"):
        return f"At the roundabout, take exit {maneuver.get('exit', '')}{onto}".strip()
    return f"Continue{onto}" if not modifier else f"Continue {modifier}{onto}"


def _ors(profile_mode: str, first: campus.Entrance, second: campus.Entrance, key: str) -> campus.Outdoor:
    base = os.environ.get("ORS_API_URL", "https://api.heigit.org/openrouteservice").rstrip("/")
    response = httpx.post(
        f"{base}/v2/directions/{ORS_PROFILES[profile_mode]}/geojson",
        headers={"Authorization": key, "Content-Type": "application/json"},
        json={"coordinates": [[first.lon, first.lat], [second.lon, second.lat]], "instructions": True,
              "language": "en", "units": "m"},
        timeout=8,
    )
    response.raise_for_status()
    feature = response.json()["features"][0]
    summary = feature["properties"]["summary"]
    line = feature["geometry"]["coordinates"]
    steps = [{"instruction": s["instruction"], "distance_m": round(s["distance"]), "at": line[min(s["way_points"][0], len(line) - 1)][:2]}
             for s in feature["properties"]["segments"][0]["steps"]]
    return campus.Outdoor(round(summary["distance"], 1), round(summary["duration"] / 60, 3),
                          feature["geometry"]["coordinates"], steps, False,
                          f"OpenRouteService ({ORS_PROFILES[profile_mode]})", profile_mode)


def _osrm(mode: str, first: campus.Entrance, second: campus.Entrance) -> campus.Outdoor:
    response = httpx.get(
        f"https://routing.openstreetmap.de/{OSRM_INSTANCES[mode]}/route/v1/driving/"
        f"{first.lon},{first.lat};{second.lon},{second.lat}",
        params={"overview": "full", "geometries": "geojson", "steps": "true"},
        headers={"User-Agent": USER_AGENT}, timeout=8,
    )
    response.raise_for_status()
    body = response.json()
    if body.get("code") != "Ok":
        raise ValueError(body.get("code", "no route"))
    route = body["routes"][0]
    steps = [{"instruction": _maneuver_text(s), "distance_m": round(s["distance"]), "at": s["maneuver"]["location"]}
             for s in route["legs"][0]["steps"]]
    source = "OpenStreetMap routing (foot, not wheelchair-aware)" if mode == "wheelchair" else f"OpenStreetMap routing ({mode})"
    return campus.Outdoor(round(route["distance"], 1), round(route["duration"] / 60, 3),
                          route["geometry"]["coordinates"], steps, False, source, mode)


def _provider(mode: str, problems: list[str]) -> campus.OutdoorProvider:
    """OpenRouteService, then OSRM, then None (the planner keeps its labelled estimate)."""
    key = os.environ.get("ORS_API_KEY", "")

    def note(text: str) -> None:
        if text not in problems:
            problems.append(text)

    def provider(first: campus.Entrance, second: campus.Entrance) -> campus.Outdoor | None:
        global _ors_refused
        cache_key = (mode, round(first.lat, 5), round(first.lon, 5), round(second.lat, 5), round(second.lon, 5))
        if cache_key in _cache:
            return _cache[cache_key]
        result = None
        if key and not _ors_refused:
            try:
                result = _ors(mode, first, second, key)
            except httpx.HTTPStatusError as error:
                code = error.response.status_code
                if code in (401, 403):
                    _ors_refused = f"OpenRouteService refused the API key (HTTP {code})"
                else:
                    note(f"OpenRouteService answered HTTP {code}.")
            except (httpx.HTTPError, KeyError, IndexError, ValueError) as error:
                note(f"OpenRouteService failed ({type(error).__name__}).")
        if result is None:
            try:
                result = _osrm(mode, first, second)
            except (httpx.HTTPError, KeyError, IndexError, ValueError) as error:
                note(f"No routing service answered ({type(error).__name__}); the outdoor leg is an estimate.")
                return None
        _cache[cache_key] = result
        return result

    # Evaluate lazily so the refusal note is attached once per request, not once per pair.
    def with_notes(first: campus.Entrance, second: campus.Entrance) -> campus.Outdoor | None:
        result = provider(first, second)
        if _ors_refused:
            note(f"{_ors_refused}; used OpenStreetMap routing instead.")
        return result

    return with_notes


def _anchor(building_id: str) -> campus.Anchor:
    if building_id not in GEOREF:
        raise CampusError(422, f"{building_id} has no real-world location; only OSM-sourced buildings can be joined outdoors.")
    return campus.Anchor(*GEOREF[building_id][:2])


def _leg_payload(leg: campus.IndoorLeg | None, building, at: str | None, role: str) -> dict | None:
    if leg is None:
        return None
    return {
        "kind": "indoor", "role": role, "building_id": leg.building_id, "building_name": leg.building_name,
        "distance_m": leg.distance_m, "from": building.label(leg.from_space), "to": building.label(leg.to_space),
        "at": leg.from_space, "target": leg.to_space, "trivial": leg.trivial, "route": leg.route,
        "door": {"opening_id": leg.door.opening_id, "label": leg.door.label, "lat": leg.door.lat, "lon": leg.door.lon,
                 "step_free": leg.door.step_free, "width_m": leg.door.width_m},
    }


class CampusError(Exception):
    """A request the planner cannot serve; status mirrors the HTTP code the endpoint answers with."""

    def __init__(self, status: int, detail) -> None:
        super().__init__(str(detail))
        self.status, self.detail = status, detail


def resolve_building(query: str) -> str:
    """A building id or (part of) its name, among the buildings that have a real-world location."""
    from server.app import manifest  # imported late: server.app includes this router

    if query in GEOREF:
        return query
    q = query.strip().lower()
    names = {r["building_id"]: r["name"] for r in manifest() if r["building_id"] in GEOREF}
    exact = [i for i, n in names.items() if n.lower() == q]
    matches = exact or [i for i, n in names.items() if q and (q in n.lower() or q in i.lower())]
    if len(matches) == 1:
        return matches[0]
    if not matches:
        raise CampusError(404, f"No building with a real-world location matches '{query}'.")
    raise CampusError(409, {"error": f"'{query}' matches several buildings", "which": "building",
                            "candidates": [{"id": i, "label": names[i]} for i in matches[:8]]})


def route_between(body: CampusRouteRequest) -> dict:
    from server.app import load  # imported late: server.app includes this router

    try:
        a, b = load(body.from_building), load(body.to_building)
    except (FileNotFoundError, KeyError) as error:
        raise CampusError(404, f"unknown building: {error}") from error
    if a.id == b.id:
        raise CampusError(422, "Both ends are in the same building: use the normal indoor route.")
    sessions = {a.id: Session(a), b.id: Session(b)}
    spaces: dict[str, str | None] = {}
    for role, building, room in (("from", a, body.from_room), ("to", b, body.to_room)):
        try:
            spaces[role] = sessions[building.id].place(room) if room else None
        except ResolveError as error:
            raise CampusError(409, {"error": str(error), "which": role, "candidates": error.candidates[:8]}) from error
    mode = body.mode
    step_free = mode == "wheelchair"  # the transport mode is the only switch: a wheelchair uses only step-free doors and lifts indoors
    args = {"step_free": step_free, "min_door_width_m": body.min_door_width_m}
    problems: list[str] = []
    try:
        plan = campus.plan_campus(
            a, _anchor(a.id), spaces["from"], b, _anchor(b.id), spaces["to"],
            sessions[a.id].constraints(**args), sessions[b.id].constraints(**args),
            outdoor=_provider(mode, problems), mode=mode,
        )
    except (campus.NoCampusRoute, ValueError) as error:
        raise CampusError(404, str(error)) from error
    if plan.outdoor.estimated:
        problems.insert(0, "Outdoor distance is a straight-line estimate: no routing service answered.")
    if step_free and not (mode == "wheelchair" and plan.outdoor.provider.startswith("OpenRouteService")):
        problems.append("Step-free applies to doors and lifts inside the buildings; the outdoor path is not checked for kerbs or steps.")
    if mode in ("bike", "car"):
        problems.append(f"Outdoor leg by {mode}: the walk from {'parking' if mode == 'car' else 'the bike stand'} to each door is not modelled.")
    first, second = _leg_payload(plan.first, a, None, "exit"), _leg_payload(plan.second, b, None, "entry")
    outdoor = {"kind": "outdoor", "distance_m": plan.outdoor.distance_m, "duration_min": plan.outdoor.duration_min,
               "polyline": plan.outdoor.polyline, "steps": plan.outdoor.steps, "estimated": plan.outdoor.estimated,
               "provider": plan.outdoor.provider, "mode": mode,
               "from": {"building_id": a.id, "label": plan.exit_a.label, "lat": plan.exit_a.lat, "lon": plan.exit_a.lon},
               "to": {"building_id": b.id, "label": plan.entry_b.label, "lat": plan.entry_b.lat, "lon": plan.entry_b.lon}}
    door_to_door_min = sum(leg["distance_m"] for leg in (first, second) if leg) / campus.WALK_SPEED_M_S / 60 + plan.outdoor.duration_min
    return {
        "from_building": {"id": a.id, "name": a.info["name"]}, "to_building": {"id": b.id, "name": b.info["name"]},
        "legs": [leg for leg in (first, outdoor, second) if leg],
        "total_m": plan.total_m, "duration_min": round(door_to_door_min, 1), "mode": mode,
        "entrance_pairs_considered": plan.candidates_considered, "alternatives": plan.alternatives,
        "warnings": problems,
    }


@router.post("/api/campus/route")
def campus_route(body: CampusRouteRequest) -> dict:
    try:
        return route_between(body)
    except CampusError as error:
        raise HTTPException(error.status, error.detail) from error
