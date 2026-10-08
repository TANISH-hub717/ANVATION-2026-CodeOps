"""Synthetic workforce dataset for ResQWork (Round-1 MVP).

3-day roster (Mon-Wed) x 3 shifts (Morning, Afternoon, Night) = 9 slots.
Each slot needs a certain number of people per skill.
"""

DAYS = ["Mon", "Tue", "Wed"]
SHIFTS = ["Morning", "Afternoon", "Night"]
SKILLS = ["technical", "support", "operations"]

SHIFT_HOURS = {
    "Morning": "06:00-14:00",
    "Afternoon": "14:00-22:00",
    "Night": "22:00-06:00",
}

# A slot is one shift on one day, e.g. "Mon-Morning"
SLOTS = [f"{d}-{s}" for d in DAYS for s in SHIFTS]

EMPLOYEES = [
    {"id": "E1", "name": "Asha Rao",     "skills": ["technical", "support"]},
    {"id": "E2", "name": "Rahul Mehta",  "skills": ["technical"]},
    {"id": "E3", "name": "Priya Nair",   "skills": ["support", "operations"]},
    {"id": "E4", "name": "Vikram Singh", "skills": ["operations"]},
    {"id": "E5", "name": "Neha Kapoor",  "skills": ["technical", "operations"]},
    {"id": "E6", "name": "Arjun Das",    "skills": ["support"]},
    {"id": "E7", "name": "Kavya Iyer",   "skills": ["support", "technical"]},
    {"id": "E8", "name": "Rohan Pillai", "skills": ["operations", "support"]},
]

# Slots each employee CANNOT work (personal availability).
UNAVAILABLE = {
    "E2": ["Mon-Night", "Tue-Night", "Wed-Night"],   # no nights
    "E3": ["Mon-Night", "Tue-Night", "Wed-Night"],   # no nights
    "E4": ["Mon-Morning"],                           # appointment
    "E6": ["Wed-Morning", "Wed-Afternoon", "Wed-Night"],  # leave on Wed
}

# Base demand per shift type (same every day): skill -> headcount
BASE_DEMAND = {
    "Morning":   {"technical": 1, "support": 1, "operations": 1},
    "Afternoon": {"technical": 1, "support": 1},
    "Night":     {"operations": 1},
}

# Initial (published) schedule: list of {employee, slot, skill}
INITIAL_SCHEDULE = [
    {"employee": "E1", "slot": "Mon-Morning",   "skill": "technical"},
    {"employee": "E3", "slot": "Mon-Morning",   "skill": "support"},
    {"employee": "E8", "slot": "Mon-Morning",   "skill": "operations"},
    {"employee": "E2", "slot": "Mon-Afternoon", "skill": "technical"},
    {"employee": "E6", "slot": "Mon-Afternoon", "skill": "support"},
    {"employee": "E4", "slot": "Mon-Night",     "skill": "operations"},

    {"employee": "E5", "slot": "Tue-Morning",   "skill": "technical"},
    {"employee": "E6", "slot": "Tue-Morning",   "skill": "support"},
    {"employee": "E3", "slot": "Tue-Morning",   "skill": "operations"},
    {"employee": "E2", "slot": "Tue-Afternoon", "skill": "technical"},
    {"employee": "E7", "slot": "Tue-Afternoon", "skill": "support"},
    {"employee": "E8", "slot": "Tue-Night",     "skill": "operations"},

    {"employee": "E7", "slot": "Wed-Morning",   "skill": "technical"},
    {"employee": "E1", "slot": "Wed-Morning",   "skill": "support"},
    {"employee": "E4", "slot": "Wed-Morning",   "skill": "operations"},
    {"employee": "E5", "slot": "Wed-Afternoon", "skill": "technical"},
    {"employee": "E3", "slot": "Wed-Afternoon", "skill": "support"},
    {"employee": "E8", "slot": "Wed-Night",     "skill": "operations"},
]


def slot_day(slot: str) -> str:
    return slot.split("-")[0]


def slot_shift(slot: str) -> str:
    return slot.split("-")[1]


def base_demand():
    """slot -> {skill: required headcount} (all skills present, 0 if none)."""
    out = {}
    for slot in SLOTS:
        req = BASE_DEMAND[slot_shift(slot)]
        out[slot] = {k: req.get(k, 0) for k in SKILLS}
    return out


def employee_by_id():
    return {e["id"]: e for e in EMPLOYEES}
