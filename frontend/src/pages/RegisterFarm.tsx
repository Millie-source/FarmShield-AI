import L from 'leaflet'
import { useState } from 'react'
import { MapContainer, Marker, TileLayer, useMapEvents } from 'react-leaflet'
import { useNavigate } from 'react-router-dom'
import { api } from '../api/client'
import type { Crop, FarmCreate } from '../api/types'
import { Button, Card, CROP_EMOJI, Spinner } from '../components/ui'
import { useScenario } from '../context/ScenarioContext'

// Leaflet's default marker assets don't resolve under Vite; point at the CDN copies.
L.Icon.Default.mergeOptions({
  iconRetinaUrl: 'https://unpkg.com/leaflet@1.9.4/dist/images/marker-icon-2x.png',
  iconUrl: 'https://unpkg.com/leaflet@1.9.4/dist/images/marker-icon.png',
  shadowUrl: 'https://unpkg.com/leaflet@1.9.4/dist/images/marker-shadow.png',
})

const CROPS: { key: Crop; label: string }[] = [
  { key: 'maize', label: 'Maize' },
  { key: 'beans', label: 'Beans' },
  { key: 'potatoes', label: 'Potatoes' },
  { key: 'tomatoes', label: 'Tomatoes' },
  { key: 'kale', label: 'Kale (sukuma wiki)' },
]

const JUJA: [number, number] = [-1.0955, 37.0144]

function ClickToPlace({ onPick }: { onPick: (lat: number, lon: number) => void }) {
  useMapEvents({ click: (e) => onPick(e.latlng.lat, e.latlng.lng) })
  return null
}

const daysAgo = (n: number) => {
  const d = new Date()
  d.setDate(d.getDate() - n)
  return d.toISOString().slice(0, 10)
}

export default function RegisterFarm() {
  const nav = useNavigate()
  const { bump } = useScenario()
  const [form, setForm] = useState<FarmCreate>({
    farmer_name: '',
    phone: '',
    language: 'sw',
    farm_name: '',
    crop: 'maize',
    planting_date: daysAgo(60),
    lat: JUJA[0],
    lon: JUJA[1],
    area_ha: null,
  })
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const set = <K extends keyof FarmCreate>(k: K, v: FarmCreate[K]) => setForm((f) => ({ ...f, [k]: v }))

  const submit = async (e: React.FormEvent) => {
    e.preventDefault()
    setBusy(true)
    setError(null)
    try {
      const farm = await api.farms.create({ ...form, area_ha: form.area_ha || null })
      bump()
      nav(`/farms/${farm.id}`)
    } catch (err) {
      const detail = (err as { detail?: unknown }).detail
      setError(Array.isArray(detail) ? detail.map((d: { msg: string }) => d.msg).join('; ') : err instanceof Error ? err.message : String(err))
    } finally {
      setBusy(false)
    }
  }

  const input = 'mt-1 w-full rounded-lg border border-stone-300 bg-white px-3 py-2 text-sm focus:border-brand-500 focus:outline-none focus:ring-2 focus:ring-brand-100'
  const label = 'block text-xs font-semibold uppercase tracking-wider text-stone-500'

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">Register a farm</h1>
        <p className="text-sm text-stone-500">Takes 30 seconds. The first risk assessment runs immediately.</p>
      </div>
      <form onSubmit={submit} className="grid gap-6 lg:grid-cols-[1fr_1.1fr]">
        <Card title="Farmer & crop">
          <div className="grid gap-4 sm:grid-cols-2">
            <div className="sm:col-span-2">
              <label className={label}>Farmer name</label>
              <input className={input} required minLength={2} value={form.farmer_name} onChange={(e) => set('farmer_name', e.target.value)} placeholder="Wanjiku Kamau" />
            </div>
            <div>
              <label className={label}>Phone (for SMS)</label>
              <input className={input} required value={form.phone} onChange={(e) => set('phone', e.target.value)} placeholder="+254711000001 or 0711000001" />
            </div>
            <div>
              <label className={label}>Language</label>
              <select className={input} value={form.language} onChange={(e) => set('language', e.target.value as 'en' | 'sw')}>
                <option value="sw">Kiswahili</option>
                <option value="en">English</option>
              </select>
            </div>
            <div className="sm:col-span-2">
              <label className={label}>Farm / plot name</label>
              <input className={input} required minLength={2} value={form.farm_name} onChange={(e) => set('farm_name', e.target.value)} placeholder="Kamau Maize Plot" />
            </div>
            <div className="sm:col-span-2">
              <label className={label}>Crop</label>
              <div className="mt-1 grid grid-cols-2 gap-2 sm:grid-cols-3">
                {CROPS.map((c) => (
                  <button
                    type="button"
                    key={c.key}
                    onClick={() => set('crop', c.key)}
                    className={`flex items-center gap-2 rounded-lg border px-3 py-2 text-sm transition ${
                      form.crop === c.key ? 'border-brand-500 bg-brand-50 font-semibold text-brand-700' : 'border-stone-200 hover:bg-stone-50'
                    }`}
                  >
                    <span aria-hidden>{CROP_EMOJI[c.key]}</span> {c.label}
                  </button>
                ))}
              </div>
            </div>
            <div>
              <label className={label}>Planting date</label>
              <input className={input} type="date" required max={daysAgo(0)} value={form.planting_date} onChange={(e) => set('planting_date', e.target.value)} />
            </div>
            <div>
              <label className={label}>Area (ha, optional)</label>
              <input className={input} type="number" step="0.1" min="0.05" value={form.area_ha ?? ''} onChange={(e) => set('area_ha', e.target.value ? Number(e.target.value) : null)} />
            </div>
          </div>
        </Card>

        <Card title="Location (click the map or type)">
          <div className="h-64 overflow-hidden rounded-xl ring-1 ring-stone-200 sm:h-72">
            <MapContainer center={JUJA} zoom={13} scrollWheelZoom>
              <TileLayer attribution='&copy; <a href="https://osm.org/copyright">OpenStreetMap</a>' url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png" />
              <ClickToPlace onPick={(lat, lon) => setForm((f) => ({ ...f, lat: +lat.toFixed(5), lon: +lon.toFixed(5) }))} />
              <Marker position={[form.lat, form.lon]} />
            </MapContainer>
          </div>
          <div className="mt-3 grid grid-cols-2 gap-3">
            <div>
              <label className={label}>Latitude</label>
              <input className={input} type="number" step="0.00001" value={form.lat} onChange={(e) => set('lat', Number(e.target.value))} />
            </div>
            <div>
              <label className={label}>Longitude</label>
              <input className={input} type="number" step="0.00001" value={form.lon} onChange={(e) => set('lon', Number(e.target.value))} />
            </div>
          </div>
          <p className="mt-2 text-xs text-stone-500">Default is the JKUAT Conduit weather station in Juja.</p>
          {error && <p className="mt-3 rounded-lg bg-red-50 p-2 text-sm text-red-700">{error}</p>}
          <Button type="submit" className="mt-4 w-full" disabled={busy}>
            {busy && <Spinner />} Register & assess risk
          </Button>
        </Card>
      </form>
    </div>
  )
}
