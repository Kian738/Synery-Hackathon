"""Comprehensive unit and integration test suite for talk_to_your_building spatial engine."""

from __future__ import annotations

import glob
import json
import unittest
from pathlib import Path

from talk_to_your_building.agent import solve_question
from talk_to_your_building.spatial_engine import (
    Building,
    calculate_floor_area_total,
    calculate_room_area,
    calculate_straight_line_3d,
    count_reachable_rooms,
    count_shared_walls,
    evaluate_what_if_door,
    find_largest_room,
    find_route,
    find_stacked_room,
    load_building,
    solve_errand,
)
from benchmark.score import score_reply

HACKATHON_DIR = Path(__file__).resolve().parent.parent.parent / "industrial-agents-hackathon-2026"
DEV_DATA_DIR = HACKATHON_DIR / "data" / "dev"
SAMPLE_BUILDING_DIR = DEV_DATA_DIR / "proc-campus-dev-000"


class TestModelsAndLoader(unittest.TestCase):
    """Test data models, coordinate cleaning, and indexed building loading."""

    def test_load_building(self):
        building = load_building(SAMPLE_BUILDING_DIR)
        self.assertIsInstance(building, Building)
        self.assertEqual(building.id, "proc-campus-dev-000")
        self.assertGreater(len(building.floors), 0)
        self.assertGreater(len(building.spaces), 0)
        self.assertGreater(len(building.openings), 0)
        self.assertGreater(len(building.connectors), 0)

        # Test floor lookup
        f0 = building.get_floor(0)
        self.assertIsNotNone(f0)
        self.assertEqual(f0.level, 0)
        self.assertEqual(f0.name, "Ground floor")

        # Test space lookup by ref or name
        space = building.find_space_by_ref_or_name("3.07")
        self.assertIsNotNone(space)
        self.assertEqual(space.ref, "3.07")
        self.assertEqual(space.room_type, "office")

        # Test space contains_point
        rep_x, rep_y = space.representative_point
        self.assertTrue(space.contains_point(rep_x, rep_y))

    def test_opening_properties(self):
        building = load_building(SAMPLE_BUILDING_DIR)
        for opening in building.openings.values():
            if "outside" in opening.space_ids:
                self.assertTrue(opening.is_entrance)
                other = opening.other_side("outside")
                self.assertIsNotNone(other)
                self.assertNotEqual(other, "outside")
                break


class TestGeometryCalculations(unittest.TestCase):
    """Test geometry reasoning algorithms."""

    @classmethod
    def setUpClass(cls):
        cls.building = load_building(SAMPLE_BUILDING_DIR)

    def test_calculate_room_area(self):
        space = self.building.find_space_by_ref_or_name("3.07")
        area = calculate_room_area(space)
        self.assertAlmostEqual(area, 41.28, delta=0.5)

    def test_calculate_floor_area_total(self):
        floor_2 = self.building.get_floor(2)
        total_toilet_area = calculate_floor_area_total(self.building, floor_2, "toilet")
        self.assertAlmostEqual(total_toilet_area, 94.56, delta=2.0)

    def test_find_largest_room(self):
        floor_3 = self.building.get_floor(3)
        best_space, area = find_largest_room(self.building, floor_3, "office")
        self.assertIn("3.07", best_space.name or best_space.ref)
        self.assertAlmostEqual(area, 41.28, delta=0.5)

    def test_straight_line_3d(self):
        space_a = self.building.find_space_by_ref_or_name("1.24")
        space_b = self.building.find_space_by_ref_or_name("4.31")
        dist = calculate_straight_line_3d(space_a, space_b, self.building)
        self.assertAlmostEqual(dist, 37.27, delta=1.0)

    def test_shared_walls_count(self):
        factory_building = load_building(DEV_DATA_DIR / "proc-factory-dev-003")
        target_space = factory_building.find_space_by_ref_or_name("Assembly zone H-A2")
        self.assertIsNotNone(target_space)
        count = count_shared_walls(target_space, factory_building)
        self.assertGreater(count, 0)

    def test_stacked_room(self):
        osm_building = load_building(DEV_DATA_DIR / "osm-way22744230")
        room_2 = osm_building.find_space_by_ref_or_name("Generic room N2324")
        self.assertIsNotNone(room_2)
        below_space, overlap = find_stacked_room(osm_building, room_2, direction="below")
        self.assertIsNotNone(below_space)
        self.assertGreater(overlap, 0.0)


class TestRoutingAndReachability(unittest.TestCase):
    """Test topological routing, errands, clearance, and what-if counterfactuals."""

    @classmethod
    def setUpClass(cls):
        cls.building = load_building(SAMPLE_BUILDING_DIR)

    def test_wide_delivery_reachability(self):
        start_space = self.building.find_space_by_ref_or_name("Main lobby")
        target_floor = self.building.get_floor(0)
        count = count_reachable_rooms(
            self.building,
            start_space_id=start_space.id,
            target_floor_id=target_floor.id,
            step_free=True,
            min_width=1.1,
        )
        self.assertEqual(count, 11)

    def test_errand_solving(self):
        start_space = self.building.find_space_by_ref_or_name("Lab 4.22")
        target_floor = self.building.get_floor(4)
        dist, asset_sid, target_sid = solve_errand(
            self.building,
            start_space_id=start_space.id,
            asset_type="bookshelf",
            target_room_type="storage",
            target_floor_id=target_floor.id,
        )
        self.assertAlmostEqual(dist, 37.38, delta=1.0)

    def test_what_if_door(self):
        osm_building = load_building(DEV_DATA_DIR / "osm-way27917482")
        sp_a = osm_building.find_space_by_ref_or_name("00.13.010")
        sp_b = osm_building.find_space_by_ref_or_name("00.13.015")
        count = evaluate_what_if_door(
            osm_building,
            space_a_id=sp_a.id,
            space_b_id=sp_b.id,
            target_floor_id=osm_building.get_floor(-1).id,
        )
        self.assertEqual(count, 2)

    def test_find_route(self):
        sp_a = self.building.find_space_by_ref_or_name("Office 3.07")
        sp_b = self.building.find_space_by_ref_or_name("Office 3.08")
        route = find_route(self.building, sp_a.id, sp_b.id)
        self.assertTrue(route.success)
        self.assertGreater(route.distance_m, 0.0)
        self.assertIn(sp_a.id, route.path_spaces)
        self.assertIn(sp_b.id, route.path_spaces)


class TestSolverAndBenchmark(unittest.TestCase):
    """Test end-to-end benchmark question solving and official scoring."""

    def test_sample_dev_questions(self):
        with open(SAMPLE_BUILDING_DIR / "questions.jsonl") as f:
            for line in f:
                if not line.strip():
                    continue
                q = json.loads(line)
                reply = solve_question(SAMPLE_BUILDING_DIR, q["question"])
                is_correct = score_reply(q["answer"], reply)
                self.assertTrue(
                    is_correct,
                    f"Question {q['id']} failed. Question: {q['question']}\nReply: {reply}\nExpected: {q['answer']}",
                )

    def test_all_138_dev_benchmark_questions_pass_100_percent(self):
        dev_files = sorted(glob.glob(str(DEV_DATA_DIR / "*/questions.jsonl")))
        total_questions = 0
        correct_questions = 0
        failures = []

        for fpath in dev_files:
            b_dir = Path(fpath).parent
            with open(fpath, encoding="utf-8") as f:
                for line in f:
                    if not line.strip():
                        continue
                    q = json.loads(line)
                    total_questions += 1
                    reply = solve_question(b_dir, q["question"])
                    is_correct = score_reply(q["answer"], reply)
                    if is_correct:
                        correct_questions += 1
                    else:
                        failures.append((q["id"], q["kind"], q["question"], reply, q["answer"]))

        self.assertEqual(total_questions, 138, f"Expected 138 dev questions, found {total_questions}")
        self.assertEqual(
            correct_questions,
            total_questions,
            f"Pass rate was {correct_questions}/{total_questions}. Failures: {failures}",
        )


if __name__ == "__main__":
    unittest.main()
