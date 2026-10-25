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
from fastapi.responses import StreamingResponse, FileResponse
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
    "sunday": {"label": "Judges' route scoring, replicated", "llm": "optional", "args": ["--split", "--kinds"]},
    "generated": {"label": "New route questions on any building", "llm": "optional", "args": ["--split", "--per-building", "--limit", "--seed"]},
    "rules": {"label": "Every route rule as a property", "llm": False, "args": ["--split", "--pairs", "--samples", "--limit", "--seed"]},
    "roundtrip": {"label": "Question text round trip, any building", "llm": False, "args": ["--split", "--per-building", "--limit", "--seed"]},
    "walls": {"label": "Drawn routes vs drawn walls", "llm": False, "args": ["--split", "--pairs", "--limit", "--seed"]},
    "differential": {"label": "Our graph vs the kit's", "llm": False, "args": ["--split", "--limit", "--pairs", "--closures"]},
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
_summary_cache = {}


def summaries() -> list[dict]:
    out = []
    for path in sorted(RUNS.glob("*/summary.json")):
        try:
            signature=(path.stat().st_mtime_ns,path.stat().st_size)
            cached=_summary_cache.get(str(path))
            if cached and cached[0]==signature: summary=dict(cached[1])
            else:
                summary=json.loads(path.read_text(encoding='utf8'))
                _summary_cache[str(path)]=(signature,summary.copy())
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


@router.get('/readiness')
def readiness():
    from server.readiness import readiness as report
    return report(summaries())


@router.get('/features')
def features():
    from server.readiness import features as report
    return report(summaries())


@router.get('/cases')
def cases():
    from eval.conversations import cases as catalog
    return catalog()


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


@router.get('/runs/{run}/artifacts/{name}')
def artifact(run:str,name:str):
    directory=(RUNS/run).resolve()
    target=(directory/name).resolve()
    if directory.parent!=RUNS.resolve() or target.parent!=directory or target.suffix not in ('.png','.json','.log','.xml') or not target.is_file():
        raise HTTPException(404,'Unknown artifact')
    return FileResponse(target)


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
    suite: str | None = None
    profile: str | None = None
    args: list[str] = []


@router.post("/jobs")
def launch(body: Launch) -> dict:
    if body.profile is not None and body.profile not in ('smoke','full','live','demo'):
        raise HTTPException(422, 'unknown test profile')
    if body.profile is None and body.suite not in SUITES:
        raise HTTPException(422, "unknown suite")
    if body.profile and body.args: raise HTTPException(422, 'Profiles do not accept arbitrary arguments')
    allowed = set(SUITES[body.suite]["args"]) | {"-v"} if not body.profile else set()
    flags = [a for a in body.args if a.startswith("-")]
    if any(f not in allowed for f in flags):
        raise HTTPException(422, f"allowed flags for {body.suite}: {sorted(allowed)}")
    job_id = uuid.uuid4().hex[:8]
    env = {**os.environ, "PYTHONIOENCODING": "utf-8", "FLOORWISE_MAX_TOKENS": JOB_TOKEN_BUDGET, 'FLOORWISE_LAB_JOB_ID': job_id}
    if body.profile in ('smoke','full') or (not body.profile and "llm" not in body.args and "paraphrase" not in body.args and SUITES[body.suite]["llm"] in ("optional", False)):
        env["FLOORWISE_OFFLINE"] = "1"
    command = [sys.executable, '-u', '-m', 'eval.product', body.profile] if body.profile else [sys.executable, "-u", "-m", "eval", body.suite, *body.args]
    job = {"id": job_id, "suite": body.profile or body.suite, "args": body.args, "started": time.time(), "lines": [], "done": False,
           "code": None, "run": None}
    JOBS[job_id] = job

    def work() -> None:
        before = {p.name for p in RUNS.glob("*")} if RUNS.exists() else set()
        process = subprocess.Popen(command, cwd=ROOT, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                   text=True, encoding="utf-8", errors="replace")
        job["process"] = process
        def terminate():
            if os.name == 'nt': subprocess.run(['taskkill','/PID',str(process.pid),'/T','/F'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
            else: process.terminate()
        job['terminate'] = terminate
        deadline = threading.Timer(JOB_TIMEOUT_S, lambda: (job["lines"].append(f"[lab] stopped: over {JOB_TIMEOUT_S}s"), terminate()))
        deadline.start()
        for line in process.stdout:
            job["lines"].append(line.rstrip())
            if line.startswith('PHASE '): job['phase'] = line.strip()[6:]
            if line.startswith('CASE '): job['progress'] = line.strip()
        job["code"] = process.wait()
        deadline.cancel()
        new = sorted({p.name for p in RUNS.glob("*")} - before)
        owned = [s for s in summaries() if s.get('config',{}).get('job_id') == job_id]
        parent = next((s for s in owned if s.get('config',{}).get('profile') == body.profile and body.profile), None)
        job["run"] = parent['run'] if parent else owned[-1]['run'] if owned else None
        job["done"] = True

    threading.Thread(target=work, daemon=True).start()
    return {"id": job_id}


@router.post("/jobs/{job_id}/cancel")
def cancel(job_id: str) -> dict:
    job = JOBS.get(job_id)
    if not job or job["done"] or "process" not in job:
        raise HTTPException(404, "no running job")
    job["lines"].append("[lab] cancelled by user")
    job.get('terminate', job['process'].kill)()
    return {"cancelled": job_id}


@router.get("/jobs")
def jobs() -> list[dict]:
    return [{k: v for k, v in j.items() if k not in ("lines", "process", 'terminate')} | {"last": j["lines"][-1] if j["lines"] else ""}
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
