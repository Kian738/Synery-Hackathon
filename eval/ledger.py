"""Run ledger: every eval run writes runs/<timestamp>_<suite>/ with results.jsonl and summary.json,
so runs can be compared over time (eval.report) instead of eyeballed."""

import json
import subprocess
import time
import uuid
from collections import Counter, defaultdict
from pathlib import Path

from floorwise.paths import ROOT

RUNS = ROOT / "runs"


def known_issues() -> dict:
    """Ids of questions diagnosed as unanswerable from their wording (eval/known_issues.json)."""
    path = Path(__file__).with_name("known_issues.json")
    try:
        return {k: v for k, v in json.loads(path.read_text(encoding="utf-8")).items() if not k.startswith("_")}
    except (OSError, ValueError):
        return {}


def git_sha() -> str:
    try:
        return subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"], cwd=ROOT, capture_output=True, text=True, check=True
        ).stdout.strip()
    except Exception:  # noqa: BLE001
        return "nogit"


class Ledger:
    completed: list[Path] = []

    def __init__(self, suite: str, config: dict, name: str | None = None) -> None:
        stamp = time.strftime("%Y%m%d-%H%M%S")
        self.directory = RUNS / f"{stamp}_{suite}{'_' + name if name else ''}_{uuid.uuid4().hex[:8]}"
        self.directory.mkdir(parents=True, exist_ok=False)
        self.suite, self.config = suite, dict(config)
        import os
        if os.environ.get('FLOORWISE_LAB_JOB_ID'):
            self.config['job_id'] = os.environ['FLOORWISE_LAB_JOB_ID']
        from eval.evidence import fingerprint
        self.fingerprint = fingerprint()
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

        known = known_issues()
        failures = [row for row in self.rows if row.get("correct") is False]
        explained = [row for row in failures if row.get("id") in known]
        unexplained = [row for row in failures if row.get("id") not in known]
        total = len(self.rows)
        correct = sum(1 for row in self.rows if row.get("correct"))
        cluster_ci = clustered(self.rows)
        from eval.evidence import fingerprint, compatible
        source_changed=not compatible(self.fingerprint, fingerprint())
        summary = {
            "suite": self.suite,
            "config": self.config,
            "git": git_sha(),
            "fingerprint": self.fingerprint,
            "source_changed": source_changed,
            "incomplete": any(row.get('outcome') == 'incomplete' for row in self.rows),
            "outcomes": dict(Counter(row.get('outcome', 'passed' if row.get('correct') else 'failed') for row in self.rows)),
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
            # A miss is "known" only when eval/known_issues.json has a diagnosis for that exact id.
            "known_failures": len(explained),
            "unexplained_failures": len(unexplained),
            "unexplained_ids": [row.get("id") for row in unexplained][:50],
        }
        (self.directory / "summary.json").write_text(json.dumps(summary, indent=1), encoding="utf-8")
        self.completed.append(self.directory / "summary.json")
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
    if summary.get("known_failures") or summary.get("unexplained_failures"):
        print(f"  misses: {summary.get('known_failures', 0)} known (diagnosed), {summary.get('unexplained_failures', 0)} unexplained"
              + (f" -> {', '.join(summary['unexplained_ids'][:6])}" if summary.get("unexplained_ids") else ""))
    if summary.get("usage"):
        print(f"  usage: {summary['usage']}")
