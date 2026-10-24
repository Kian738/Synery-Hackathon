"""uv run python -m eval <suite> [suite args]   suites: routes solver parser e2e e2e_basic robust metamorphic build interaction report
uv run python -m eval gates                      every offline gate in order (free, no API key needed)"""

import importlib
import os
import sys

SUITES = ["routes", "solver", "parser", "e2e", "e2e_basic", "robust", "metamorphic", "build", "interaction", "report"]
GATES = [
    ["routes", "--split", "train,dev"],
    ["solver", "--split", "train,dev"],
    ["parser", "--split", "train,dev"],
    ["parser", "--split", "test"],
    ["e2e", "--split", "train,dev"],
    ["e2e_basic", "--split", "dev"],
    ["robust", "--split", "dev"],
    ["metamorphic", "--split", "dev"],
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
            run(gate[0], gate[1:])
        return
    run(sys.argv[1], sys.argv[2:])


if __name__ == "__main__":
    main()
