"""Counts old-style (pre control kit) tokens per web component, so the move to the kit can be measured and re-run.

  uv run python scripts/ux_inventory.py            # table
  uv run python scripts/ux_inventory.py --check    # exit 1 if a kit-migrated area gained legacy tokens (used by a test)"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "web" / "src"
LEGACY = re.compile(r"\b(border-ink(?:-\d)?|bg-white|bg-mark|bg-ink-2|font-sign|border-signal|border-mandatory|border-concrete|text-ink-[34]|hover:bg-concrete)\b")
KIT = re.compile(r"\b(k-ctl|k-seg|k-pop|k-card|k-dock|IconButton|Segmented|Popover|Dock)\b")
SKIP = {"lab", "companion"}  # migrated last: counted but not enforced


def inventory() -> list[tuple[str, int, int]]:
    rows = []
    for path in sorted(ROOT.rglob("*.tsx")):
        text = path.read_text(encoding="utf-8")
        legacy, kit = len(LEGACY.findall(text)), len(KIT.findall(text))
        if legacy or kit:
            rows.append((str(path.relative_to(ROOT)).replace("\\", "/"), legacy, kit))
    return sorted(rows, key=lambda r: -r[1])


def main() -> int:
    rows = inventory()
    print(f"{'file':44} {'legacy':>7} {'kit':>5}")
    for name, legacy, kit in rows:
        print(f"{name:44} {legacy:7} {kit:5}")
    total = sum(r[1] for r in rows if r[0].split("/")[0] not in SKIP)
    print(f"\nlegacy tokens outside Lab/companion: {total}")
    if "--check" in sys.argv:
        budget = int((Path(__file__).with_name("ux_budget.txt").read_text().strip() or "0")) if Path(__file__).with_name("ux_budget.txt").exists() else None
        if budget is not None and total > budget:
            print(f"over budget ({budget}): new legacy styling was added")
            return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
