"""Turn solver results into a reply whose last 'Answer:' line the official scorer can read."""


def number(value: float, decimals: int = 2) -> str:
    text = f"{value:.{decimals}f}".rstrip("0").rstrip(".")
    return text or "0"


def space_label(building, space_id: str) -> str:
    """Full name, which always contains the ref when the space has one."""
    space = building.spaces[space_id]
    name = space.get("name") or ""
    ref = space.get("ref") or ""
    if ref and ref not in name:
        return f"{name} {ref}".strip()
    return name or ref or space_id
