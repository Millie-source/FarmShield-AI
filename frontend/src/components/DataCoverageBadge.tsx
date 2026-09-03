import type { DataCoverage } from '../api/types'

const plural = (n: number, w: string) => `${n} ${w}${n === 1 ? '' : 's'}`

/** "5 real days · 25 modelled days · JKUAT station" - how much of the scoring window is measured. */
export default function DataCoverageBadge({ coverage, sources, className = '' }: { coverage: DataCoverage | null | undefined; sources?: string[]; className?: string }) {
  if (!coverage) return null
  const allReal = coverage.synthetic_days === 0
  const tone = allReal ? 'border-emerald-200 bg-emerald-50 text-emerald-800' : coverage.real_days > 0 ? 'border-sky-200 bg-sky-50 text-sky-800' : 'border-stone-200 bg-stone-50 text-stone-600'
  const title = [
    coverage.station,
    coverage.from && coverage.to ? `${coverage.from} → ${coverage.to}` : null,
    sources?.length ? `sources: ${sources.join(', ')}` : null,
  ]
    .filter(Boolean)
    .join('\n')
  return (
    <span title={title} className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-0.5 text-xs font-medium ${tone} ${className}`}>
      <span aria-hidden>📡</span>
      {plural(coverage.real_days, 'real day')} · {plural(coverage.synthetic_days, 'modelled day')} · JKUAT station
    </span>
  )
}
