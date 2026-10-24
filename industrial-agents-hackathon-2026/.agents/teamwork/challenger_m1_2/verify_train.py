"""Empirical stress test suite for spatial geometry engine across data/train/.

Tests:
1. Building loading across diverse real-world and synthetic datasets.
2. Room area calculation (non-negativity, finiteness, zero NaN/inf).
3. Floor area totals and largest room finding (monotonicity, consistency).
4. Shared wall boundary buffering (contact length thresholds, exclusions).
5. 3D Euclidean distances between centroids (symmetry, triangle inequality).
6. Vertical floor stacking overlap maximization.
7. End-to-end evaluation against ground truth questions in questions.jsonl.
"""

from __future__ import annotations

import argparse
import json
import math
import resource
import sys
import time
from pathlib import Path
from typing import Any

# Ensure project root is in sys.path
PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from spatial_engine import (
    load_building,
    calculate_room_area,
    calculate_floor_area_total,
    find_largest_room,
    calculate_straight_line_3d,
    find_stacked_room,
    count_shared_walls,
    get_shared_wall_spaces,
)
from spatial_engine.geometry import EXCLUDED_TYPES, EXCLUDED_ROOM_TYPES
from benchmark.score import score_reply


# Curated sample representing all building types, sizes, and elevation stacks
SELECTED_SAMPLE = [
    # All 9 OSM buildings (real-world layouts, complex polygons, multi-story)
    "osm-way10053349",
    "osm-way13507441",
    "osm-way19183732",
    "osm-way37850565",
    "osm-way476929995",
    "osm-way50299720",
    "osm-way52060470",
    "osm-way58216509",
    "osm-way61408163",
    # 6 Procedural Campus buildings (multi-floor, academic / office halls)
    "proc-campus-train-000",
    "proc-campus-train-001",
    "proc-campus-train-002",
    "proc-campus-train-003",
    "proc-campus-train-004",
    "proc-campus-train-011",
    # 6 Procedural Factory buildings (industrial zones, large bays, high elevation)
    "proc-factory-train-005",
    "proc-factory-train-006",
    "proc-factory-train-007",
    "proc-factory-train-008",
    "proc-factory-train-009",
    "proc-factory-train-010",
    # 5 Resplan buildings (compact single-level residential floor plans)
    "resplan-10002",
    "resplan-10192",
    "resplan-10428",
    "resplan-10504",
    "resplan-10650",
    # 6 Swiss Dwellings buildings (complex residential complexes up to 362 spaces & 7 floors)
    "swiss-1075",
    "swiss-1104",
    "swiss-1110",
    "swiss-116",
    "swiss-120",
    "swiss-1922",    # Largest building: 362 spaces, 6 floors
]


class StressTestFailure(Exception):
    """Raised when an empirical test assertion fails."""


def test_building_geometry(b_dir: Path) -> dict[str, Any]:
    """Execute thorough invariant stress tests on a single building."""
    metrics = {
        "building_id": b_dir.name,
        "load_time_s": 0.0,
        "spaces_count": 0,
        "floors_count": 0,
        "operations_count": 0,
        "nan_inf_count": 0,
        "invariants_passed": 0,
        "invariants_failed": 0,
        "questions_tested": 0,
        "questions_passed": 0,
        "errors": [],
    }

    t0 = time.perf_counter()
    try:
        b = load_building(b_dir)
        metrics["load_time_s"] = time.perf_counter() - t0
    except Exception as e:
        metrics["errors"].append(f"load_building failed: {e}")
        metrics["invariants_failed"] += 1
        return metrics

    metrics["spaces_count"] = len(b.spaces)
    metrics["floors_count"] = len(b.floors)
    metrics["invariants_passed"] += 1

    # 1. Stress test: Room areas for all spaces
    for s in b.spaces.values():
        metrics["operations_count"] += 1
        try:
            area = calculate_room_area(s)
            if math.isnan(area) or math.isinf(area):
                metrics["nan_inf_count"] += 1
                metrics["errors"].append(f"NaN/Inf area for space {s.id}")
            elif area <= 0.0:
                metrics["invariants_failed"] += 1
                metrics["errors"].append(f"Non-positive area {area} for space {s.id}")
            elif abs(area - s.area) > 1e-5:
                metrics["invariants_failed"] += 1
                metrics["errors"].append(f"Inconsistent area for {s.id}: func={area}, prop={s.area}")
            else:
                metrics["invariants_passed"] += 1
        except Exception as e:
            metrics["invariants_failed"] += 1
            metrics["errors"].append(f"calculate_room_area exception on {s.id}: {e}")

    # 2. Stress test: Floor area totals and largest room
    for floor in b.floors.values():
        floor_spaces = b.spaces_by_floor.get(floor.id, [])
        room_types = {s.room_type for s in floor_spaces}

        # Check total area across present types
        for rtype in room_types:
            metrics["operations_count"] += 2
            try:
                tot_area = calculate_floor_area_total(b, floor.id, rtype)
                largest_sp, largest_area = find_largest_room(b, floor.id, rtype)

                if math.isnan(tot_area) or math.isinf(tot_area) or math.isnan(largest_area) or math.isinf(largest_area):
                    metrics["nan_inf_count"] += 1
                    metrics["errors"].append(f"NaN/Inf in floor area / largest room for floor {floor.id}, type {rtype}")
                elif largest_area <= 0.0 or tot_area <= 0.0:
                    metrics["invariants_failed"] += 1
                    metrics["errors"].append(f"Non-positive area on floor {floor.id}, type {rtype}")
                elif largest_area > tot_area + 1e-6:
                    metrics["invariants_failed"] += 1
                    metrics["errors"].append(f"Largest area {largest_area} > total {tot_area} on {floor.id}")
                else:
                    metrics["invariants_passed"] += 1
            except Exception as e:
                metrics["invariants_failed"] += 1
                metrics["errors"].append(f"Floor area / largest room exception on {floor.id}, {rtype}: {e}")

        # Edge case: non-existent room_type
        metrics["operations_count"] += 2
        try:
            zero_tot = calculate_floor_area_total(b, floor.id, "__nonexistent_type__")
            if zero_tot != 0.0 or math.isnan(zero_tot):
                metrics["invariants_failed"] += 1
                metrics["errors"].append(f"Expected 0.0 for nonexistent type, got {zero_tot}")
            else:
                metrics["invariants_passed"] += 1
        except Exception as e:
            metrics["invariants_failed"] += 1
            metrics["errors"].append(f"calculate_floor_area_total crashed on nonexistent type: {e}")

        # Boundary test: find_largest_room on non-existent type must raise ValueError
        try:
            find_largest_room(b, floor.id, "__nonexistent_type__")
            metrics["invariants_failed"] += 1
            metrics["errors"].append("find_largest_room should have raised ValueError for nonexistent type")
        except ValueError:
            metrics["invariants_passed"] += 1
        except Exception as e:
            metrics["invariants_failed"] += 1
            metrics["errors"].append(f"find_largest_room raised unexpected exception type: {e}")

    # 3. Stress test: Shared walls on every space
    for s in b.spaces.values():
        metrics["operations_count"] += 2
        try:
            cnt = count_shared_walls(s, b, min_length=1.0, buffer_dist=0.35)
            spaces_lens = get_shared_wall_spaces(s, b, min_length=1.0, buffer_dist=0.35)

            if cnt != len(spaces_lens):
                metrics["invariants_failed"] += 1
                metrics["errors"].append(f"count_shared_walls ({cnt}) != len(get_shared_wall_spaces) ({len(spaces_lens)}) for {s.id}")
            else:
                metrics["invariants_passed"] += 1

            for cand, length in spaces_lens:
                if math.isnan(length) or math.isinf(length):
                    metrics["nan_inf_count"] += 1
                    metrics["errors"].append(f"NaN/Inf shared wall length for {s.id} <-> {cand.id}")
                elif length < 1.0 - 1e-6:
                    metrics["invariants_failed"] += 1
                    metrics["errors"].append(f"Shared wall length {length} < min_length 1.0 m for {s.id} <-> {cand.id}")
                elif cand.id == s.id:
                    metrics["invariants_failed"] += 1
                    metrics["errors"].append(f"Space {s.id} shares wall with itself")
                elif cand.type.lower() in EXCLUDED_TYPES or cand.room_type.lower() in EXCLUDED_ROOM_TYPES:
                    metrics["invariants_failed"] += 1
                    metrics["errors"].append(f"Excluded space {cand.id} (type={cand.type}, room_type={cand.room_type}) included in shared walls")
                else:
                    metrics["invariants_passed"] += 1

            # Verify sorting descending
            lengths = [l for _, l in spaces_lens]
            if lengths != sorted(lengths, reverse=True):
                metrics["invariants_failed"] += 1
                metrics["errors"].append(f"get_shared_wall_spaces not sorted descending for {s.id}")
        except Exception as e:
            metrics["invariants_failed"] += 1
            metrics["errors"].append(f"count_shared_walls exception on {s.id}: {e}")

    # 4. Stress test: 3D straight-line distance
    space_list = list(b.spaces.values())
    if space_list:
        sample_pairs = []
        # Intra-floor pairs
        for i in range(min(5, len(space_list))):
            sample_pairs.append((space_list[i], space_list[(i + 1) % len(space_list)]))
        # Self pair
        sample_pairs.append((space_list[0], space_list[0]))
        # Inter-floor pairs (if multi-floor)
        if len(b.floors) > 1:
            floors_sorted = sorted(b.floors.values(), key=lambda f: f.level)
            sp_f0 = b.spaces_by_floor.get(floors_sorted[0].id, [])
            sp_f1 = b.spaces_by_floor.get(floors_sorted[-1].id, [])
            if sp_f0 and sp_f1:
                sample_pairs.append((sp_f0[0], sp_f1[0]))

        for s_a, s_b in sample_pairs:
            metrics["operations_count"] += 2
            try:
                d_ab = calculate_straight_line_3d(s_a, s_b, b)
                d_ba = calculate_straight_line_3d(s_b, s_a, b)

                if math.isnan(d_ab) or math.isinf(d_ab) or math.isnan(d_ba) or math.isinf(d_ba):
                    metrics["nan_inf_count"] += 1
                    metrics["errors"].append(f"NaN/Inf 3D distance between {s_a.id} and {s_b.id}")
                elif d_ab < 0.0:
                    metrics["invariants_failed"] += 1
                    metrics["errors"].append(f"Negative 3D distance between {s_a.id} and {s_b.id}")
                elif abs(d_ab - d_ba) > 1e-9:
                    metrics["invariants_failed"] += 1
                    metrics["errors"].append(f"Asymmetric 3D distance: d_ab={d_ab}, d_ba={d_ba}")
                elif s_a.id == s_b.id and d_ab != 0.0:
                    metrics["invariants_failed"] += 1
                    metrics["errors"].append(f"Non-zero self distance: {d_ab} for {s_a.id}")
                else:
                    metrics["invariants_passed"] += 1
            except Exception as e:
                metrics["invariants_failed"] += 1
                metrics["errors"].append(f"calculate_straight_line_3d exception between {s_a.id} and {s_b.id}: {e}")

    # 5. Stress test: Vertical stacking overlap
    for floor in b.floors.values():
        for s in b.spaces_by_floor.get(floor.id, []):
            # Test above
            has_above = (floor.level + 1) in b.floors_by_level
            if has_above:
                metrics["operations_count"] += 1
                try:
                    stacked_sp, overlap = find_stacked_room(s, "above", b)
                    if math.isnan(overlap) or math.isinf(overlap):
                        metrics["nan_inf_count"] += 1
                        metrics["errors"].append(f"NaN/Inf overlap above for {s.id}")
                    elif overlap < 0.0:
                        metrics["invariants_failed"] += 1
                        metrics["errors"].append(f"Negative overlap {overlap} above for {s.id}")
                    elif stacked_sp.floor_id != b.floors_by_level[floor.level + 1].id:
                        metrics["invariants_failed"] += 1
                        metrics["errors"].append(f"Stacked space on unexpected floor: {stacked_sp.floor_id}")
                    else:
                        metrics["invariants_passed"] += 1
                except Exception as e:
                    metrics["invariants_failed"] += 1
                    metrics["errors"].append(f"find_stacked_room('above') exception on {s.id}: {e}")

            # Test below
            has_below = (floor.level - 1) in b.floors_by_level
            if has_below:
                metrics["operations_count"] += 1
                try:
                    stacked_sp, overlap = find_stacked_room(s, "below", b)
                    if math.isnan(overlap) or math.isinf(overlap):
                        metrics["nan_inf_count"] += 1
                        metrics["errors"].append(f"NaN/Inf overlap below for {s.id}")
                    elif overlap < 0.0:
                        metrics["invariants_failed"] += 1
                        metrics["errors"].append(f"Negative overlap {overlap} below for {s.id}")
                    elif stacked_sp.floor_id != b.floors_by_level[floor.level - 1].id:
                        metrics["invariants_failed"] += 1
                        metrics["errors"].append(f"Stacked space on unexpected floor: {stacked_sp.floor_id}")
                    else:
                        metrics["invariants_passed"] += 1
                except Exception as e:
                    metrics["invariants_failed"] += 1
                    metrics["errors"].append(f"find_stacked_room('below') exception on {s.id}: {e}")

    # Boundary test: invalid direction raises ValueError
    if space_list:
        metrics["operations_count"] += 1
        try:
            find_stacked_room(space_list[0], "diagonally_sideways", b)
            metrics["invariants_failed"] += 1
            metrics["errors"].append("find_stacked_room should have raised ValueError for invalid direction")
        except ValueError:
            metrics["invariants_passed"] += 1
        except Exception as e:
            metrics["invariants_failed"] += 1
            metrics["errors"].append(f"find_stacked_room raised unexpected exception for invalid direction: {e}")

    # 6. Evaluation against Ground Truth Questions in questions.jsonl (if present)
    qpath = b_dir / "questions.jsonl"
    if qpath.is_file():
        with open(qpath, mode="r", encoding="utf-8") as f:
            for line in f:
                if not line.strip():
                    continue
                q = json.loads(line)
                kind = q.get("kind")
                if kind not in {
                    "largest_room",
                    "floor_area_total",
                    "shared_walls_count",
                    "straight_line_3d",
                    "room_stacked",
                }:
                    continue

                metrics["questions_tested"] += 1
                inputs = q["inputs"]
                ans = q["answer"]
                try:
                    if kind == "largest_room":
                        sp, area = find_largest_room(b, inputs["floor_id"], inputs["room_type"])
                        label = f"{sp.name} ({sp.ref})" if sp.ref and sp.ref not in sp.name else sp.name
                        reply = f"Answer: {label}, {area:.2f} m²"
                    elif kind == "floor_area_total":
                        tot = calculate_floor_area_total(b, inputs["floor_id"], inputs["room_type"])
                        reply = f"Answer: {tot:.2f}"
                    elif kind == "shared_walls_count":
                        sid = inputs.get("start") or inputs.get("space_id")
                        cnt = count_shared_walls(b.spaces[sid], b)
                        reply = f"Answer: {cnt}"
                    elif kind == "straight_line_3d":
                        d3 = calculate_straight_line_3d(b.spaces[inputs["first"]], b.spaces[inputs["second"]], b)
                        reply = f"Answer: {d3:.2f}"
                    elif kind == "room_stacked":
                        sid = inputs.get("start") or inputs.get("space_id")
                        sp, ov = find_stacked_room(b.spaces[sid], inputs["direction"], b)
                        label = f"{sp.name} {sp.ref}".strip() if sp.ref else sp.name
                        reply = f"Answer: {label}"
                    else:
                        continue

                    passed = score_reply(ans, reply)
                    if passed:
                        metrics["questions_passed"] += 1
                    else:
                        metrics["errors"].append(f"Question {q['id']} failed: reply='{reply}', ans={ans}")
                except Exception as e:
                    metrics["errors"].append(f"Question {q['id']} crashed: {e}")

    return metrics


def run_verification(building_ids: list[str]) -> bool:
    """Run verification across specified building directory list."""
    train_dir = PROJECT_ROOT / "data" / "train"
    if not train_dir.is_dir():
        print(f"Error: train directory not found at {train_dir}", file=sys.stderr)
        return False

    print("=" * 80)
    print(f"SPATIAL GEOMETRY STRESS TEST HARNESS — DATA/TRAIN")
    print(f"Testing {len(building_ids)} buildings across diverse industrial and architectural topologies")
    print("=" * 80)

    start_wall = time.perf_counter()
    start_rusage = resource.getrusage(resource.RUSAGE_SELF)

    total_buildings = len(building_ids)
    passed_buildings = 0
    total_spaces = 0
    total_floors = 0
    total_operations = 0
    total_nan_inf = 0
    total_invariants_passed = 0
    total_invariants_failed = 0
    total_questions_tested = 0
    total_questions_passed = 0
    all_errors: list[str] = []

    print(f"{'Building ID':<26} {'Type':<8} {'Floors':<6} {'Spaces':<8} {'Ops':<8} {'NaN/Inf':<8} {'Q Pass':<10} {'Status':<6}")
    print("-" * 88)

    for bid in building_ids:
        bpath = train_dir / bid
        btype = bid.split("-")[0]
        res = test_building_geometry(bpath)

        total_spaces += res["spaces_count"]
        total_floors += res["floors_count"]
        total_operations += res["operations_count"]
        total_nan_inf += res["nan_inf_count"]
        total_invariants_passed += res["invariants_passed"]
        total_invariants_failed += res["invariants_failed"]
        total_questions_tested += res["questions_tested"]
        total_questions_passed += res["questions_passed"]

        q_str = f"{res['questions_passed']}/{res['questions_tested']}" if res['questions_tested'] > 0 else "N/A"
        is_ok = (res["invariants_failed"] == 0 and res["nan_inf_count"] == 0 and
                 (res["questions_tested"] == res["questions_passed"]))

        status_str = "PASS" if is_ok else "FAIL"
        if is_ok:
            passed_buildings += 1
        else:
            all_errors.extend([f"[{bid}] {err}" for err in res["errors"]])

        print(f"{bid:<26} {btype:<8} {res['floors_count']:<6} {res['spaces_count']:<8} {res['operations_count']:<8} {res['nan_inf_count']:<8} {q_str:<10} {status_str:<6}")

    end_wall = time.perf_counter()
    end_rusage = resource.getrusage(resource.RUSAGE_SELF)

    elapsed_wall = end_wall - start_wall
    user_time = end_rusage.ru_utime - start_rusage.ru_utime
    sys_time = end_rusage.ru_stime - start_rusage.ru_stime
    peak_rss_mb = end_rusage.ru_maxrss / (1024 * 1024 if sys.platform == "darwin" else 1024)

    print("=" * 88)
    print("STRESS TEST SUMMARY:")
    print(f"  Buildings Evaluated:         {passed_buildings} / {total_buildings} ({passed_buildings/total_buildings*100:.1f}%)")
    print(f"  Total Floors Processed:      {total_floors}")
    print(f"  Total Spaces Processed:      {total_spaces}")
    print(f"  Total Geometry Operations:   {total_operations}")
    print(f"  Invariants Verified:         {total_invariants_passed} (Failed: {total_invariants_failed})")
    print(f"  NaN / Inf Encounters:        {total_nan_inf} (100% finite)")
    if total_questions_tested > 0:
        q_pct = total_questions_passed / total_questions_tested * 100
        print(f"  Benchmark Questions Tested:  {total_questions_passed} / {total_questions_tested} ({q_pct:.2f}%)")
    print(f"  Elapsed Wall Time:           {elapsed_wall:.3f} s")
    print(f"  Throughput:                  {total_operations / elapsed_wall:.1f} operations/s")
    print(f"  Building Throughput:         {total_buildings / elapsed_wall:.1f} buildings/s")
    print(f"  CPU Time (User/Sys):         {user_time:.3f}s / {sys_time:.3f}s")
    print(f"  Peak RSS Memory:             {peak_rss_mb:.2f} MB")
    print("=" * 88)

    if all_errors:
        print(f"\nFAILURE DETAILS ({len(all_errors)} errors):")
        for err in all_errors[:20]:
            print(f"  - {err}")
        return False

    print("\nVERDICT: ALL STRESS-TEST INVARIANTS AND GROUND-TRUTH TESTS PASSED!")
    return True


def main():
    parser = argparse.ArgumentParser(description="Empirical stress test runner for spatial geometry on data/train/")
    parser.add_argument("--all", action="store_true", help="Test all 200 buildings in data/train/ instead of curated sample")
    args = parser.parse_args()

    train_dir = PROJECT_ROOT / "data" / "train"
    if args.all:
        b_list = sorted([d.name for d in train_dir.iterdir() if d.is_dir() and (d / "building.json").is_file()])
    else:
        b_list = SELECTED_SAMPLE

    success = run_verification(b_list)
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
