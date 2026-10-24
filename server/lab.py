"""Benchmark Lab API: read eval runs (runs/*), compare them, browse the dataset, launch suites with live logs."""

import asyncio
import csv
import json
import os
import subprocess
import sys
import threading
import time
import uuid
from collections import Counter, defaultdict
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from eval.ledger import RUNS
from floorwise.paths import DATA, ROOT

router = APIRouter(prefix="/api/lab")

SUITES = {
    "routes": {"label": "Route model vs warm-up gold", "llm": False, "args": ["--split"]},
    "solver": {"label": "Solver with gold inputs", "llm": False, "args": ["--split", "--kinds"]},
    "parser": {"label": "Text -> ids vs gold", "llm": "optional", "args": ["--split", "--parser", "--limit", "--model"]},
    "e2e": {"label": "Benchmark end to end", "llm": "optional", "args": ["--split", "--kinds"]},
    "e2e_basic": {"label": "Warm-up families end to end", "llm": "optional", "args": ["--split"]},
    "robust": {"label": "Reworded questions", "llm": "optional", "args": ["--split", "--variants", "--limit"]},
    "metamorphic": {"label": "Invariance and properties", "llm": False, "args": ["--split", "--limit"]},
    "build": {"label": "Rebuild floors from images", "llm": False, "args": ["--split", "--limit"]},
    "interaction": {"label": "Tricky users + judge", "llm": True, "args": ["--only", "--judge-model"]},
    "walkability": {"label": "Drawn routes are walkable", "llm": False, "args": ["--split", "--pairs", "--limit"]},
    "gates": {"label": "All free checks", "llm": False, "args": []},
}
JOBS: dict[str, dict] = {}
JOB_TIMEOUT_S = int(os.environ.get("FLOORWISE_JOB_TIMEOUT_S", "1200"))
JOB_TOKEN_BUDGET = os.environ.get("FLOORWISE_JOB_MAX_TOKENS", "300000")


def summaries() -> list[dict]:
    out = []
    for path in sorted(RUNS.glob("*/summary.json")):
        try:
            summary = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        summary["run"] = path.parent.name
        summary["started"] = path.parent.name[:15]
        out.append(summary)
    return out


@router.get("/checks")
def checks() -> dict:
    from server.checks import sheet

    return sheet(summaries())


@router.get("/suites")
def suites() -> dict:
    from floorwise import llm

    status = llm.info()
    return {"suites": SUITES, "provider": {"name": status.name, "available": status.available, "models": status.models}}


@router.get("/runs")
def runs() -> list[dict]:
    return [{k: v for k, v in s.items() if k not in ("by_source",)} for s in reversed(summaries())]


@router.get("/runs/{run}")
def run_detail(run: str) -> dict:
    directory = RUNS / run
    if not (directory / "summary.json").exists() or directory.parent != RUNS:
        raise HTTPException(404, "unknown run")
    summary = json.loads((directory / "summary.json").read_text(encoding="utf-8"))
    rows = [json.loads(line) for line in (directory / "results.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
    return {"summary": summary, "rows": rows}


@router.get("/compare")
def compare(a: str, b: str) -> dict:
    left, right = run_detail(a), run_detail(b)
    before = {r["id"]: r for r in left["rows"]}
    after = {r["id"]: r for r in right["rows"]}
    changes = []
    for item_id in sorted(set(before) | set(after)):
        old, new = before.get(item_id), after.get(item_id)
        old_ok = old.get("correct") if old else None
        new_ok = new.get("correct") if new else None
        if old_ok != new_ok:
            changes.append({"id": item_id, "kind": (new or old).get("kind"), "source": (new or old).get("source"),
                            "before": old_ok, "after": new_ok,
                            "status": "fixed" if new_ok and old_ok is False else "broken" if old_ok and new_ok is False else "changed"})
    order = {"broken": 0, "changed": 1, "fixed": 2}
    changes.sort(key=lambda c: order[c["status"]])
    return {"a": left["summary"], "b": right["summary"], "changes": changes,
            "counts": dict(Counter(c["status"] for c in changes))}


@router.get("/dataset")
def dataset() -> dict:
    with (DATA / "manifest.csv").open(encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    kinds: dict[str, Counter] = defaultdict(Counter)
    for split in ("train", "dev", "test"):
        for path in (DATA / split).glob("*/questions.jsonl"):
            for line in path.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    kinds[path.parent.name][json.loads(line)["kind"]] += 1
    for row in rows:
        row["kinds"] = dict(kinds.get(row["building_id"], {}))
    totals = Counter()
    for split_rows in rows:
        totals[split_rows["split"]] += 1
    return {"buildings": rows, "splits": dict(totals)}


class Launch(BaseModel):
    suite: str
    args: list[str] = []


@router.post("/jobs")
def launch(body: Launch) -> dict:
    if body.suite not in SUITES:
        raise HTTPException(422, "unknown suite")
    allowed = set(SUITES[body.suite]["args"]) | {"-v"}
    flags = [a for a in body.args if a.startswith("-")]
    if any(f not in allowed for f in flags):
        raise HTTPException(422, f"allowed flags for {body.suite}: {sorted(allowed)}")
    job_id = uuid.uuid4().hex[:8]
    env = {**os.environ, "PYTHONIOENCODING": "utf-8", "FLOORWISE_MAX_TOKENS": JOB_TOKEN_BUDGET}
    if "llm" not in body.args and "paraphrase" not in body.args and SUITES[body.suite]["llm"] in ("optional", False):
        env["FLOORWISE_OFFLINE"] = "1"
    command = [sys.executable, "-u", "-m", "eval", body.suite, *body.args]
    job = {"id": job_id, "suite": body.suite, "args": body.args, "started": time.time(), "lines": [], "done": False,
           "code": None, "run": None}
    JOBS[job_id] = job

    def work() -> None:
        before = {p.name for p in RUNS.glob("*")} if RUNS.exists() else set()
        process = subprocess.Popen(command, cwd=ROOT, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                   text=True, encoding="utf-8", errors="replace")
        job["process"] = process
        deadline = threading.Timer(JOB_TIMEOUT_S, lambda: (job["lines"].append(f"[lab] stopped: over {JOB_TIMEOUT_S}s"), process.kill()))
        deadline.start()
        for line in process.stdout:
            job["lines"].append(line.rstrip())
        job["code"] = process.wait()
        deadline.cancel()
        new = sorted({p.name for p in RUNS.glob("*")} - before)
        job["run"] = new[-1] if new else None
        job["done"] = True

    threading.Thread(target=work, daemon=True).start()
    return {"id": job_id}


@router.post("/jobs/{job_id}/cancel")
def cancel(job_id: str) -> dict:
    job = JOBS.get(job_id)
    if not job or job["done"] or "process" not in job:
        raise HTTPException(404, "no running job")
    job["lines"].append("[lab] cancelled by user")
    job["process"].kill()
    return {"cancelled": job_id}


@router.get("/jobs")
def jobs() -> list[dict]:
    return [{k: v for k, v in j.items() if k not in ("lines", "process")} | {"last": j["lines"][-1] if j["lines"] else ""}
            for j in sorted(JOBS.values(), key=lambda j: -j["started"])]


@router.get("/jobs/{job_id}/stream")
async def stream(job_id: str) -> StreamingResponse:
    if job_id not in JOBS:
        raise HTTPException(404, "unknown job")
    job = JOBS[job_id]

    async def events():
        sent = 0
        while True:
            lines = job["lines"]
            while sent < len(lines):
                yield f"data: {json.dumps({'type': 'line', 'text': lines[sent]})}\n\n"
                sent += 1
            if job["done"] and sent >= len(job["lines"]):
                yield f"data: {json.dumps({'type': 'done', 'code': job['code'], 'run': job['run']})}\n\n"
                break
            await asyncio.sleep(0.25)

    return StreamingResponse(events(), media_type="text/event-stream")


@router.get("/route-preview")
def route_preview(building: str, start: str, destination: str = "", step_free: bool = False) -> dict:
    """Route geometry for drill-down views. start may be a comma-separated list of stops."""
    from floorwise.core.graph import Constraints
    from floorwise.core.routing import NoRoute, plan_route
    from server.app import load

    b = load(building)
    stops = [s for s in start.split(",") if s] + ([destination] if destination else [])
    try:
        return plan_route(b, stops, Constraints(step_free=step_free)).to_dict()
    except (NoRoute, KeyError) as error:
        raise HTTPException(422, str(error)) from error
