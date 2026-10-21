import { useEffect, useReducer, useRef, useState } from 'react'
import { AnimatePresence, motion } from 'motion/react'
import { api } from '../api'
import { json, pretty } from './ui'

const STAGES = [
  ['intake', 'Intake', 'Cleans up the raw document and detects its format'],
  ['extraction', 'Extraction', 'The model pulls out people, organizations, dates, amounts and key terms'],
  ['classification', 'Classification', 'The model decides: contract, invoice, report or correspondence'],
  ['summarization', 'Summarization', 'The model writes a summary shaped for that document type'],
  ['quality', 'Quality check', 'The judge walks backward and scores every step against the source'],
]
const PACE = [['Slow', 1.3], ['Normal', 0.7], ['Fast', 0.15]]
const norm = (s) => s.toLowerCase().replace(/\s+/g, '')

const init = () => ({ text: '', current: null, trace: null, error: null, running: false,
  stages: Object.fromEntries(STAGES.map(([k]) => [k, { status: 'waiting' }])) })
const up = (s, k, patch) => ({ ...s, stages: { ...s.stages, [k]: { ...s.stages[k], ...patch } } })

function reduce(s, ev) {
  switch (ev.type) {
    case 'reset': return { ...init(), running: true }
    case 'trace_start': return { ...s, text: ev.text }
    case 'start': return { ...up(s, ev.step, { status: 'running', input: ev.input }), current: ev.step }
    case 'prompt': return up(s, s.current, { status: 'prompt', prompt: ev.prompt })
    case 'response': return up(s, s.current, { status: 'response', raw: ev.raw, tokens: ev.tokens })
    case 'end': return up(s, ev.span.step, { status: ev.span.status === 'error' ? 'error' : 'done', output: ev.span.output,
      confidence: ev.span.confidence, latency: ev.span.latency_ms, tokens: ev.span.tokens, error: ev.span.error, raw: ev.span.raw_response })
    case 'analysis_start': return up(s, 'quality', { status: 'running' })
    case 'done': return { ...up(s, 'quality', { status: 'done' }), trace: ev.trace, running: false }
    case 'error': return { ...s, error: ev.message, running: false }
    default: return s
  }
}

function Typewriter({ text, ms = 700 }) {
  const [n, setN] = useState(0)
  useEffect(() => {
    setN(0); const step = Math.max(1, Math.ceil(text.length / (ms / 20)))
    const t = setInterval(() => setN((v) => (v + step >= text.length ? (clearInterval(t), text.length) : v + step)), 20)
    return () => clearInterval(t)
  }, [text, ms])
  return <>{text.slice(0, n)}</>
}

function Doc({ text, ents }) {
  const spans = []
  ents.forEach((e) => { let i = text.indexOf(e.value); while (i !== -1 && e.value) { spans.push([i, i + e.value.length, e.type]); i = text.indexOf(e.value, i + 1) } })
  spans.sort((a, b) => a[0] - b[0])
  const out = []; let pos = 0
  spans.forEach(([a, b, t], k) => {
    if (a < pos) return
    out.push(text.slice(pos, a))
    out.push(<motion.mark key={k} className={`m ${t}`} initial={{ opacity: 0.2 }} animate={{ opacity: 1 }} transition={{ delay: k * 0.05 }}>{text.slice(a, b)}</motion.mark>)
    pos = b
  })
  out.push(text.slice(pos))
  return <pre className="doc">{out}</pre>
}

function Output({ step, o, text }) {
  if (!o) return null
  if (step === 'intake') return <p>Format <b>{o.fmt}</b> · <b>{o.char_count}</b> characters</p>
  if (step === 'extraction') return (
    <div className="ents">{o.entities.map((e) => {
      const ghost = !norm(text).includes(norm(e.value))
      return <span key={e.type + e.value} className={`ent ${ghost ? 'ghost' : e.type}`} title={ghost ? 'Not found in the document' : e.type}>{e.type}: {e.value}{ghost ? ' (not in document)' : ''}</span>
    })}</div>)
  if (step === 'classification') return <p><span className="tag no_defect_found">{o.doc_type}</span> {o.rationale}</p>
  if (step === 'summarization') return <><p className="explain">{o.headline}</p><ul className="bul">{o.bullets.map((b) => <li key={b}>{b}</li>)}</ul></>
  return null
}

function Dots({ n }) {
  return <span className="conf" title={`Self-reported confidence ${n}/5`}>{[1, 2, 3, 4, 5].map((i) => <i key={i} className={i <= n ? (n <= 2 ? 'on low' : 'on') : ''} />)}</span>
}

function Stage({ k, label, desc, st, text, last, trace }) {
  const [open, setOpen] = useState({})
  const status = st.status
  const diag = trace?.diagnosis
  const bad = diag && diag.category !== 'no_defect_found' && diag.root_step === k
  const down = diag?.propagated_to?.includes(k)
  const tone = status === 'error' || bad ? 'bad' : down ? 'down' : status === 'done' && st.confidence != null && st.confidence <= 2 ? 'low' : status
  const show = (name, label, body) => body ? (
    <details className="sec" open={open[name] ?? (status === 'prompt' || status === 'response') ? true : open[name]}
      onToggle={(e) => setOpen((o) => ({ ...o, [name]: e.target.open }))}>
      <summary>{label}</summary>{body}
    </details>) : null
  return (
    <div className={`stage ${tone} ${status !== 'waiting' ? 'live' : ''}`}>
      <div className="sn">
        {status === 'running' || status === 'prompt' || status === 'response'
          ? <motion.b animate={{ scale: [1, 1.25, 1] }} transition={{ repeat: Infinity, duration: 1 }} />
          : <b />}
        {!last && <span className="trail"><motion.i initial={{ height: 0 }} animate={{ height: status === 'done' || status === 'error' ? '100%' : 0 }} transition={{ duration: 0.5 }} /></span>}
      </div>
      <motion.div className="scard" layout>
        <header className="phead">
          <h3>{label}</h3>
          <span className="meta">{status === 'waiting' ? 'waiting' : status === 'running' ? 'receiving input…' : status === 'prompt' ? 'waiting for the model…'
            : status === 'response' ? 'model replied, validating…' : bad ? 'root cause' : down ? 'affected by upstream error' : status === 'error' ? 'failed' : 'done'}</span>
        </header>
        <p className="muted sdesc">{desc}</p>
        {k === 'quality' ? <Quality st={st} trace={trace} /> : (
          <AnimatePresence initial={false}>
            {status !== 'waiting' && (
              <motion.div key="b" initial={{ opacity: 0, height: 0 }} animate={{ opacity: 1, height: 'auto' }} style={{ overflow: 'hidden' }}>
                {st.error && <p className="err">{st.error}</p>}
                {st.status === 'done' && <Output step={k} o={st.output} text={text} />}
                {st.status === 'done' && st.confidence != null && <p className="meta">Self-reported confidence <Dots n={st.confidence} /> · {st.tokens} tokens · {st.latency} ms</p>}
                {show('in', 'What this step received', st.input && <pre className="code">{json(k === 'intake' || !st.input.text ? st.input : { ...st.input, text: st.input.text.slice(0, 160) + '…' })}</pre>)}
                {show('prompt', 'Prompt sent to the model', st.prompt && <pre className="code"><Typewriter text={st.prompt} /></pre>)}
                {show('raw', 'Raw model response', st.raw && <pre className="code"><Typewriter text={st.raw} ms={500} /></pre>)}
              </motion.div>
            )}
          </AnimatePresence>
        )}
      </motion.div>
    </div>
  )
}

function Quality({ st, trace }) {
  if (st.status === 'waiting') return null
  if (st.status === 'running') return <p className="meta">Checking whether each output is grounded in the source…</p>
  const d = trace?.diagnosis
  if (!d) return null
  return (
    <div>
      {Object.entries(d.scores).map(([step, v], i) => (
        <div className="bar" key={step}><span>{pretty(step)}</span>
          <div><motion.i initial={{ width: 0 }} animate={{ width: `${v * 100}%` }} transition={{ delay: i * 0.12, duration: 0.6 }} className={v < 0.6 ? 'bad' : ''} /></div>
          <em>{v.toFixed(2)}</em></div>))}
      <p className="explain">{d.explanation}</p>
    </div>
  )
}

export default function Live({ onOpen }) {
  const [s, dispatch] = useReducer(reduce, undefined, init)
  const [samples, setSamples] = useState([])
  const [pick, setPick] = useState('')
  const [text, setText] = useState('')
  const [pace, setPace] = useState(0.7)
  const file = useRef()
  useEffect(() => { api.samples().then((x) => { setSamples(x); setPick('0') }).catch(() => {}) }, [])

  const run = async (fd) => {
    dispatch({ type: 'reset' })
    try { await api.stream(fd, dispatch) } catch (e) { dispatch({ type: 'error', message: e.message }) }
  }
  const runSample = () => { const d = samples[+pick]; const f = new FormData()
    f.append('text', d.text); f.append('doc_id', d.doc_id); f.append('golden_type', d.golden_type); if (d.fault) f.append('fault', d.fault); f.append('pace', pace); run(f) }
  const runText = () => { const f = new FormData(); f.append('text', text); f.append('doc_id', 'pasted-document'); f.append('pace', pace); run(f) }
  const runFile = (fl) => { if (!fl) return; const f = new FormData(); f.append('file', fl); f.append('pace', pace); run(f) }

  const docText = s.stages.intake.output?.text || s.text
  const ents = s.stages.extraction.output?.entities || []
  const missing = ents.filter((e) => docText && !norm(docText).includes(norm(e.value)))

  return (
    <div className="page">
      <header className="top"><div><h2>Live workflow</h2>
        <p className="muted">Watch one document move through every step: what each step receives, the prompt, the model's reply, and what comes out.</p></div></header>
      <section className="panel ctrl">
        <label>Sample document
          <select value={pick} onChange={(e) => setPick(e.target.value)}>
            {samples.map((d, i) => <option key={d.doc_id} value={i}>{d.doc_id} · {d.golden_type}{d.scenario !== 'clean' ? ` · ${pretty(d.scenario)}` : ''}</option>)}</select></label>
        <button className="btn primary" disabled={s.running || !samples.length} onClick={runSample}>Run sample</button>
        <button className="btn ghost" disabled={s.running} onClick={() => file.current.click()}>Upload file</button>
        <input ref={file} type="file" hidden accept=".txt,.md,.pdf" onChange={(e) => { runFile(e.target.files[0]); e.target.value = '' }} />
        <label>Speed<select value={pace} onChange={(e) => setPace(+e.target.value)}>{PACE.map(([l, v]) => <option key={l} value={v}>{l}</option>)}</select></label>
        <details className="paste"><summary>Paste text instead</summary>
          <textarea rows={5} value={text} onChange={(e) => setText(e.target.value)} placeholder="Paste a document" />
          <button className="btn ghost" disabled={s.running || !text.trim()} onClick={runText}>Run pasted text</button></details>
      </section>
      {s.error && <p className="err">{s.error}</p>}
      {!docText && !s.running && !s.error && <div className="empty"><h3>Nothing running</h3><p>Pick a sample (try one marked hallucination) and press Run sample.</p></div>}
      {(docText || s.running) && (
        <div className="live-grid">
          <aside className="docpanel panel">
            <h3>Document</h3>
            <p className="muted sdesc">Entities light up as extraction finishes.</p>
            <Doc text={docText} ents={ents} />
            {missing.length > 0 && <div className="ghostbox"><b>Not in the document:</b> {missing.map((e) => <span key={e.value} className="ent ghost">{e.value}</span>)}</div>}
          </aside>
          <div className="timeline">
            {STAGES.map(([k, label, desc], i) => (
              <Stage key={k} k={k} label={label} desc={desc} st={s.stages[k]} text={docText} last={i === STAGES.length - 1} trace={s.trace} />))}
            {s.trace && <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} className="doneRow">
              <button className="btn primary" onClick={() => onOpen(s.trace.trace_id)}>Open in trace explorer to flag and confirm</button></motion.div>}
          </div>
        </div>)}
    </div>
  )
}
