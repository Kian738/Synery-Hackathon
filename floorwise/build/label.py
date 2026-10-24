"""Name and type rebuilt rooms with Claude vision, using set-of-mark prompting: every detected region gets a
numbered mark drawn on the plan, and Claude reads the label printed in each numbered region."""

import base64
import io
import os
from pathlib import Path
from typing import Literal

import anthropic
from PIL import Image, ImageDraw
from pydantic import BaseModel

from floorwise.build.from_image import FloorScan

MODEL = os.environ.get("FLOORWISE_VISION_MODEL", "claude-opus-5-5")
ROOM_TYPES = (
    "bedroom living_room kitchen bathroom toilet storage corridor balcony stairwell lift office meeting_room "
    "seminar_room lecture_hall lab makerspace library server_room technical_room lobby canteen shop print_room "
    "locker_room production_zone additive_zone assembly_zone warehouse_zone logistics_zone quality_lab generic_room"
).split()


class RegionLabel(BaseModel):
    mark: int
    name: str
    ref: str | None
    type: Literal["room", "corridor", "hall", "stair", "lift", "outdoor"]
    room_type: str


class PlanLabels(BaseModel):
    floor_name: str | None
    regions: list[RegionLabel]


def annotate(image_path: Path, floor_scan: FloorScan, scale: int = 2) -> bytes:
    image = Image.open(image_path).convert("RGB")
    image = image.resize((image.width * scale, image.height * scale), Image.LANCZOS)
    draw = ImageDraw.Draw(image)
    for region in floor_scan.regions:
        x, y = region.centre_px[0] * scale, region.centre_px[1] * scale
        # Put the mark slightly below the centre so the printed label stays readable.
        y += 14
        text = str(region.index)
        draw.rounded_rectangle((x - 11, y - 9, x + 11 + 6 * (len(text) - 1), y + 9), radius=5, fill=(220, 30, 60))
        draw.text((x - 5, y - 7), text, fill=(255, 255, 255))
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def label_with_vision(image_path: Path, floor_scan: FloorScan, client: anthropic.Anthropic | None = None) -> dict[int, dict]:
    client = client or anthropic.Anthropic()
    data = base64.standard_b64encode(annotate(image_path, floor_scan)).decode()
    response = client.messages.parse(
        model=MODEL,
        max_tokens=16000,
        output_config={"effort": "low"},
        output_format=PlanLabels,
        messages=[{
            "role": "user",
            "content": [
                {"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": data}},
                {"type": "text", "text": (
                    "This is a floor plan. Every detected space has a red numbered mark. For each mark, read the "
                    "room label printed in that space (e.g. '0.21' or 'H-A3'), give a full name (e.g. 'Office 0.21'), "
                    "the ref (the number part, or null), the space type, and a room_type from: "
                    + ", ".join(ROOM_TYPES) + ". Use the colours and shapes: long thin grey spaces are corridors; "
                    "large yellow spaces are halls (production, assembly, warehouse, logistics zones). "
                    f"Marks: {', '.join(str(r.index) for r in floor_scan.regions)}."
                )},
            ],
        }],
    )
    if response.parsed_output is None:
        return {}
    known = {r.index for r in floor_scan.regions}
    return {
        label.mark: {"name": label.name, "ref": label.ref, "type": label.type,
                     "room_type": label.room_type if label.room_type in ROOM_TYPES else None}
        for label in response.parsed_output.regions if label.mark in known
    }
