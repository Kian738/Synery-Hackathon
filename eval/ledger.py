"""Run ledger: every eval run writes runs/<timestamp>_<suite>/ with results.jsonl and summary.json,
so runs can be compared over time (eval.report) instead of eyeballed."""

import json
import subprocess
import time
from collections import Counter, defaultdict
from pathlib import Path

from floorwise.paths import ROOT

RUNS = ROOT / "runs"


def git_sha() -> str:
    try:
        return subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"], cwd=ROOT, capture_output=True, text=True, check=True
        ).stdout.strip()
    except Exception:  # noqa: BLE001
        return "nogit"


class Ledger:
    def __init__(self, suite: str, config: dict, name: str | None = None) -> None:
        stamp = time.strftime("%Y%m%d-%H%M%S")
        self.directory = RUNS / f"{stamp}_{suite}{'_' + name if name else ''}"
        self.directory.mkdir(parents=True, exist_ok=True)
        self.suite, self.config = suite, dict(config)
        import os

        if os.environ.get("FLOORWISE_OFFLINE") != "1":
            from floorwise import llm

            info = llm.info()
            self.config["llm"] = f"{info.name}:{info.models['chat']}" if info.available else "none"
        self.handle = (self.directory / "results.jsonl").open("w", encoding="utf-8")
        self.rows: list[dict] = []
        self.started = time.time()
        self.usage: Counter = Counter()

    def record(self, **row) -> None:
        self.rows.append(row)
        self.handle.write(json.dumps(row, ensure_ascii=False, default=str) + "\n")
        self.handle.flush()

    def add_usage(self, usage: dict) -> None:
        self.usage.update({k: v for k, v in usage.items() if isinstance(v, (int, float))})

    def finish(self, quiet: bool = False) -> dict:
        self.handle.close()
        by_kind: dict[str, Counter] = defaultdict(Counter)
        by_source: dict[str, Counter] = defaultdict(Counter)
        for row in self.rows:
            outcome = "correct" if row.get("correct") else "wrong"
            by_kind[row.get("kind", "?")][outcome] += 1
            by_source[row.get("source", "?")][outcome] += 1
        from eval.stats import clustered, wilson

        total = len(self.rows)
        correct = sum(1 for row in self.rows if row.get("correct"))
        cluster_ci = clustered(self.rows)
        summary = {
            "suite": self.suite,
            "config": self.config,
            "git": git_sha(),
            "seconds": round(time.time() - self.started, 1),
            "total": total,
            "correct": correct,
            "accuracy": round(correct / total, 4) if total else None,
            "ci95_wilson": [round(v, 4) for v in wilson(correct, total)],
            "ci95_clustered": [round(v, 4) for v in cluster_ci] if cluster_ci else None,
            "buildings": len({row.get("building") for row in self.rows if row.get("building")}),
            "by_kind": {k: dict(v) for k, v in sorted(by_kind.items())},
            "by_source": {k: dict(v) for k, v in sorted(by_source.items())},
            "usage": dict(self.usage),
        }
        (self.directory / "summary.json").write_text(json.dumps(summary, indent=1), encoding="utf-8")
        if not quiet:
            print_summary(summary)
            print(f"run saved to {self.directory}")
        return summary


def print_summary(summary: dict) -> None:
    print(f"\n[{summary['suite']}]  {summary['correct']}/{summary['total']}  ({(summary['accuracy'] or 0):.1%})")
    for title, table in (("kind", summary["by_kind"]), ("source", summary["by_source"])):
        print(f"  by {title}:")
        for key, counts in table.items():
            right, wrong = counts.get("correct", 0), counts.get("wrong", 0)
            print(f"    {key:28s} {right:4d}/{right + wrong:<4d}" + ("" if not wrong else "   <-- misses"))
    if summary.get("usage"):
        print(f"  usage: {summary['usage']}")
