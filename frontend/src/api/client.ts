import type {
  Alert,
  AlertPreview,
  BulkRisk,
  Farm,
  FarmCreate,
  PartnerInfo,
  Risk,
  RiskHistoryItem,
  Scenario,
  ScenarioState,
  ScenarioSwitch,
  TriggerCheckIn,
  TriggerCheckOut,
  WeatherHistory,
} from './types'

export const API_URL: string = (import.meta.env.VITE_API_URL as string | undefined) ?? 'http://localhost:8000'

export class ApiError extends Error {
  status: number
  detail: unknown
  constructor(status: number, detail: unknown) {
    super(typeof detail === 'string' ? detail : `HTTP ${status}`)
    this.status = status
    this.detail = detail
  }
}

export interface RawResponse<T> {
  status: number
  ms: number
  headers: Record<string, string>
  body: T
}

async function raw<T>(path: string, init: RequestInit = {}): Promise<RawResponse<T>> {
  const started = performance.now()
  const res = await fetch(`${API_URL}${path}`, {
    ...init,
    headers: { Accept: 'application/json', ...(init.body ? { 'Content-Type': 'application/json' } : {}), ...(init.headers ?? {}) },
  })
  const ms = Math.round(performance.now() - started)
  const text = await res.text()
  let body: unknown = null
  try {
    body = text ? JSON.parse(text) : null
  } catch {
    body = text
  }
  const headers: Record<string, string> = {}
  res.headers.forEach((v, k) => (headers[k] = v))
  return { status: res.status, ms, headers, body: body as T }
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const r = await raw<T>(path, init)
  if (r.status >= 400) {
    const detail = (r.body as { detail?: unknown } | null)?.detail ?? r.body
    throw new ApiError(r.status, detail)
  }
  return r.body
}

const json = (body: unknown) => JSON.stringify(body)

export const api = {
  health: () => request<{ status: string; weather_provider: string }>('/health'),

  farms: {
    list: () => request<Farm[]>('/farms'),
    get: (id: number) => request<Farm>(`/farms/${id}`),
    create: (body: FarmCreate) => request<Farm>('/farms', { method: 'POST', body: json(body) }),
    remove: (id: number) => request<void>(`/farms/${id}`, { method: 'DELETE' }),
    weather: (id: number, days = 30, scenario?: Scenario) =>
      request<WeatherHistory>(`/farms/${id}/weather?days=${days}${scenario ? `&scenario=${scenario}` : ''}`),
  },

  risk: {
    latest: (id: number) => request<Risk>(`/farms/${id}/risk`),
    assess: (id: number, scenario?: Scenario) =>
      request<Risk>(`/farms/${id}/assess${scenario ? `?scenario=${scenario}` : ''}`, { method: 'POST' }),
    history: (id: number, limit = 30) => request<RiskHistoryItem[]>(`/farms/${id}/risk/history?limit=${limit}`),
  },

  scenario: {
    get: () => request<ScenarioState>('/scenario'),
    set: (scenario: Scenario, reassess = true) =>
      request<ScenarioSwitch>('/scenario', { method: 'PUT', body: json({ scenario, reassess }) }),
  },

  alerts: {
    list: (farmId: number) => request<Alert[]>(`/farms/${farmId}/alerts`),
    preview: (farmId: number, language?: 'en' | 'sw') =>
      request<AlertPreview>(`/farms/${farmId}/alerts/preview${language ? `?language=${language}` : ''}`, { method: 'POST' }),
    send: (farmId: number, language?: 'en' | 'sw', force = true) =>
      request<Alert>(`/farms/${farmId}/alerts/send?force=${force}${language ? `&language=${language}` : ''}`, { method: 'POST' }),
  },

  /** Partner API: every call carries the X-API-Key header and returns the raw response for the live viewer. */
  partner: (apiKey: string) => {
    const h = { 'X-API-Key': apiKey }
    return {
      me: () => raw<PartnerInfo>('/api/v1/me', { headers: h }),
      risk: (farmId: number, fresh = false) => raw<Risk>(`/api/v1/risk/${farmId}${fresh ? '?fresh=true' : ''}`, { headers: h }),
      bulk: (farmIds: number[]) => raw<BulkRisk>(`/api/v1/risk/bulk?farm_ids=${farmIds.join(',')}`, { headers: h }),
      checkTrigger: (body: TriggerCheckIn) =>
        raw<TriggerCheckOut>('/api/v1/insurance/check-trigger', { method: 'POST', headers: h, body: json(body) }),
    }
  },
}

export function curlFor(method: string, path: string, headers: Record<string, string> = {}, body?: unknown): string {
  const parts = [`curl -X ${method} "${API_URL}${path}"`]
  for (const [k, v] of Object.entries(headers)) parts.push(`  -H "${k}: ${v}"`)
  if (body !== undefined) {
    parts.push('  -H "Content-Type: application/json"')
    parts.push(`  -d '${JSON.stringify(body)}'`)
  }
  return parts.join(' \\\n')
}
