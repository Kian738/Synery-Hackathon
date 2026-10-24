# Adversarial Challenge & Handoff Report — Milestone 1 (Challenger 1)

**Date:** 2026-10-24  
**Agent:** `teamwork_preview_challenger` (challenger_m1_1)  
**Parent Task ID:** `99a36772-9103-445c-a001-17463bb30980`  
**Verdict:** **REJECT** (Exposed critical crashes, false-positive wall adjacency, and zero-overlap assignment bugs)

---

## Challenge Summary

- **Overall Risk Assessment**: **HIGH**
- **Test Harness**: `.agents/teamwork/challenger_m1_1/stress_test.py` (17 tests executed: 10 passed, 7 bugs exposed)
- **Target Files Tested**:
  - `spatial_engine/building_loader.py`
  - `spatial_engine/geometry.py`

---

## 1. Observation

### 1.1 Loader Crashes on Non-Simple Polygons (`spatial_engine/building_loader.py:143-152`)
In `spatial_engine/building_loader.py`:
```python
142:         poly = Polygon(coords)
143:         if not poly.is_valid:
144:             poly = make_valid(poly)
145:             if isinstance(poly, MultiPolygon):
146:                 poly = max(poly.geoms, key=lambda g: g.area)
...
152:         exterior_ring = poly.exterior
```
- When `coords` has a pinch-point vertex touching itself (e.g. `[(0, 0), (10, 0), (10, 10), (5, 5), (0, 10), (5, 5)]`), `make_valid(poly)` returns a `shapely.geometry.collection.GeometryCollection`.
- When `coords` has an antenna spike (e.g. `[(0, 0), (5, 0), (5, 5), (10, 5), (5, 5), (0, 5)]`), `make_valid(poly)` returns a `GeometryCollection`.
- When `coords` has 3 collinear points with 0 area (e.g. `[(0, 0), (5, 5), (10, 10)]`), `make_valid(poly)` returns a `MultiLineString`.
- Neither `GeometryCollection` nor `MultiLineString` has an `.exterior` attribute.
- **Verbatim Error**:
  ```
  AttributeError: 'GeometryCollection' object has no attribute 'exterior'
  AttributeError: 'MultiLineString' object has no attribute 'exterior'
  ```

### 1.2 Shared Wall False Positives Below 1.0 m Threshold (`spatial_engine/geometry.py:258-278`)
In `spatial_engine/geometry.py`:
```python
258:     exterior_ring = target_space.polygon.exterior
259:     buffered_boundary = exterior_ring.buffer(buffer_dist)
...
271:         cand_exterior = candidate.polygon.exterior
272:         try:
273:             inter = buffered_boundary.intersection(cand_exterior)
274:             inter_len = float(inter.length)
...
277:         if inter_len >= min_length - 1e-6:
278:             results.append((candidate, inter_len))
```
- In Test 2.1 (`cand_coords = [(10, 2.0), (20, 2.0), (20, 2.99), (10, 2.99)]`), the actual shared wall contact length is exactly $0.99\text{ m}$.
- The $0.35\text{ m}$ buffer dilates outward around the two corners into the candidate room's perpendicular walls by $2 \times 0.35 = 0.70\text{ m}$.
- `inter.length` is measured as $0.99 + 0.70 = 1.69\text{ m}$.
- `count_shared_walls(target, bldg, min_length=1.0)` returned `1` instead of `0`.
- In Test 2.3 (`cand_coords = [(10, 2.0), (20, 2.0), (20, 2.35), (10, 2.35)]`), actual wall contact is only $0.35\text{ m}$, but `inter.length` is $0.35 + 0.70 = 1.05\text{ m} \ge 1.0\text{ m}$, returning `1` instead of `0`.
- In Test 2.5, across a $0.20\text{ m}$ physical wall gap, a $0.99\text{ m}$ parallel wall penetrates the $0.35\text{ m}$ buffer by $0.15\text{ m}$ on each perpendicular side, yielding $0.99 + 0.30 = 1.29\text{ m} \ge 1.0\text{ m}$, returning `1` instead of `0`.

### 1.3 Zero-Overlap False Assignment in `find_stacked_room` (`spatial_engine/geometry.py:204-223`)
In `spatial_engine/geometry.py`:
```python
205:     best_space: Optional[Space] = None
206:     max_overlap = -1.0
207: 
208:     for cand in candidates:
209:         try:
210:             inter = poly_base.intersection(cand.polygon)
211:             overlap = float(inter.area)
212:         except Exception:
213:             overlap = 0.0
214: 
215:         if overlap > max_overlap:
216:             max_overlap = overlap
217:             best_space = cand
218: 
219:     if best_space is None:
220:         raise ValueError(
221:             f"Unable to find overlapping space on floor {target_floor.id}"
222:         )
223: 
224:     return best_space, max_overlap
```
- In Test 4.2, the base space is at $[0, 10] \times [0, 10]$ on Floor 0, and Floor 1 has spaces at $[1000, 1010] \times [1000, 1010]$ and $[2000, 2010] \times [2000, 2010]$ (completely disjoint, $0.0\text{ m}^2$ overlap).
- Because `max_overlap` is initialized to `-1.0`, on the first candidate, `overlap = 0.0` satisfies `0.0 > -1.0`.
- `best_space` is assigned to `candidates[0]`, and `max_overlap` becomes `0.0`.
- Lines 219-222 (`if best_space is None: raise ValueError`) are unreachable whenever `candidates` is non-empty.
- **Verbatim Result**: `find_stacked_room` returned `('S1_DISJOINT', 0.0)` claiming a completely disjoint room is stacked above.

---

## 2. Logic Chain

1. **Loader Crash**:
   - `Polygon(coords)` on non-simple real-world CAD geometries triggers `not poly.is_valid`.
   - `make_valid` repairs such topologies by isolating 2D polygonal areas and 1D line spikes into a `GeometryCollection`, or collinear segments into `MultiLineString`.
   - `building_loader.py` only extracts from `isinstance(poly, MultiPolygon)`, leaving `poly` as a `GeometryCollection` or `MultiLineString`.
   - Calling `poly.exterior` directly on those types raises an unhandled `AttributeError`, crashing the ingestion pipeline.

2. **Shared Wall False Positives**:
   - The competition specification requires: *"Count every room whose wall runs along it for at least 1 m"*.
   - Buffering a 1D exterior ring by `0.35m` creates a 2D ribbon with rounded caps at every vertex.
   - Any perpendicular wall of an adjacent room that meets the corner or wall intersection penetrates into the 2D ribbon by up to $0.35\text{ m}$.
   - Intersecting the ribbon with `cand.polygon.exterior` measures the sum of the true shared wall PLUS the perpendicular penetrations ($2 \times 0.35\text{ m} = 0.70\text{ m}$).
   - Any wall of length $\ge 0.30\text{ m}$ is measured as $\ge 1.0\text{ m}$. Specifically, an overlap of $0.99\text{ m}$ is measured as $1.69\text{ m}$, falsely incrementing `shared_walls_count`.

3. **Zero-Overlap False Assignment**:
   - When querying `find_stacked_room` on floors where rooms do not geometrically align or are offset/disjoint, the function should report that no overlapping room exists (`ValueError` or zero-overlap signal).
   - Initializing `max_overlap = -1.0` causes any non-overlapping candidate (`overlap = 0.0`) to be selected as the "best" stacked room.
   - Upstream benchmark solvers will output an arbitrary room name instead of detecting that no stacked room exists.

---

## 3. Caveats

- On standard dev benchmark buildings (`data/dev/proc-factory-dev-012`, `osm-way22744230`, etc.), shared walls are typically $> 3.0\text{ m}$ and polygons are pre-conditioned without spikes, which masked these defects during worker unit tests.
- 3D centroid calculation across elevations and large GIS/UTM coordinate spaces (Test Suite 3) demonstrated high precision (error $< 10^{-9}\text{ m}$), confirming that centroid mathematics and elevation handling are robust.
- Direction validation and floor resolution in `find_stacked_room` and `resolve_floor` correctly handle boundary elevation checks.

---

## 4. Conclusion & Verdict

**Verdict:** **REJECT**

The implementation under review fails on 7 adversarial test cases. Before Milestone 1 can be approved, the worker must address:
1. **`spatial_engine/building_loader.py`**: Handle `GeometryCollection` (extracting polygons via `[g for g in poly.geoms if isinstance(g, Polygon)]`) and filter out zero-area 1D geometries (`MultiLineString`/`LineString`) before accessing `.exterior`.
2. **`spatial_engine/geometry.py:get_shared_wall_spaces`**: Correct the boundary contact measurement to exclude perpendicular wall penetration or project the contact segment strictly along the shared collinear edge. Overlaps of $0.99\text{ m}$ must not count toward the $1.0\text{ m}$ threshold.
3. **`spatial_engine/geometry.py:find_stacked_room`**: Initialize `max_overlap = 0.0` (or require `max_overlap > 1e-6`) so that disjoint floors with zero overlap properly trigger `if best_space is None: raise ValueError(...)`.

---

## 5. Verification Method

To independently execute and verify these findings:

```bash
# Run the adversarial stress test harness:
/Users/konstantin/.local/bin/uv run python .agents/teamwork/challenger_m1_1/stress_test.py
```

Expected output:
- Total: 17 executed
- Passed: 10
- Bugs exposed: 7 (Tests 1.3, 1.4, 1.6, 2.1, 2.3, 2.5, 4.2)
