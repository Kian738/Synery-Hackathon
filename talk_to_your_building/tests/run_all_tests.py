#!/usr/bin/env python3
"""Unified E2E Test Runner for Talk to Your Building (Track 01).

Runs all 4 test tiers, outputs a structured scorecard summary table,
and returns exit code 0 on complete success.

Usage:
    uv run python talk_to_your_building/tests/run_all_tests.py
    python talk_to_your_building/tests/run_all_tests.py --tier 1
    python talk_to_your_building/tests/run_all_tests.py --verbose
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import glob
import os
from pathlib import Path
import sys
import time
import unittest

# Ensure path resolution and virtualenv site-packages availability
_TESTS_DIR = Path(__file__).resolve().parent
_PACKAGE_DIR = _TESTS_DIR.parent
_REPO_DIR = _PACKAGE_DIR.parent
_STUDENT_KIT_DIR = _REPO_DIR / "industrial-agents-hackathon-2026"

for p in [_PACKAGE_DIR, _REPO_DIR, _STUDENT_KIT_DIR]:
    if str(p) not in sys.path and p.exists():
        sys.path.insert(0, str(p))

try:
    import shapely  # noqa: F401
except ImportError:
    for pattern in [
        str(_STUDENT_KIT_DIR / ".venv" / "lib" / "python*" / "site-packages"),
        str(_REPO_DIR / ".venv" / "lib" / "python*" / "site-packages"),
    ]:
        for sp in glob.glob(pattern):
            if sp not in sys.path:
                sys.path.append(sp)


@dataclass
class TierResult:
    tier_num: int
    tier_name: str
    total: int
    passed: int
    failed: int
    errors: int
    skipped: int
    duration_sec: float


class UnifiedTestRunner:
    """Executes test tiers and formats structured scorecard reports."""

    TIER_MODULES = {
        1: ("Tier 1: Feature Coverage (>=5 tests/feat)", "talk_to_your_building.tests.tier1_feature_tests"),
        2: ("Tier 2: Boundary & Corner Cases (>=5/feat)", "talk_to_your_building.tests.tier2_boundary_tests"),
        3: ("Tier 3: Cross-Feature Combinations", "talk_to_your_building.tests.tier3_combination_tests"),
        4: ("Tier 4: Real-World Workload Scenarios", "talk_to_your_building.tests.tier4_workload_tests"),
        5: ("Tier 5: Adversarial Stress & Fuzzing", "talk_to_your_building.tests.tier5_adversarial_tests"),
    }

    def __init__(self, verbosity: int = 1):
        self.verbosity = verbosity

    def run_tier(self, tier_num: int) -> TierResult:
        tier_name, module_name = self.TIER_MODULES[tier_num]
        loader = unittest.TestLoader()

        try:
            suite = loader.loadTestsFromName(module_name)
        except Exception as e:
            print(f"Error loading {module_name}: {e}")
            return TierResult(tier_num, tier_name, 0, 0, 1, 0, 0, 0.0)

        # Silent or verbose runner stream
        stream = sys.stdout if self.verbosity > 1 else open(os.devnull, "w")
        runner = unittest.TextTestRunner(stream=stream, verbosity=self.verbosity)

        t0 = time.perf_counter()
        result = runner.run(suite)
        t_elapsed = time.perf_counter() - t0

        if stream is not sys.stdout:
            stream.close()

        total = result.testsRun
        failed = len(result.failures)
        errors = len(result.errors)
        skipped = len(result.skipped)
        passed = total - failed - errors - skipped

        if failed > 0 or errors > 0:
            print(f"\n[FAILURES in Tier {tier_num}]")
            for f in result.failures:
                print(f"FAILED: {f[0]}\n{f[1]}")
            for err in result.errors:
                print(f"ERROR: {err[0]}\n{err[1]}")

        return TierResult(
            tier_num=tier_num,
            tier_name=tier_name,
            total=total,
            passed=passed,
            failed=failed,
            errors=errors,
            skipped=skipped,
            duration_sec=round(t_elapsed, 3),
        )

    def print_summary(self, results: list[TierResult]) -> int:
        print("\n" + "=" * 80)
        print("          TALK TO YOUR BUILDING (TRACK 01) — E2E TEST SCORECARD")
        print("=" * 80)
        print(f"{'Tier':<4} | {'Description':<42} | {'Pass':<5} | {'Fail':<5} | {'Skip':<5} | {'Time (s)':<8}")
        print("-" * 80)

        tot_tests = 0
        tot_passed = 0
        tot_failed = 0
        tot_errors = 0
        tot_skipped = 0
        tot_duration = 0.0

        for r in results:
            tot_tests += r.total
            tot_passed += r.passed
            tot_failed += r.failed
            tot_errors += r.errors
            tot_skipped += r.skipped
            tot_duration += r.duration_sec

            print(
                f"T{r.tier_num:<3} | {r.tier_name:<42} | {r.passed:<5} | {r.failed + r.errors:<5} | {r.skipped:<5} | {r.duration_sec:<8.3f}"
            )

        print("-" * 80)
        print(
            f"{'ALL':<4} | {'TOTAL CONSOLIDATED SUITE':<42} | {tot_passed:<5} | {tot_failed + tot_errors:<5} | {tot_skipped:<5} | {tot_duration:<8.3f}"
        )
        print("=" * 80)

        all_passed = (tot_failed == 0 and tot_errors == 0 and tot_tests > 0)
        if all_passed:
            print(f"  >>> OVERALL RESULT: ALL {tot_passed} TESTS PASSED (100% SUCCESS) <<<")
            print("=" * 80 + "\n")
            return 0
        else:
            print(f"  >>> OVERALL RESULT: FAILED ({tot_failed + tot_errors} failures/errors) <<<")
            print("=" * 80 + "\n")
            return 1


def main() -> int:
    parser = argparse.ArgumentParser(description="Run Talk to Your Building E2E test tiers.")
    parser.add_argument("--tier", type=int, choices=[1, 2, 3, 4, 5], help="Run a specific tier (1, 2, 3, 4, or 5).")
    parser.add_argument("-v", "--verbose", action="store_true", help="Enable verbose per-test output.")
    args = parser.parse_args()

    verbosity = 2 if args.verbose else 1
    runner = UnifiedTestRunner(verbosity=verbosity)

    tiers_to_run = [args.tier] if args.tier else [1, 2, 3, 4, 5]

    print(f"Executing Talk to Your Building E2E Test Suite (Tiers: {', '.join(str(t) for t in tiers_to_run)})...")
    results = []
    for t in tiers_to_run:
        print(f"Running Tier {t}...", end="", flush=True)
        res = runner.run_tier(t)
        print(f" done ({res.passed}/{res.total} passed in {res.duration_sec}s)")
        results.append(res)

    exit_code = runner.print_summary(results)
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
