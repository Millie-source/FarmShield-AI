import { useEffect, useState } from 'react'

const API_URL = import.meta.env.VITE_API_URL ?? 'http://localhost:8000'

export default function App() {
  const [health, setHealth] = useState<string>('checking...')

  useEffect(() => {
    fetch(`${API_URL}/health`)
      .then((r) => r.json())
      .then((d) => setHealth(`${d.app} - ${d.status}`))
      .catch(() => setHealth('API unreachable'))
  }, [])

  return (
    <main className="min-h-screen flex flex-col items-center justify-center gap-4">
      <h1 className="text-4xl font-bold tracking-tight text-emerald-700">FarmShield AI</h1>
      <p className="text-slate-600">Hyperlocal climate risk infrastructure for smallholder farmers.</p>
      <span className="rounded-full bg-emerald-100 px-3 py-1 text-sm text-emerald-800">API: {health}</span>
    </main>
  )
}
