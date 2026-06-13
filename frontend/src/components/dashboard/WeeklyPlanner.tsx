import { useCallback, useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import {
  CalendarDays,
  Check,
  CloudRain,
  Loader2,
  MapPin,
  RefreshCw,
  Shirt,
  Sparkles,
  Sun,
  Trash2,
} from 'lucide-react'
import GlassCard from '@/components/ui/GlassCard'
import { useApp } from '@/store'
import { plannerApi, type PlannerForecastDay } from '@/lib/api'
import { fetchWeather } from '@/hooks/useWeather'
import type { PlannedDay } from '@/types'

function todayISO(): string {
  return new Date().toISOString().slice(0, 10)
}

function isToday(dateStr: string): boolean {
  return dateStr === todayISO()
}

function dayLabel(dateStr: string): string {
  return new Date(`${dateStr}T12:00:00`).toLocaleDateString('en-US', {
    weekday: 'short', month: 'short', day: 'numeric',
  })
}

function WeatherChip({ day }: { day: PlannedDay }) {
  if (!day.weather_condition) return null
  const rainy = /rain|shower|drizzle|storm|snow/i.test(day.weather_condition)
  const Icon = rainy ? CloudRain : Sun
  const temps = day.temp_high != null
    ? ` ${Math.round(day.temp_high)}°${day.temp_low != null ? `/${Math.round(day.temp_low)}°` : ''}`
    : ''
  return (
    <span className="inline-flex items-center gap-1 text-[11px] text-slate-400 dark:text-white/40">
      <Icon size={11} /> {day.weather_condition}{temps}
    </span>
  )
}

export default function WeeklyPlanner() {
  const { currentUser, closetItems } = useApp()
  const permissions = currentUser?.permissions ?? null
  const coords = permissions?.location_coords ?? null

  const [days, setDays] = useState<PlannedDay[]>([])
  const [loading, setLoading] = useState(true)
  const [planning, setPlanning] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [busyDate, setBusyDate] = useState<string | null>(null)

  // Load the persisted week on mount.
  useEffect(() => {
    let cancelled = false
    plannerApi.getWeek()
      .then(week => { if (!cancelled) setDays(week.days) })
      .catch(() => { /* empty week is fine */ })
      .finally(() => { if (!cancelled) setLoading(false) })
    return () => { cancelled = true }
  }, [])

  const generatePlan = useCallback(async () => {
    setPlanning(true)
    setError(null)
    try {
      // Pass the local 7-day forecast when we have coords; otherwise the
      // server plans from the profile location (or by occasion alone).
      let forecast: PlannerForecastDay[] | undefined
      if (coords) {
        try {
          const wx = await fetchWeather(coords.lat, coords.lon)
          forecast = wx.daily.slice(0, 7).map(d => ({
            date: d.date,
            condition: d.condition,
            temp_high: d.temp_max,
            temp_low: d.temp_min,
          }))
        } catch { /* fall through to server-side weather */ }
      }
      const week = await plannerApi.generate({ start_date: todayISO(), days: forecast })
      setDays(week.days)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Plan generation failed')
    } finally {
      setPlanning(false)
    }
  }, [coords])

  const markWorn = useCallback(async (planDate: string) => {
    setBusyDate(planDate)
    try {
      const updated = await plannerApi.markWorn(planDate)
      setDays(prev => prev.map(d => (d.plan_date === planDate ? updated : d)))
    } catch { /* keep prior state */ } finally {
      setBusyDate(null)
    }
  }, [])

  const clearDay = useCallback(async (planDate: string) => {
    setBusyDate(planDate)
    try {
      await plannerApi.clearDay(planDate)
      setDays(prev => prev.filter(d => d.plan_date !== planDate))
    } catch { /* keep prior state */ } finally {
      setBusyDate(null)
    }
  }, [])

  if (closetItems.length === 0) {
    return (
      <GlassCard padding="lg" className="text-center text-slate-500 dark:text-white/60">
        <Shirt size={28} className="mx-auto mb-3 opacity-30" />
        <p className="font-semibold text-slate-700 dark:text-white/80">Add items to plan your week</p>
        <p className="text-sm mt-1">The planner only suggests outfits from your wardrobe.</p>
      </GlassCard>
    )
  }

  return (
    <GlassCard padding="md" className="space-y-4">
      <div className="flex items-start justify-between gap-3 flex-wrap">
        <div>
          <h3 className="font-semibold text-base text-slate-800 dark:text-white flex items-center gap-2">
            <CalendarDays size={16} className="text-brand-500" /> Weekly outfit calendar
          </h3>
          <p className="text-xs text-slate-500 dark:text-white/50 mt-1">
            FANI plans your week from the forecast, your style, and what you haven't worn lately.
          </p>
          {permissions?.location_label ? (
            <p className="text-[11px] text-slate-400 dark:text-white/40 mt-0.5 flex items-center gap-1">
              <MapPin size={10} /> {permissions.location_label}
            </p>
          ) : (
            <p className="text-[11px] text-slate-400 dark:text-white/40 mt-0.5">
              <Link to="/profile?tab=settings" className="underline">Enable location</Link> for weather-aware picks.
            </p>
          )}
        </div>
        <button onClick={generatePlan} disabled={planning} className="btn-primary text-xs gap-1.5">
          {planning ? <Loader2 size={12} className="animate-spin" /> : days.length ? <RefreshCw size={12} /> : <Sparkles size={12} />}
          {planning ? 'Planning…' : days.length ? 'Replan week' : 'Plan my week'}
        </button>
      </div>

      {error && <p className="text-xs text-red-500">{error}</p>}
      {loading && <p className="text-sm text-slate-400 dark:text-white/40">Loading your week…</p>}
      {!loading && days.length === 0 && !planning && (
        <p className="text-sm text-slate-400 dark:text-white/40">
          No plan yet — FANI can fill the next 7 days in one tap.
        </p>
      )}

      {days.length > 0 && (
        <div className="grid sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-3">
          {days.map(d => (
            <div
              key={d.plan_date}
              className={`rounded-xl p-3 border transition-colors
                          ${isToday(d.plan_date)
                            ? 'bg-brand-50 dark:bg-brand-500/[0.08] border-brand-200 dark:border-brand-400/30'
                            : 'bg-cream-50 dark:bg-white/[0.03] border-cream-200 dark:border-white/[0.06] hover:border-cream-300 dark:hover:border-white/[0.12]'}`}
            >
              <div className="flex items-center justify-between mb-1.5">
                <p className="text-sm font-semibold text-slate-800 dark:text-white">
                  {dayLabel(d.plan_date)}
                  {isToday(d.plan_date) && <span className="ml-1.5 text-[10px] font-bold text-brand-500">TODAY</span>}
                </p>
                <WeatherChip day={d} />
              </div>

              {d.items.length > 0 && (
                <div className="flex -space-x-2 mb-2">
                  {d.items.slice(0, 4).map(it => (
                    <div key={it.id}
                         title={it.name}
                         className="w-9 h-9 rounded-lg overflow-hidden border-2 border-white dark:border-slate-800 bg-slate-100 dark:bg-slate-700 flex items-center justify-center">
                      {it.image_url
                        ? <img src={it.image_url} alt={it.name} className="w-full h-full object-cover" />
                        : <span className="text-sm">👕</span>}
                    </div>
                  ))}
                  {d.items.length > 4 && (
                    <div className="w-9 h-9 rounded-lg border-2 border-white dark:border-slate-800 bg-slate-200 dark:bg-slate-600 flex items-center justify-center text-[10px] font-bold text-slate-600 dark:text-white/70">
                      +{d.items.length - 4}
                    </div>
                  )}
                </div>
              )}

              <p className="text-xs text-slate-600 dark:text-white/70 capitalize">{d.occasion}</p>
              {d.reasoning && (
                <p className="text-[11px] text-slate-500 dark:text-white/50 mt-0.5 line-clamp-2">{d.reasoning}</p>
              )}

              <div className="flex items-center gap-2 mt-2">
                {d.is_worn ? (
                  <span className="inline-flex items-center gap-1 text-[11px] font-semibold text-emerald-600 dark:text-emerald-400">
                    <Check size={11} /> Worn
                  </span>
                ) : (
                  <button
                    onClick={() => markWorn(d.plan_date)}
                    disabled={busyDate === d.plan_date || d.items.length === 0}
                    className="inline-flex items-center gap-1 text-[11px] font-medium text-brand-600 dark:text-brand-400 hover:underline disabled:opacity-40"
                  >
                    {busyDate === d.plan_date ? <Loader2 size={11} className="animate-spin" /> : <Check size={11} />}
                    Wore it
                  </button>
                )}
                <button
                  onClick={() => clearDay(d.plan_date)}
                  disabled={busyDate === d.plan_date}
                  className="inline-flex items-center gap-1 text-[11px] text-slate-400 dark:text-white/40 hover:text-red-500 disabled:opacity-40"
                >
                  <Trash2 size={11} /> Clear
                </button>
              </div>
            </div>
          ))}
        </div>
      )}
    </GlassCard>
  )
}
