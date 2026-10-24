"""Leaderboard of every eval run (runs/*/summary.json) as one HTML page: latest score per suite, its trend,
and per-kind regressions against the previous run of the same suite and config.

  uv run python -m eval.report   -> runs/report.html"""

import html
import json
from collections import defaultdict

from eval.ledger import RUNS


def load() -> list[dict]:
    runs = []
    for path in sorted(RUNS.glob("*/summary.json")):
        summary = json.loads(path.read_text(encoding="utf-8"))
        summary["run"] = path.parent.name
        runs.append(summary)
    return runs


def key(summary: dict) -> str:
    config = {k: v for k, v in summary.get("config", {}).items() if v}
    return f"{summary['suite']} {json.dumps(config, sort_keys=True)}"


def kind_rates(summary: dict) -> dict[str, float]:
    return {k: v.get("correct", 0) / max(1, v.get("correct", 0) + v.get("wrong", 0)) for k, v in summary["by_kind"].items()}


def main() -> None:
    groups = defaultdict(list)
    for summary in load():
        groups[key(summary)].append(summary)
    rows = []
    for name, runs in sorted(groups.items()):
        latest = runs[-1]
        previous = runs[-2] if len(runs) > 1 else None
        trend = " ".join(f"{(r['accuracy'] or 0) * 100:.1f}" for r in runs[-8:])
        regressions = []
        if previous:
            before, after = kind_rates(previous), kind_rates(latest)
            regressions = [f"{k}: {before[k]:.0%}→{after[k]:.0%}" for k in after if k in before and after[k] < before[k] - 1e-9]
        rows.append(
            f"<tr><td>{html.escape(name)}</td><td class=num>{(latest['accuracy'] or 0) * 100:.1f}%</td>"
            f"<td class=num>{latest['correct']}/{latest['total']}</td><td>{html.escape(trend)}</td>"
            f"<td class={'bad' if regressions else 'ok'}>{html.escape(', '.join(regressions) or 'none')}</td>"
            f"<td>{latest['git']}</td><td>{latest['run']}</td></tr>"
        )
    page = f"""<!doctype html><html><head><meta charset=utf-8><title>Floorwise evals</title><style>
body{{font:14px Inter,system-ui,sans-serif;margin:24px;background:#0f1216;color:#e7eaee}}
table{{border-collapse:collapse;width:100%}}td,th{{padding:6px 10px;border-bottom:1px solid #2a313b;text-align:left}}
th{{color:#8b95a3;font-weight:500}}.num{{text-align:right;font-variant-numeric:tabular-nums}}.bad{{color:#ff5a5f}}.ok{{color:#3ccf91}}
</style></head><body><h2>Floorwise eval leaderboard</h2>
<table><tr><th>suite + config</th><th>latest</th><th></th><th>trend (last 8, %)</th><th>regressions vs previous</th><th>git</th><th>run</th></tr>
{''.join(rows)}</table></body></html>"""
    out = RUNS / "report.html"
    out.write_text(page, encoding="utf-8")
    print(f"{len(rows)} suites -> {out}")


if __name__ == "__main__":
    main()
