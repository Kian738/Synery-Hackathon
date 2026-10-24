## 2026-10-24T13:59:46Z
Objective:
Investigate existing codebase, data loaders, graph models, dependencies, and spatial reasoning algorithms.
Investigate:
1. Explore `starter_agent/` and any other existing modules in the repository:
   - What data models, classes, parser utilities, and graph structures are implemented?
   - How does `starter_agent` currently load building data, parse geometries, construct navigation graphs, or answer queries?
   - What questions can it currently answer, and what are its shortcomings or missing features?
2. Inspect Python environment and available packages:
   - Check `pyproject.toml`, `requirements.txt`, or environment configuration.
   - What spatial/graph/geometry libraries are available (e.g. Shapely, NetworkX, SciPy, NumPy, Pydantic, etc.)?
3. Gap analysis against R1 & R2:
   - R1 Spatial Reasoning: room areas (polygon/polygon with holes), 3D centroids, shared walls (wall segments, geometric adjacency), wide delivery clearance, step-free reachability graph, errand (TSP / multi-stop shortest path), what-if door analysis.
   - R2 Multi-Floor Routing & Constraint Engine: multi-floor connectors (stairs, lifts), step-free constraints (lifts only vs stairs), door clearance filtering (width thresholds), dynamic closures (rooms, connectors), 3D straight-line distance.
4. Recommend a clean, modular architectural design for the core spatial reasoning and routing engine.
