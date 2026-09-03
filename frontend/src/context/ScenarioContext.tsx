/* eslint-disable react-refresh/only-export-components */
import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from 'react'
import { api } from '../api/client'
import type { Scenario } from '../api/types'

interface ScenarioCtx {
  scenario: Scenario
  provider: string
  switching: boolean
  /** Bumps every time the scenario changes so pages can refetch. */
  version: number
  setScenario: (s: Scenario) => Promise<void>
  bump: () => void
  apiOnline: boolean
}

const Ctx = createContext<ScenarioCtx | null>(null)

export function ScenarioProvider({ children }: { children: ReactNode }) {
  const [scenario, setLocal] = useState<Scenario>('normal')
  const [provider, setProvider] = useState('mock')
  const [switching, setSwitching] = useState(false)
  const [version, setVersion] = useState(0)
  const [apiOnline, setApiOnline] = useState(true)

  useEffect(() => {
    api.scenario
      .get()
      .then((s) => {
        setLocal(s.scenario)
        setProvider(s.provider)
        setApiOnline(true)
      })
      .catch(() => setApiOnline(false))
  }, [])

  const setScenario = useCallback(async (s: Scenario) => {
    setSwitching(true)
    try {
      const r = await api.scenario.set(s, true)
      setLocal(r.scenario)
      setVersion((v) => v + 1)
      setApiOnline(true)
    } catch {
      setApiOnline(false)
    } finally {
      setSwitching(false)
    }
  }, [])

  const bump = useCallback(() => setVersion((v) => v + 1), [])

  const value = useMemo(
    () => ({ scenario, provider, switching, version, setScenario, bump, apiOnline }),
    [scenario, provider, switching, version, setScenario, bump, apiOnline],
  )
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>
}

export function useScenario(): ScenarioCtx {
  const v = useContext(Ctx)
  if (!v) throw new Error('useScenario must be used inside ScenarioProvider')
  return v
}
