"""Test suite for CLI interface in talk_to_your_building.cli."""

from __future__ import annotations

import csv
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
HACKATHON_DIR = REPO_ROOT / "industrial-agents-hackathon-2026"
DEV_DATA_DIR = HACKATHON_DIR / "data" / "dev"
SAMPLE_BUILDING_DIR = DEV_DATA_DIR / "proc-campus-dev-000"


class TestCLI(unittest.TestCase):
    """Test CLI execution modes."""

    def test_cli_single_question(self):
        cmd = [
            sys.executable,
            "-m",
            "talk_to_your_building.cli",
            "--building-dir",
            str(SAMPLE_BUILDING_DIR),
            "--question",
            "Which is the largest office on the floor 3, and how big is it in m²? Finish with a line 'Answer: <room name or number>, <area> m²'.",
        ]
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            cwd=str(REPO_ROOT),
            env={"PYTHONPATH": f"{REPO_ROOT}:{HACKATHON_DIR}"},
        )
        self.assertEqual(result.returncode, 0, f"CLI failed: {result.stderr}")
        self.assertIn("Answer: Office 3.07, 41.28 m²", result.stdout)

    def test_cli_batch_jsonl(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            out_csv = Path(tmpdir) / "sub.csv"
            cmd = [
                sys.executable,
                "-m",
                "talk_to_your_building.cli",
                "--building-dir",
                str(SAMPLE_BUILDING_DIR),
                "--question-file",
                str(SAMPLE_BUILDING_DIR / "questions.jsonl"),
                "--submission-csv",
                str(out_csv),
            ]
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                cwd=str(REPO_ROOT),
                env={"PYTHONPATH": f"{REPO_ROOT}:{HACKATHON_DIR}"},
            )
            self.assertEqual(result.returncode, 0, f"CLI failed: {result.stderr}")
            self.assertTrue(out_csv.exists())
            with open(out_csv, mode="r", encoding="utf-8") as f:
                reader = csv.reader(f)
                header = next(reader)
                self.assertEqual(header, ["question_id", "answer"])
                rows = list(reader)
                self.assertEqual(len(rows), 5)


if __name__ == "__main__":
    unittest.main()
