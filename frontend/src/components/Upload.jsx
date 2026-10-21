import { useRef, useState } from 'react'
import { motion } from 'motion/react'
import { api } from '../api'

const TYPES = ['', 'contract', 'invoice', 'report', 'correspondence']

export default function Upload({ onDone }) {
  const [drag, setDrag] = useState(false)
  const [text, setText] = useState('')
  const [name, setName] = useState('')
  const [golden, setGolden] = useState('')
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState('')
  const input = useRef()

  const go = async (fn) => {
    setBusy(true); setErr('')
    try { onDone(await fn()) } catch (e) { setErr(e.message) } finally { setBusy(false) }
  }
  const files = (list) => [...list].forEach((f) => go(() => api.upload(f, golden)))
  const paste = () => go(() => api.run({ text, doc_id: name || 'pasted-document', golden_type: golden || undefined }))

  return (
    <div className="page">
      <header className="top"><div><h2>Upload a document</h2>
        <p className="muted">It runs through all four steps and appears in the trace explorer. Supports .txt, .md and text-based .pdf.</p></div></header>
      <motion.div className={drag ? 'drop over' : 'drop'} animate={{ scale: drag ? 1.015 : 1 }}
        onDragOver={(e) => { e.preventDefault(); setDrag(true) }} onDragLeave={() => setDrag(false)}
        onDrop={(e) => { e.preventDefault(); setDrag(false); files(e.dataTransfer.files) }}>
        <h3>{busy ? 'Running the pipeline…' : 'Drop files here'}</h3>
        <p className="muted">or</p>
        <button className="btn primary" disabled={busy} onClick={() => input.current.click()}>Choose files</button>
        <input ref={input} type="file" multiple hidden accept=".txt,.md,.pdf,text/plain,application/pdf"
          onChange={(e) => files(e.target.files)} />
      </motion.div>
      <section className="panel mt">
        <h3>Or paste text</h3>
        <div className="confirm">
          <label>Document name<input className="field" value={name} onChange={(e) => setName(e.target.value)} placeholder="e.g. vendor-contract" /></label>
          <label>Document text<textarea rows={8} value={text} onChange={(e) => setText(e.target.value)} placeholder="Paste the document here" /></label>
          <label>Known document type (optional, enables misclassification checks)
            <select value={golden} onChange={(e) => setGolden(e.target.value)}>
              {TYPES.map((t) => <option key={t} value={t}>{t || 'Not sure'}</option>)}</select></label>
          <button className="btn primary" disabled={busy || !text.trim()} onClick={paste}>Run through pipeline</button>
        </div>
      </section>
      {err && <p className="err">{err}</p>}
    </div>
  )
}
