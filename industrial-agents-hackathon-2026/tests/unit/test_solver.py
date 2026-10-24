"""Unit test suite for Milestone 3: Deterministic Benchmark Solver & Runner.

Validates the classifier, space resolution, all 9 question solvers, regex formatting,
single-number scoring compliance, building caching, and benchmark_runner CLI integration.
"""

from __future__ import annotations

import csv
import json
import tempfile
import unittest
from pathlib import Path

from benchmark.score import ANSWER_LINE, numbers_in, score_reply
from benchmark_runner import load_benchmark_questions, run_benchmark, write_submission
from spatial_engine.building_loader import load_building
from spatial_engine.solver import (
    _format_space_label,
    answer,
    classify_question,
    clear_building_cache,
    evaluate_dataset,
    get_cached_building,
    parse_floor_level,
    resolve_space_by_text,
    solve_question,
)


class TestQuestionClassifier(unittest.TestCase):
    """Test deterministic question classifier across all 9 question kinds."""

    def test_classify_largest_room(self):
        q = "Which is the largest kitchen on the ground floor, and how big is it in m²? Finish with a line 'Answer: <room name or number>, <area> m²'."
        self.assertEqual(classify_question(q), "largest_room")

    def test_classify_floor_area_total(self):
        q = "Facilities want the total floor area of every kitchen on the floor 1 added together. How many square metres is that? Finish with a line 'Answer: <number>'."
        self.assertEqual(classify_question(q), "floor_area_total")

    def test_classify_straight_line_3d(self):
        q = "We're planning a wireless sensor link between Office 2.35 (Floor 2) and Office 0.37 (Ground floor). What is the straight-line distance in metres between the centres of the two rooms (each room's floor-plan centroid, at its floor's elevation)? Finish with a line 'Answer: <number>'."
        self.assertEqual(classify_question(q), "straight_line_3d")

    def test_classify_room_stacked_below(self):
        q = "A washing machine is leaking onto the floor of Generic room 00.04.032A (Ground floor). Which room directly below it will the water reach? Finish with a line 'Answer: <room name or number>'."
        self.assertEqual(classify_question(q), "room_stacked")

    def test_classify_room_stacked_above(self):
        q = "There's water dripping from the ceiling in Kitchen 0.16 (Ground floor). Which room is directly above it? Finish with a line 'Answer: <room name or number>'."
        self.assertEqual(classify_question(q), "room_stacked")

    def test_classify_shared_walls_count(self):
        q = "We're soundproofing Living room 0.01 (Ground floor). How many other rooms on that floor share a wall with it? Count every room whose wall runs along it for at least 1 m, with or without a door between them; corridors, stairwells and lifts don't count. Finish with a line 'Answer: <number>'."
        self.assertEqual(classify_question(q), "shared_walls_count")

    def test_classify_wide_delivery_count(self):
        q = "I'm moving a 1.0 m wide hospital bed. It can't go on stairs or steps (lifts are fine), and every door it passes through must be at least 1.0 m wide. It arrives through the entrance into Logistics zone H-D4 (Ground floor). Into how many rooms on the floor 1 can it be delivered? Finish with a line 'Answer: <number>'."
        self.assertEqual(classify_question(q), "wide_delivery_count")

    def test_classify_step_free_reachable_count(self):
        q = "Lift 1 is out of service. A wheelchair user comes in through the entrance into Stairwell N0320A (Ground floor). How many rooms on the floor 2 can they still reach? Finish with a line 'Answer: <number>'."
        self.assertEqual(classify_question(q), "step_free_reachable_count")

    def test_classify_errand(self):
        q = "I'm in Toilet 0.36 (Ground floor). I need to grab a dining table from the room that has one closest to me, then carry it to the largest meeting room on the floor 1. I can carry it on the stairs. How far will I walk in total, in metres? Finish with a line 'Answer: <number>'."
        self.assertEqual(classify_question(q), "errand")

    def test_classify_what_if_door(self):
        q = "What if we add a door between Generic room N0808 (Ground floor) and Generic room N0809 (Ground floor), in the middle of the wall they share? How many rooms on the floor 3 would then have a shorter walk out of the building, to their nearest entrance, by more than 1 m? Finish with a line 'Answer: <number>'."
        self.assertEqual(classify_question(q), "what_if_door")

    def test_classify_invalid_raises(self):
        with self.assertRaises(ValueError):
            classify_question("What is the capital of France?")


class TestFloorAndSpaceResolution(unittest.TestCase):
    """Test floor level parsing and space resolution."""

    def test_parse_floor_level(self):
        self.assertEqual(parse_floor_level("Ground floor"), 0)
        self.assertEqual(parse_floor_level("Ground Floor"), 0)
        self.assertEqual(parse_floor_level("Floor 1"), 1)
        self.assertEqual(parse_floor_level("Floor 4"), 4)
        self.assertEqual(parse_floor_level("Floor -1"), -1)
        self.assertEqual(parse_floor_level("Basement 1"), -1)
        self.assertEqual(parse_floor_level("Basement 2"), -2)
        self.assertEqual(parse_floor_level("3"), 3)
        self.assertEqual(parse_floor_level("-2"), -2)

    def test_resolve_space_by_text(self):
        bdir = Path("data/dev/proc-factory-dev-012")
        building = load_building(bdir)

        # Exact name
        s = resolve_space_by_text(building, "Office 0.34", "Ground floor")
        self.assertIsNotNone(s)
        self.assertEqual(s.id, "proc-factory-dev-012-F0-S034")

        # Ref only
        s_ref = resolve_space_by_text(building, "0.34", "Ground floor")
        self.assertIsNotNone(s_ref)
        self.assertEqual(s_ref.id, "proc-factory-dev-012-F0-S034")

        # With conversational prefix
        s_pref = resolve_space_by_text(building, "entrance into Office 0.34", "Ground floor")
        self.assertIsNotNone(s_pref)
        self.assertEqual(s_pref.id, "proc-factory-dev-012-F0-S034")

        # Non-existent space
        s_none = resolve_space_by_text(building, "NonExistentRoom 999", "Ground floor")
        self.assertIsNone(s_none)


class TestSolverDevExecution(unittest.TestCase):
    """Test solver answering logic across individual dev questions and ground truth scoring."""

    @classmethod
    def setUpClass(cls):
        clear_building_cache()
        cls.bdir_factory = Path("data/dev/proc-factory-dev-012")
        cls.bdir_osm = Path("data/dev/osm-way22744230")
        cls.bdir_swiss = Path("data/dev/swiss-2211")

    def test_solve_largest_room(self):
        q = "Which is the largest kitchen on the ground floor, and how big is it in m²? Finish with a line 'Answer: <room name or number>, <area> m²'."
        ans = answer(self.bdir_factory, q)
        self.assertTrue(ans.startswith("Answer: "))
        self.assertIn("m²", ans)
        committed = ANSWER_LINE.findall(ans)[-1]
        nums = numbers_in(committed)
        self.assertTrue(len(nums) >= 1)
        self.assertTrue(any(abs(n - 28.2) <= 1.5 for n in nums))

    def test_solve_floor_area_total(self):
        q = "Facilities want the total floor area of every kitchen on the floor 1 added together. How many square metres is that? Finish with a line 'Answer: <number>'."
        ans = answer(self.bdir_factory, q)
        committed = ANSWER_LINE.findall(ans)[-1]
        nums = numbers_in(committed)
        self.assertEqual(len(nums), 1)
        self.assertAlmostEqual(nums[0], 106.3, delta=5.5)

    def test_solve_wide_delivery_count(self):
        q = "I'm moving a 1.0 m wide hospital bed. It can't go on stairs or steps (lifts are fine), and every door it passes through must be at least 1.0 m wide. It arrives through the entrance into Logistics zone H-D4 (Ground floor). Into how many rooms on the floor 1 can it be delivered? Finish with a line 'Answer: <number>'."
        ans = answer(self.bdir_factory, q)
        committed = ANSWER_LINE.findall(ans)[-1]
        nums = numbers_in(committed)
        self.assertEqual(len(nums), 1)
        self.assertEqual(nums[0], 10.0)

    def test_solve_errand(self):
        q = "I'm in Toilet 0.36 (Ground floor). I need to grab a dining table from the room that has one closest to me, then carry it to the largest meeting room on the floor 1. I can carry it on the stairs. How far will I walk in total, in metres? Finish with a line 'Answer: <number>'."
        ans = answer(self.bdir_factory, q)
        committed = ANSWER_LINE.findall(ans)[-1]
        nums = numbers_in(committed)
        self.assertEqual(len(nums), 1)
        self.assertAlmostEqual(nums[0], 165.75, delta=2.0)

    def test_solve_shared_walls_count(self):
        q = "We're soundproofing Office 0.34 (Ground floor). How many other rooms on that floor share a wall with it? Count every room whose wall runs along it for at least 1 m, with or without a door between them; corridors, stairwells and lifts don't count. Finish with a line 'Answer: <number>'."
        ans = answer(self.bdir_factory, q)
        committed = ANSWER_LINE.findall(ans)[-1]
        nums = numbers_in(committed)
        self.assertEqual(len(nums), 1)
        self.assertEqual(nums[0], 4.0)

    def test_solve_straight_line_3d(self):
        q = "We're planning a wireless sensor link between Office 2.35 (Floor 2) and Office 0.37 (Ground floor). What is the straight-line distance in metres between the centres of the two rooms (each room's floor-plan centroid, at its floor's elevation)? Finish with a line 'Answer: <number>'."
        ans = answer(self.bdir_factory, q)
        committed = ANSWER_LINE.findall(ans)[-1]
        nums = numbers_in(committed)
        self.assertEqual(len(nums), 1)
        self.assertAlmostEqual(nums[0], 27.37, delta=1.0)

    def test_solve_step_free_reachable_count(self):
        q = "Lift 1 is out of service. A wheelchair user comes in through the entrance into Stairwell N0320A (Ground floor). How many rooms on the floor 2 can they still reach? Finish with a line 'Answer: <number>'."
        ans = answer(self.bdir_osm, q)
        committed = ANSWER_LINE.findall(ans)[-1]
        nums = numbers_in(committed)
        self.assertEqual(len(nums), 1)
        self.assertEqual(nums[0], 30.0)

    def test_solve_question_alias(self):
        q = "Facilities want the total floor area of every kitchen on the floor 1 added together. How many square metres is that? Finish with a line 'Answer: <number>'."
        ans1 = answer(self.bdir_factory, q)
        ans2 = solve_question(self.bdir_factory, q)
        self.assertEqual(ans1, ans2)


class TestBenchmarkScoringCompliance(unittest.TestCase):
    """Test strict adherence to benchmark/score.py constraints."""

    def test_number_answer_single_number_requirement(self):
        # score.py: len(numbers_in(text)) == 1
        truth = {"type": "number", "value": 42.0, "relative_tolerance": 0.05, "absolute_tolerance": 0.0}
        valid_reply = "Answer: 42.0"
        invalid_reply_two_numbers = "Answer: 42.0 on floor 2"
        invalid_reply_m2 = "Answer: 42.0 m^2"

        self.assertTrue(score_reply(truth, valid_reply))
        self.assertFalse(score_reply(truth, invalid_reply_two_numbers))
        self.assertFalse(score_reply(truth, invalid_reply_m2))

    def test_largest_room_space_and_area(self):
        truth = {
            "type": "space",
            "accept": ["0.30", "Kitchen 0.30"],
            "reject": ["0.54", "Kitchen 0.54"],
            "area": {"type": "number", "value": 28.2, "relative_tolerance": 0.05, "absolute_tolerance": 0.0},
        }
        good_reply = "Answer: Kitchen 0.30, 28.2 m²"
        runner_up_first = "Answer: Kitchen 0.54 was larger than Kitchen 0.30, 28.2 m²"
        missing_area = "Answer: Kitchen 0.30"

        self.assertTrue(score_reply(truth, good_reply))
        self.assertFalse(score_reply(truth, runner_up_first))
        self.assertFalse(score_reply(truth, missing_area))


class TestBenchmarkRunnerCLI(unittest.TestCase):
    """Test benchmark_runner functions and CLI evaluation pipeline."""

    def test_load_benchmark_questions_jsonl(self):
        qs = load_benchmark_questions(Path("data/dev"), "questions.jsonl")
        self.assertEqual(len(qs), 138)
        self.assertTrue(all(len(item) == 2 for item in qs))

    def test_load_benchmark_questions_csv(self):
        qs = load_benchmark_questions(Path("data/test"), "data/test/questions.csv")
        self.assertEqual(len(qs), 145)

    def test_write_submission_csv(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            out_path = Path(tmpdir) / "submission.csv"
            replies = [("q1", "Answer: 42"), ("q2", "Answer: Room 1, 10.5 m²")]
            write_submission(out_path, replies)
            self.assertTrue(out_path.exists())

            with out_path.open("r", encoding="utf-8") as f:
                rows = list(csv.DictReader(f))
            self.assertEqual(len(rows), 2)
            self.assertEqual(rows[0]["question_id"], "q1")
            self.assertEqual(rows[0]["answer"], "Answer: 42")

    def test_run_benchmark_single_building(self):
        # Run on single dev building and verify 100% pass
        ret = run_benchmark(
            target_path=Path("data/dev/proc-factory-dev-012"),
            questions_file="questions.jsonl",
            verbose=False,
        )
        self.assertEqual(ret, 0)


class TestEvaluateDataset(unittest.TestCase):
    """Test dataset evaluator metrics."""

    def test_dev_evaluation_100_percent(self):
        clear_building_cache()
        acc = evaluate_dataset("data/dev")
        self.assertIn("all", acc)
        self.assertEqual(acc["all"], 1.0)
        for k in (
            "errand",
            "floor_area_total",
            "largest_room",
            "room_stacked",
            "shared_walls_count",
            "step_free_reachable_count",
            "straight_line_3d",
            "what_if_door",
            "wide_delivery_count",
        ):
            self.assertIn(k, acc)
            self.assertEqual(acc[k], 1.0)


if __name__ == "__main__":
    unittest.main()
