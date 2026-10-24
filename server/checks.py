"""The Lab's inspection sheet: every eval suite as a plain-language check with a target, grouped by what the
jury grades. One place to edit names, targets and what a run costs."""

from dataclasses import asdict, dataclass, field


@dataclass
class Check:
    id: str
    group: str
    title: str
    proves: str
    suite: str
    args: list[str]
    target: float  # share of items that must pass
    cost: str  # "free" or a rough LLM cost
    config: dict = field(default_factory=dict)  # how to recognise this check's runs (subset of the run config)


GROUPS = [
    ("benchmark", "Benchmark answers", "55 % of the grade: the hidden Sunday building and the test set are scored on these answers."),
    ("sunday", "Ready for an unseen building", "Things that must hold on a building and wording we have never seen."),
    ("conversation", "Conversation", "25 % of the grade: tricky users, judged on asking only what is needed, showing understanding, followable directions."),
    ("build", "Build from floor plans", "Level 4: turning plan images into a navigable building."),
]

CHECKS = [
    Check("answers_dev", "benchmark", "Answers benchmark questions correctly",
          "All 9 benchmark question types on the 40 dev buildings, scored by the official scorer.",
          "e2e", ["--split", "dev"], 0.99, "free", {"splits": "dev"}),
    Check("answers_train", "benchmark", "Same on 200 more buildings",
          "The benchmark path on train + dev (655 questions). Guards against tuning to dev.",
          "e2e", ["--split", "train,dev"], 0.99, "free", {"splits": "train,dev"}),
    Check("routes_basic", "benchmark", "Finds things and routes like the dataset",
          "Locate, count, route, step-free, closures and tours from the question text (dev).",
          "e2e_basic", ["--split", "dev"], 0.99, "free", {"splits": "dev"}),
    Check("route_model", "benchmark", "Route lengths match the dataset to the centimetre",
          "Our graph against 2,130 warm-up answers.", "routes", ["--split", "train,dev"], 1.0, "free", {"splits": "train,dev"}),
    Check("solver", "benchmark", "Geometry and counting are exact",
          "Every benchmark answer when the solver is given the right rooms (areas, walls, stacking, reach).",
          "solver", ["--split", "train,dev"], 1.0, "free", {"splits": "train,dev"}),
    Check("test_coverage", "benchmark", "Every test question is understood",
          "All 145 public test questions parse and resolve to real rooms (no answers exist to score).",
          "parser", ["--split", "test"], 1.0, "free", {"splits": "test", "parser": "rules"}),
    Check("reworded", "sunday", "Survives reworded questions",
          "Same questions with different case, floor words, room numbers only, typos.",
          "robust", ["--split", "dev", "--variants", "perturb"], 1.0, "free", {"split": "dev", "variants": "perturb"}),
    Check("llm_parser", "sunday", "Understands new phrasings (Claude)",
          "When the free parser does not recognise the wording, Claude must extract the right rooms.",
          "parser", ["--split", "dev", "--parser", "llm", "--limit", "40"], 0.95, "≈ $0.05", {"splits": "dev", "parser": "llm"}),
    Check("paraphrase", "sunday", "Understands free paraphrases (Claude)",
          "Dev questions rewritten by a model, answered end to end.",
          "robust", ["--split", "dev", "--variants", "paraphrase", "--limit", "30"], 0.9, "≈ $0.20", {"split": "dev", "variants": "paraphrase"}),
    Check("invariance", "sunday", "Answers don't depend on how the file is written",
          "Moving, shuffling or rotating a building must not change answers; routes keep sane properties.",
          "metamorphic", ["--split", "dev"], 1.0, "free", {"splits": "dev"}),
    Check("walkable", "sunday", "Drawn routes are walkable",
          "Routes stay inside rooms, go around furniture and never jump between entrances.",
          "walkability", ["--split", "dev", "--pairs", "4"], 1.0, "free", {"split": "dev"}),
    Check("conversation", "conversation", "Handles tricky users",
          "8 scripted people (first day, wheelchair, technician, facility manager, vague, wrong room, avoid, change of mind) "
          "with rule checks and a judge.", "interaction", [], 0.85, "≈ $0.50 (Claude)", {}),
    Check("build_plans", "build", "Rebuilds floors from plan images",
          "Rooms and doors recovered from plan images match the true plan (IoU ≥ 0.5).",
          "build", ["--split", "dev", "--limit", "15"], 0.6, "free", {"split": "dev"}),
]


def matches(check: Check, summary: dict) -> bool:
    if summary.get("suite") != check.suite:
        return False
    config = summary.get("config") or {}
    for key, value in check.config.items():
        have = config.get(key)
        if isinstance(have, list):
            have = ",".join(have)
        if str(have) != str(value):
            return False
    if "(Claude)" in check.title and not str(config.get("llm", "")).startswith("anthropic"):
        return False
    if check.suite == "parser" and "parser" not in check.config and config.get("parser") not in (None, "rules"):
        return False
    return True


def sheet(summaries: list[dict]) -> dict:
    rows = []
    for check in CHECKS:
        runs = [s for s in summaries if matches(check, s)]
        latest = runs[-1] if runs else None
        accuracy = latest.get("accuracy") if latest else None
        status = "not run" if latest is None else ("pass" if (accuracy or 0) >= check.target else "fail")
        rows.append({**asdict(check), "status": status, "latest": latest, "history": [s.get("accuracy") for s in runs[-10:]]})
    counts = {k: sum(1 for r in rows if r["status"] == k) for k in ("pass", "fail", "not run")}
    return {"groups": [{"id": g, "title": t, "about": a} for g, t, a in GROUPS], "checks": rows, "counts": counts}
