import { useCallback, useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { api } from '../api/client'
import type { Farm, Risk, RiskHistoryItem, WeatherHistory } from '../api/types'
import AdviceCard from '../components/AdviceCard'
import AlertsPanel from '../components/AlertsPanel'
import DataCoverageBadge from '../components/DataCoverageBadge'
import ReasonsList from '../components/ReasonsList'
import RiskPanel from '../components/RiskPanel'
import WeatherChart from '../components/WeatherChart'
import { Button, Card, CROP_EMOJI, ErrorBox, fmtDateTime, LevelPill, prettyStage, Skeleton, Spinner, Toast } from '../components/ui'
import { useScenario } from '../context/ScenarioContext'

export default function FarmDetail() {
  const { id } = useParams()
  const farmId = Number(id)
  const { version } = useScenario()
  const [farm, setFarm] = useState<Farm | null>(null)
  const [risk, setRisk] = useState<Risk | null>(null)
  const [weather, setWeather] = useState<WeatherHistory | null>(null)
  const [history, setHistory] = useState<RiskHistoryItem[]>([])
  const [error, setError] = useState<unknown>(null)
  const [assessing, setAssessing] = useState(false)
  const [toast, setToast] = useState<string | null>(null)

  const notify = (m: string) => {
    setToast(m)
    setTimeout(() => setToast(null), 3000)
  }

  const load = useCallback(() => {
    Promise.all([api.farms.get(farmId), api.risk.latest(farmId), api.farms.weather(farmId, 30), api.risk.history(farmId, 10)])
      .then(([f, r, w, h]) => {
        setFarm(f)
        setRisk(r)
        setWeather(w)
        setHistory(h)
        setError(null)
      })
      .catch(setError)
  }, [farmId])

  useEffect(load, [load, version])

  const reassess = async () => {
    setAssessing(true)
    try {
      const r = await api.risk.assess(farmId)
      setRisk(r)
      setHistory(await api.risk.history(farmId, 10))
      notify(`Re-assessed: ${r.overall.score}/100 ${r.overall.level}`)
    } catch (e) {
      setError(e)
    } finally {
      setAssessing(false)
    }
  }

  if (error) return <ErrorBox error={error} retry={load} />
  if (!farm || !risk) {
    return (
      <div className="space-y-4">
        <Skeleton className="h-10 w-72" />
        <Skeleton className="h-72" />
        <Skeleton className="h-40" />
      </div>
    )
  }

  const progress = Math.round(risk.stage.progress * 100)

  return (
    <div className="space-y-6">
      {toast && <Toast message={toast} kind="success" />}
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <Link to="/" className="text-xs font-medium text-stone-500 hover:text-stone-800">← All farms</Link>
          <h1 className="mt-1 flex items-center gap-2 text-2xl font-bold tracking-tight">
            <span aria-hidden>{CROP_EMOJI[farm.crop]}</span> {farm.farm_name}
          </h1>
          <p className="text-sm text-stone-500">
            {farm.farmer_name} · {farm.phone} · {farm.lat.toFixed(4)}, {farm.lon.toFixed(4)} · {farm.area_ha ? `${farm.area_ha} ha` : 'area n/a'}
          </p>
          <DataCoverageBadge coverage={risk.data_coverage} sources={risk.data_sources} className="mt-2" />
        </div>
        <Button variant="ghost" onClick={reassess} disabled={assessing}>
          {assessing ? <Spinner /> : '↻'} Re-assess now
        </Button>
      </div>

      <div className="rounded-2xl border border-stone-200 bg-white p-4">
        <div className="flex flex-wrap items-center justify-between gap-2 text-sm">
          <span>
            <span className="font-semibold">{farm.crop_display}</span> · planted {new Date(farm.planting_date).toLocaleDateString('en-KE')} · day{' '}
            {risk.stage.day_after_planting}
          </span>
          <span className="font-semibold">
            <span className="capitalize">{prettyStage(risk.stage.name)}</span> stage{' '}
            <span className="font-normal text-stone-500">
              (day {risk.stage.day_in_stage + 1} of {risk.stage.stage_length_days}) · needs {risk.stage.water_need_mm_week} mm/week
            </span>
          </span>
        </div>
        <div className="mt-2 h-2 overflow-hidden rounded-full bg-stone-100">
          <div className="h-full rounded-full bg-brand-500 transition-all duration-700" style={{ width: `${progress}%` }} />
        </div>
      </div>

      <RiskPanel risk={risk} />

      <div className="grid gap-6 lg:grid-cols-2">
        <AdviceCard advice={risk.advice} defaultLang={farm.language} />
        <ReasonsList risk={risk} />
      </div>

      {weather && <WeatherChart readings={weather.readings} source={weather.source} soil={risk.soil_moisture_pct} soilSource={risk.soil_moisture_source} heatMetric={risk.heat_metric} />}

      <AlertsPanel farmId={farm.id} language={farm.language} onSent={notify} />

      <Card title="Assessment history">
        {history.length === 0 ? (
          <p className="text-sm text-stone-500">No history yet.</p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="text-left text-xs uppercase tracking-wider text-stone-500">
                <tr>
                  <th className="py-1.5 pr-3">When</th>
                  <th className="py-1.5 pr-3">Scenario</th>
                  <th className="py-1.5 pr-3">Stage</th>
                  <th className="py-1.5 pr-3">Drought</th>
                  <th className="py-1.5 pr-3">Flood</th>
                  <th className="py-1.5 pr-3">Heat</th>
                  <th className="py-1.5 pr-3">Health</th>
                  <th className="py-1.5 pr-3">Overall</th>
                  <th className="py-1.5">Trigger</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-stone-100 tabular-nums">
                {history.map((h) => (
                  <tr key={h.assessment_id}>
                    <td className="py-1.5 pr-3 text-stone-500">{fmtDateTime(h.assessed_at)}</td>
                    <td className="py-1.5 pr-3">{h.scenario?.replace('_', ' ') ?? 'live'}</td>
                    <td className="py-1.5 pr-3 capitalize">{prettyStage(h.stage)}</td>
                    <td className="py-1.5 pr-3">{h.drought}</td>
                    <td className="py-1.5 pr-3">{h.flood}</td>
                    <td className="py-1.5 pr-3">{h.heat}</td>
                    <td className="py-1.5 pr-3">{h.crop_health}</td>
                    <td className="py-1.5 pr-3"><LevelPill level={h.overall_level}>{h.overall_score}</LevelPill></td>
                    <td className="py-1.5">{h.insurance_triggered ? '⚠️ yes' : '—'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>
    </div>
  )
}
