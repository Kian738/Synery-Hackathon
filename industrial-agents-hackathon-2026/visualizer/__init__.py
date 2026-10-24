"""Interactive Visualizer & Real-Time Operational Dispatcher.

Talk to Your Building — Industrial Agents Hackathon 2026 (Track 01).
Zero-dependency Python standard library HTTP/REST backend and modern
WebGL 2D/3D multi-floor building dashboard with voice navigation.
"""

from __future__ import annotations

from .server import VisualizerServer, create_server, VisualizerService

__version__ = "1.0.0"
__all__ = ["VisualizerServer", "create_server", "VisualizerService", "__version__"]
