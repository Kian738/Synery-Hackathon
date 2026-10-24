"""Verified multi-hop reasoning: a typed operator algebra, plans checked as DAGs, per-step postconditions and abstention.

    from floorwise.reason import run_plan
    trace = run_plan(building_or_dir, plan)   # plan: dict, JSON text or Plan; trace.answer or trace.abstained
"""

from floorwise.reason.execute import run_plan
from floorwise.reason.operators import REGISTRY, Operator, Param, Registry
from floorwise.reason.plan import PlanError, check_plan, parse_plan
from floorwise.reason.types import (
    Abstain,
    Abstention,
    Plan,
    ScenarioSpec,
    Step,
    StepResult,
    Trace,
    World,
)

__all__ = [
    "REGISTRY",
    "Abstain",
    "Abstention",
    "Operator",
    "Param",
    "Plan",
    "PlanError",
    "Registry",
    "ScenarioSpec",
    "Step",
    "StepResult",
    "Trace",
    "World",
    "check_plan",
    "parse_plan",
    "run_plan",
]
from floorwise.reason import evac_ops  # noqa: E402,F401  (registers the evacuation operators)
