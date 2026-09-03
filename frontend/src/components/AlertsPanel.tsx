import { useCallback, useEffect, useState } from 'react'
import { api, ApiError } from '../api/client'
import type { Alert, AlertPreview } from '../api/types'
import { Button, Card, fmtDateTime, Spinner } from './ui'

export default function AlertsPanel({ farmId, language, onSent }: { farmId: number; language: 'en' | 'sw'; onSent?: (msg: string) => void }) {
  const [lang, setLang] = useState<'en' | 'sw'>(language)
  const [preview, setPreview] = useState<AlertPreview | null>(null)
  const [alerts, setAlerts] = useState<Alert[]>([])
  const [busy, setBusy] = useState<'preview' | 'send' | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [unsupported, setUnsupported] = useState(false)

  const load = useCallback(() => {
    api.alerts
      .list(farmId)
      .then((a) => {
        setAlerts(a)
        setUnsupported(false)
      })
      .catch((e) => {
        if (e instanceof ApiError && (e.status === 404 || e.status === 405)) setUnsupported(true)
      })
  }, [farmId])

  useEffect(load, [load])

  const doPreview = async () => {
    setBusy('preview')
    setError(null)
    try {
      setPreview(await api.alerts.preview(farmId, lang))
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setBusy(null)
    }
  }

  const doSend = async () => {
    setBusy('send')
    setError(null)
    try {
      const a = await api.alerts.send(farmId, lang, true)
      onSent?.(`SMS ${a.status} via ${a.provider} to ${a.recipient}`)
      setPreview(null)
      load()
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setBusy(null)
    }
  }

  if (unsupported) {
    return (
      <Card title="SMS alerts">
        <p className="text-sm text-stone-500">Alert endpoints are not available on this backend build yet.</p>
      </Card>
    )
  }

  return (
    <Card
      title="SMS alerts"
      action={
        <div className="flex items-center gap-2">
          <select
            value={lang}
            onChange={(e) => setLang(e.target.value as 'en' | 'sw')}
            className="rounded-lg border border-stone-200 bg-white px-2 py-1 text-xs"
            aria-label="SMS language"
          >
            <option value="en">English</option>
            <option value="sw">Kiswahili</option>
          </select>
          <Button variant="ghost" onClick={doPreview} disabled={busy !== null}>
            {busy === 'preview' && <Spinner />} Preview message
          </Button>
          <Button onClick={doSend} disabled={busy !== null}>
            {busy === 'send' && <Spinner />} Send SMS alert
          </Button>
        </div>
      }
    >
      {error && <p className="mb-3 text-sm text-red-700">{error}</p>}
      {preview && (
        <div className="mb-4 rounded-2xl bg-stone-900 p-4 text-stone-100">
          <div className="mb-2 flex items-center justify-between text-xs text-stone-400">
            <span>To {preview.recipient} · via {preview.sender}</span>
            <span className={preview.chars > 160 ? 'text-amber-300' : ''}>{preview.chars}/160 chars</span>
          </div>
          <p className="font-mono text-sm leading-relaxed">{preview.message}</p>
          <p className="mt-2 text-xs text-stone-400">
            {preview.would_send ? '✅ Alert policy would send this automatically' : '⏸ Alert policy would hold this'}: {preview.reason}
          </p>
        </div>
      )}
      {alerts.length === 0 ? (
        <p className="text-sm text-stone-500">No alerts sent yet for this farm.</p>
      ) : (
        <ul className="divide-y divide-stone-100">
          {alerts.map((a) => (
            <li key={a.id} className="flex flex-col gap-1 py-2.5 text-sm sm:flex-row sm:items-start sm:gap-4">
              <span className="w-36 shrink-0 text-xs text-stone-500">{fmtDateTime(a.created_at)}</span>
              <span className="flex-1 font-mono text-[13px] text-stone-800">{a.message}</span>
              <span
                className={`shrink-0 rounded-full px-2 py-0.5 text-xs font-semibold ${
                  a.status === 'sent' ? 'bg-emerald-50 text-emerald-700' : a.status === 'failed' ? 'bg-red-50 text-red-700' : 'bg-stone-100 text-stone-600'
                }`}
              >
                {a.status} · {a.provider}
              </span>
            </li>
          ))}
        </ul>
      )}
    </Card>
  )
}
