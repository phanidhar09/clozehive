import { useEffect, useRef, useState } from 'react'
import { MapPin } from 'lucide-react'
import { DESTINATIONS } from './constants'

// ── Destination combobox ──────────────────────────────────────────────────

export function DestinationInput({ value, onChange }: { value: string; onChange: (v: string) => void }) {
  const [open, setOpen] = useState(false)
  const [query, setQuery] = useState(value)
  const wrapRef = useRef<HTMLDivElement>(null)

  const matches = query.length >= 1
    ? DESTINATIONS.filter(d => d.toLowerCase().includes(query.toLowerCase())).slice(0, 8)
    : []

  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (wrapRef.current && !wrapRef.current.contains(e.target as Node)) setOpen(false)
    }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [])

  return (
    <div ref={wrapRef} className="relative">
      <label className="block text-xs font-semibold text-slate-700 dark:text-white/80 mb-1.5 uppercase tracking-wider">
        Destination *
      </label>
      <div className="relative">
        <MapPin size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400 pointer-events-none" />
        <input
          type="text"
          value={query}
          placeholder="e.g. Miami, Paris, Bali…"
          onChange={e => { setQuery(e.target.value); onChange(e.target.value); setOpen(true) }}
          onFocus={() => setOpen(true)}
          className="w-full pl-9 pr-3 py-2.5 rounded-xl border border-slate-300 dark:border-white/10 bg-white dark:bg-slate-900 text-slate-900 dark:text-white text-sm focus:outline-none focus:ring-2 focus:ring-brand-500"
        />
      </div>
      {open && matches.length > 0 && (
        <ul className="absolute z-50 mt-1 w-full bg-white dark:bg-slate-800 border border-slate-200 dark:border-white/10 rounded-xl shadow-lg overflow-hidden max-h-56 overflow-y-auto">
          {matches.map(dest => (
            <li
              key={dest}
              onMouseDown={() => { setQuery(dest); onChange(dest); setOpen(false) }}
              className="flex items-center gap-2 px-3 py-2 text-sm cursor-pointer text-slate-800 dark:text-white hover:bg-brand-50 dark:hover:bg-brand-500/10"
            >
              <MapPin size={11} className="text-slate-400 flex-shrink-0" />
              {dest}
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
