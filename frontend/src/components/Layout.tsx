import { NavLink, Outlet } from 'react-router-dom'
import type { Scenario } from '../api/types'
import { useScenario } from '../context/ScenarioContext'
import { Spinner } from './ui'

const SCENARIOS: { key: Scenario; label: string; icon: string; hint: string }[] = [
  { key: 'normal', label: 'Normal', icon: '⛅', hint: 'Typical September: light showers' },
  { key: 'dry_spell', label: 'Dry spell', icon: '☀️', hint: '3 weeks without rain, 33°C' },
  { key: 'heavy_rain', label: 'Heavy rain', icon: '🌧️', hint: '300+ mm in a week' },
]

function ScenarioSwitcher() {
  const { scenario, switching, setScenario, provider } = useScenario()
  return (
    <div className="flex items-center gap-2" title={`Weather provider: ${provider}`}>
      <span className="hidden text-xs font-medium uppercase tracking-wider text-stone-500 sm:inline">Weather</span>
      <div className="flex rounded-full bg-stone-100 p-1 ring-1 ring-stone-200">
        {SCENARIOS.map((s) => (
          <button
            key={s.key}
            onClick={() => setScenario(s.key)}
            disabled={switching}
            title={s.hint}
            className={`flex items-center gap-1 rounded-full px-3 py-1 text-xs font-semibold transition sm:text-sm ${
              scenario === s.key ? 'bg-white text-stone-900 shadow' : 'text-stone-500 hover:text-stone-800'
            }`}
          >
            <span aria-hidden>{s.icon}</span>
            <span className="hidden sm:inline">{s.label}</span>
          </button>
        ))}
      </div>
      {switching && <Spinner className="text-brand-600" />}
    </div>
  )
}

const nav = [
  { to: '/', label: 'Dashboard' },
  { to: '/register', label: 'Register farm' },
  { to: '/partners', label: 'For insurers & banks' },
]

export default function Layout() {
  const { apiOnline } = useScenario()
  return (
    <div className="min-h-screen">
      <header className="sticky top-0 z-40 border-b border-stone-200 bg-white/90 backdrop-blur">
        <div className="mx-auto flex max-w-6xl flex-wrap items-center gap-3 px-4 py-3">
          <NavLink to="/" className="flex items-center gap-2">
            <span className="grid h-9 w-9 place-items-center rounded-xl bg-brand-600 text-lg text-white shadow">🛡️</span>
            <div className="leading-tight">
              <div className="text-base font-bold tracking-tight">FarmShield AI</div>
              <div className="text-[11px] text-stone-500">Climate risk infrastructure</div>
            </div>
          </NavLink>
          <nav className="order-3 flex w-full gap-1 sm:order-2 sm:ml-6 sm:w-auto">
            {nav.map((n) => (
              <NavLink
                key={n.to}
                to={n.to}
                end={n.to === '/'}
                className={({ isActive }) =>
                  `rounded-lg px-3 py-1.5 text-sm font-medium ${isActive ? 'bg-brand-50 text-brand-700' : 'text-stone-600 hover:bg-stone-100'}`
                }
              >
                {n.label}
              </NavLink>
            ))}
          </nav>
          <div className="order-2 ml-auto sm:order-3">
            <ScenarioSwitcher />
          </div>
        </div>
        {!apiOnline && (
          <div className="bg-amber-100 px-4 py-1.5 text-center text-xs font-medium text-amber-900">
            API not reachable at the configured URL. Start the backend with <code>make api</code> and refresh.
          </div>
        )}
      </header>
      <main className="mx-auto max-w-6xl px-4 py-6">
        <Outlet />
      </main>
      <footer className="mx-auto max-w-6xl px-4 pb-8 text-center text-xs text-stone-400">
        FarmShield AI · JHUB Africa Hack the Weather 2026 · Data: JKUAT Conduit weather station · Scoring: FAO-56 / KALRO rules
      </footer>
    </div>
  )
}
