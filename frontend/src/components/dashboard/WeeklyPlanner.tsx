import { useCallback, useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { CalendarDays, Loader2, MapPin, RefreshCw, Shirt } from 'lucide-react'
import GlassCard from '@/components/ui/GlassCard'
import { useApp } from '@/store'
import { generateOutfitOnce } from '@/lib/api'
import { fetchWeather, type WeatherData } from '@/hooks/useWeather'
import type { OutfitSuggestion } from '@/types'

interface DayPlan {
  date: string
  condition: string
  temp: number
  outfit?: OutfitSuggestion
  error?: string
}

function inferOccasion(dateStr: string): string {
  const day = new Date(dateStr).getDay()
  return day === 0 || day === 6 ? 'casual' : 'business casual'
}

export default function WeeklyPlanner() {
  const { currentUser, closetItems } = useApp()
  const permissions = currentUser?.permissions ?? null
  const coords = permissions?.location_coords ?? null

  const [weather, setWeather] = useState<WeatherData | null>(null)
  const [weatherErr, setWeatherErr] = useState<string | null>(null)
  const [plan, setPlan] = useState<DayPlan[]>([])
  const [planning, setPlanning] = useState(false)

  useEffect(() => {
    if (!coords) { setWeather(null); return }
    let cancelled = false
    setWeatherErr(null)
    fetchWeather(coords.lat, coords.lon)
      .then(d => { if (!cancelled) setWeather(d) })
      .catch(e => { if (!cancelled) setWeatherErr(e instanceof Error ? e.message : 'Weather unavailable') })
    return () => { cancelled = true }
  }, [coords])

  const generatePlan = useCallback(async () => {
    if (!weather) return
    setPlanning(true)
    setPlan([])
    const next: DayPlan[] = []
    for (const day of weather.daily.slice(0, 7)) {
      const occasion = inferOccasion(day.date)
      const temp = (day.temp_max + day.temp_min) / 2
      try {
        const result = await generateOutfitOnce({
          occasion,
          weather: day.condition,
          temperature: temp,
          user_profile: {
            body_profile:  currentUser?.body_profile ?? null,
            style_profile: currentUser?.style_profile ?? null,
            preferences:   currentUser?.preferences ?? null,
          },
        })
        next.push({ date: day.date, condition: day.condition, temp: Math.round(temp), outfit: result.outfits?.[0] })
      } catch (e) {
        next.push({ date: day.date, condition: day.condition, temp: Math.round(temp), error: e instanceof Error ? e.message : 'Generation failed' })
      }
      setPlan([...next])
    }
    setPlanning(false)
  }, [weather, currentUser?.body_profile, currentUser?.style_profile, currentUser?.preferences])

  // ── Empty / disabled states ──────────────────────────────────────────────
  if (!permissions?.location) {
    return (
      <GlassCard padding="lg" className="text-center text-slate-500 dark:text-white/60">
        <CalendarDays size={28} className="mx-auto mb-3 opacity-30" />
        <p className="font-semibold text-slate-700 dark:text-white/80">Plan your week</p>
        <p className="text-sm mt-1">
          Enable location in <Link to="/profile?tab=settings" className="underline text-indigo-600 dark:text-indigo-400">Profile → Settings</Link> to get a 7-day outfit plan based on local weather.
        </p>
      </GlassCard>
    )
  }

  if (closetItems.length === 0) {
    return (
      <GlassCard padding="lg" className="text-center text-slate-500 dark:text-white/60">
        <Shirt size={28} className="mx-auto mb-3 opacity-30" />
        <p className="font-semibold text-slate-700 dark:text-white/80">Add items to plan your week</p>
        <p className="text-sm mt-1">The planner only suggests outfits from your wardrobe.</p>
      </GlassCard>
    )
  }

  // ── Active planner ───────────────────────────────────────────────────────
  return (
    <GlassCard padding="md" className="space-y-4">
      <div className="flex items-start justify-between gap-3 flex-wrap">
        <div>
          <h3 className="font-semibold text-base text-slate-800 dark:text-white flex items-center gap-2">
            <CalendarDays size={16} className="text-indigo-500" /> Weekly planner
          </h3>
          <p className="text-xs text-slate-500 dark:text-white/50 mt-1">
            7-day outfit plan from local weather + your style + closet.
          </p>
          {permissions.location_label && (
            <p className="text-[11px] text-slate-400 dark:text-white/40 mt-0.5 flex items-center gap-1">
              <MapPin size={10} /> {permissions.location_label}
            </p>
          )}
        </div>
        <button onClick={generatePlan} disabled={!weather || planning} className="btn-primary text-xs gap-1.5">
          {planning ? <Loader2 size={12} className="animate-spin" /> : <RefreshCw size={12} />}
          {planning ? 'Planning…' : plan.length ? 'Regenerate' : 'Generate plan'}
        </button>
      </div>

      {weatherErr && <p className="text-xs text-red-500">Weather error: {weatherErr}</p>}
      {!weather && !weatherErr && <p className="text-sm text-slate-400 dark:text-white/40">Loading weather…</p>}

      {plan.length > 0 && (
        <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-3">
          {plan.map(d => (
            <div
              key={d.date}
              className="rounded-xl p-3 bg-cream-50 dark:bg-white/[0.03]
                         border border-cream-200 dark:border-white/[0.06]
                         hover:border-cream-300 dark:hover:border-white/[0.12] transition-colors"
            >
              <div className="flex items-center justify-between mb-1.5">
                <p className="text-sm font-semibold text-slate-800 dark:text-white">
                  {new Date(d.date).toLocaleDateString('en-US', { weekday: 'short', month: 'short', day: 'numeric' })}
                </p>
                <p className="text-xs text-slate-400 dark:text-white/40">{d.condition} · {d.temp}°C</p>
              </div>
              {d.outfit ? (
                <>
                  <p className="text-sm text-slate-700 dark:text-white/80">{d.outfit.name}</p>
                  <p className="text-[11px] text-slate-500 dark:text-white/50 mt-0.5 line-clamp-2">
                    {d.outfit.style_notes ?? d.outfit.explanation}
                  </p>
                </>
              ) : d.error ? (
                <p className="text-xs text-red-500">{d.error}</p>
              ) : (
                <p className="text-xs text-slate-400 dark:text-white/40">No outfit returned.</p>
              )}
            </div>
          ))}
        </div>
      )}
    </GlassCard>
  )
}
