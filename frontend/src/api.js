// Uses VITE_API_URL in production, or falls back to local backend during development
const API_BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000';

export default API_BASE_URL;

const j = async (url, opts = {}) => {
  const r = await fetch(API_BASE_URL + '/api' + url, { headers: { 'Content-Type': 'application/json' }, ...opts })
  if (!r.ok) throw new Error(await r.text())
  return r.json()
}
const post = (url, body) => j(url, { method: 'POST', body: body ? JSON.stringify(body) : undefined })

export const api = {
  upload: async (file, golden) => {
    const f = new FormData(); f.append('file', file); if (golden) f.append('golden_type', golden)
    const r = await fetch('/api/upload', { method: 'POST', body: f })
    if (!r.ok) throw new Error((await r.json().catch(() => ({}))).detail || 'Upload failed')
    return r.json()
  },
  run: (body) => post('/run', body),
  samples: () => j('/samples'),
  stream: async (fd, onEvent) => {
    const r = await fetch('/api/stream', { method: 'POST', body: fd })
    if (!r.ok) throw new Error((await r.json().catch(() => ({}))).detail || 'Run failed')
    const rd = r.body.getReader(), dec = new TextDecoder()
    let buf = ''
    for (;;) {
      const { done, value } = await rd.read()
      if (done) break
      buf += dec.decode(value, { stream: true })
      let i
      while ((i = buf.indexOf('\n\n')) >= 0) {
        const line = buf.slice(0, i).split('\n').find((l) => l.startsWith('data: '))
        buf = buf.slice(i + 2)
        if (line) onEvent(JSON.parse(line.slice(6)))
      }
    }
  },
  traces: () => j('/traces'),
  trace: (id) => j(`/traces/${id}`),
  batch: () => post('/run-batch'),
  flag: (id) => post(`/traces/${id}/flag`),
  confirm: (id, body) => post(`/traces/${id}/confirm`, body),
  evals: () => j('/evals'),
  rerun: () => post('/evals/rerun'),
  patch: (fault) => post('/demo/patch', { fault }),
  reset: () => post('/demo/reset'),
  analytics: () => j('/analytics'),
  health: () => j('/health'),
}
