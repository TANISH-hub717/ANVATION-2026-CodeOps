"""ResQWork FastAPI backend.

Run:  uvicorn main:app --reload --port 8000   (from the backend/ folder)
"""
import copy
from typing import Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from data import (
    DAYS, SHIFTS, SKILLS, SLOTS, SHIFT_HOURS, EMPLOYEES, UNAVAILABLE,
    INITIAL_SCHEDULE, base_demand,
)
from metrics import coverage, fairness, change_cost, conflicts, explain, validate
from solver import solve

app = FastAPI(title="ResQWork API", version="1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


class RescheduleRequest(BaseModel):
    absent_employee: Optional[str] = None
    demand_spike: int = Field(0, ge=0, le=10)
    spike_day: str = "Tue"
    spike_shift: str = "Morning"
    spike_skill: str = "technical"


@app.get("/")
def root():
    return {"service": "ResQWork", "endpoints": ["/api/scenario", "/api/reschedule"]}


@app.get("/api/scenario")
def scenario():
    demand = base_demand()
    fair = fairness(INITIAL_SCHEDULE)
    return {
        "employees": [
            {**e, "unavailable": UNAVAILABLE.get(e["id"], [])} for e in EMPLOYEES
        ],
        "days": DAYS,
        "shifts": SHIFTS,
        "shift_hours": SHIFT_HOURS,
        "skills": SKILLS,
        "slots": SLOTS,
        "demand": demand,
        "initial_schedule": INITIAL_SCHEDULE,
        "coverage": coverage(INITIAL_SCHEDULE, demand),
        "fairness_score": fair["score"],
        "workloads": fair["workloads"],
    }


@app.post("/api/reschedule")
def reschedule(req: RescheduleRequest):
    emp_ids = {e["id"] for e in EMPLOYEES}
    absent = req.absent_employee or None
    if absent in ("", "none", "None"):
        absent = None
    if absent is not None and absent not in emp_ids:
        raise HTTPException(400, f"Unknown employee '{absent}'")
    if req.spike_day not in DAYS or req.spike_shift not in SHIFTS or req.spike_skill not in SKILLS:
        raise HTTPException(400, "Invalid spike day / shift / skill")

    # Build disrupted demand
    demand = copy.deepcopy(base_demand())
    spike_slot = f"{req.spike_day}-{req.spike_shift}"
    demand[spike_slot][req.spike_skill] += req.demand_spike

    result = solve(demand, absent=absent)
    revised = result["schedule"]

    cov = coverage(revised, demand)
    conf = conflicts(revised, demand, absent)
    cc = change_cost(INITIAL_SCHEDULE, revised)
    fair_before = fairness(INITIAL_SCHEDULE)["score"]
    fair_after = fairness(revised, absent)
    violations = validate(revised, absent)

    spike = {"amount": req.demand_spike, "slot": spike_slot, "skill": req.spike_skill}
    lines = explain(INITIAL_SCHEDULE, revised, absent, spike, conf, fair_before, fair_after["score"])

    return {
        "revised_schedule": revised,
        "demand": demand,
        "coverage": cov,
        "unmet_demand": sum(c["shortfall"] for c in conf),
        "change_cost": cc["total"],
        "changes": {
            "removed": [{"employee": e, "slot": s} for e, s in cc["removed"]],
            "added": [{"employee": e, "slot": s} for e, s in cc["added"]],
            "role_changed": [{"employee": e, "slot": s} for e, s in cc["role_changed"]],
        },
        "fairness_score": fair_after["score"],
        "fairness_before": fair_before,
        "workloads": fair_after["workloads"],
        "conflicts": conf,
        "explanation": " ".join(lines),
        "explanation_lines": lines,
        "solver": {
            "status": result["status"],
            "objective": result.get("objective"),
            "solve_time_ms": result.get("solve_time_ms"),
            "weights": result.get("weights"),
            "constraint_violations": violations,
        },
    }
