/* eslint-disable react-refresh/only-export-components */
import type { ReactNode } from 'react'
import type { HealthLabel, Level } from '../api/types'

export const LEVEL_DOT: Record<Level, string> = { HIGH: '🔴', MEDIUM: '🟡', LOW: '🟢' }
export const HEALTH_DOT: Record<HealthLabel, string> = { POOR: '🔴', FAIR: '🟡', GOOD: '🟢' }
export const LEVEL_TEXT: Record<Level, string> = { HIGH: 'text-risk-high', MEDIUM: 'text-amber-600', LOW: 'text-risk-low' }
export const LEVEL_BG: Record<Level, string> = {
  HIGH: 'bg-red-50 text-red-700 ring-red-200',
  MEDIUM: 'bg-amber-50 text-amber-700 ring-amber-200',
  LOW: 'bg-emerald-50 text-emerald-700 ring-emerald-200',
}
export const LEVEL_SOLID: Record<Level, string> = { HIGH: 'bg-risk-high', MEDIUM: 'bg-risk-medium', LOW: 'bg-risk-low' }
export const CROP_EMOJI: Record<string, string> = { maize: '🌽', beans: '🫘', potatoes: '🥔', tomatoes: '🍅', kale: '🥬' }

export const prettyStage = (s: string) => s.replace(/_/g, ' ')
export const fmtDate = (iso: string) => new Date(iso).toLocaleDateString('en-KE', { day: 'numeric', month: 'short' })
export const fmtDateTime = (iso: string) =>
  new Date(iso).toLocaleString('en-KE', { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' })

export function LevelPill({ level, children }: { level: Level; children?: ReactNode }) {
  return (
    <span className={`inline-flex items-center gap-1 rounded-full px-2.5 py-0.5 text-xs font-semibold ring-1 ${LEVEL_BG[level]}`}>
      {LEVEL_DOT[level]} {children ?? level}
    </span>
  )
}

export function Card({ title, action, children, className = '' }: { title?: ReactNode; action?: ReactNode; children: ReactNode; className?: string }) {
  return (
    <section className={`rounded-2xl border border-stone-200 bg-white p-5 shadow-sm ${className}`}>
      {(title || action) && (
        <header className="mb-4 flex items-center justify-between gap-3">
          {title && <h2 className="text-sm font-semibold uppercase tracking-wider text-stone-500">{title}</h2>}
          {action}
        </header>
      )}
      {children}
    </section>
  )
}

export function Button({
  children,
  variant = 'primary',
  className = '',
  ...props
}: React.ButtonHTMLAttributes<HTMLButtonElement> & { variant?: 'primary' | 'ghost' | 'danger' }) {
  const styles = {
    primary: 'bg-brand-600 text-white hover:bg-brand-700 disabled:bg-stone-300',
    ghost: 'bg-white text-stone-700 ring-1 ring-stone-200 hover:bg-stone-50 disabled:text-stone-400',
    danger: 'bg-red-600 text-white hover:bg-red-700 disabled:bg-stone-300',
  }[variant]
  return (
    <button
      className={`inline-flex items-center justify-center gap-2 rounded-lg px-3.5 py-2 text-sm font-medium transition disabled:cursor-not-allowed ${styles} ${className}`}
      {...props}
    >
      {children}
    </button>
  )
}

export function Skeleton({ className = '' }: { className?: string }) {
  return <div className={`animate-pulse rounded-lg bg-stone-200 ${className}`} />
}

export function ErrorBox({ error, retry }: { error: unknown; retry?: () => void }) {
  const msg = error instanceof Error ? error.message : String(error)
  return (
    <div className="rounded-xl border border-red-200 bg-red-50 p-4 text-sm text-red-800">
      <p className="font-semibold">Something went wrong</p>
      <p className="mt-1 break-words">{msg}</p>
      {retry && (
        <Button variant="ghost" className="mt-3" onClick={retry}>
          Retry
        </Button>
      )}
    </div>
  )
}

export function Spinner({ className = '' }: { className?: string }) {
  return (
    <svg className={`h-4 w-4 animate-spin ${className}`} viewBox="0 0 24 24" fill="none" aria-hidden>
      <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
      <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v4a4 4 0 00-4 4H4z" />
    </svg>
  )
}

export function Toast({ message, kind = 'info' }: { message: string; kind?: 'info' | 'success' | 'error' }) {
  const color = { info: 'bg-stone-900', success: 'bg-emerald-700', error: 'bg-red-700' }[kind]
  return (
    <div className={`fixed bottom-5 left-1/2 z-50 -translate-x-1/2 rounded-full px-4 py-2 text-sm text-white shadow-lg ${color}`} role="status">
      {message}
    </div>
  )
}
