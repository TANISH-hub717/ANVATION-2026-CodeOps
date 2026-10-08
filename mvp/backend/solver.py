"""CP-SAT rescheduling model.

Decision variables
  x[e, s, k] = 1 if employee e works slot s in role (skill) k
  a[e, s]    = sum_k x[e, s, k]  -> 1 if employee e is assigned to slot s
  u[s, k]    = unmet demand (slack) for skill k in slot s

Hard constraints
  - unavailable / absent employees are never assigned
  - employee must possess the skill of the role they fill
  - at most one shift per day (no overlapping shifts)
  - no Night shift followed by next-day Morning (minimum rest)
  - coverage: sum_e x[e,s,k] + u[s,k] == demand[s,k]   (slack keeps it feasible)

Objective (strict priority via weights)
  W_UNMET * unmet + W_CHANGE * changes + W_FAIR * fairness_deviation
  The weights are derived from the data so each level strictly dominates the next:
    W_FAIR = 1
    W_CHANGE > largest possible fairness_deviation      (3 * n^2, max 1 shift/day)
    W_UNMET  > W_CHANGE * max changes + max fairness     (max changes = E * S)
  so the solver never trades a covered position for fewer changes, nor a change
  for better fairness.
"""
from ortools.sat.python import cp_model

from data import DAYS, SKILLS, SLOTS, EMPLOYEES, INITIAL_SCHEDULE
from metrics import is_available


def objective_weights(n_active):
    max_fair = len(DAYS) * n_active * n_active          # sum_e |n*load_e - total|
    w_fair = 1
    w_change = max_fair + 1
    w_unmet = w_change * len(EMPLOYEES) * len(SLOTS) + max_fair + 1
    return {"unmet": w_unmet, "change": w_change, "fairness": w_fair}


def solve(demand, absent=None, time_limit=5.0):
    model = cp_model.CpModel()
    emp_ids = [e["id"] for e in EMPLOYEES]
    skills_of = {e["id"]: set(e["skills"]) for e in EMPLOYEES}
    active = [e for e in emp_ids if e != absent]
    weights = objective_weights(len(active))

    # --- variables -------------------------------------------------------
    x = {}
    for e in emp_ids:
        for s in SLOTS:
            for k in SKILLS:
                x[e, s, k] = model.new_bool_var(f"x_{e}_{s}_{k}")
                # Hard: skill, availability, absence
                if k not in skills_of[e] or not is_available(e, s, absent) or demand[s][k] == 0:
                    model.add(x[e, s, k] == 0)

    a = {}
    for e in emp_ids:
        for s in SLOTS:
            a[e, s] = model.new_bool_var(f"a_{e}_{s}")
            # one role per slot; a = 1 iff assigned
            model.add(sum(x[e, s, k] for k in SKILLS) == a[e, s])

    # Hard: at most one shift per day (no overlapping shifts)
    for e in emp_ids:
        for d in DAYS:
            model.add(sum(a[e, s] for s in SLOTS if s.startswith(d + "-")) <= 1)

    # Hard: minimum rest — no Night followed by next-day Morning
    for e in emp_ids:
        for i in range(len(DAYS) - 1):
            model.add(a[e, f"{DAYS[i]}-Night"] + a[e, f"{DAYS[i+1]}-Morning"] <= 1)

    # Coverage with unmet-demand slack (never infeasible)
    u = {}
    for s in SLOTS:
        for k in SKILLS:
            req = demand[s][k]
            u[s, k] = model.new_int_var(0, req, f"u_{s}_{k}")
            model.add(sum(x[e, s, k] for e in emp_ids) + u[s, k] == req)
    unmet = sum(u.values())

    # Change cost vs. initial schedule (assignment add/remove + role switch)
    init_role = {(i["employee"], i["slot"]): i["skill"] for i in INITIAL_SCHEDULE}
    change_terms = []
    for e in emp_ids:
        for s in SLOTS:
            if (e, s) in init_role:
                k0 = init_role[e, s]
                # 1 if they no longer hold the same role in that slot
                change_terms.append(1 - x[e, s, k0])
            else:
                change_terms.append(a[e, s])
    changes = sum(change_terms)

    # Fairness: |n*load_e - total| for active employees (linear MAD, scaled by n)
    n = len(active)
    load = {e: sum(a[e, s] for s in SLOTS) for e in active}
    total = sum(load.values())
    dev = []
    big = n * len(SLOTS) * len(EMPLOYEES)
    for e in active:
        d = model.new_int_var(0, big, f"dev_{e}")
        model.add(d >= n * load[e] - total)
        model.add(d >= total - n * load[e])
        dev.append(d)
    fairness_dev = sum(dev)

    model.minimize(weights["unmet"] * unmet + weights["change"] * changes
                   + weights["fairness"] * fairness_dev)

    # --- solve -----------------------------------------------------------
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = time_limit
    solver.parameters.num_workers = 8
    solver.parameters.random_seed = 42
    status = solver.solve(model)

    if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        # Should not happen thanks to slack, but never crash the API.
        return {"status": solver.status_name(status), "schedule": [], "objective": None,
                "weights": weights}

    schedule = []
    for s in SLOTS:
        for e in emp_ids:
            for k in SKILLS:
                if solver.value(x[e, s, k]) == 1:
                    schedule.append({"employee": e, "slot": s, "skill": k})

    return {
        "status": solver.status_name(status),
        "schedule": schedule,
        "objective": solver.objective_value,
        "weights": weights,
        "unmet": int(sum(solver.value(v) for v in u.values())),
        "solve_time_ms": round(solver.wall_time * 1000, 1),
    }
