import { useEffect, useMemo, useRef, useState } from 'react'
import {
  CalendarDays, Sparkles, Check, Trash2, Loader2, Shirt, ChevronLeft, ChevronRight,
  Plus, X, Sun, Cloud, CloudRain, CloudSnow, Wind, Package,
} from 'lucide-react'
import BackButton from '@/components/ui/BackButton'
import GlassCard from '@/components/ui/GlassCard'
import PageHeader from '@/components/ui/PageHeader'
import { FaniLoader } from '@/components/system/FaniLoader'
import { closetApi, plannerApi } from '@/lib/api'
import { toastStore } from '@/store/notificationStore'
import type { ClosetItem, PlannedDay } from '@/types'
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

/** Occasions offered per day — mirrors what the planner/generator produces. */
const OCCASIONS = [
  'work', 'casual', 'smart casual', 'weekend', 'date night', 'formal', 'active', 'travel',
] as const

/** Closet grouping order in the picker drawer. */
const CATEGORY_ORDER = ['tops', 'bottoms', 'outerwear', 'dresses', 'shoes', 'accessories', 'other']

function apiErr(err: unknown, fallback: string): string {
  const d = (err as { response?: { data?: { detail?: unknown; message?: string } } })?.response?.data
  if (typeof d?.detail === 'string') return d.detail
  if (d?.message) return d.message
  return err instanceof Error && err.message ? err.message : fallback
}

/** Pick a weather glyph from the free-text condition the planner stores. */
function WeatherIcon({ condition, size = 13 }: { condition?: string | null; size?: number }) {
  const c = (condition ?? '').toLowerCase()
  if (c.includes('rain') || c.includes('drizzle') || c.includes('shower')) return <CloudRain size={size} />
  if (c.includes('snow') || c.includes('sleet')) return <CloudSnow size={size} />
  if (c.includes('wind')) return <Wind size={size} />
  if (c.includes('cloud') || c.includes('overcast')) return <Cloud size={size} />
  if (c.includes('sun') || c.includes('clear') || c.includes('fair')) return <Sun size={size} />
  return <Cloud size={size} />
}

/** Small square thumbnail used for both planned items and closet chips. */
function ItemThumb({ item, size = 'sm' }: { item: { name: string; image_url?: string | null }; size?: 'sm' | 'xs' }) {
  const box = size === 'sm' ? 'h-7 w-7' : 'h-6 w-6'
  return (
    <span
      className={cn(
        box,
        'shrink-0 rounded-md overflow-hidden bg-slate-100 dark:bg-white/[0.06]',
        'border border-cream-200 dark:border-white/[0.08]',
        'flex items-center justify-center text-slate-300 dark:text-white/20',
      )}
    >
      {item.image_url
        ? <img src={item.image_url} alt="" loading="lazy" decoding="async" className="h-full w-full object-cover" />
        : <Shirt size={size === 'sm' ? 13 : 11} />}
    </span>
  )
}

// ── Per-day card (one column of the week strip) ────────────────────────────────

function DayCard({
  date,
  plan,
  busy,
  isPicking,
  onOccasionChange,
  onRemoveItem,
  onPickItem,
  onSaveNote,
  onMarkWorn,
  onClear,
}: {
  date: string
  plan: PlannedDay | undefined
  busy: boolean
  isPicking: boolean
  onOccasionChange: (date: string, occasion: string) => void
  onRemoveItem: (date: string, itemId: string) => void
  onPickItem: (date: string) => void
  onSaveNote: (date: string, note: string) => void
  onMarkWorn: (date: string) => void
  onClear: (date: string) => void
}) {
  const d = parseISODate(date)
  const isToday = date === TODAY_ISO
  const isPast = date < TODAY_ISO
  const items = plan?.items ?? []
  const hasOutfit = items.length > 0
  const isWorn = !!plan?.is_worn
  // A worn day is locked: `PUT /planner/{date}` resets is_worn, so editing would
  // silently undo the wear log (and the wear counts already written to the items).
  const locked = isWorn

  // The API stores a day note in `reasoning`, so a FANI-written explanation and a
  // user note share one field. Show FANI's text as prose; seed the note box only
  // once the day is user-owned (source === 'manual').
  const savedNote = plan?.source === 'manual' ? (plan.reasoning ?? '') : ''
  const [note, setNote] = useState(savedNote)
  useEffect(() => { setNote(savedNote) }, [savedNote])

  const commitNote = () => {
    const next = note.trim()
    if (next !== savedNote.trim()) onSaveNote(date, next)
  }

  return (
    <GlassCard
      padding="none"
      className={cn(
        'w-[16.5rem] shrink-0 snap-start flex flex-col',
        'sm:w-[17.5rem]',
        isToday && 'ring-2 ring-brand-400/60',
        isPicking && 'ring-2 ring-brand-500 shadow-glow-sm',
        isPast && !isWorn && 'opacity-75 hover:opacity-100 transition-opacity',
      )}
    >
      {/* Header: weekday + date + weather */}
      <div className="flex items-start justify-between gap-2 px-4 pt-4">
        <div className="min-w-0">
          <div className="flex items-center gap-1.5">
            <span className="font-semibold text-slate-800 dark:text-white">{WEEKDAY.format(d)}</span>
            {isToday && (
              <span className="text-[10px] font-bold uppercase tracking-wide px-1.5 py-0.5 rounded
                               bg-brand-50 dark:bg-brand-500/15 text-brand-600 dark:text-brand-400">
                Today
              </span>
            )}
          </div>
          <span className="text-xs text-slate-400 dark:text-white/40">{DAYNUM.format(d)}</span>
        </div>
        {(plan?.weather_condition || plan?.temp_high != null) && (
          <span
            className="flex items-center gap-1 shrink-0 text-xs px-2 py-1 rounded-lg
                       bg-slate-50 dark:bg-white/[0.05] text-slate-500 dark:text-white/50"
            title={plan?.weather_condition ?? undefined}
          >
            <WeatherIcon condition={plan?.weather_condition} />
            {plan?.temp_high != null && (
              <span className="font-medium">{Math.round(plan.temp_high)}°</span>
            )}
          </span>
        )}
      </div>

      {/* Occasion */}
      <div className="px-4 pt-3">
        <div className="relative">
          <select
            value={plan?.occasion || ''}
            disabled={locked || busy}
            onChange={e => onOccasionChange(date, e.target.value)}
            aria-label={`Occasion for ${WEEKDAY.format(d)}`}
            className={cn(
              'w-full appearance-none text-sm font-medium rounded-xl px-3 py-2 pr-8',
              // Only the chosen occasion is title-cased — the placeholder reads as a sentence.
              plan?.occasion ? 'capitalize' : '',
              'border border-cream-200 dark:border-white/[0.08]',
              'bg-white/70 dark:bg-white/[0.04] text-slate-700 dark:text-white/80',
              'focus:outline-none focus:ring-2 focus:ring-brand-400/50',
              'disabled:opacity-60 disabled:cursor-not-allowed',
            )}
          >
            <option value="" disabled>Pick an occasion</option>
            {OCCASIONS.map(o => <option key={o} value={o} className="capitalize">{o}</option>)}
          </select>
          <ChevronRight
            size={14}
            className="pointer-events-none absolute right-3 top-1/2 -translate-y-1/2 rotate-90 text-slate-400 dark:text-white/40"
          />
        </div>
      </div>

      {/* Items */}
      <div className="px-4 pt-3 flex-1 flex flex-col gap-1.5">
        {items.map(item => (
          <div
            key={item.id}
            className="group flex items-center gap-2 rounded-lg py-1 pl-1 pr-1
                       hover:bg-slate-50 dark:hover:bg-white/[0.04] transition-colors"
          >
            <ItemThumb item={item} />
            <span className="flex-1 min-w-0 truncate text-sm text-slate-700 dark:text-white/80" title={item.name}>
              {item.name}
            </span>
            {!locked && (
              <button
                onClick={() => onRemoveItem(date, item.id)}
                disabled={busy}
                aria-label={`Remove ${item.name}`}
                className="shrink-0 p-1 rounded-md text-slate-300 dark:text-white/25
                           opacity-0 group-hover:opacity-100 focus-visible:opacity-100
                           hover:bg-red-50 dark:hover:bg-red-900/20 hover:text-red-500
                           transition disabled:opacity-50"
              >
                <X size={13} />
              </button>
            )}
          </div>
        ))}

        {!hasOutfit && (
          <p className="text-xs text-slate-400 dark:text-white/40 py-2">
            Nothing planned yet.
          </p>
        )}

        {!locked && (
          <button
            onClick={() => onPickItem(date)}
            disabled={busy}
            className={cn(
              'flex items-center gap-2 rounded-lg py-1 pl-1 pr-2 text-sm font-medium transition-colors',
              'text-slate-400 dark:text-white/40 hover:text-brand-600 dark:hover:text-brand-400',
              'disabled:opacity-50',
              isPicking && 'text-brand-600 dark:text-brand-400',
            )}
          >
            <span className="h-7 w-7 shrink-0 rounded-md flex items-center justify-center
                             border border-dashed border-cream-300 dark:border-white/[0.14]">
              <Plus size={13} />
            </span>
            {isPicking ? 'Choose below…' : 'Add item'}
          </button>
        )}
      </div>

      {/* FANI's reasoning for this day (only while the day is still FANI's pick) */}
      {plan?.source === 'fani' && plan.reasoning && (
        <p className="px-4 pt-3 text-xs leading-relaxed text-slate-500 dark:text-white/50 line-clamp-3">
          <Sparkles size={10} className="inline mr-1 -mt-0.5 text-brand-500" />
          {plan.reasoning}
        </p>
      )}

      {/* Note + actions */}
      <div className="px-4 pb-4 pt-3 mt-auto space-y-2">
        <input
          value={note}
          disabled={locked || busy}
          onChange={e => setNote(e.target.value)}
          onBlur={commitNote}
          onKeyDown={e => { if (e.key === 'Enter') e.currentTarget.blur() }}
          placeholder="Add a note…"
          aria-label={`Note for ${WEEKDAY.format(d)}`}
          className="w-full text-sm rounded-xl px-3 py-2
                     border border-cream-200 dark:border-white/[0.08]
                     bg-white/70 dark:bg-white/[0.04]
                     text-slate-700 dark:text-white/80 placeholder:text-slate-400 dark:placeholder:text-white/30
                     focus:outline-none focus:ring-2 focus:ring-brand-400/50
                     disabled:opacity-60"
        />

        {isWorn ? (
          <div className="flex items-center justify-center gap-1.5 py-2 rounded-xl text-xs font-medium
                          bg-emerald-50 dark:bg-emerald-900/20 text-emerald-700 dark:text-emerald-400">
            <Check size={13} /> {isToday ? 'Worn today' : 'Worn'}
          </div>
        ) : hasOutfit ? (
          <div className="flex items-center gap-2">
            <button
              onClick={() => onClear(date)}
              disabled={busy}
              className="flex-1 flex items-center justify-center gap-1.5 text-xs font-medium px-2 py-2 rounded-xl
                         bg-slate-100 dark:bg-white/[0.06] text-slate-500 dark:text-white/50
                         hover:bg-red-50 dark:hover:bg-red-900/20 hover:text-red-500
                         transition-colors disabled:opacity-50"
            >
              <Trash2 size={12} /> Clear
            </button>
            <button
              onClick={() => onMarkWorn(date)}
              disabled={busy}
              className="flex-1 flex items-center justify-center gap-1.5 text-xs font-medium px-2 py-2 rounded-xl
                         bg-emerald-500/90 text-white hover:bg-emerald-600
                         transition-colors disabled:opacity-50"
            >
              {busy ? <Loader2 size={12} className="animate-spin" /> : <Check size={12} />}
              Mark worn
            </button>
          </div>
        ) : null}
      </div>
    </GlassCard>
  )
}

// ── Closet picker drawer ───────────────────────────────────────────────────────

function ClosetDrawer({
  items,
  loading,
  open,
  pickingDate,
  busy,
  onToggle,
  onAdd,
  onDonePicking,
}: {
  items: ClosetItem[]
  loading: boolean
  open: boolean
  pickingDate: string | null
  busy: boolean
  onToggle: () => void
  onAdd: (itemId: string) => void
  onDonePicking: () => void
}) {
  const grouped = useMemo(() => {
    const map = new Map<string, ClosetItem[]>()
    for (const item of items) {
      const key = (item.category || 'other').toLowerCase()
      const bucket = map.get(key)
      if (bucket) bucket.push(item)
      else map.set(key, [item])
    }
    return [...map.entries()].sort((a, b) => {
      const ai = CATEGORY_ORDER.indexOf(a[0])
      const bi = CATEGORY_ORDER.indexOf(b[0])
      return (ai < 0 ? 99 : ai) - (bi < 0 ? 99 : bi)
    })
  }, [items])

  return (
    <GlassCard padding="none" className="overflow-hidden">
      <button
        onClick={onToggle}
        aria-expanded={open}
        className="w-full flex items-center justify-between gap-3 px-4 py-3 text-left
                   hover:bg-slate-50/60 dark:hover:bg-white/[0.03] transition-colors"
      >
        <span className="flex items-center gap-2 min-w-0">
          <Package size={16} className="text-brand-500 shrink-0" />
          <span className="font-semibold text-sm text-slate-800 dark:text-white">Your closet</span>
          {!loading && (
            <span className="text-xs text-slate-400 dark:text-white/40">{items.length} items</span>
          )}
        </span>
        <span className="flex items-center gap-1 text-xs font-medium text-slate-500 dark:text-white/50 shrink-0">
          {open ? 'Hide' : 'Show'}
          <ChevronRight size={14} className={cn('transition-transform', open ? '-rotate-90' : 'rotate-90')} />
        </span>
      </button>

      {open && (
        <div className="px-4 pb-4 border-t border-cream-200/70 dark:border-white/[0.08]">
          {pickingDate && (
            <div className="sticky top-0 z-10 -mx-4 px-4 py-2.5 mb-3
                            flex items-center justify-between gap-3
                            bg-brand-50/95 dark:bg-brand-500/15 backdrop-blur-sm">
              <span className="text-xs font-medium text-brand-700 dark:text-brand-300">
                Tap an item to add it to {WEEKDAY.format(parseISODate(pickingDate))} {DAYNUM.format(parseISODate(pickingDate))}
              </span>
              <button
                onClick={onDonePicking}
                className="text-xs font-semibold text-brand-700 dark:text-brand-300 hover:underline shrink-0"
              >
                Done
              </button>
            </div>
          )}

          {loading ? (
            <div className="flex items-center gap-2 py-6 text-sm text-slate-400 dark:text-white/40">
              <Loader2 size={14} className="animate-spin" /> Loading your closet…
            </div>
          ) : items.length === 0 ? (
            <p className="py-6 text-sm text-slate-400 dark:text-white/40">
              Your closet is empty — add a few pieces and FANI can plan around them.
            </p>
          ) : (
            <div className="pt-3 space-y-4 max-h-72 overflow-y-auto">
              {grouped.map(([category, group]) => (
                <div key={category}>
                  <h3 className="text-[10px] font-bold uppercase tracking-wider text-slate-400 dark:text-white/35 mb-2">
                    {category}
                  </h3>
                  <div className="flex flex-wrap gap-2">
                    {group.map(item => (
                      <button
                        key={item.id}
                        onClick={() => onAdd(item.id)}
                        disabled={!pickingDate || busy}
                        title={pickingDate ? `Add ${item.name}` : 'Tap “Add item” on a day first'}
                        className="flex items-center gap-2 pl-1 pr-2.5 py-1 rounded-full
                                   border border-cream-200 dark:border-white/[0.08]
                                   bg-white/70 dark:bg-white/[0.04]
                                   text-sm text-slate-700 dark:text-white/80
                                   enabled:hover:border-brand-400 enabled:hover:text-brand-600
                                   dark:enabled:hover:text-brand-400
                                   transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                      >
                        <ItemThumb item={item} size="xs" />
                        <span className="max-w-[9rem] truncate">{item.name}</span>
                      </button>
                    ))}
                  </div>
                </div>
              ))}
            </div>
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

  const [closet, setCloset] = useState<ClosetItem[]>([])
  const [closetLoading, setClosetLoading] = useState(false)
  const [closetLoaded, setClosetLoaded] = useState(false)
  const [closetOpen, setClosetOpen] = useState(false)
  const [pickingDate, setPickingDate] = useState<string | null>(null)

  const closetRef = useRef<HTMLDivElement>(null)

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

  const ensureCloset = async () => {
    if (closetLoaded || closetLoading) return
    setClosetLoading(true)
    try {
      const res = await closetApi.list()
      setCloset(res.items)
      setClosetLoaded(true)
    } catch (err) {
      toastStore.add({
        variant: 'error', icon: '👕', title: 'Could not load closet',
        body: apiErr(err, 'Try again.'),
      })
    } finally {
      setClosetLoading(false)
    }
  }

  /** Merge a day the API just returned back into the week, keeping date order. */
  const upsertDay = (updated: PlannedDay) => {
    setDays(prev => [...prev.filter(d => d.plan_date !== updated.plan_date), updated]
      .sort((a, b) => a.plan_date.localeCompare(b.plan_date)))
  }

  /**
   * Persist an edit for one day. Unspecified fields fall back to what's already
   * planned so a partial edit never wipes the rest of the day.
   */
  const saveDay = async (
    date: string,
    patch: { item_ids?: string[]; occasion?: string; notes?: string },
  ) => {
    const plan = planByDate[date]
    setBusyDate(date)
    try {
      const updated = await plannerApi.setDay(date, {
        item_ids: patch.item_ids ?? (plan?.items ?? []).map(i => i.id),
        occasion: patch.occasion ?? plan?.occasion ?? undefined,
        notes: patch.notes,
      })
      upsertDay(updated)
    } catch (err) {
      toastStore.add({
        variant: 'error', icon: '🗓️', title: 'Could not save',
        body: apiErr(err, 'Your change was not saved.'),
      })
    } finally {
      setBusyDate(null)
    }
  }

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
      upsertDay(updated)
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
      if (pickingDate === date) setPickingDate(null)
    } catch (err) {
      toastStore.add({ variant: 'error', icon: '🗓️', title: 'Could not clear', body: apiErr(err, 'Try again.') })
    } finally {
      setBusyDate(null)
    }
  }

  const handleRemoveItem = (date: string, itemId: string) => {
    const remaining = (planByDate[date]?.items ?? []).filter(i => i.id !== itemId).map(i => i.id)
    // Removing the last piece is a "clear", not an empty plan row.
    if (remaining.length === 0) return handleClear(date)
    return saveDay(date, { item_ids: remaining })
  }

  const handlePickItem = async (date: string) => {
    setPickingDate(date)
    setClosetOpen(true)
    await ensureCloset()
    closetRef.current?.scrollIntoView({ behavior: 'smooth', block: 'nearest' })
  }

  const handleAddFromCloset = (itemId: string) => {
    if (!pickingDate) return
    const current = (planByDate[pickingDate]?.items ?? []).map(i => i.id)
    if (current.includes(itemId)) {
      toastStore.add({ variant: 'default', icon: '👕', title: 'Already planned', body: 'That piece is already in this day.' })
      return
    }
    return saveDay(pickingDate, { item_ids: [...current, itemId] })
  }

  const handleToggleCloset = async () => {
    const next = !closetOpen
    setClosetOpen(next)
    if (!next) setPickingDate(null)
    if (next) await ensureCloset()
  }

  const shiftWeek = (deltaWeeks: number) => {
    setPickingDate(null)
    setStartDate(toISODate(addDays(parseISODate(startDate), deltaWeeks * PLAN_DAYS)))
  }

  const rangeLabel = `${RANGE_FMT.format(parseISODate(weekDates[0]))} – ${RANGE_FMT.format(parseISODate(weekDates[weekDates.length - 1]))}`

  return (
    <div className="max-w-6xl space-y-6">
      <BackButton fallback="/dashboard" label="Back to Dashboard" />

      <PageHeader
        icon={<CalendarDays size={18} />}
        chipClassName="bg-gradient-to-br from-brand-500 to-brand-600 shadow-glow-sm"
        iconColor="text-white"
        title="Weekly Planner"
        subtitle="AI-planned, fully editable — weather-aware and drawn from your closet"
        stackActionsOnMobile
        actions={
          <button
            onClick={handleGenerate}
            disabled={generating || loading}
            className="flex items-center justify-center gap-2 text-sm font-medium px-4 py-2 rounded-xl
                       bg-gradient-to-br from-brand-500 to-brand-600 text-white shadow-glow-sm
                       hover:from-brand-600 hover:to-brand-700 transition-colors disabled:opacity-60"
          >
            {generating ? <Loader2 size={15} className="animate-spin" /> : <Sparkles size={15} />}
            {hasAnyPlan ? 'Regenerate' : 'Plan my week'}
          </button>
        }
      />

      {/* Week navigation */}
      <div className="flex items-center justify-between gap-2">
        <button
          onClick={() => shiftWeek(-1)}
          disabled={loading}
          className="flex items-center gap-1 text-sm text-slate-500 dark:text-white/50
                     hover:text-slate-800 dark:hover:text-white disabled:opacity-50 transition-colors"
        >
          <ChevronLeft size={16} /> Prev
        </button>
        <div className="flex items-center gap-3 min-w-0">
          <span className="text-sm font-medium text-slate-700 dark:text-white/80 truncate">{rangeLabel}</span>
          {startDate !== TODAY_ISO && (
            <button
              onClick={() => setStartDate(TODAY_ISO)}
              className="text-xs font-medium text-brand-600 dark:text-brand-400 hover:underline shrink-0"
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
        <>
          {/* Week strip — seven day columns, scrolled horizontally */}
          <div className="-mx-4 px-4 sm:mx-0 sm:px-0">
            <div className="flex gap-4 overflow-x-auto snap-x snap-mandatory scrollbar-hide pb-2">
              {weekDates.map(date => (
                <DayCard
                  key={date}
                  date={date}
                  plan={planByDate[date]}
                  busy={busyDate === date}
                  isPicking={pickingDate === date}
                  onOccasionChange={(d, occasion) => saveDay(d, { occasion })}
                  onRemoveItem={handleRemoveItem}
                  onPickItem={handlePickItem}
                  onSaveNote={(d, notes) => saveDay(d, { notes })}
                  onMarkWorn={handleMarkWorn}
                  onClear={handleClear}
                />
              ))}
            </div>
          </div>

          <div ref={closetRef}>
            <ClosetDrawer
              items={closet}
              loading={closetLoading}
              open={closetOpen}
              pickingDate={pickingDate}
              busy={busyDate !== null}
              onToggle={handleToggleCloset}
              onAdd={handleAddFromCloset}
              onDonePicking={() => setPickingDate(null)}
            />
          </div>
        </>
      )}
    </div>
  )
}
