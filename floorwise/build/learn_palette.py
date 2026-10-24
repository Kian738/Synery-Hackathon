"""Learn which plan fill colour means which space type, from the training plans (image + building.json).

  uv run python -m floorwise.build.learn_palette   -> writes floorwise/build/palette.json"""

import collections
import json
from pathlib import Path

import numpy as np
from PIL import Image
from shapely.geometry import Polygon

from floorwise.core.model import Building
from floorwise.paths import DATA

OUTPUT = Path(__file__).with_name("palette.json")


def main() -> None:
    votes: dict[str, collections.Counter] = collections.defaultdict(collections.Counter)
    for path in sorted((DATA / "train").glob("*/building.json")):
        building = Building.load(path.parent)
        for floor in building.floors.values():
            image_path = path.parent / f"floor_{floor['level']}_plain.png"
            if not image_path.exists():
                continue
            image = np.array(Image.open(image_path).convert("RGB"))
            spaces = building.spaces_on(floor["id"])
            from floorwise.build.from_image import scan

            regions = scan(image_path).regions
            if not regions:
                continue
            xs = [c[0] for s in spaces for c in s["polygon"]]
            ys = [c[1] for s in spaces for c in s["polygon"]]
            px = [x for r in regions for x, _ in r.polygon_px]
            py = [y for r in regions for _, y in r.polygon_px]
            scale = ((max(px) - min(px)) / max(1e-9, max(xs) - min(xs)) + (max(py) - min(py)) / max(1e-9, max(ys) - min(ys))) / 2
            for space in spaces:
                point = Polygon(space["polygon"]).representative_point()
                col = int(round(min(px) + (point.x - min(xs)) * scale))
                row = int(round(min(py) + (max(ys) - point.y) * scale))
                if 0 <= row < image.shape[0] and 0 <= col < image.shape[1]:
                    colour = "#%02x%02x%02x" % tuple(int(v) for v in image[row, col])
                    votes[colour][f"{space['type']}|{space['room_type']}"] += 1
    table = {}
    for colour, counter in votes.items():
        total = sum(counter.values())
        if total < 5:
            continue
        (best, count), = counter.most_common(1)
        space_type, room_type = best.split("|")
        table[colour] = {"type": space_type, "room_type": room_type, "share": round(count / total, 3), "n": total,
                         "also": [k for k, _ in counter.most_common(4)[1:]]}
    OUTPUT.write_text(json.dumps(dict(sorted(table.items(), key=lambda kv: -kv[1]["n"])), indent=1), encoding="utf-8")
    print(f"{len(table)} colours -> {OUTPUT}")
    for colour, entry in list(table.items())[:30]:
        print(colour, entry["type"], entry["room_type"], entry["share"], entry["n"])


if __name__ == "__main__":
    main()
