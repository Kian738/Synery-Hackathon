"""Fast, free parser for the question shapes we know. Returns None when a question doesn't fit, so the
Claude parser takes over: rules give determinism on known shapes, Claude gives coverage on new wording."""

import re

from floorwise.agent.spec import QuerySpec

_ORD = r"(?:first|second|third|fourth|fifth|sixth|seventh|eighth|ninth|\d+(?:st|nd|rd|th))"
FLOOR_NAME = (r"(?:ground floor|floor\s*-?\d+|basement\s*\d*|level\s*-?\d+|storey\s*-?\d+|" + _ORD + r"\s+(?:floor|storey|level|basement))")
SPACE = r"(?P<{name}>.+?\(" + FLOOR_NAME + r"\))"  # "Bathroom 0.05 (apartment 2) (Ground floor)"
FLOOR = r"(?:the\s+)?(?P<floor>" + FLOOR_NAME + ")"


def _space(name: str) -> str:
    return SPACE.format(name=name)


PATTERNS: list[tuple[str, re.Pattern]] = [
    ("largest_room", re.compile(rf"which is the largest (?P<room_type>.+?) on {FLOOR}\s*,", re.I)),
    ("floor_area_total", re.compile(rf"total floor area of (?:every|all) (?P<room_type>.+?) on {FLOOR}", re.I)),
    (
        "errand",
        re.compile(
            rf"i'?m in {_space('start')}\.\s*i need to grab an? (?P<asset_type>.+?) from the room that has one closest"
            rf".*?carry it to the largest (?P<room_type>.+?) on {FLOOR}\.(?P<rest>.*)",
            re.I | re.S,
        ),
    ),
    (
        "wide_delivery_count",
        re.compile(
            rf"(?P<width>\d+(?:\.\d+)?)\s*m wide.*?arrives through the entrance into {_space('start')}\."
            rf"\s*into how many rooms on {FLOOR}",
            re.I | re.S,
        ),
    ),
    (
        "step_free_reachable_count",
        re.compile(
            rf"^(?P<closed>.+?) is (?:out of service|closed).*?entrance into {_space('start')}\."
            rf"\s*how many rooms on {FLOOR}",
            re.I | re.S,
        ),
    ),
    ("room_stacked_above", re.compile(rf"(?:ceiling|roof) (?:in|of) {_space('start')}\.\s*which room is directly above", re.I)),
    ("room_stacked_below", re.compile(rf"floor of {_space('start')}\.\s*which room directly below", re.I)),
    ("shared_walls_count", re.compile(rf"soundproofing {_space('start')}\.\s*how many other rooms", re.I)),
    ("straight_line_3d", re.compile(rf"between {_space('first')} and {_space('second')}\.\s*what is the straight-line distance", re.I)),
    (
        "what_if_door",
        re.compile(
            rf"add a door between {_space('first')} and {_space('second')}\s*,.*?how many rooms on {FLOOR}\s+would",
            re.I | re.S,
        ),
    ),
]


BASIC: list[tuple[str, re.Pattern]] = [
    ("locate", re.compile(r"^where is (?:the |a |an )?(?P<item>[^?]+?)\??$", re.I)),
    ("count", re.compile(rf"^how many (?P<item>.+?) items are on {FLOOR}\??$", re.I)),
    ("tour", re.compile(r"^starting at (?P<stops>.+?) in this order\.", re.I)),
    (
        "route",
        re.compile(
            rf"^(?:(?P<closed>.+?) is closed for maintenance\.\s*)?(?P<prefix>how do i get|is there a step-free route)"
            rf" from {_space('start')} to {_space('destination')}\?",
            re.I,
        ),
    ),
]


def parse_basic(text: str) -> QuerySpec | None:
    request = re.fullmatch(
        r"(?:please\s+)?(?:find|show|plan)(?:\s+me)?\s+(?:an?|the)\s+"
        r"(?:(?P<mode>step-free|indoor|walking)\s+)?route\s+from\s+"
        r"(?P<start>.+?)\s+to\s+(?P<destination>.+?)[.?]?", text, re.I,
    )
    if request:
        return QuerySpec(kind="route", start=request["start"], destination=request["destination"],
                         step_free=(request["mode"] or "").lower() == "step-free")
    for kind, pattern in BASIC:
        match = pattern.search(text)
        if not match:
            continue
        groups = match.groupdict()
        if kind in ("locate", "count"):
            return QuerySpec(kind=kind, item=groups["item"].strip(), floor=groups.get("floor"))
        if kind == "tour":
            pieces = re.split(r",\s*visit\s+", groups["stops"], maxsplit=1, flags=re.I)
            if len(pieces) == 2:
                stops = [pieces[0]] + re.split(r",\s*then\s+|,\s*(?=[A-Z])", pieces[1])
            else:  # dictated, no commas: "A (ground floor) visit B (floor 1) then C (floor 4)"
                stops = re.split(r"\s*,?\s*\b(?:visit|then)\b\s+", groups["stops"], flags=re.I)
            stops = [stop.strip() for stop in stops if stop.strip()]
            if len(stops) < 2:
                continue
            return QuerySpec(kind="tour", stops=stops)
        return QuerySpec(
            kind="route", start=groups["start"], destination=groups["destination"], closed=groups.get("closed"),
            step_free="step-free" in groups["prefix"].lower(),
        )
    return None


FORKLIFT = re.compile(r"\bfork[- ]?lifts?\b", re.I)
BAYS = re.compile(r"production (?:bays?|zones?|halls?)[^.?!]{0,100}(?:destination|shortcut|through)|(?:destination|shortcut)[^.?!]{0,80}production (?:bays?|zones?)", re.I)
NO_STAIRS = re.compile(r"\b(?:without|no|avoid(?:ing)?|can'?t (?:use|take)|cannot (?:use|take))\s+(?:the\s+|any\s+)?stairs?\b", re.I)


def with_rules(spec: QuerySpec | None, text: str) -> QuerySpec | None:
    """Route rules stated beside the question (the judges' rule list). Only routes and tours carry them."""
    if spec is None or spec.kind not in ("route", "tour", "errand"):
        return spec
    update = {}
    if FORKLIFT.search(text):
        update["forklift"] = True
    if BAYS.search(text):
        update["bays_destinations"] = True
    if spec.kind != "errand" and NO_STAIRS.search(text):
        update["stairs_allowed"] = False
    return spec.model_copy(update=update) if update else spec


def parse_rules(question: str) -> QuerySpec | None:
    text = " ".join(question.split())
    return with_rules(_parse(text), text)


def _parse(text: str) -> QuerySpec | None:
    basic = parse_basic(text)
    if basic is not None:
        return basic
    for kind, pattern in PATTERNS:
        match = pattern.search(text)
        if not match:
            continue
        groups = {k: (v.strip() if isinstance(v, str) else v) for k, v in match.groupdict().items()}
        spec = {"kind": kind}
        if kind.startswith("room_stacked"):
            spec = {"kind": "room_stacked", "direction": "above" if kind.endswith("above") else "below"}
        for key in ("floor", "room_type", "asset_type", "start", "first", "second", "closed"):
            if groups.get(key):
                spec[key] = groups[key]
        if groups.get("width"):
            spec["min_width"] = float(groups["width"])
        if kind == "errand":
            rest = (groups.get("rest") or "").lower()
            spec["stairs_allowed"] = not ("can't" in rest and "stairs" in rest) and "cannot use the stairs" not in rest
        return QuerySpec(**spec)
    return None
