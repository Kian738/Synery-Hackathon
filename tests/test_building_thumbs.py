"""Building Atlas thumbnails: valid, deterministic isometric SVG for every kind of building."""
import xml.etree.ElementTree as ET

from fastapi.testclient import TestClient

from server.app import app

client = TestClient(app)
SAMPLES = ["proc-campus-test-013", "proc-factory-dev-003", "swiss-1785", "osm-way27917482"]


def test_thumbnails_are_valid_svg_with_one_layer_per_floor():
    for building in SAMPLES:
        response = client.get(f"/api/buildings/{building}/thumb.svg")
        assert response.status_code == 200 and response.headers["content-type"].startswith("image/svg+xml")
        root = ET.fromstring(response.text)
        assert root.tag.endswith("svg") and root.attrib["viewBox"] == "0 0 240 150"
        polygons = [e for e in root.iter() if e.tag.endswith("polygon")]
        floors = len(client.get(f"/api/buildings/{building}").json()["floors"])
        assert len(polygons) >= floors


def test_thumbnails_are_deterministic_and_unknown_buildings_404():
    one = client.get("/api/buildings/swiss-1785/thumb.svg").text
    assert one == client.get("/api/buildings/swiss-1785/thumb.svg").text
    assert client.get("/api/buildings/does-not-exist/thumb.svg").status_code == 404
