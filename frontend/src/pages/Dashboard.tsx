import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../api/client'
import type { Farm } from '../api/types'
import { useScenario } from '../context/ScenarioContext'
import { useAnimatedNumber } from '../hooks/useAnimatedNumber'
import { Button, CROP_EMOJI, ErrorBox, LEVEL_SOLID, LEVEL_TEXT, LevelPill, prettyStage, Skeleton } from '../components/ui'

function FarmCard({ farm }: { farm: Farm }) {
  const r = farm.latest_risk
  const score = useAnimatedNumber(r?.overall_score ?? 0)
  return (
    <Link
      to={`/farms/${farm.id}`}
      className="group relative flex flex-col overflow-hidden rounded-2xl border border-stone-200 bg-white p-5 shadow-sm transition hover:-translate-y-0.5 hover:shadow-md"
    >
      {r && <span className={`absolute inset-x-0 top-0 h-1 ${LEVEL_SOLID[r.overall_level]}`} />}
      <div className="flex items-start justify-between gap-3">
        <div>
          <h3 className="text-lg font-bold tracking-tight">{farm.farm_name}</h3>
          <p className="text-sm text-stone-500">{farm.farmer_name} · {farm.phone}</p>
        </div>
        <span className="text-3xl" aria-hidden>{CROP_EMOJI[farm.crop] ?? '🌱'}</span>
      </div>
      <div className="mt-3 flex flex-wrap items-center gap-2 text-sm">
        <span className="rounded-lg bg-stone-100 px-2 py-0.5 font-medium">{farm.crop_display}</span>
        <span className="text-stone-600">
          {prettyStage(farm.stage)} · day {farm.days_after_planting}
        </span>
      </div>
      <div className="mt-5 flex items-end justify-between">
        {r ? (
          <>
            <div>
              <div className={`text-5xl font-black tabular-nums leading-none ${LEVEL_TEXT[r.overall_level]}`}>{score}</div>
              <div className="mt-1 text-xs text-stone-400">/ 100 overall</div>
            </div>
            <div className="flex flex-col items-end gap-1.5">
              <LevelPill level={r.overall_level}>{r.overall_label}</LevelPill>
              {r.insurance_triggered && (
                <span className="rounded-full bg-red-600 px-2 py-0.5 text-[11px] font-bold text-white">INSURANCE TRIGGER</span>
              )}
            </div>
          </>
        ) : (
          <span className="text-sm text-stone-400">Not yet assessed</span>
        )}
      </div>
    </Link>
  )
}

export default function Dashboard() {
  const { version, scenario } = useScenario()
  const [farms, setFarms] = useState<Farm[] | null>(null)
  const [error, setError] = useState<unknown>(null)

  const load = () => {
    api.farms
      .list()
      .then((f) => {
        setFarms(f)
        setError(null)
      })
      .catch(setError)
  }
  useEffect(load, [version])

  const high = farms?.filter((f) => f.latest_risk?.overall_level === 'HIGH').length ?? 0
  const triggered = farms?.filter((f) => f.latest_risk?.insurance_triggered).length ?? 0

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">Farms near Juja</h1>
          <p className="text-sm text-stone-500">
            Live risk scores from the JKUAT weather station · scenario <span className="font-semibold">{scenario.replace('_', ' ')}</span>
          </p>
        </div>
        <Link to="/register">
          <Button>+ Register farm</Button>
        </Link>
      </div>

      {farms && (
        <div className="grid grid-cols-3 gap-3">
          {[
            { label: 'Farms', value: farms.length, tone: 'text-stone-900' },
            { label: 'High risk', value: high, tone: high ? 'text-risk-high' : 'text-stone-900' },
            { label: 'Insurance triggers', value: triggered, tone: triggered ? 'text-risk-high' : 'text-stone-900' },
          ].map((s) => (
            <div key={s.label} className="rounded-2xl border border-stone-200 bg-white px-4 py-3">
              <div className="text-xs font-medium uppercase tracking-wider text-stone-500">{s.label}</div>
              <div className={`text-2xl font-bold tabular-nums ${s.tone}`}>{s.value}</div>
            </div>
          ))}
        </div>
      )}

      {error ? <ErrorBox error={error} retry={load} /> : null}
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {farms === null && !error && [0, 1, 2].map((i) => <Skeleton key={i} className="h-48" />)}
        {farms?.map((f) => <FarmCard key={f.id} farm={f} />)}
      </div>
    </div>
  )
}
