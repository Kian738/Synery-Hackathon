"""CLI entrypoint for Talk to Your Building Interactive Visualizer.

Usage:
    python -m visualizer [building_dir] [--port 8000] [--no-browser]
    uv run python -m visualizer data/dev/proc-factory-dev-003 --port 8080
"""

from __future__ import annotations

import argparse
import sys
import threading
import time
import webbrowser
from pathlib import Path

from .server import create_server


def main() -> None:
    """Parse command line arguments and launch the visualizer HTTP server."""
    parser = argparse.ArgumentParser(
        prog="python -m visualizer",
        description="Interactive 2D/3D Multi-Floor Building Visualizer & Operational Dispatcher",
    )
    parser.add_argument(
        "building_dir",
        nargs="?",
        default=None,
        help="Path to building directory containing building.json (default: proc-factory-dev-003)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8000,
        help="Port number to listen on (default: 8000)",
    )
    parser.add_argument(
        "--host",
        type=str,
        default="127.0.0.1",
        help="Host address to bind (default: 127.0.0.1)",
    )
    parser.add_argument(
        "--no-browser",
        action="store_true",
        help="Do not automatically launch web browser on startup",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable verbose HTTP request logging",
    )

    args = parser.parse_args()

    if args.verbose:
        import os
        os.environ["VISUALIZER_VERBOSE"] = "1"

    building_path = Path(args.building_dir) if args.building_dir else None

    # Instantiate server
    server = create_server(
        host=args.host,
        port=args.port,
        initial_building_dir=building_path,
    )

    url = f"http://{args.host}:{args.port}"
    active_b = server.service.current_building
    b_name = active_b.name if active_b else "None"
    b_id = active_b.id if active_b else "None"
    floors_count = len(active_b.floors) if active_b else 0
    spaces_count = len(active_b.spaces) if active_b else 0

    print("=" * 72)
    print("   TALK TO YOUR BUILDING // INTERACTIVE DISPATCH VISUALIZER")
    print("=" * 72)
    print(f"  • Local Web Server:  {url}")
    print(f"  • Active Building:   {b_name} ({b_id})")
    print(f"  • Elevation Levels:  {floors_count} floors")
    print(f"  • Spatial Entities:  {spaces_count} rooms & corridors")
    print(f"  • Available Datasets: {len(server.service.available_buildings)} buildings indexed")
    print("=" * 72)
    print("  REST API Endpoints:")
    print(f"    - GET  {url}/api/buildings")
    print(f"    - GET  {url}/api/building?id=<building_id>")
    print(f"    - POST {url}/api/route")
    print(f"    - POST {url}/api/closures")
    print(f"    - POST {url}/api/door")
    print(f"    - POST {url}/api/voice_command")
    print("=" * 72)
    print("  Interactive Capabilities:")
    print("    - 3D Multi-Floor Stacked & Exploded View (1.0x - 4.0x)")
    print("    - 2D Orthographic Top-Down Layout")
    print("    - Animated 3D Route Tube & Traveling Beacon")
    print("    - Dynamic Connector / Space Closures")
    print("    - Synthetic Door Placement (<= 0.6 m)")
    print("    - Hands-Free Web Speech Recognition & Audio Guidance")
    print("=" * 72)
    print("Press Ctrl+C to terminate.")

    # Open browser
    if not args.no_browser:
        def _open():
            time.sleep(0.4)
            webbrowser.open(url)

        threading.Thread(target=_open, daemon=True).start()

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down visualizer server...")
        server.shutdown()
        server.server_close()
        print("Server stopped.")


if __name__ == "__main__":
    main()
