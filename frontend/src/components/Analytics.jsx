import { useEffect, useState } from 'react'
import { Area, AreaChart, Bar, BarChart, CartesianGrid, Cell, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { api } from '../api'
import { CountUp, Empty, pretty } from './ui'

const TIP = { contentStyle: { background: '#111211', border: '1px solid #242424', borderRadius: 10 } }
const COLORS = ['#8afad7', '#d1a06c', '#49A78C', '#E8DBB5', '#a37d53']

export default function Analytics() {
  const [a, setA] = useState(null)
  useEffect(() => { api.analytics().then(setA) }, [])
  if (!a) return <p className="muted pad">Loading…</p>
  if (!a.total) return <Empty title="Nothing to analyze">Run the batch to populate failure analytics.</Empty>
  const cat = a.by_category.map((c) => ({ ...c, name: pretty(c.name) }))
  return (
    <div className="page">
      <header className="top"><div><h2>Failure analytics</h2><p className="muted">Where to invest engineering effort first.</p></div></header>
      <div className="kpis">
        <div className="kpi"><b><CountUp value={a.total} /></b><span>traces</span></div>
        <div className="kpi"><b><CountUp value={(100 * a.defects) / a.total} dec={0} suffix="%" /></b><span>failure rate</span></div>
        <div className="kpi"><b><CountUp value={a.avg_diagnosis_ms} dec={2} /> ms</b><span>average time to root cause</span></div>
        <div className="kpi"><b><CountUp value={a.evals} /></b><span>eval cases</span></div>
      </div>
      <div className="grid2">
        <section className="panel"><h3>Failure types</h3>
          <ResponsiveContainer width="100%" height={240}><BarChart data={cat} layout="vertical" margin={{ left: 40 }}>
            <CartesianGrid stroke="#242424" horizontal={false} /><XAxis type="number" stroke="#afafaf" allowDecimals={false} />
            <YAxis type="category" dataKey="name" stroke="#afafaf" width={150} /><Tooltip {...TIP} cursor={{ fill: '#111211' }} />
            <Bar dataKey="count" radius={6}>{cat.map((_, i) => <Cell key={i} fill={COLORS[i % COLORS.length]} />)}</Bar></BarChart></ResponsiveContainer>
        </section>
        <section className="panel"><h3>Step that fails most often</h3>
          <ResponsiveContainer width="100%" height={240}><BarChart data={a.by_step}>
            <CartesianGrid stroke="#242424" vertical={false} /><XAxis dataKey="name" stroke="#afafaf" />
            <YAxis stroke="#afafaf" allowDecimals={false} /><Tooltip {...TIP} cursor={{ fill: '#111211' }} />
            <Bar dataKey="count" fill="#8afad7" radius={6} /></BarChart></ResponsiveContainer>
        </section>
        <section className="panel wide"><h3>Failure rate by batch of 10 documents</h3>
          <ResponsiveContainer width="100%" height={220}><AreaChart data={a.failure_rate}>
            <defs><linearGradient id="g" x1="0" x2="0" y1="0" y2="1"><stop offset="0" stopColor="#d1a06c" stopOpacity={0.5} /><stop offset="1" stopColor="#d1a06c" stopOpacity={0} /></linearGradient></defs>
            <CartesianGrid stroke="#242424" /><XAxis dataKey="name" stroke="#afafaf" /><YAxis stroke="#afafaf" unit="%" />
            <Tooltip {...TIP} /><Area type="monotone" dataKey="rate" stroke="#d1a06c" strokeWidth={2.5} fill="url(#g)" /></AreaChart></ResponsiveContainer>
        </section>
      </div>
    </div>
  )
}
