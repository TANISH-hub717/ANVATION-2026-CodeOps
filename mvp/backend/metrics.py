"""Pure-Python helpers: validation, coverage, fairness, change cost, explanation.

No OR-Tools import here, so these can be used and tested independently.
"""
from collections import defaultdict

from data import (
    DAYS, SKILLS, SLOTS, EMPLOYEES, UNAVAILABLE,
    slot_day, slot_shift, employee_by_id,
)


def is_available(emp_id, slot, absent=None):
    if absent and emp_id == absent:
        return False
    return slot not in UNAVAILABLE.get(emp_id, [])


def coverage(schedule, demand):
    """Per-slot coverage plus overall percentage."""
    assigned = defaultdict(lambda: defaultdict(int))
    for a in schedule:
        assigned[a["slot"]][a["skill"]] += 1

    per_slot = {}
    total_req = total_cov = 0
    for slot in SLOTS:
        req = sum(demand[slot].values())
        cov = sum(min(assigned[slot][k], demand[slot][k]) for k in SKILLS)
        per_slot[slot] = {
            "required": req,
            "assigned": sum(assigned[slot].values()),
            "covered": cov,
            "by_skill": {
                k: {"required": demand[slot][k], "assigned": assigned[slot][k]}
                for k in SKILLS if demand[slot][k] > 0 or assigned[slot][k] > 0
            },
        }
        total_req += req
        total_cov += cov
    pct = round(100.0 * total_cov / total_req, 1) if total_req else 100.0
    return {"slots": per_slot, "required": total_req, "covered": total_cov, "percent": pct}


def workloads(schedule, absent=None):
    """Shifts per employee (absent employee excluded)."""
    load = {e["id"]: 0 for e in EMPLOYEES if e["id"] != absent}
    for a in schedule:
        if a["employee"] in load:
            load[a["employee"]] += 1
    return load


def fairness(schedule, absent=None):
    """Mean absolute deviation of workload, normalised by average workload.

    0.0 = perfectly even workload. Higher = less fair.
    """
    load = workloads(schedule, absent)
    if not load:
        return {"score": 0.0, "average": 0.0, "workloads": {}}
    avg = sum(load.values()) / len(load)
    mad = sum(abs(v - avg) for v in load.values()) / len(load)
    score = round(mad / avg, 3) if avg > 0 else 0.0
    return {"score": score, "average": round(avg, 2), "workloads": load}


def change_cost(initial, revised):
    """Number of employee-slot assignments added or removed (role switch = 1)."""
    init_map = {(a["employee"], a["slot"]): a["skill"] for a in initial}
    rev_map = {(a["employee"], a["slot"]): a["skill"] for a in revised}
    removed = [k for k in init_map if k not in rev_map]
    added = [k for k in rev_map if k not in init_map]
    role_changed = [k for k in rev_map if k in init_map and init_map[k] != rev_map[k]]
    return {
        "total": len(removed) + len(added) + len(role_changed),
        "removed": removed,
        "added": added,
        "role_changed": role_changed,
    }


def validate(schedule, absent=None):
    """Return list of hard-constraint violations (should be empty)."""
    emps = employee_by_id()
    errs = []
    per_day = defaultdict(int)
    worked = set()
    for a in schedule:
        e, s, k = a["employee"], a["slot"], a["skill"]
        if not is_available(e, s, absent):
            errs.append(f"{e} assigned to {s} but unavailable/absent")
        if k not in emps[e]["skills"]:
            errs.append(f"{e} lacks skill {k} for {s}")
        per_day[(e, slot_day(s))] += 1
        worked.add((e, s))
    for (e, d), n in per_day.items():
        if n > 1:
            errs.append(f"{e} has {n} shifts on {d}")
    for e in emps:
        for i in range(len(DAYS) - 1):
            if (e, f"{DAYS[i]}-Night") in worked and (e, f"{DAYS[i+1]}-Morning") in worked:
                errs.append(f"{e} works {DAYS[i]} Night then {DAYS[i+1]} Morning (no rest)")
    return errs


def conflicts(schedule, demand, absent=None):
    """Unfilled demand, with the reason it could not be filled."""
    emps = employee_by_id()
    assigned = defaultdict(int)
    for a in schedule:
        assigned[(a["slot"], a["skill"])] += 1
    out = []
    for slot in SLOTS:
        for k in SKILLS:
            req = demand[slot][k]
            got = assigned[(slot, k)]
            if got < req:
                qualified = [
                    e for e in emps.values()
                    if k in e["skills"] and is_available(e["id"], slot, absent)
                ]
                if len(qualified) < req:
                    reason = (f"Only {len(qualified)} available employee(s) have the "
                              f"'{k}' skill for {slot}, but {req} are required.")
                    elsewhere = [e["name"] for e in qualified
                                 if not any(a["employee"] == e["id"] and a["slot"] == slot
                                            for a in schedule)]
                    if elsewhere:
                        reason += (f" {', '.join(elsewhere)} could not be used here: "
                                   f"needed on another shift or blocked by the "
                                   f"one-shift-per-day / rest rules.")
                else:
                    reason = (f"{len(qualified)} qualified employee(s) exist, but they are "
                              f"blocked by one-shift-per-day / rest rules or needed elsewhere.")
                out.append({
                    "slot": slot,
                    "day": slot_day(slot),
                    "shift": slot_shift(slot),
                    "skill": k,
                    "required": req,
                    "assigned": got,
                    "shortfall": req - got,
                    "reason": reason,
                })
    return out


def explain(initial, revised, absent, spike, conflict_list, fair_before, fair_after):
    """Human-readable reasoning for the revised schedule."""
    emps = employee_by_id()
    name = lambda e: emps[e]["name"]
    lines = []

    if absent:
        lost = [a for a in initial if a["employee"] == absent]
        if lost:
            slots = ", ".join(f"{a['slot']} ({a['skill']})" for a in lost)
            lines.append(f"{name(absent)} ({absent}) is absent, so they were removed from: {slots}.")
        else:
            lines.append(f"{name(absent)} ({absent}) is absent but had no scheduled shifts.")
    if spike and spike.get("amount", 0) > 0:
        lines.append(f"Demand spike: +{spike['amount']} {spike['skill']} staff needed on "
                     f"{spike['slot']}.")

    init_map = {(a["employee"], a["slot"]): a["skill"] for a in initial}
    rev_map = {(a["employee"], a["slot"]): a["skill"] for a in revised}
    spike_slot = spike["slot"] if spike and spike.get("amount", 0) > 0 else None
    spike_skill = spike["skill"] if spike_slot else None

    for s in SLOTS:
        # roles that were held in this slot initially but are no longer held by the same person
        vacated = [(e, k) for (e, sl), k in init_map.items()
                   if sl == s and rev_map.get((e, sl)) != k]
        # people newly holding a role in this slot (new assignment or role switch)
        filled = sorted((e, k) for (e, sl), k in rev_map.items()
                        if sl == s and init_map.get((e, sl)) != k)
        for e, k in filled:
            match = next(((ve, vk) for ve, vk in vacated if vk == k and ve != e), None)
            if match:
                vacated.remove(match)
                ve = match[0]
                if ve == absent:
                    cause = f"replacing {name(ve)} (absent)"
                elif (ve, s) in rev_map:
                    cause = f"taking over the {k} role {name(ve)} left when switching roles"
                else:
                    cause = f"taking over from {name(ve)}"
            elif s == spike_slot and k == spike_skill:
                cause = "to meet the demand spike"
            else:
                cause = f"to fill an open {k} position"
            if (e, s) in init_map:
                lines.append(f"{name(e)} stays on {s} but switches role "
                             f"{init_map[(e, s)]} -> {k}, {cause}.")
            else:
                lines.append(f"Assigned {name(e)} to {s} as {k}, {cause}.")

    for (e, s), k in sorted(init_map.items(), key=lambda x: SLOTS.index(x[0][1])):
        if (e, s) not in rev_map and e != absent:
            new_slots = [sl for (ee, sl) in rev_map if ee == e and (ee, sl) not in init_map]
            if new_slots:
                lines.append(f"{name(e)} was moved off {s} ({k}) and now works "
                             f"{', '.join(new_slots)}, where they were needed more.")
            else:
                lines.append(f"{name(e)} was released from {s} ({k}).")

    if conflict_list:
        total = sum(c["shortfall"] for c in conflict_list)
        lines.append(f"UNRESOLVED: {total} position(s) could not be staffed. "
                     f"The optimizer filled everything it legally could and flagged the rest "
                     f"instead of breaking availability, skill or rest constraints.")
    else:
        lines.append("All demand is covered without violating availability, skill or rest rules.")

    lines.append(f"Fairness (lower is better): {fair_before} before -> {fair_after} after. "
                 f"Priority order used: coverage > minimal changes > fairness.")
    return lines
