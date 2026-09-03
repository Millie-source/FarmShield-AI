import { Bar, BarChart, CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import type { WeatherReading } from '../api/types'
import { Card, fmtDate } from './ui'

const RAIN = '#2a78d6'
const TMAX = '#eb6834'
const TMIN = '#eda100'
const GRID = '#ecebe4'
const INK = '#6f6e66'

/** 30-day rainfall (bars) and temperature (lines) as two stacked single-axis charts. */
export default function WeatherChart({ readings, source }: { readings: WeatherReading[]; source: string }) {
  const data = readings.map((r) => ({ ...r, day: fmtDate(r.date) }))
  const totalRain = Math.round(readings.reduce((a, r) => a + r.rainfall_mm, 0))
  const last7 = Math.round(readings.slice(-7).reduce((a, r) => a + r.rainfall_mm, 0))
  return (
    <Card
      title="Last 30 days of weather"
      action={
        <span className="text-xs text-stone-500">
          {totalRain} mm total · {last7} mm last 7 days · {source}
        </span>
      }
    >
      <div className="text-xs font-semibold text-stone-500">Rainfall (mm/day)</div>
      <div className="h-40">
        <ResponsiveContainer>
          <BarChart data={data} margin={{ top: 8, right: 8, left: -18, bottom: 0 }}>
            <CartesianGrid vertical={false} stroke={GRID} />
            <XAxis dataKey="day" tick={{ fontSize: 10, fill: INK }} tickLine={false} axisLine={{ stroke: GRID }} interval={4} />
            <YAxis tick={{ fontSize: 10, fill: INK }} tickLine={false} axisLine={false} />
            <Tooltip cursor={{ fill: '#f5f5f4' }} formatter={(v) => [`${v} mm`, 'Rain']} contentStyle={{ fontSize: 12, borderRadius: 8 }} />
            <Bar dataKey="rainfall_mm" fill={RAIN} radius={[3, 3, 0, 0]} maxBarSize={14} isAnimationActive={false} />
          </BarChart>
        </ResponsiveContainer>
      </div>
      <div className="mt-3 text-xs font-semibold text-stone-500">Temperature (°C) — max and min</div>
      <div className="h-40">
        <ResponsiveContainer>
          <LineChart data={data} margin={{ top: 8, right: 8, left: -18, bottom: 0 }}>
            <CartesianGrid vertical={false} stroke={GRID} />
            <XAxis dataKey="day" tick={{ fontSize: 10, fill: INK }} tickLine={false} axisLine={{ stroke: GRID }} interval={4} />
            <YAxis domain={[10, 36]} tick={{ fontSize: 10, fill: INK }} tickLine={false} axisLine={false} />
            <Tooltip contentStyle={{ fontSize: 12, borderRadius: 8 }} formatter={(v, name) => [`${v} °C`, name === 'temp_max_c' ? 'Max' : 'Min']} />
            <Line type="monotone" dataKey="temp_max_c" stroke={TMAX} strokeWidth={2} dot={false} name="temp_max_c" isAnimationActive={false} />
            <Line type="monotone" dataKey="temp_min_c" stroke={TMIN} strokeWidth={2} dot={false} name="temp_min_c" isAnimationActive={false} />
          </LineChart>
        </ResponsiveContainer>
      </div>
      <div className="mt-2 flex gap-4 text-xs text-stone-500">
        <span className="flex items-center gap-1"><i className="inline-block h-2 w-3 rounded-sm" style={{ background: RAIN }} /> Rainfall</span>
        <span className="flex items-center gap-1"><i className="inline-block h-0.5 w-3" style={{ background: TMAX }} /> Max temp</span>
        <span className="flex items-center gap-1"><i className="inline-block h-0.5 w-3" style={{ background: TMIN }} /> Min temp</span>
        <span className="ml-auto">Soil moisture today: {readings.at(-1)?.soil_moisture_pct ?? '–'}%</span>
      </div>
    </Card>
  )
}
