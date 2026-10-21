import { useEffect, useState } from 'react'
import { motion } from 'motion/react'
import { api } from './api'
import Explorer from './components/Explorer'
import Evals from './components/Evals'
import Analytics from './components/Analytics'
import Upload from './components/Upload'
import Live from './components/Live'
import { Empty, pretty } from './components/ui'

const NAV = [['live', 'Live workflow'], ['upload', 'Upload document'], ['explorer', 'Trace explorer'], ['evals', 'Eval dataset'], ['analytics', 'Analytics']]
const FILTERS = ['all', 'failure', 'degraded', 'success']

export default function App() {
  const [view, setView] = useState('live')
  const [traces, setTraces] = useState([])
  const [sel, setSel] = useState(null)
  const [filter, setFilter] = useState('all')

  const refresh = async () => {
    const t = await api.traces()
    setTraces(t)
    setSel((s) => s || t.find((x) => x.status === 'failure')?.trace_id || t[0]?.trace_id || null)
  }
  useEffect(() => { refresh() }, [])
  const shown = traces.filter((t) => filter === 'all' || t.status === filter)

  return (
    <div className="shell">
      <aside className="side">
        <div className="brand"><h1>FailureForensics</h1><p>Find the step that broke your pipeline</p></div>
        <nav>
          {NAV.map(([k, label]) => (
            <button key={k} className={view === k ? 'nav on' : 'nav'} onClick={() => setView(k)}>
              {view === k && <motion.span layoutId="navpill" className="pill" />}
              <span>{label}</span>
            </button>
          ))}
        </nav>
        <div className="chips">
          {FILTERS.map((f) => (
            <button key={f} className={filter === f ? 'chip on' : 'chip'} onClick={() => setFilter(f)}>{f}</button>
          ))}
        </div>
        <div className="tlist">
          {shown.map((t) => (
            <motion.button layout key={t.trace_id} onClick={() => { setSel(t.trace_id); setView('explorer') }}
              className={sel === t.trace_id ? 'trow on' : 'trow'}>
              <i className={`dot ${t.status}`} />
              <b>{t.doc_id}</b>
              <small>{t.category && t.category !== 'no_defect_found' ? pretty(t.category) : t.status}</small>
            </motion.button>
          ))}
          {!shown.length && <p className="muted pad">No traces yet.</p>}
        </div>
      </aside>
      <main className="main">
        {view === 'explorer' && (sel ? <Explorer id={sel} onChanged={refresh} />
          : <Empty title="No traces yet">Run a sample in Live workflow or upload a document to create your first trace.</Empty>)}
        {view === 'live' && <Live onOpen={async (id) => { await refresh(); setSel(id); setView('explorer') }} onSaved={refresh} />}
        {view === 'upload' && <Upload onDone={async (t) => { setSel(t.trace_id); await refresh(); setSel(t.trace_id); setView('explorer') }} />}
        {view === 'evals' && <Evals />}
        {view === 'analytics' && <Analytics key={traces.length} />}
      </main>
    </div>
  )
}
