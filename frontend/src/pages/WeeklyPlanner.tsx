import { useEffect, useMemo, useState } from 'react'
import {
  CalendarDays, Sparkles, Check, Trash2, Loader2, Cloud, Shirt, ChevronLeft, ChevronRight,
} from 'lucide-react'
import BackButton from '@/components/ui/BackButton'
import GlassCard from '@/components/ui/GlassCard'
import PageHeader from '@/components/ui/PageHeader'
import Badge from '@/components/ui/Badge'
import { FaniLoader } from '@/components/system/FaniLoader'
import { plannerApi } from '@/lib/api'
import { toastStore } from '@/store/notificationStore'
import type { PlannedDay } from '@/types'
import { cn } from '@/lib/utils'

// ── Date helpers (local time — never round-trip through UTC, which can shift the day) ──

function toISODate(d: Date): string {
  const y = d.getFullYear()
  const m = String(d.getMonth() + 1).padStart(2, '0')
  const day = String(d.getDate()).padStart(2, '0')
  return `${y}-${m}-${day}`
}

function parseISODate(s: string): Date {
  const [y, m, d] = s.split('-').map(Number)
  return new Date(y, m - 1, d)
}

function addDays(d: Date, n: number): Date {
  const next = new Date(d)
  next.setDate(next.getDate() + n)
  return next
}

const WEEKDAY = new Intl.DateTimeFormat(undefined, { weekday: 'short' })
const DAYNUM = new Intl.DateTimeFormat(undefined, { day: 'numeric', month: 'short' })
const RANGE_FMT = new Intl.DateTimeFormat(undefined, { day: 'numeric', month: 'short' })

const TODAY_ISO = toISODate(new Date())
const PLAN_DAYS = 7

function apiErr(err: unknown, fallback: string): string {
  const d = (err as { response?: { data?: { detail?: unknown; message?: string } } })?.response?.data
  if (typeof d?.detail === 'string') return d.detail
  if (d?.message) return d.message
  return err instanceof Error && err.message ? err.message : fallback
}

// ── Per-day card ───────────────────────────────────────────────────────────────

function DayCard({
  date,
  plan,
  busy,
  onMarkWorn,
  onClear,
}: {
  date: string
  plan: PlannedDay | undefined
  busy: boolean
  onMarkWorn: (date: string) => void
  onClear: (date: string) => void
}) {
  const d = parseISODate(date)
  const isToday = date === TODAY_ISO
  const isPast = date < TODAY_ISO
  const items = plan?.items ?? []
  const hasOutfit = items.length > 0
  const tempHigh = plan?.temp_high
  const tempLow = plan?.temp_low

  return (
    <GlassCard
      className={cn(
        'p-4 flex flex-col gap-3 transition-shadow',
        isToday && 'ring-2 ring-brand-400/50',
        isPast && !plan?.is_worn && 'opacity-70',
      )}
    >
      {/* Header: weekday + date + weather */}
      <div className="flex items-start justify-between gap-2">
        <div>
          <div className="flex items-center gap-2">
            <span className="font-semibold text-slate-800 dark:text-white">{WEEKDAY.format(d)}</span>
            {isToday && (
              <span className="text-[10px] font-bold uppercase tracking-wide text-brand-600 dark:text-brand-400">
                Today
              </span>
            )}
          </div>
          <span className="text-xs text-slate-400 dark:text-white/40">{DAYNUM.format(d)}</span>
        </div>
        {(plan?.weather_condition || tempHigh != null) && (
          <div className="flex items-center gap-1.5 text-xs text-slate-500 dark:text-white/50 shrink-0">
            <Cloud size={13} />
            <span className="capitalize">
              {plan?.weather_condition || '—'}
              {tempHigh != null && (
                <span className="ml-1 text-slate-400 dark:text-white/40">
                  {Math.round(tempHigh)}°{tempLow != null && `/${Math.round(tempLow)}°`}
                </span>
              )}
            </span>
          </div>
        )}
      </div>

      {/* Occasion + source */}
      {(plan?.occasion || plan?.source) && (
        <div className="flex items-center gap-2 flex-wrap">
          {plan?.occasion && (
            <Badge variant="gray" className="text-xs capitalize">{plan.occasion}</Badge>
          )}
          {plan?.source === 'fani' && (
            <span className="inline-flex items-center gap-1 text-[11px] font-medium text-brand-600 dark:text-brand-400">
              <Sparkles size={11} /> FANI pick
            </span>
          )}
          {plan?.source === 'manual' && (
            <span className="text-[11px] font-medium text-slate-400 dark:text-white/40">Manual</span>
          )}
        </div>
      )}

      {/* Outfit items or empty state */}
      {hasOutfit ? (
        <div className="flex flex-wrap gap-2">
          {items.map(item => (
            <div
              key={item.id}
              className="group relative h-16 w-16 rounded-xl overflow-hidden bg-slate-100 dark:bg-white/[0.06]
                         border border-cream-200 dark:border-white/[0.08]"
              title={`${item.name}${item.color ? ` · ${item.color}` : ''}`}
            >
              {item.image_url ? (
                <img src={item.image_url} alt={item.name} loading="lazy" decoding="async" className="h-full w-full object-cover" />
              ) : (
                <div className="h-full w-full flex items-center justify-center text-slate-300 dark:text-white/20">
                  <Shirt size={20} />
                </div>
              )}
            </div>
          ))}
        </div>
      ) : (
        <div className="flex flex-col items-center justify-center gap-1 py-6 text-center
                        rounded-xl border border-dashed border-cream-300 dark:border-white/[0.08]">
          <Shirt size={18} className="text-slate-300 dark:text-white/20" />
          <p className="text-xs text-slate-400 dark:text-white/40">No outfit planned</p>
        </div>
      )}

      {/* FANI reasoning */}
      {plan?.reasoning && (
        <p className="text-xs text-slate-500 dark:text-white/50 leading-relaxed line-clamp-3">
          {plan.reasoning}
        </p>
      )}

      {/* Actions */}
      {hasOutfit && (
        <div className="flex items-center justify-end gap-2 mt-auto pt-1">
          {plan?.is_worn ? (
            <span className="inline-flex items-center gap-1.5 text-xs font-medium text-emerald-600 dark:text-emerald-400">
              <Check size={13} /> Worn
            </span>
          ) : (
            <>
              <button
                onClick={() => onClear(date)}
                disabled={busy}
                aria-label="Clear day"
                className="flex items-center gap-1.5 text-xs font-medium px-2.5 py-1.5 rounded-lg
                           bg-slate-100 dark:bg-white/[0.06] text-slate-500 dark:text-white/50
                           hover:bg-red-50 dark:hover:bg-red-900/20 hover:text-red-500
                           transition-colors disabled:opacity-50"
              >
                <Trash2 size={12} /> Clear
              </button>
              <button
                onClick={() => onMarkWorn(date)}
                disabled={busy}
                className="flex items-center gap-1.5 text-xs font-medium px-2.5 py-1.5 rounded-lg
                           bg-emerald-50 dark:bg-emerald-900/20 text-emerald-700 dark:text-emerald-400
                           hover:bg-emerald-100 dark:hover:bg-emerald-900/40
                           transition-colors disabled:opacity-50"
              >
                {busy ? <Loader2 size={12} className="animate-spin" /> : <Check size={12} />}
                Mark worn
              </button>
            </>
          )}
        </div>
      )}
    </GlassCard>
  )
}

// ── Page ─────────────────────────────────────────────────────────────────────

export default function WeeklyPlanner() {
  const [startDate, setStartDate] = useState<string>(TODAY_ISO)
  const [days, setDays] = useState<PlannedDay[]>([])
  const [loading, setLoading] = useState(true)
  const [generating, setGenerating] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [busyDate, setBusyDate] = useState<string | null>(null)

  // The 7 calendar dates for the visible week (computed from startDate).
  const weekDates = useMemo(() => {
    const first = parseISODate(startDate)
    return Array.from({ length: PLAN_DAYS }, (_, i) => toISODate(addDays(first, i)))
  }, [startDate])

  const planByDate = useMemo(() => {
    const map: Record<string, PlannedDay> = {}
    for (const day of days) map[day.plan_date] = day
    return map
  }, [days])

  const hasAnyPlan = days.length > 0

  const load = async (start: string) => {
    setLoading(true)
    setError(null)
    try {
      const res = await plannerApi.getWeek(start)
      setDays(res.days)
    } catch (err) {
      setError(apiErr(err, 'Failed to load your weekly plan.'))
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    load(startDate)
  }, [startDate])

  const handleGenerate = async () => {
    setGenerating(true)
    setError(null)
    try {
      const res = await plannerApi.generate({ start_date: startDate })
      setDays(res.days)
      toastStore.add({
        variant: 'success',
        icon: '🗓️',
        title: 'Week planned',
        body: 'FANI built your outfits for the week.',
      })
    } catch (err) {
      const msg = apiErr(err, 'Could not generate your weekly plan.')
      setError(msg)
      toastStore.add({ variant: 'error', icon: '🗓️', title: 'Planning failed', body: msg })
    } finally {
      setGenerating(false)
    }
  }

  const handleMarkWorn = async (date: string) => {
    setBusyDate(date)
    try {
      const updated = await plannerApi.markWorn(date)
      setDays(prev => prev.map(d => (d.plan_date === date ? updated : d)))
      toastStore.add({ variant: 'success', icon: '👕', title: 'Logged', body: 'Marked as worn — wear counts updated.' })
    } catch (err) {
      toastStore.add({ variant: 'error', icon: '👕', title: 'Could not log', body: apiErr(err, 'Try again.') })
    } finally {
      setBusyDate(null)
    }
  }

  const handleClear = async (date: string) => {
    setBusyDate(date)
    try {
      await plannerApi.clearDay(date)
      setDays(prev => prev.filter(d => d.plan_date !== date))
    } catch (err) {
      toastStore.add({ variant: 'error', icon: '🗓️', title: 'Could not clear', body: apiErr(err, 'Try again.') })
    } finally {
      setBusyDate(null)
    }
  }

  const shiftWeek = (deltaWeeks: number) => {
    setStartDate(toISODate(addDays(parseISODate(startDate), deltaWeeks * PLAN_DAYS)))
  }

  const rangeLabel = `${RANGE_FMT.format(parseISODate(weekDates[0]))} – ${RANGE_FMT.format(parseISODate(weekDates[weekDates.length - 1]))}`

  return (
    <div className="max-w-5xl space-y-6">
      <BackButton fallback="/dashboard" label="Back to Dashboard" />

      <PageHeader
        icon={<CalendarDays size={18} />}
        chipClassName="bg-gradient-to-br from-brand-500 to-brand-600 shadow-glow-sm"
        iconColor="text-white"
        title="Weekly Planner"
        subtitle="Let FANI plan your outfits for the week — weather-aware and drawn from your closet"
        actions={
          <button
            onClick={handleGenerate}
            disabled={generating || loading}
            className="flex items-center gap-2 text-sm font-medium px-4 py-2 rounded-xl
                       bg-gradient-to-br from-brand-500 to-brand-600 text-white shadow-glow-sm
                       hover:from-brand-600 hover:to-brand-700 transition-colors disabled:opacity-60"
          >
            {generating ? <Loader2 size={15} className="animate-spin" /> : <Sparkles size={15} />}
            {hasAnyPlan ? 'Regenerate week' : 'Plan my week'}
          </button>
        }
      />

      {/* Week navigation */}
      <div className="flex items-center justify-between">
        <button
          onClick={() => shiftWeek(-1)}
          disabled={loading}
          className="flex items-center gap-1 text-sm text-slate-500 dark:text-white/50
                     hover:text-slate-800 dark:hover:text-white disabled:opacity-50 transition-colors"
        >
          <ChevronLeft size={16} /> Previous
        </button>
        <div className="flex items-center gap-3">
          <span className="text-sm font-medium text-slate-700 dark:text-white/80">{rangeLabel}</span>
          {startDate !== TODAY_ISO && (
            <button
              onClick={() => setStartDate(TODAY_ISO)}
              className="text-xs font-medium text-brand-600 dark:text-brand-400 hover:underline"
            >
              This week
            </button>
          )}
        </div>
        <button
          onClick={() => shiftWeek(1)}
          disabled={loading}
          className="flex items-center gap-1 text-sm text-slate-500 dark:text-white/50
                     hover:text-slate-800 dark:hover:text-white disabled:opacity-50 transition-colors"
        >
          Next <ChevronRight size={16} />
        </button>
      </div>

      {/* Content */}
      {loading ? (
        <div className="flex items-center justify-center py-20">
          <FaniLoader
            size="md"
            messages={['Reading your closet…', 'Checking the week ahead…', 'Laying out your outfits…']}
            subline="FANI is planning your week"
          />
        </div>
      ) : generating ? (
        <div className="flex items-center justify-center py-20">
          <FaniLoader
            messages={[
              'Reading your closet…',
              'Checking the weather…',
              'Balancing colors & repeats…',
              'Planning each day…',
              'Almost there…',
            ]}
            subline="FANI is building your week"
          />
        </div>
      ) : error ? (
        <GlassCard className="p-6 flex items-center gap-3 text-red-600 dark:text-red-400">
          <Cloud size={20} />
          <p className="text-sm">{error}</p>
        </GlassCard>
      ) : (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {weekDates.map(date => (
            <DayCard
              key={date}
              date={date}
              plan={planByDate[date]}
              busy={busyDate === date}
              onMarkWorn={handleMarkWorn}
              onClear={handleClear}
            />
          ))}
        </div>
      )}
    </div>
  )
}
