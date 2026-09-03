import type { Risk } from '../api/types'
import { useAnimatedNumber } from '../hooks/useAnimatedNumber'
import { HEALTH_DOT, LEVEL_DOT } from './ui'

const ROWS: { key: keyof Risk['sub_scores']; label: string }[] = [
  { key: 'drought', label: 'Drought Risk' },
  { key: 'flood', label: 'Flood Risk' },
  { key: 'heat', label: 'Heat Stress' },
  { key: 'crop_health', label: 'Crop Health' },
]

const LEVEL_COLOR = { HIGH: 'text-red-400', MEDIUM: 'text-amber-300', LOW: 'text-emerald-400' } as const
const BAR_COLOR = { HIGH: 'bg-red-500', MEDIUM: 'bg-amber-400', LOW: 'bg-emerald-500' } as const

/** The hero: FARM RISK SCORE panel. */
export default function RiskPanel({ risk }: { risk: Risk }) {
  const score = useAnimatedNumber(risk.overall.score)

  return (
    <section className="relative overflow-hidden rounded-3xl bg-stone-900 p-6 text-stone-100 shadow-xl ring-1 ring-black/20 sm:p-8">
      <div
        className={`pointer-events-none absolute -right-24 -top-24 h-72 w-72 rounded-full blur-3xl transition-colors duration-700 ${
          risk.overall.level === 'HIGH' ? 'bg-red-600/30' : risk.overall.level === 'MEDIUM' ? 'bg-amber-500/25' : 'bg-emerald-500/25'
        }`}
      />
      <h2 className="relative text-xs font-bold uppercase tracking-[0.25em] text-stone-400">Farm Risk Score</h2>

      <div className="relative mt-5 grid gap-8 md:grid-cols-[1fr_auto] md:items-center">
        <ul className="space-y-3 font-mono text-[15px] sm:text-base">
          {ROWS.map(({ key, label }) => {
            const s = risk.sub_scores[key]
            const dot = key === 'crop_health' && s.label ? HEALTH_DOT[s.label] : LEVEL_DOT[s.level]
            const text = key === 'crop_health' && s.label ? s.label : s.level
            return (
              <li key={key} className="grid grid-cols-[9rem_1fr_auto] items-center gap-3 sm:grid-cols-[10rem_1fr_auto]">
                <span className="text-stone-300">{label}</span>
                <span className="h-1.5 overflow-hidden rounded-full bg-stone-700/70">
                  <span
                    className={`block h-full rounded-full transition-all duration-700 ${BAR_COLOR[s.level]}`}
                    style={{ width: `${Math.max(3, s.score)}%` }}
                  />
                </span>
                <span className={`flex items-center gap-2 font-bold ${LEVEL_COLOR[s.level]}`}>
                  <span aria-hidden>{dot}</span>
                  {text}
                  <span className="w-8 text-right text-xs font-normal text-stone-500">{s.score}</span>
                </span>
              </li>
            )
          })}
        </ul>

        {/* keyed on assessment id so a new assessment re-mounts and replays the pulse */}
        <div key={risk.assessment_id} className="animate-pulse-once text-center md:text-right">
          <div className="text-xs font-semibold uppercase tracking-widest text-stone-400">Overall</div>
          <div className="mt-1 flex items-baseline justify-center gap-1 md:justify-end">
            <span className={`text-6xl font-black tabular-nums tracking-tight sm:text-7xl ${LEVEL_COLOR[risk.overall.level]}`}>{score}</span>
            <span className="text-2xl font-semibold text-stone-500">/ 100</span>
          </div>
          <div className={`mt-2 text-lg font-bold tracking-wide sm:text-xl ${LEVEL_COLOR[risk.overall.level]}`}>
            {LEVEL_DOT[risk.overall.level]} {risk.overall.label}
          </div>
          <div className="mt-3 text-xs text-stone-400">
            {risk.crop} · {risk.stage.name.replace(/_/g, ' ')} · day {risk.stage.day_after_planting}
            {risk.stage.is_critical && <span className="ml-2 rounded bg-red-500/20 px-1.5 py-0.5 text-red-300">critical stage</span>}
          </div>
        </div>
      </div>

      <div className="relative mt-6 flex flex-wrap items-center gap-x-4 gap-y-1 border-t border-stone-800 pt-4 text-xs text-stone-400">
        <span>
          Insurance trigger:{' '}
          {risk.insurance_trigger.triggered ? (
            <span className="font-semibold text-red-300">TRIGGERED</span>
          ) : (
            <span className="font-semibold text-emerald-300">not met</span>
          )}{' '}
          <span className="text-stone-500">({risk.insurance_trigger.rule.replace(/_/g, ' ')})</span>
        </span>
        <span>Data: {risk.data_sources.join(', ')}</span>
        <span>{risk.readings_used} daily readings</span>
        <span className="ml-auto">{new Date(risk.assessed_at).toLocaleString('en-KE')}</span>
      </div>
    </section>
  )
}
