"""Entity linking: words people use ("the floor 2", "Office 0.29 (Ground floor)", "meeting rooms",
"Lift 1", "a coat rack") -> ids in one building. Deterministic, with ranked candidates when unsure, so
the agent can ask back instead of guessing."""

import re
from dataclasses import dataclass, field

from rapidfuzz import fuzz, process

from floorwise.core.model import Building

ORDINALS = {"first": 1, "second": 2, "third": 3, "fourth": 4, "fifth": 5, "sixth": 6, "seventh": 7, "eighth": 8, "ninth": 9}
FUZZY_ACCEPT = 90


class ResolveError(ValueError):
    def __init__(self, message: str, candidates: list[dict] | None = None) -> None:
        super().__init__(message)
        self.candidates = candidates or []


@dataclass
class Resolution:
    id: str
    confidence: float
    alternatives: list[str] = field(default_factory=list)


def normalise(text: str) -> str:
    text = text.lower().replace("_", " ").replace("’", "'")
    text = re.sub(r"\s+", " ", text)
    return text.strip(" .,;:'\"")


# ---------- floors ----------

def floor_level_from_text(text: str) -> int | None:
    t = normalise(text)
    t = re.sub(r"^(the|on|level of)\s+", "", t)
    if t in ("ground floor", "ground", "ground level", "eg", "erdgeschoss", "floor 0", "level 0", "g", "gf"):
        return 0
    match = re.fullmatch(r"(?:basement|underground|ug|level -|floor -|b)\s*-?\s*(\d+)", t)
    if match:
        return -int(match.group(1))
    if t in ("basement", "cellar"):
        return -1
    match = re.fullmatch(r"(?:floor|level|storey|story|og|stock)\s*(-?\d+)", t)
    if match:
        return int(match.group(1))
    match = re.fullmatch(r"(\d+)(?:st|nd|rd|th)?\s*(?:floor|level|storey|og)", t)
    if match:
        return int(match.group(1))
    match = re.fullmatch(r"(\w+)\s+(?:floor|level|storey)", t)
    if match and match.group(1) in ORDINALS:
        return ORDINALS[match.group(1)]
    match = re.fullmatch(r"(\w+)\s+basement", t)
    if match and match.group(1) in ORDINALS:
        return -ORDINALS[match.group(1)]
    return None


def resolve_floor(building: Building, text: str | int) -> str:
    if isinstance(text, int):
        level = text
    else:
        if text in building.floors:
            return text
        for floor in building.floors.values():
            if normalise(floor["name"]) == normalise(text):
                return floor["id"]
        level = floor_level_from_text(text)
    if level is None or level not in building.floors_by_level:
        names = [floor["name"] for floor in sorted(building.floors.values(), key=lambda f: f["level"])]
        raise ResolveError(f"Unknown floor '{text}'. Floors: {', '.join(names)}")
    return building.floors_by_level[level]["id"]


# ---------- spaces ----------

SPACE_WITH_FLOOR = re.compile(r"^(?P<name>.+?)\s*\((?P<floor>[^()]+)\)\s*$")


def resolve_space(building: Building, mention: str, floor_hint: str | None = None) -> Resolution:
    """'Office 0.29 (Ground floor)', 'Office 0.29', '0.29', or a space id."""
    mention = mention.strip()
    if mention in building.spaces:
        return Resolution(mention, 1.0)
    match = SPACE_WITH_FLOOR.match(mention)
    if match and floor_hint is None:
        try:
            floor_hint = resolve_floor(building, match.group("floor"))
            mention = match.group("name")
        except ResolveError:
            pass
    pool = [s for s in building.spaces.values() if floor_hint is None or s["floor_id"] == floor_hint]
    key = normalise(mention)
    exact = [s["id"] for s in pool if normalise(s["name"]) == key]
    if not exact:
        exact = [s["id"] for s in pool if s.get("ref") and normalise(s["ref"]) == key]
    if len(exact) == 1:
        return Resolution(exact[0], 1.0)
    if len(exact) > 1:
        raise ResolveError(
            f"'{mention}' matches {len(exact)} spaces; which one?",
            [{"id": i, "label": building.label(i), "hint": hints.get(i, "")} for i in exact for hints in [distinguishing_hints(building, exact)]],
        )
    # Dictated or typed without dots and brackets ("generic room 0106056" for "Generic room 01.06.056"): same letters and digits, one space.
    squash = lambda text: "".join(ch for ch in normalise(text) if ch.isalnum())
    flat = squash(mention)
    if flat:
        loose = [s["id"] for s in pool if squash(s["name"]) == flat]
        if len(loose) == 1:
            return Resolution(loose[0], 0.97)
    # "room 0.29", "the 2.04 lab": a token that is a room number settles it when unique on the floor.
    refs = [t for t in key.split() if any(ch.isdigit() for ch in t)]
    for token in refs:
        by_ref = [s["id"] for s in pool if s.get("ref") and normalise(s["ref"]) == token]
        if len(by_ref) == 1:
            return Resolution(by_ref[0], 0.95)
    choices = {s["id"]: normalise(f"{s['name']} {s.get('ref') or ''}") for s in pool}
    ranked = process.extract(key, choices, scorer=fuzz.token_set_ratio, limit=5)
    if ranked and ranked[0][1] >= FUZZY_ACCEPT and (len(ranked) == 1 or ranked[0][1] - ranked[1][1] >= 5):
        return Resolution(ranked[0][2], ranked[0][1] / 100, [r[2] for r in ranked[1:]])
    raise ResolveError(
        f"No space matches '{mention}' exactly.",
        [{"id": r[2], "label": building.label(r[2]), "score": round(r[1])} for r in ranked],
    )


def distinguishing_hints(building: Building, ids: list[str]) -> dict[str, str]:
    """For spaces that share a name: a short phrase each, from what is recorded (neighbour, contents, position on the
    floor plan), so a person can be asked 'the one next to the Kitchen or the one with the printer?' instead of a list
    of identical labels. Only said when it is true of the data; never used to choose between them."""
    from collections import Counter

    from shapely.geometry import Polygon

    names = {i: normalise(building.spaces[i]["name"]) for i in ids}
    hints: dict[str, str] = {}
    for i in ids:
        parts = []
        near = sorted({building.spaces[o]["name"] for op in building.openings.values() if i in op["space_ids"]
                       for o in op["space_ids"] if o != i and o in building.spaces and normalise(building.spaces[o]["name"]) not in names.values()})
        if near:
            parts.append("next to " + ", ".join(near[:2]))
        things = Counter(a["type"].replace("_", " ") for a in building.assets.values() if a["space_id"] == i)
        if things:
            parts.append("with " + ", ".join(f"{n} {t}" for t, n in things.most_common(2)))
        floor_spaces = [x for x in building.spaces.values() if x["floor_id"] == building.spaces[i]["floor_id"] and x.get("polygon")]
        if floor_spaces and building.spaces[i].get("polygon"):
            xs = [Polygon(x["polygon"]).centroid for x in floor_spaces]
            cx, cy = sum(c.x for c in xs) / len(xs), sum(c.y for c in xs) / len(xs)
            c = Polygon(building.spaces[i]["polygon"]).centroid
            side = ("left" if c.x < cx else "right") if abs(c.x - cx) > abs(c.y - cy) * 0.5 else ""
            end = ("top" if c.y > cy else "bottom") if abs(c.y - cy) > abs(c.x - cx) * 0.5 else ""
            if side or end:
                parts.append("on the " + "-".join(x for x in (end, side) if x) + " of the plan")
        hints[i] = "; ".join(parts)
    return hints


# ---------- vocabularies: room types, asset types ----------

def _singular(word: str) -> str:
    if word.endswith("ies"):
        return word[:-3] + "y"
    if word.endswith(("ches", "shes", "sses", "xes")):
        return word[:-2]
    if word.endswith("s") and not word.endswith("ss"):
        return word[:-1]
    return word


def _vocab_match(text: str, vocabulary: set[str], what: str) -> str:
    key = normalise(text)
    key = re.sub(r"^(a|an|the|every|all|each)\s+", "", key)
    candidates = {normalise(v): v for v in vocabulary}
    for attempt in (key, " ".join(_singular(w) for w in key.split()), _singular(key)):
        if attempt in candidates:
            return candidates[attempt]
    if what == "room type":
        # "Office spaces" and "lift rooms" describe the type, not a new
        # dataset-specific category. Preserve exact compound types above first.
        stripped = re.sub(r"\s+(?:spaces?|rooms?)$", "", key)
        for attempt in (stripped, " ".join(_singular(w) for w in stripped.split())):
            if attempt in candidates:
                return candidates[attempt]
    ranked = process.extract(key, list(candidates), scorer=fuzz.ratio, limit=3)
    if ranked and ranked[0][1] >= 78 and (len(ranked) == 1 or ranked[0][1] - ranked[1][1] >= 8):
        return candidates[ranked[0][0]]
    raise ResolveError(f"Unknown {what} '{text}'.", [{"id": candidates[r[0]], "score": round(r[1])} for r in ranked])


def room_types(building: Building) -> set[str]:
    return {space["room_type"] for space in building.spaces.values()}


def asset_types(building: Building) -> set[str]:
    return {asset["type"] for asset in building.assets.values()}


def resolve_room_type(building: Building, text: str) -> str:
    return _vocab_match(text, room_types(building), "room type")


def asset_aliases(building: Building) -> dict[str, str]:
    """Words people use for an item type, from asset names: 'Seating row 0.18-A' -> lecture_seating_row."""
    aliases: dict[str, set[str]] = {}
    for asset in building.assets.values():
        words = [w for w in normalise(asset["name"]).split() if not any(ch.isdigit() for ch in w)]
        if words:
            aliases.setdefault(" ".join(words), set()).add(asset["type"])
    return {alias: next(iter(types)) for alias, types in aliases.items() if len(types) == 1}


def resolve_asset_type(building: Building, text: str) -> str:
    vocabulary = asset_types(building)
    try:
        return _vocab_match(text, vocabulary, "item type")
    except ResolveError as error:
        key = normalise(re.sub(r"^(a|an|the)\s+", "", normalise(text)))
        aliases = asset_aliases(building)
        for attempt in (key, " ".join(_singular(w) for w in key.split())):
            if attempt in aliases:
                return aliases[attempt]
        suffix = [v for v in vocabulary if normalise(v).endswith(" " + key) or normalise(v).endswith(" " + _singular(key))]
        if len(suffix) == 1:
            return suffix[0]
        raise error


# ---------- connectors and closable elements ----------

def resolve_connector(building: Building, text: str) -> str:
    if text in building.connectors:
        return text
    key = normalise(text)
    key = re.sub(r"^the\s+", "", key)
    named = [c["id"] for c in building.connectors.values() if normalise(c["name"]) == key]
    if len(named) == 1:
        return named[0]
    choices = {c["id"]: normalise(f"{c['name']} {c['kind']}") for c in building.connectors.values()}
    ranked = process.extract(key, choices, scorer=fuzz.token_set_ratio, limit=4)
    if ranked and ranked[0][1] >= FUZZY_ACCEPT and (len(ranked) == 1 or ranked[0][1] > ranked[1][1]):
        return ranked[0][2]
    raise ResolveError(
        f"Which stair or lift is '{text}'?",
        [{"id": r[2], "label": building.connectors[r[2]]["name"], "score": round(r[1])} for r in ranked],
    )


def resolve_element(building: Building, text: str) -> str:
    """Anything that can be closed: a lift or staircase, a room or corridor, or an opening id."""
    if text in building.connectors or text in building.spaces or text in building.openings:
        return text
    key = normalise(re.sub(r"^the\s+", "", normalise(text)))
    named = [c["id"] for c in building.connectors.values() if normalise(c["name"]) == key]
    if len(named) == 1:
        return named[0]
    try:
        return resolve_space(building, text).id
    except ResolveError as space_error:
        try:
            return resolve_connector(building, text)
        except ResolveError:
            raise space_error from None


def resolve_avoid(building: Building, text: str) -> tuple[str, str]:
    """('space', id) for one named room, ('type', value) for a kind of room ("production bays", "corridors")."""
    try:
        return "space", resolve_space(building, text).id
    except ResolveError:
        return "type", resolve_room_type(building, text)
