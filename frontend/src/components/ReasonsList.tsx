import type { Risk } from '../api/types'
import { Card, LEVEL_DOT, HEALTH_DOT } from './ui'

const GROUPS: { key: keyof Risk['sub_scores']; label: string }[] = [
  { key: 'drought', label: 'Drought' },
  { key: 'flood', label: 'Flood' },
  { key: 'heat', label: 'Heat stress' },
  { key: 'crop_health', label: 'Crop health' },
]

export default function ReasonsList({ risk }: { risk: Risk }) {
  return (
    <Card title="Why this score">
      <div className="grid gap-4 sm:grid-cols-2">
        {GROUPS.map(({ key, label }) => {
          const s = risk.sub_scores[key]
          const dot = key === 'crop_health' && s.label ? HEALTH_DOT[s.label] : LEVEL_DOT[s.level]
          return (
            <div key={key} className="rounded-xl bg-stone-50 p-3 ring-1 ring-stone-100">
              <div className="mb-1.5 flex items-center justify-between text-sm font-semibold">
                <span>
                  {dot} {label}
                </span>
                <span className="text-stone-500">{s.score}/100</span>
              </div>
              <ul className="space-y-1 text-sm text-stone-700">
                {s.reasons.map((r, i) => (
                  <li key={i} className="flex gap-2">
                    <span className="text-stone-400">•</span>
                    <span>{r}</span>
                  </li>
                ))}
              </ul>
            </div>
          )
        })}
      </div>
      <p className="mt-3 text-xs text-stone-400">
        Overall weights at this stage:{' '}
        {Object.entries(risk.overall.weights)
          .map(([k, v]) => `${k.replace('_', ' ')} ${Math.round(v * 100)}%`)
          .join(' · ')}
        . Overall never drops below 85% of the worst hazard.
      </p>
    </Card>
  )
}
