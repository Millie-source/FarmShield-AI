import { useEffect, useRef, useState } from 'react'

/** Eases a displayed number from its previous value to `target` (for the live scenario flip). */
export function useAnimatedNumber(target: number, durationMs = 700): number {
  const [value, setValue] = useState(target)
  const fromRef = useRef(target)
  const frame = useRef<number | null>(null)

  useEffect(() => {
    const from = fromRef.current
    if (from === target) return
    const start = performance.now()
    const tick = (now: number) => {
      const t = Math.min(1, (now - start) / durationMs)
      const eased = 1 - Math.pow(1 - t, 3)
      const v = Math.round(from + (target - from) * eased)
      setValue(v)
      if (t < 1) frame.current = requestAnimationFrame(tick)
      else fromRef.current = target
    }
    frame.current = requestAnimationFrame(tick)
    return () => {
      if (frame.current) cancelAnimationFrame(frame.current)
      fromRef.current = target
    }
  }, [target, durationMs])

  return value
}
