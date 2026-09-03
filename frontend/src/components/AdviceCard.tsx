import { useState } from 'react'
import type { Advice } from '../api/types'
import { Card } from './ui'

export default function AdviceCard({ advice, defaultLang = 'en' }: { advice: Advice; defaultLang?: 'en' | 'sw' }) {
  const [lang, setLang] = useState<'en' | 'sw'>(defaultLang)
  return (
    <Card
      title={lang === 'en' ? 'What to do now' : 'Cha kufanya sasa'}
      action={
        <div className="flex rounded-full bg-stone-100 p-0.5 text-xs font-semibold ring-1 ring-stone-200">
          {(['en', 'sw'] as const).map((l) => (
            <button
              key={l}
              onClick={() => setLang(l)}
              className={`rounded-full px-3 py-1 transition ${lang === l ? 'bg-brand-600 text-white shadow' : 'text-stone-600 hover:text-stone-900'}`}
            >
              {l === 'en' ? 'English' : 'Kiswahili'}
            </button>
          ))}
        </div>
      }
    >
      <p className="text-[15px] leading-relaxed text-stone-800">{lang === 'en' ? advice.en : advice.sw}</p>
      <p className="mt-3 text-xs text-stone-400">
        {advice.source === 'gemini' ? '✨ Written by Gemini from the rule-based assessment' : '📋 Rule-based advice (Gemini unavailable or not configured)'}
      </p>
    </Card>
  )
}
