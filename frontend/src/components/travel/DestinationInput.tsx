import { useEffect, useRef, useState } from 'react'
import { MapPin, Loader2 } from 'lucide-react'

// ── Destination combobox ──────────────────────────────────────────────────
// Cities are fetched live from the Open-Meteo geocoding API (free, no key —
// the same service used by useWeather.ts), so every city worldwide is
// searchable without bundling a hardcoded list.

interface GeoHit {
  id: number
  name: string
  admin1?: string
  country?: string
}

function formatHit(h: GeoHit): string {
  return [h.name, h.admin1, h.country].filter(Boolean).join(', ')
}

export function DestinationInput({ value, onChange }: { value: string; onChange: (v: string) => void }) {
  const [open, setOpen] = useState(false)
  const [query, setQuery] = useState(value)
  const [matches, setMatches] = useState<GeoHit[]>([])
  const [loading, setLoading] = useState(false)
  const wrapRef = useRef<HTMLDivElement>(null)
  const justPickedRef = useRef(false)

  // Debounced live search against Open-Meteo geocoding.
  useEffect(() => {
    const q = query.trim()
    if (justPickedRef.current) { justPickedRef.current = false; return }
    if (q.length < 2) { setMatches([]); setLoading(false); return }

    const ctrl = new AbortController()
    const t = setTimeout(async () => {
      setLoading(true)
      try {
        const url = new URL('https://geocoding-api.open-meteo.com/v1/search')
        url.searchParams.set('name', q)
        url.searchParams.set('count', '8')
        url.searchParams.set('language', 'en')
        url.searchParams.set('format', 'json')
        const r = await fetch(url, { signal: ctrl.signal })
        const j = await r.json()
        setMatches(Array.isArray(j?.results) ? j.results : [])
      } catch {
        // Network/abort errors leave the previous matches untouched.
      } finally {
        setLoading(false)
      }
    }, 250)

    return () => { clearTimeout(t); ctrl.abort() }
  }, [query])

  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (wrapRef.current && !wrapRef.current.contains(e.target as Node)) setOpen(false)
    }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [])

  const pick = (label: string) => {
    justPickedRef.current = true
    setQuery(label)
    onChange(label)
    setMatches([])
    setOpen(false)
  }

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
          className="w-full pl-9 pr-9 py-2.5 rounded-xl border border-slate-300 dark:border-white/10 bg-white dark:bg-slate-900 text-slate-900 dark:text-white text-sm focus:outline-none focus:ring-2 focus:ring-brand-500"
        />
        {loading && (
          <Loader2 size={14} className="absolute right-3 top-1/2 -translate-y-1/2 text-slate-400 animate-spin" />
        )}
      </div>
      {open && matches.length > 0 && (
        <ul className="absolute z-50 mt-1 w-full bg-white dark:bg-slate-800 border border-slate-200 dark:border-white/10 rounded-xl shadow-lg overflow-hidden max-h-56 overflow-y-auto">
          {matches.map(hit => {
            const label = formatHit(hit)
            return (
              <li
                key={hit.id}
                onMouseDown={() => pick(label)}
                className="flex items-center gap-2 px-3 py-2 text-sm cursor-pointer text-slate-800 dark:text-white hover:bg-brand-50 dark:hover:bg-brand-500/10"
              >
                <MapPin size={11} className="text-slate-400 flex-shrink-0" />
                {label}
              </li>
            )
          })}
        </ul>
      )}
    </div>
  )
}
