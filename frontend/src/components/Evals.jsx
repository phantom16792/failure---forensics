import { useEffect, useState } from 'react'
import { motion } from 'motion/react'
import { CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { api } from '../api'
import { CountUp, Empty, json, pretty } from './ui'

const FAULTS = [['hallucination', 'Grounding filter for extraction'], ['misclassify', 'Classifier prompt fix'],
  ['context_loss', 'Summary must keep dates and amounts'], ['prompt_failure', 'Strict JSON output mode']]

export default function Evals() {
  const [data, setData] = useState({ cases: [], runs: [] })
  const [busy, setBusy] = useState(false)
  const [shipped, setShipped] = useState([])
  const load = () => api.evals().then(setData)
  useEffect(() => { load() }, [])
  const rerun = async () => { setBusy(true); await api.rerun(); await load(); setBusy(false) }
  const ship = async (f) => { await api.patch(f); setShipped((s) => [...s, f]) }
  const resolved = data.cases.filter((c) => c.resolved).length
  const trend = data.runs.map((r, i) => ({ name: `Run ${i + 1}`, resolved: r.resolved, total: r.total }))

  return (
    <div className="page">
      <header className="top"><div><h2>Eval dataset</h2>
        <p className="muted">Every confirmed diagnosis becomes a regression test.</p></div>
        <button className="btn primary" onClick={rerun} disabled={busy || !data.cases.length}>{busy ? 'Re-running…' : 'Re-run regression'}</button>
      </header>
      <div className="kpis">
        <div className="kpi"><b><CountUp value={data.cases.length} /></b><span>cases collected</span></div>
        <div className="kpi"><b><CountUp value={resolved} /></b><span>known issues resolved</span></div>
        <div className="kpi"><b><CountUp value={data.cases.length ? (100 * resolved) / data.cases.length : 0} suffix="%" /></b><span>resolution rate</span></div>
      </div>
      <div className="cols">
        <section className="panel"><h3>Known issues resolved over time</h3>
          {trend.length ? (
            <ResponsiveContainer width="100%" height={220}>
              <LineChart data={trend}><CartesianGrid stroke="#242424" />
                <XAxis dataKey="name" stroke="#afafaf" /><YAxis stroke="#afafaf" allowDecimals={false} />
                <Tooltip contentStyle={{ background: '#111211', border: '1px solid #242424', borderRadius: 10 }} />
                <Line type="monotone" dataKey="resolved" stroke="#8afad7" strokeWidth={3} dot={{ r: 4 }} />
                <Line type="monotone" dataKey="total" stroke="#898989" strokeDasharray="4 4" dot={false} />
              </LineChart>
            </ResponsiveContainer>
          ) : <Empty title="No regression runs yet">Re-run the dataset after changing the pipeline to see the trend.</Empty>}
          <h3 className="mt">Ship a fix</h3>
          <p className="muted">Simulates a pipeline change for one failure class, then re-run to see cases flip to resolved.</p>
          <div className="fixes">{FAULTS.map(([f, label]) => (
            <button key={f} className="btn ghost" disabled={shipped.includes(f)} onClick={() => ship(f)}>{shipped.includes(f) ? `Shipped: ${label}` : label}</button>))}
          </div>
        </section>
        <section className="panel list">
          <h3>Cases</h3>
          {!data.cases.length && <Empty title="No eval cases yet">Flag a bad trace, confirm the diagnosis, and a case appears here.</Empty>}
          {data.cases.map((c) => (
            <motion.details layout key={c.eval_id} className="case" initial={{ opacity: 0, x: -8 }} animate={{ opacity: 1, x: 0 }}>
              <summary><i className={c.resolved ? 'dot success' : 'dot failure'} /> <b>#{c.eval_id}</b> {pretty(c.category)} <small>at {c.failing_step}</small></summary>
              <div className="diff two"><div className="pane"><h4>Bad output</h4><pre className="code">{json(c.bad_output)}</pre></div>
                <div className="pane"><h4>Corrected</h4><pre className="code">{json(c.corrected_output)}</pre></div></div>
            </motion.details>
          ))}
        </section>
      </div>
    </div>
  )
}
