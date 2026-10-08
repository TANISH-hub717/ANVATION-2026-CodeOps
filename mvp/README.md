# ResQWork — Dynamic Workforce Rescheduling (Round-1 MVP)

FastAPI + Google OR-Tools CP-SAT backend, React + Vite dashboard.
A 3-day roster (Mon–Wed × Morning/Afternoon/Night = 9 shifts) for 8 employees with
technical / support / operations skills. Pick a disruption, click **Reschedule**,
and CP-SAT repairs the schedule.

## Run

Requires Python 3.10+ and Node 18+. Use two terminals.

**Terminal 1 — backend (port 8000)**
```bash
cd resqwork/backend
python -m venv .venv
# macOS/Linux:
source .venv/bin/activate
# Windows (PowerShell):  .venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn main:app --reload --port 8000
```
Check: http://localhost:8000/api/scenario returns JSON. Swagger UI: http://localhost:8000/docs

**Terminal 2 — frontend (port 5173)**
```bash
cd resqwork/frontend
npm install
npm run dev
```
Open http://localhost:5173

The frontend calls `http://localhost:8000` (CORS is open on the backend).
If the backend runs elsewhere: `VITE_API_URL=http://host:8000 npm run dev`

## Demo script

Use the **Quick demo scenarios** buttons (or the dropdowns + Reschedule):

| Scenario | Expected result |
|---|---|
| Employee absence (E1 Asha) | 100% coverage, 5 changes, Asha's shifts struck through, replacements outlined green |
| Demand spike (+2 support, Tue Afternoon) | 100% coverage, 8 changes (a swap chain is needed because of one-shift-per-day and rest rules) |
| Absence + spike (E7 absent, +1 operations Mon Night) | 100% coverage, 7 changes |
| Impossible coverage (E1 absent, +5 technical Tue Morning) | 82.6% coverage, 4 unmet positions, red Tue-Morning cell, conflict table with the reason |

Why the impossible case leaves exactly 4 unmet: with Asha absent, only 3 people hold the
technical skill, Tuesday needs 7 technical positions (6 Morning + 1 Afternoon), and nobody
works two shifts on one day. 7 − 3 = 4. The solver proves this is the minimum (status OPTIMAL).

## API

`GET /api/scenario` → employees (with skills + unavailable slots), days, shifts, skills, slots,
demand, initial_schedule, coverage, fairness_score, workloads.

`POST /api/reschedule`
```json
{ "absent_employee": "E1", "demand_spike": 2,
  "spike_day": "Tue", "spike_shift": "Morning", "spike_skill": "technical" }
```
All fields are optional. `absent_employee` defaults to none, `demand_spike` to 0 (allowed 0–10),
and `spike_day` / `spike_shift` / `spike_skill` default to `Tue` / `Morning` / `technical`.
The original two-field form `{"absent_employee": "E1", "demand_spike": 2}` works as-is.

Returns `revised_schedule`, `demand` (after the spike), `coverage`, `unmet_demand`, `change_cost`,
`changes`, `fairness_score`, `fairness_before`, `workloads`, `conflicts`, `explanation`,
`explanation_lines`, and `solver` (`status`, `objective`, `solve_time_ms`, `weights`,
`constraint_violations`).

Errors: unknown employee or invalid day/shift/skill → 400; wrong type, out-of-range spike,
malformed JSON or empty body → 422.

Quick test without the UI:
```bash
curl -X POST localhost:8000/api/reschedule -H "Content-Type: application/json" \
  -d '{"absent_employee":"E1","demand_spike":5,"spike_day":"Tue","spike_shift":"Morning","spike_skill":"technical"}'
```

## Model (backend/solver.py)

- `x[e,s,k]` = 1 if employee e works shift s in role k; `a[e,s] = Σk x[e,s,k]`
- Hard constraints: availability, absence, skill match, at most 1 shift per day,
  no Night → next-day Morning (rest rule)
- Coverage: `Σe x[e,s,k] + unmet[s,k] == demand[s,k]` — the unmet slack means the model is
  never infeasible; shortages are reported instead of crashing
- Objective: `W_unmet·unmet + W_change·changes + W_fair·fairness_deviation`, with weights
  derived from the data so the priority is strict
  (coverage ≫ fewer changes ≫ fairness): `W_fair = 1`, `W_change` > the largest possible
  fairness term, `W_unmet` > the largest possible change + fairness total. With no absence
  that is 14089 / 193 / 1; with one absence 10804 / 148 / 1 (computed per request, shown in the UI).
  `fairness_deviation = Σe |n·load_e − total_load|` (linear, integer form of mean absolute deviation)

Every solver result is re-checked by an independent validator (`metrics.validate`) and any
violation is shown in the UI.

## Metric definitions

- **Coverage** = filled positions / required positions, against the demand *after* the spike.
- **Change cost** = number of employee-shift differences between the initial and revised
  schedule: each assignment removed counts 1, each added counts 1, and each person who keeps a
  shift but switches role counts 1. Forced changes are included — e.g. E1's absence alone
  removes 2 assignments. The solver minimizes exactly this same quantity.
- **Fairness** = mean |workload − average workload| / average workload over the 3-day period,
  for non-absent employees (workload = number of shifts). 0 = perfectly even.

## Files

```
backend/data.py          synthetic employees, availability, demand, initial schedule
backend/solver.py        CP-SAT model
backend/metrics.py       coverage, fairness, change cost, conflicts, explanation, validator
backend/main.py          FastAPI app + CORS
backend/requirements.txt
frontend/src/App.jsx     dashboard
frontend/src/App.css     styles
```
