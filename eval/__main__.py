"""uv run python -m eval <suite> [suite args]   suites: atlas routes solver parser e2e e2e_basic sunday generated rules robust metamorphic build interaction report
uv run python -m eval gates                      every offline gate in order (free, no API key needed)"""

import importlib
import os
import sys

SUITES = ["scenarios","unseen","private","chat_regressions","atlas", "routes", "solver", "parser", "e2e", "e2e_basic", "sunday", "generated", "rules", "roundtrip", "walls", "edits", "robust", "metamorphic", "walkability", "build", "interaction", "differential", "rehearse", "report", "gold", "audit_all", "connectivity", "overlaps", "orientation"]
GATES = [
    ["routes", "--split", "train,dev"],
    ["solver", "--split", "train,dev"],
    ["parser", "--split", "train,dev"],
    ["parser", "--split", "test"],
    ["e2e", "--split", "train,dev"],
    ["e2e_basic", "--split", "train,dev"],
    ["sunday", "--split", "train,dev"],
    ["generated", "--split", "dev", "--per-building", "4"],
    ["rules", "--split", "dev", "--limit", "16", "--pairs", "2", "--samples", "3"],
    ["roundtrip", "--split", "dev", "--per-building", "6"],
    ["walls", "--split", "dev", "--pairs", "4"],
    ["edits", "--split", "dev", "--per-building", "2", "--limit", "12"],
    ["robust", "--split", "dev"],
    ["metamorphic", "--split", "dev"],
    ["walkability", "--split", "dev", "--pairs", "4"],
    ["differential", "--split", "dev", "--limit", "8"],
    ["gold", "--split", "train,dev", "--per-building", "4"],
    ["gold", "--split", "train,dev", "--per-building", "6", "--holdout"],
    ["report"],
]


def run(suite: str, args: list[str]) -> None:
    sys.argv = [f"eval.{suite}", *args]
    importlib.import_module(f"eval.{suite}").main()


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if len(sys.argv) < 2 or sys.argv[1] not in SUITES + ["gates"]:
        sys.exit(__doc__)
    if sys.argv[1] == "gates":
        os.environ.setdefault("FLOORWISE_OFFLINE", "1")
        for gate in GATES:
            print(f"\n##### {' '.join(gate)}")
            from eval.ledger import Ledger
            import json
            before = len(Ledger.completed)
            run(gate[0], gate[1:])
            if gate[0] != "report":
                created = Ledger.completed[before:]
                if len(created) != 1:
                    raise SystemExit(f"Gate {gate[0]} did not produce exactly one summary")
                summary = json.loads(created.pop().read_text(encoding="utf-8"))
                if summary.get("source_changed") or summary.get("incomplete") or any(
                    summary.get("outcomes", {}).get(outcome, 0) for outcome in ("error", "skipped", "incomplete")
                ):
                    raise SystemExit(f"FAILED {gate[0]}: source changed, required cases skipped, or evaluation incomplete")
                threshold = {"walls": 0.98}.get(gate[0], 1.0)  # walls: data oddities at entrances leave about 1 %; strict: only diagnosed misses (eval/known_issues.json) may remain
                explained = summary.get("known_failures", 0)
                if summary["total"] and summary["total"] > explained:
                    summary["accuracy"] = summary["correct"] / (summary["total"] - explained)
                if gate[0] == "walkability":
                    withheld = summary["by_kind"].get("no validated route (guidance withheld)", {}).get("correct", 0)
                    unreachable = summary["by_kind"].get("no route in the building model (not walked)", {}).get("correct", 0)
                    walked = summary["total"] - unreachable
                    if walked and (walked - withheld) / walked < 0.8:
                        raise SystemExit("FAILED walkability: fewer than 80% of sampled pairs have validated routes")
                if not summary["total"] or summary["accuracy"] is None or summary["accuracy"] < threshold:
                    raise SystemExit(f"FAILED {gate[0]}: {summary['accuracy']} below {threshold}")
                if summary.get("unexplained_failures"):  # strict: only diagnosed misses may remain, however high the score
                    raise SystemExit(f"FAILED {gate[0]}: {summary['unexplained_failures']} unexplained miss(es): {summary['unexplained_ids'][:8]}")
        return
    run(sys.argv[1], sys.argv[2:])


if __name__ == "__main__":
    main()
