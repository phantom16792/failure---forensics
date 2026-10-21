import { Fragment, useEffect, useState } from 'react'
import { AnimatePresence, motion } from 'motion/react'
import { api } from '../api'
import { Empty, json, pretty } from './ui'

const STEPS = [['intake', 'Intake'], ['extraction', 'Extraction'], ['classification', 'Classification'], ['summarization', 'Summarization']]
const CATS = ['extraction_hallucination', 'misclassification', 'propagation_error', 'prompt_failure', 'context_loss', 'no_defect_found']
const TABS = ['input', 'output', 'prompt', 'raw_response']
const sleep = (ms) => new Promise((r) => setTimeout(r, ms))

function nodeState(span, diag) {
  if (!span) return 'skipped'
  if (diag?.category && diag.category !== 'no_defect_found' && diag.root_step === span.step) return 'root'
  if (diag?.propagated_to?.includes(span.step)) return 'downstream'
  if (span.status === 'error') return 'root'
  if (span.confidence != null && span.confidence <= 2) return 'low'
  return 'ok'
}
const LABEL = { ok: 'healthy', low: 'low confidence', root: 'root cause', downstream: 'propagated', skipped: 'did not run' }

function Graph({ trace, diag, selected, onSelect, scan }) {
  const by = Object.fromEntries(trace.spans.map((s) => [s.step, s]))
  return (
    <div className="graph" role="list">
      {STEPS.map(([k, label], i) => {
        const span = by[k], st = nodeState(span, diag)
        return (
          <Fragment key={k}>
            {i > 0 && (
              <div className="wire" aria-hidden>
                <motion.i key={`${trace.trace_id}-${scan}`}
                  initial={{ x: scan >= 0 ? '120%' : '-120%' }} animate={{ x: scan >= 0 ? '-120%' : '120%' }}
                  transition={{ duration: scan >= 0 ? 0.38 : 0.7, delay: scan >= 0 ? 0 : i * 0.18 }} />
              </div>
            )}
            <motion.button role="listitem" className={`node ${st} ${selected === k ? 'sel' : ''}`}
              onClick={() => span && onSelect(k)} disabled={!span}
              animate={{ scale: scan === i ? 1.07 : 1 }} whileHover={span ? { y: -3 } : {}}
              transition={{ type: 'spring', stiffness: 380, damping: 22 }}>
              {st === 'root' && <motion.span className="halo" initial={{ opacity: 0, scale: 0.6 }} animate={{ opacity: [0.7, 0], scale: [1, 1.5] }} transition={{ duration: 1.6, repeat: Infinity }} />}
              <strong>{label}</strong>
              <em>{LABEL[st]}</em>
              <small>{span ? `${span.confidence != null ? `confidence ${span.confidence}/5 · ` : ''}${span.latency_ms} ms` : '—'}</small>
              {span?.judge && <small>judge {span.judge.score.toFixed(2)}</small>}
            </motion.button>
          </Fragment>
        )
      })}
    </div>
  )
}

function SpanDetail({ span }) {
  const [tab, setTab] = useState('output')
  useEffect(() => setTab('output'), [span?.span_id])
  if (!span) return <Empty title="Select a step">Click a node to inspect its input, output, prompt and raw response.</Empty>
  const val = span[tab]
  return (
    <section className="panel">
      <header className="phead">
        <h3>{pretty(span.step)}</h3>
        <span className="meta">{span.tokens} tokens · {span.latency_ms} ms · span {span.span_id}</span>
      </header>
      <div className="tabs">{TABS.map((t) => (
        <button key={t} className={tab === t ? 'tab on' : 'tab'} onClick={() => setTab(t)}>{pretty(t)}</button>))}
      </div>
      {span.error && <p className="err">{span.error}</p>}
      <AnimatePresence mode="wait">
        <motion.pre key={tab + span.span_id} className="code" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} transition={{ duration: 0.12 }}>
          {typeof val === 'string' ? val || '(no LLM call in this step)' : json(val)}
        </motion.pre>
      </AnimatePresence>
    </section>
  )
}

const lines = (o) => json(o).split('\n')
function Pane({ title, body, against, mark }) {
  const nz = (l) => l.trim().replace(/,$/, '')
  const other = new Set(against ? lines(against).map(nz) : [])
  return (
    <div className="pane"><h4>{title}</h4>
      <pre className="code">{lines(body).map((l, i) => <div key={i} className={mark && !other.has(nz(l)) && !l.includes('"confidence"') ? mark : ''}>{l}</div>)}</pre>
    </div>
  )
}

function Diagnosis({ trace, onFlag, flagging, onSaved }) {
  const d = trace.diagnosis
  const [cat, setCat] = useState(d?.category)
  const [fix, setFix] = useState('')
  const [saved, setSaved] = useState(null)
  useEffect(() => { setCat(d?.category); setFix(d?.expected ? json(d.expected) : ''); setSaved(null) }, [trace.trace_id, d?.category])
  if (!d) return (
    <section className="panel center">
      <h3>Is this output wrong?</h3>
      <p className="muted">Flag it and the analyzer walks backward through every step to find where quality first dropped.</p>
      <button className="btn primary" onClick={onFlag} disabled={flagging}>{flagging ? 'Tracing backward…' : 'Flag as bad output'}</button>
    </section>
  )
  const root = trace.spans.find((s) => s.step === d.root_step)
  const confirm = async () => {
    let corrected
    try { corrected = fix ? JSON.parse(fix) : undefined } catch { return setSaved({ error: 'Corrected output must be valid JSON.' }) }
    const r = await api.confirm(trace.trace_id, { category: cat, step: d.root_step, corrected_output: corrected })
    setSaved({ id: r.eval_id }); onSaved()
  }
  return (
    <motion.section className="panel" initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }}>
      <header className="phead">
        <h3>Diagnosis</h3><span className={`tag ${d.category}`}>{pretty(d.category)}</span>
      </header>
      <p className="explain">{d.explanation}</p>
      <small className="muted">Diagnosed in {d.diagnosis_ms} ms</small>
      {root && d.expected && d.category !== 'no_defect_found' && (
        <div className="diff">
          <Pane title="Received" body={root.input.text ? { ...root.input, text: root.input.text.slice(0, 140) + '…' } : root.input} />
          <Pane title="Produced" body={root.output ?? { error: root.error }} against={d.expected} mark="del" />
          <Pane title="Should have produced" body={d.expected} against={root.output} mark="add" />
        </div>
      )}
      {d.category !== 'no_defect_found' && (
        <div className="confirm">
          <label>Failure category
            <select value={cat} onChange={(e) => setCat(e.target.value)}>{CATS.map((c) => <option key={c} value={c}>{pretty(c)}</option>)}</select>
          </label>
          <label>Corrected output (JSON)
            <textarea value={fix} onChange={(e) => setFix(e.target.value)} rows={5} />
          </label>
          <button className="btn primary" onClick={confirm} disabled={!!saved?.id}>
            {saved?.id ? `Added to eval set (case ${saved.id})` : cat === d.category ? 'Confirm diagnosis and add to eval set' : 'Override category and add to eval set'}
          </button>
          {saved?.error && <p className="err">{saved.error}</p>}
        </div>
      )}
    </motion.section>
  )
}

export default function Explorer({ id, onChanged }) {
  const [trace, setTrace] = useState(null)
  const [step, setStep] = useState('extraction')
  const [scan, setScan] = useState(-1)
  const [flagging, setFlagging] = useState(false)

  useEffect(() => { setTrace(null); api.trace(id).then((t) => { setTrace(t); setStep(t.diagnosis?.root_step || 'extraction') }) }, [id])
  if (!trace) return <p className="muted pad">Loading trace…</p>

  const flag = async () => {
    setFlagging(true)
    try {
      const req = api.flag(id)
      for (let i = trace.spans.length - 1; i >= 0; i--) { setScan(i); await sleep(380) }
      const t = await req
      setTrace(t); setStep(t.diagnosis?.root_step || step); onChanged()
    } finally { setScan(-1); setFlagging(false) }
  }
  const span = trace.spans.find((s) => s.step === step)
  const out = trace.final_output

  return (
    <div className="explorer">
      <header className="top">
        <div><h2>{trace.doc_id}</h2><p className="muted">trace {trace.trace_id} · score {trace.final_score}</p></div>
        <span className={`tag ${trace.status}`}>{trace.status}</span>
      </header>
      <Graph trace={trace} diag={trace.diagnosis} selected={step} onSelect={setStep} scan={scan} />
      <div className="cols">
        <SpanDetail span={span} />
        <div className="stack">
          <Diagnosis trace={trace} onFlag={flag} flagging={flagging} onSaved={() => { api.trace(id).then(setTrace); onChanged() }} />
          {out && (
            <section className="panel"><h3>Final output</h3>
              <p className="explain">{out.headline}</p>
              <ul className="bul">{out.bullets.map((b) => <li key={b}>{b}</li>)}</ul>
            </section>
          )}
        </div>
      </div>
    </div>
  )
}
