"""uv run python -m eval <suite> [suite args]   suites: atlas routes solver parser e2e e2e_basic robust metamorphic build interaction report
uv run python -m eval gates                      every offline gate in order (free, no API key needed)"""

import importlib
import os
import sys

SUITES = ["atlas", "routes", "solver", "parser", "e2e", "e2e_basic", "robust", "metamorphic", "walkability", "build", "interaction", "differential", "rehearse", "report"]
GATES = [
    ["routes", "--split", "train,dev"],
    ["solver", "--split", "train,dev"],
    ["parser", "--split", "train,dev"],
    ["parser", "--split", "test"],
    ["e2e", "--split", "train,dev"],
    ["e2e_basic", "--split", "train,dev"],
    ["robust", "--split", "dev"],
    ["metamorphic", "--split", "dev"],
    ["walkability", "--split", "dev", "--pairs", "4"],
    ["differential", "--split", "dev", "--limit", "8"],
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
            from pathlib import Path
            import json
            before = set(Path("runs").glob("*/summary.json"))
            run(gate[0], gate[1:])
            if gate[0] != "report":
                created = set(Path("runs").glob("*/summary.json")) - before
                if len(created) != 1:
                    raise SystemExit(f"Gate {gate[0]} did not produce exactly one summary")
                summary = json.loads(created.pop().read_text(encoding="utf-8"))
                threshold = {"e2e": 0.99, "e2e_basic": 0.99}.get(gate[0], 1.0)
                if gate[0] == "walkability":
                    withheld = summary["by_kind"].get("no validated route (guidance withheld)", {}).get("correct", 0)
                    if summary["total"] and (summary["total"] - withheld) / summary["total"] < 0.8:
                        raise SystemExit("FAILED walkability: fewer than 80% of sampled pairs have validated routes")
                if not summary["total"] or summary["accuracy"] is None or summary["accuracy"] < threshold:
                    raise SystemExit(f"FAILED {gate[0]}: {summary['accuracy']} below {threshold}")
        return
    run(sys.argv[1], sys.argv[2:])


if __name__ == "__main__":
    main()
