import { useEffect, useState } from 'react'

const API = import.meta.env.VITE_API_URL || 'http://localhost:8000'

const SKILL_ABBR = { technical: 'TECH', support: 'SUP', operations: 'OPS' }

const PRESETS = [
  { label: 'Employee absence', absent: 'E1', spike: 0, day: 'Tue', shift: 'Morning', skill: 'technical' },
  { label: 'Demand spike', absent: '', spike: 2, day: 'Tue', shift: 'Afternoon', skill: 'support' },
  { label: 'Absence + spike', absent: 'E7', spike: 1, day: 'Mon', shift: 'Night', skill: 'operations' },
  { label: 'Impossible coverage', absent: 'E1', spike: 5, day: 'Tue', shift: 'Morning', skill: 'technical' },
]

function ScheduleGrid({ scenario, schedule, demand, initial, absent }) {
  const { employees, days, shifts, slots } = scenario
  const cur = {}
  schedule.forEach((a) => { cur[`${a.employee}|${a.slot}`] = a.skill })
  const init = {}
  ;(initial || []).forEach((a) => { init[`${a.employee}|${a.slot}`] = a.skill })

  const assignedCount = {}
  schedule.forEach((a) => { assignedCount[a.slot] = (assignedCount[a.slot] || 0) + 1 })

  return (
    <div className="grid-wrap">
      <table className="grid">
        <thead>
          <tr>
            <th rowSpan={2} className="emp-col">Employee</th>
            {days.map((d) => <th key={d} colSpan={shifts.length} className="day-head">{d}</th>)}
            <th rowSpan={2}>Load</th>
          </tr>
          <tr>
            {days.map((d) => shifts.map((s) => (
              <th key={`${d}-${s}`} className="shift-head">{s.slice(0, 3)}</th>
            )))}
          </tr>
        </thead>
        <tbody>
          {employees.map((e) => {
            const isAbsent = e.id === absent
            const load = slots.filter((s) => cur[`${e.id}|${s}`]).length
            return (
              <tr key={e.id} className={isAbsent ? 'absent-row' : ''}>
                <td className="emp-col">
                  <div className="emp-name">{e.name} {isAbsent && <span className="tag-absent">ABSENT</span>}</div>
                  <div className="emp-meta">{e.id} · {e.skills.map((k) => SKILL_ABBR[k]).join(' / ')}</div>
                </td>
                {slots.map((s) => {
                  const key = `${e.id}|${s}`
                  const now = cur[key]
                  const before = init[key]
                  const unavailable = e.unavailable.includes(s) || isAbsent
                  let cls = 'cell'
                  let content = null
                  if (now) {
                    let state = ''
                    if (initial && !before) state = 'added'
                    else if (initial && before !== now) state = 'role'
                    content = <span className={`chip ${now} ${state}`}>{SKILL_ABBR[now]}</span>
                  } else if (initial && before) {
                    content = <span className={`chip ${before} removed`}>{SKILL_ABBR[before]}</span>
                  }
                  if (unavailable) cls += ' unavail'
                  return <td key={s} className={cls}>{content}</td>
                })}
                <td className="load">{isAbsent ? '–' : load}</td>
              </tr>
            )
          })}
        </tbody>
        <tfoot>
          <tr>
            <td className="emp-col">Coverage</td>
            {slots.map((s) => {
              const req = Object.values(demand[s]).reduce((x, y) => x + y, 0)
              const got = assignedCount[s] || 0
              return (
                <td key={s} className={`cov ${got < req ? 'short' : 'ok'}`}>{got}/{req}</td>
              )
            })}
            <td />
          </tr>
        </tfoot>
      </table>
    </div>
  )
}

function Legend({ diff }) {
  return (
    <div className="legend">
      <span><span className="chip technical">TECH</span> technical</span>
      <span><span className="chip support">SUP</span> support</span>
      <span><span className="chip operations">OPS</span> operations</span>
      <span><span className="swatch unavail" /> unavailable</span>
      {diff && <>
        <span><span className="chip support added">NEW</span> newly assigned</span>
        <span><span className="chip support removed">OLD</span> removed</span>
        <span><span className="chip support role">ROLE</span> role switch</span>
      </>}
    </div>
  )
}

function Metric({ label, value, sub, tone }) {
  return (
    <div className={`metric ${tone || ''}`}>
      <div className="metric-label">{label}</div>
      <div className="metric-value">{value}</div>
      {sub && <div className="metric-sub">{sub}</div>}
    </div>
  )
}

export default function App() {
  const [scenario, setScenario] = useState(null)
  const [loadError, setLoadError] = useState('')
  const [absent, setAbsent] = useState('E1')
  const [spike, setSpike] = useState(0)
  const [spikeDay, setSpikeDay] = useState('Tue')
  const [spikeShift, setSpikeShift] = useState('Morning')
  const [spikeSkill, setSpikeSkill] = useState('technical')
  const [result, setResult] = useState(null)
  const [lastRequest, setLastRequest] = useState(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => {
    fetch(`${API}/api/scenario`)
      .then((r) => { if (!r.ok) throw new Error(`HTTP ${r.status}`); return r.json() })
      .then(setScenario)
      .catch((e) => setLoadError(`Cannot reach backend at ${API} (${e.message}). Is uvicorn running on port 8000?`))
  }, [])

  async function reschedule(override) {
    const body = {
      absent_employee: (override ? override.absent : absent) || null,
      demand_spike: Number(override ? override.spike : spike),
      spike_day: override ? override.day : spikeDay,
      spike_shift: override ? override.shift : spikeShift,
      spike_skill: override ? override.skill : spikeSkill,
    }
    setBusy(true); setError('')
    try {
      const r = await fetch(`${API}/api/reschedule`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      })
      const text = await r.text()
      let data = null
      try { data = JSON.parse(text) } catch { /* non-JSON body, e.g. proxy or server crash page */ }
      if (!r.ok) {
        const d = data?.detail
        const msg = Array.isArray(d) ? d.map((x) => `${(x.loc || []).slice(1).join('.') || 'request'}: ${x.msg}`).join('; ')
          : d || `HTTP ${r.status}`
        throw new Error(msg)
      }
      if (!data || !Array.isArray(data.revised_schedule)) throw new Error('Unexpected response from backend')
      setResult(data)
      setLastRequest(body)
    } catch (e) {
      setError(`Reschedule failed: ${e.message}`)
    } finally {
      setBusy(false)
    }
  }

  function applyPreset(p) {
    setAbsent(p.absent); setSpike(p.spike); setSpikeDay(p.day); setSpikeShift(p.shift); setSpikeSkill(p.skill)
    reschedule(p)
  }

  if (loadError) return <div className="page"><Header /><div className="error-box">{loadError}</div></div>
  if (!scenario) return <div className="page"><Header /><div className="loading">Loading scenario…</div></div>

  const empName = (id) => scenario.employees.find((e) => e.id === id)?.name || id
  const unresolved = result ? result.conflicts.reduce((x, c) => x + c.shortfall, 0) : 0

  return (
    <div className="page">
      <Header />

      {/* Section 1 */}
      <section className="card">
        <div className="card-head">
          <h2><span className="num">1</span> Current Schedule</h2>
          <div className="pills">
            <span className="pill">Coverage {scenario.coverage.percent}%</span>
            <span className="pill">Fairness {scenario.fairness_score}</span>
            <span className="pill">{scenario.employees.length} employees · {scenario.slots.length} shifts</span>
          </div>
        </div>
        <ScheduleGrid scenario={scenario} schedule={scenario.initial_schedule} demand={scenario.demand} />
        <Legend />
      </section>

      {/* Section 2 */}
      <section className="card">
        <div className="card-head"><h2><span className="num">2</span> Disruption Controls</h2></div>
        <div className="controls">
          <label>Employee absence
            <select value={absent} onChange={(e) => setAbsent(e.target.value)}>
              <option value="">— No absence —</option>
              {scenario.employees.map((e) => <option key={e.id} value={e.id}>{e.id} · {e.name}</option>)}
            </select>
          </label>
          <label>Demand spike (+ staff)
            <select value={spike} onChange={(e) => setSpike(Number(e.target.value))}>
              {[0, 1, 2, 3, 4, 5, 6].map((n) => <option key={n} value={n}>+{n}</option>)}
            </select>
          </label>
          <label>Spike day
            <select value={spikeDay} onChange={(e) => setSpikeDay(e.target.value)} disabled={spike === 0}>
              {scenario.days.map((d) => <option key={d}>{d}</option>)}
            </select>
          </label>
          <label>Spike shift
            <select value={spikeShift} onChange={(e) => setSpikeShift(e.target.value)} disabled={spike === 0}>
              {scenario.shifts.map((s) => <option key={s}>{s}</option>)}
            </select>
          </label>
          <label>Spike skill
            <select value={spikeSkill} onChange={(e) => setSpikeSkill(e.target.value)} disabled={spike === 0}>
              {scenario.skills.map((k) => <option key={k}>{k}</option>)}
            </select>
          </label>
          <button className="primary" onClick={() => reschedule()} disabled={busy}>
            {busy ? 'Optimizing…' : '⚡ Reschedule'}
          </button>
        </div>
        <div className="presets">
          <span className="presets-label">Quick demo scenarios:</span>
          {PRESETS.map((p) => (
            <button key={p.label} className={`preset ${p.label.startsWith('Impossible') ? 'danger' : ''}`}
              onClick={() => applyPreset(p)} disabled={busy}>{p.label}</button>
          ))}
        </div>
        {error && <div className="error-box">{error}</div>}
      </section>

      {!result && (
        <section className="card empty">Choose a disruption and click <b>Reschedule</b> — the CP-SAT optimizer will repair the schedule.</section>
      )}

      {result && (
        <>
          {/* Section 3 */}
          <section className="card">
            <div className="card-head">
              <h2><span className="num">3</span> Revised Schedule</h2>
              <div className="pills">
                {lastRequest?.absent_employee && <span className="pill warn">Absent: {empName(lastRequest.absent_employee)}</span>}
                {lastRequest?.demand_spike > 0 && <span className="pill warn">+{lastRequest.demand_spike} {lastRequest.spike_skill} on {lastRequest.spike_day} {lastRequest.spike_shift}</span>}
              </div>
            </div>
            <ScheduleGrid scenario={scenario} schedule={result.revised_schedule} demand={result.demand}
              initial={scenario.initial_schedule} absent={lastRequest?.absent_employee} />
            <Legend diff />
          </section>

          {/* Section 4 */}
          <section className="card">
            <div className="card-head">
              <h2><span className="num">4</span> Metrics</h2>
              <span className="pill subtle">
                CP-SAT {result.solver.status} · {result.solver.solve_time_ms} ms · objective {result.solver.objective}
              </span>
            </div>
            <div className="metrics">
              <Metric label="Coverage" value={`${result.coverage.percent}%`}
                sub={`${result.coverage.covered} / ${result.coverage.required} positions filled`}
                tone={result.coverage.percent >= 100 ? 'good' : 'bad'} />
              <Metric label="Schedule Changes" value={result.change_cost}
                sub={`${result.changes.added.length} added · ${result.changes.removed.length} removed · ${result.changes.role_changed.length} role switches`} />
              <Metric label="Fairness" value={result.fairness_score}
                sub={`was ${result.fairness_before} · 0 = perfectly even`}
                tone={result.fairness_score <= result.fairness_before ? 'good' : ''} />
              <Metric label="Unresolved Conflicts" value={unresolved}
                sub={unresolved ? `${result.conflicts.length} slot/skill gap(s)` : 'none'}
                tone={unresolved ? 'bad' : 'good'} />
            </div>

            {result.conflicts.length > 0 && (
              <div className="conflicts">
                <h3>⚠ Unresolved conflicts</h3>
                <table>
                  <thead><tr><th>Shift</th><th>Skill</th><th>Required</th><th>Assigned</th><th>Short</th><th>Why</th></tr></thead>
                  <tbody>
                    {result.conflicts.map((c, i) => (
                      <tr key={i}>
                        <td>{c.day} {c.shift}</td><td>{c.skill}</td><td>{c.required}</td>
                        <td>{c.assigned}</td><td className="short-num">−{c.shortfall}</td><td>{c.reason}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
            {result.solver.constraint_violations.length > 0 && (
              <div className="error-box">Constraint check failed: {result.solver.constraint_violations.join('; ')}</div>
            )}
          </section>

          {/* Section 5 */}
          <section className="card">
            <div className="card-head"><h2><span className="num">5</span> Explanation / Decision Reasoning</h2></div>
            <ol className="explain">
              {result.explanation_lines.map((l, i) => (
                <li key={i} className={l.startsWith('UNRESOLVED') ? 'bad' : ''}>{l}</li>
              ))}
            </ol>
            <div className="objective-note">
              Objective minimized:{' '}
              <code>
                {result.solver.weights
                  ? `${result.solver.weights.unmet} × unmet_demand + ${result.solver.weights.change} × schedule_changes + ${result.solver.weights.fairness} × fairness_deviation`
                  : 'unmet_demand ≫ schedule_changes ≫ fairness_deviation'}
              </code>{' '}
              (weights chosen so coverage strictly outranks changes, and changes strictly outrank fairness)
            </div>
          </section>
        </>
      )}
      <footer>ResQWork · Round-1 MVP · FastAPI + OR-Tools CP-SAT + React</footer>
    </div>
  )
}

function Header() {
  return (
    <header className="header">
      <div className="logo">R</div>
      <div>
        <h1>ResQWork</h1>
        <p>Dynamic Workforce Rescheduling</p>
      </div>
    </header>
  )
}
