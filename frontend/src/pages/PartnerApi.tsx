import { useEffect, useMemo, useState } from 'react'
import { api, API_URL, curlFor, type RawResponse } from '../api/client'
import type { BulkRisk, DataCoverage, Farm, Policy } from '../api/types'
import DataCoverageBadge from '../components/DataCoverageBadge'
import { Button, Card, LevelPill, prettyStage, Spinner } from '../components/ui'
import { useScenario } from '../context/ScenarioContext'

const KEYS = [
  { label: 'acme-insurance (insurer)', value: 'fs_demo_acme_insurance_2026' },
  { label: 'harvest-sacco (SACCO)', value: 'fs_demo_harvest_sacco_2026' },
  { label: 'invalid key (see the 401)', value: 'not-a-real-key' },
]

type Endpoint = 'risk' | 'bulk' | 'trigger' | 'me'

const ENDPOINTS: { key: Endpoint; label: string; blurb: string }[] = [
  { key: 'risk', label: 'GET /api/v1/risk/{farm_id}', blurb: 'Dynamic risk score for one insured farm' },
  { key: 'bulk', label: 'GET /api/v1/risk/bulk', blurb: 'Portfolio view across many farms' },
  { key: 'trigger', label: 'POST /api/v1/insurance/check-trigger', blurb: 'Evaluate your own parametric policy' },
  { key: 'me', label: 'GET /api/v1/me', blurb: 'Verify a key' },
]

export default function PartnerApi() {
  const { version } = useScenario()
  const [farms, setFarms] = useState<Farm[]>([])
  const [apiKey, setApiKey] = useState(KEYS[0].value)
  const [endpoint, setEndpoint] = useState<Endpoint>('risk')
  const [farmId, setFarmId] = useState(1)
  const [policy, setPolicy] = useState<Policy>({ type: 'drought', window_days: 21, rainfall_threshold_mm: 30, critical_stages_only: true })
  const [resp, setResp] = useState<RawResponse<unknown> | null>(null)
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    api.farms.list().then((f) => {
      setFarms(f)
      if (f.length && !f.some((x) => x.id === farmId)) setFarmId(f[0].id)
    })
  }, [version, farmId])

  const request = useMemo(() => {
    const h = { 'X-API-Key': apiKey }
    const ids = farms.map((f) => f.id)
    switch (endpoint) {
      case 'risk':
        return { method: 'GET', path: `/api/v1/risk/${farmId}`, headers: h, body: undefined as unknown }
      case 'bulk':
        return { method: 'GET', path: `/api/v1/risk/bulk?farm_ids=${ids.join(',')}`, headers: h, body: undefined as unknown }
      case 'trigger':
        return { method: 'POST', path: '/api/v1/insurance/check-trigger', headers: h, body: { farm_id: farmId, policy } }
      case 'me':
        return { method: 'GET', path: '/api/v1/me', headers: h, body: undefined as unknown }
    }
  }, [apiKey, endpoint, farmId, farms, policy])

  const provenance = useMemo(() => {
    const b = resp?.body as { data_sources?: string[]; data_coverage?: DataCoverage | null } | undefined
    return b && Array.isArray(b.data_sources) ? b : null
  }, [resp])

  const fire = async () => {
    setBusy(true)
    try {
      const p = api.partner(apiKey)
      const r =
        endpoint === 'risk'
          ? await p.risk(farmId)
          : endpoint === 'bulk'
            ? await p.bulk(farms.map((f) => f.id))
            : endpoint === 'trigger'
              ? await p.checkTrigger({ farm_id: farmId, policy })
              : await p.me()
      setResp(r as RawResponse<unknown>)
    } finally {
      setBusy(false)
    }
  }

  const bulk = resp && endpoint === 'bulk' && resp.status === 200 ? (resp.body as BulkRisk) : null
  const input = 'rounded-lg border border-stone-300 bg-white px-2.5 py-1.5 text-sm'

  return (
    <div className="space-y-6">
      <div className="rounded-3xl bg-gradient-to-br from-brand-700 to-stone-900 p-6 text-white sm:p-8">
        <p className="text-xs font-semibold uppercase tracking-[0.25em] text-brand-100/80">For insurers, banks, SACCOs & agribusinesses</p>
        <h1 className="mt-2 text-3xl font-bold tracking-tight">Climate risk as an API</h1>
        <p className="mt-2 max-w-2xl text-sm text-stone-200">
          One call returns a dynamic, explainable risk score for any registered farm: sub-scores, reasons, growth stage and a parametric
          insurance trigger. Deterministic rules (FAO-56, KALRO), not a black box. Authenticate with <code className="rounded bg-white/10 px-1">X-API-Key</code>.
        </p>
        <div className="mt-4 flex flex-wrap gap-2 text-xs">
          <a href={`${API_URL}/docs`} target="_blank" rel="noreferrer" className="rounded-full bg-white/15 px-3 py-1 font-medium hover:bg-white/25">OpenAPI docs ↗</a>
          <a href={`${API_URL}/openapi.json`} target="_blank" rel="noreferrer" className="rounded-full bg-white/15 px-3 py-1 font-medium hover:bg-white/25">openapi.json ↗</a>
        </div>
      </div>

      <Card title="Try it live">
        <div className="grid gap-3 md:grid-cols-4">
          <label className="text-xs font-semibold text-stone-500">
            API key
            <select className={`${input} mt-1 w-full`} value={apiKey} onChange={(e) => setApiKey(e.target.value)}>
              {KEYS.map((k) => <option key={k.value} value={k.value}>{k.label}</option>)}
            </select>
          </label>
          <label className="text-xs font-semibold text-stone-500 md:col-span-2">
            Endpoint
            <select className={`${input} mt-1 w-full`} value={endpoint} onChange={(e) => setEndpoint(e.target.value as Endpoint)}>
              {ENDPOINTS.map((e) => <option key={e.key} value={e.key}>{e.label} — {e.blurb}</option>)}
            </select>
          </label>
          <label className="text-xs font-semibold text-stone-500">
            Farm
            <select className={`${input} mt-1 w-full`} value={farmId} onChange={(e) => setFarmId(Number(e.target.value))} disabled={endpoint === 'bulk' || endpoint === 'me'}>
              {farms.map((f) => <option key={f.id} value={f.id}>#{f.id} {f.farm_name} ({f.crop})</option>)}
            </select>
          </label>
        </div>

        {endpoint === 'trigger' && (
          <div className="mt-3 flex flex-wrap items-end gap-3 rounded-xl bg-stone-50 p-3 text-xs font-semibold text-stone-500">
            <label>
              Policy type
              <select className={`${input} mt-1 block`} value={policy.type} onChange={(e) => setPolicy({ ...policy, type: e.target.value as Policy['type'] })}>
                <option value="drought">drought (cumulative rain below X)</option>
                <option value="excess_rain">excess_rain (any window above X)</option>
                <option value="heat">heat (N days above T°C)</option>
              </select>
            </label>
            <label>
              Window (days)
              <input className={`${input} mt-1 block w-24`} type="number" min={1} value={policy.window_days} onChange={(e) => setPolicy({ ...policy, window_days: Number(e.target.value) })} />
            </label>
            {policy.type !== 'heat' ? (
              <label>
                Rain threshold (mm)
                <input className={`${input} mt-1 block w-28`} type="number" value={policy.rainfall_threshold_mm ?? 0} onChange={(e) => setPolicy({ ...policy, rainfall_threshold_mm: Number(e.target.value) })} />
              </label>
            ) : (
              <>
                <label>
                  Temp threshold (°C)
                  <input className={`${input} mt-1 block w-24`} type="number" value={policy.temp_threshold_c ?? 32} onChange={(e) => setPolicy({ ...policy, temp_threshold_c: Number(e.target.value) })} />
                </label>
                <label>
                  Hot days
                  <input className={`${input} mt-1 block w-20`} type="number" value={policy.hot_days_threshold ?? 5} onChange={(e) => setPolicy({ ...policy, hot_days_threshold: Number(e.target.value) })} />
                </label>
              </>
            )}
            <label className="flex items-center gap-2 pb-2">
              <input type="checkbox" checked={!!policy.critical_stages_only} onChange={(e) => setPolicy({ ...policy, critical_stages_only: e.target.checked })} />
              critical stages only
            </label>
          </div>
        )}

        <div className="mt-4 grid gap-4 lg:grid-cols-2">
          <div>
            <div className="mb-1 flex items-center justify-between text-xs font-semibold uppercase tracking-wider text-stone-500">
              <span>Request</span>
              <Button onClick={fire} disabled={busy || !farms.length}>{busy ? <Spinner /> : '▶'} Send request</Button>
            </div>
            <pre className="overflow-x-auto rounded-xl bg-stone-900 p-4 text-xs leading-relaxed text-emerald-200">{curlFor(request.method, request.path, request.headers, request.body)}</pre>
          </div>
          <div>
            <div className="mb-1 flex items-center justify-between text-xs font-semibold uppercase tracking-wider text-stone-500">
              <span>Response</span>
              {resp && (
                <span className={`rounded-full px-2 py-0.5 font-mono ${resp.status < 300 ? 'bg-emerald-50 text-emerald-700' : 'bg-red-50 text-red-700'}`}>
                  {resp.status} · {resp.ms} ms
                </span>
              )}
            </div>
            <pre className="max-h-[28rem] overflow-auto rounded-xl bg-stone-900 p-4 text-xs leading-relaxed text-stone-100">
              {resp ? JSON.stringify(resp.body, null, 2) : '// press "Send request"'}
            </pre>
            {provenance && (
              <div className="mt-2 flex flex-wrap items-center gap-1.5 text-xs">
                <span className="font-semibold uppercase tracking-wider text-stone-500">Data</span>
                {provenance.data_sources?.map((src) => (
                  <span key={src} className="rounded-full bg-stone-100 px-2 py-0.5 font-mono text-stone-700">{src}</span>
                ))}
                <DataCoverageBadge coverage={provenance.data_coverage} sources={provenance.data_sources} />
              </div>
            )}
          </div>
        </div>
      </Card>

      {bulk && (
        <Card title={`Portfolio view · ${bulk.count} farms · mean score ${bulk.summary.mean_score}`}>
          <div className="mb-3 flex flex-wrap gap-2 text-xs">
            <span className="rounded-full bg-red-50 px-2.5 py-1 font-semibold text-red-700">{bulk.summary.high_risk} high</span>
            <span className="rounded-full bg-amber-50 px-2.5 py-1 font-semibold text-amber-700">{bulk.summary.medium_risk} medium</span>
            <span className="rounded-full bg-emerald-50 px-2.5 py-1 font-semibold text-emerald-700">{bulk.summary.low_risk} low</span>
            <span className="rounded-full bg-stone-100 px-2.5 py-1 font-semibold text-stone-700">{bulk.summary.insurance_triggered} insurance triggers</span>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="text-left text-xs uppercase tracking-wider text-stone-500">
                <tr>
                  <th className="py-1.5 pr-3">Farm</th><th className="py-1.5 pr-3">Crop / stage</th><th className="py-1.5 pr-3">Drought</th><th className="py-1.5 pr-3">Flood</th>
                  <th className="py-1.5 pr-3">Heat</th><th className="py-1.5 pr-3">Health</th><th className="py-1.5 pr-3">Overall</th><th className="py-1.5">Trigger</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-stone-100 tabular-nums">
                {bulk.results.map((r) => (
                  <tr key={r.farm_id}>
                    <td className="py-1.5 pr-3 font-medium">#{r.farm_id} {r.farm_name}</td>
                    <td className="py-1.5 pr-3 capitalize">{r.crop} · {prettyStage(r.stage.name)}</td>
                    <td className="py-1.5 pr-3">{r.sub_scores.drought.score}</td>
                    <td className="py-1.5 pr-3">{r.sub_scores.flood.score}</td>
                    <td className="py-1.5 pr-3">{r.sub_scores.heat.score}</td>
                    <td className="py-1.5 pr-3">{r.sub_scores.crop_health.label}</td>
                    <td className="py-1.5 pr-3"><LevelPill level={r.overall.level}>{r.overall.score}</LevelPill></td>
                    <td className="py-1.5">{r.insurance_trigger.triggered ? <span className="font-semibold text-red-700">TRIGGERED</span> : '—'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
      )}
    </div>
  )
}
