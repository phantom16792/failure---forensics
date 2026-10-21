import { useEffect, useState } from 'react'
import { animate } from 'motion/react'

export function CountUp({ value, dec = 0, suffix = '' }) {
  const [v, setV] = useState(0)
  useEffect(() => {
    const c = animate(0, value || 0, { duration: 0.9, ease: 'easeOut', onUpdate: setV })
    return () => c.stop()
  }, [value])
  return <>{v.toFixed(dec)}{suffix}</>
}

export const pretty = (s) => (s || '').replaceAll('_', ' ')
export const json = (o) => JSON.stringify(o, null, 2)

export function Empty({ title, children }) {
  return <div className="empty"><h3>{title}</h3><p>{children}</p></div>
}
