import { useEffect, useMemo, useState } from 'react'
import { notificationStore, toastStore } from '@/store/notificationStore'
import BackButton from '@/components/ui/BackButton'
import {
  closestCenter,
  DndContext,
  DragOverlay,
  MouseSensor,
  TouchSensor,
  useDraggable,
  useDroppable,
  useSensor,
  useSensors,
  type DragEndEvent,
  type DragStartEvent,
} from '@dnd-kit/core'
import {
  arrayMove,
  rectSortingStrategy,
  SortableContext,
  useSortable,
} from '@dnd-kit/sortable'
import { CSS } from '@dnd-kit/utilities'
import {
  AlertCircle,
  Check,
  ChevronDown,
  ChevronUp,
  Cloud,
  CloudRain,
  CloudSnow,
  CloudSun,
  Lightbulb,
  Loader2,
  MapPin,
  Moon,
  Palette,
  Plus,
  RefreshCw,
  Ruler,
  Search,
  Shirt,
  Smile,
  Sparkles,
  Sun,
  Sunrise,
  Sunset,
  TrendingUp,
  Wand2,
  X,
  Zap,
} from 'lucide-react'
import { useApp } from '@/store'
import { outfitsApi } from '@/lib/api'
import { shuffleOutfit, type ShuffleAlternative } from '@/services/aiChatApi'
import { fetchWeather } from '@/hooks/useWeather'
import { cn } from '@/lib/utils'
import type { ClosetItem, OutfitAnalysis, ScoreBreakdown, SuggestedPairingItem } from '@/types'

const CANONICAL_TAB_CATEGORIES = new Set([
  'tops', 'bottoms', 'shoes', 'outerwear', 'dresses', 'accessories',
])

const CATEGORIES = ['all', 'tops', 'bottoms', 'shoes', 'outerwear', 'dresses', 'accessories', 'other'] as const
const OCCASIONS = ['casual', 'business', 'formal', 'sport', 'beach', 'date-night']

// ── Time of day ───────────────────────────────────────────────────────────────

type TimeOfDay = 'morning' | 'afternoon' | 'evening' | 'night'
const TIME_OPTIONS: { value: TimeOfDay; label: string; icon: React.ReactNode; hint: string }[] = [
  { value: 'morning',   label: 'Morning',   icon: <Sunrise size={13} />,  hint: '6 AM–12 PM' },
  { value: 'afternoon', label: 'Afternoon', icon: <Sun size={13} />,      hint: '12–6 PM'   },
  { value: 'evening',   label: 'Evening',   icon: <Sunset size={13} />,   hint: '6–10 PM'   },
  { value: 'night',     label: 'Night',     icon: <Moon size={13} />,     hint: '10 PM+'    },
]

// ── Mood ─────────────────────────────────────────────────────────────────────

type Mood = 'energetic' | 'relaxed' | 'professional' | 'creative' | 'romantic' | 'bold'
const MOOD_OPTIONS: { value: Mood; label: string; emoji: string }[] = [
  { value: 'energetic',    label: 'Energetic',    emoji: '⚡' },
  { value: 'relaxed',      label: 'Relaxed',      emoji: '😌' },
  { value: 'professional', label: 'Professional', emoji: '💼' },
  { value: 'creative',     label: 'Creative',     emoji: '🎨' },
  { value: 'romantic',     label: 'Romantic',     emoji: '🌹' },
  { value: 'bold',         label: 'Bold',         emoji: '🔥' },
]

// ── Occasion → compatible moods / times (for badge logic) ────────────────────

// ── Weather icon helper ───────────────────────────────────────────────────────

function WeatherIcon({ condition }: { condition: string }) {
  const c = condition.toLowerCase()
  if (c.includes('rain') || c.includes('shower') || c.includes('drizzle'))
    return <CloudRain size={13} />
  if (c.includes('snow'))
    return <CloudSnow size={13} />
  if (c.includes('cloud') || c.includes('overcast') || c.includes('fog'))
    return <Cloud size={13} />
  return <Sun size={13} />
}

// ── Item occasion-match badge helper ─────────────────────────────────────────

function itemMatchesOccasion(item: ClosetItem, occasion: string): boolean {
  const occ = item.occasion
  if (!occ || (Array.isArray(occ) && occ.length === 0)) return true // untagged = neutral
  const list = Array.isArray(occ) ? occ.map(o => String(o).toLowerCase()) : [String(occ).toLowerCase()]
  return list.some(o =>
    o === occasion.toLowerCase() ||
    o === 'all' ||
    o === 'versatile' ||
    o === 'all-occasion'
  )
}

function itemMatchesSeason(item: ClosetItem, currentMonth: number): boolean {
  const raw = item.season
  if (!raw || raw.length === 0) return true
  // Normalise: backend returns string[], but accept legacy string too
  const seasons = (Array.isArray(raw) ? raw : [raw]).map(s => s.toLowerCase())
  if (seasons.some(s => s === 'all-season' || s === 'all season' || s === '')) return true
  if (seasons.some(s => s === 'summer' || s === 'spring') && currentMonth >= 3 && currentMonth <= 8) return true
  if (seasons.some(s => s === 'winter' || s === 'fall' || s === 'autumn') && (currentMonth <= 2 || currentMonth >= 9)) return true
  return false
}

type CanvasItem = ClosetItem & { canvasId: string }

// ── Outfit completeness ring ──────────────────────────────────────────────────

function CompletenessRing({ items }: { items: CanvasItem[] }) {
  const filled = PREVIEW_SLOTS.filter(slot =>
    items.some(i => slot.categories.includes(i.category))
  ).length
  const total = PREVIEW_SLOTS.length
  const pct = Math.round((filled / total) * 100)
  const radius = 22
  const circ = 2 * Math.PI * radius
  const color = pct >= 80 ? '#10b981' : pct >= 60 ? '#f59e0b' : '#94a3b8'
  return (
    <div className="flex flex-col items-center gap-0.5" title={`${filled}/${total} outfit slots filled`}>
      <div className="relative w-[54px] h-[54px]">
        <svg width={54} height={54} className="-rotate-90">
          <circle cx={27} cy={27} r={radius} fill="none" stroke="currentColor" strokeWidth={5}
            className="text-slate-100 dark:text-slate-700" />
          <circle cx={27} cy={27} r={radius} fill="none" stroke={color} strokeWidth={5}
            strokeLinecap="round"
            strokeDasharray={`${(pct / 100) * circ} ${circ}`}
            style={{ transition: 'stroke-dasharray 0.5s ease' }}
          />
        </svg>
        <div className="absolute inset-0 flex items-center justify-center pointer-events-none">
          <span className="text-[11px] font-bold text-slate-700 dark:text-white">{pct}%</span>
        </div>
      </div>
      <span className="text-[9px] text-slate-400 leading-none">{filled}/{total} slots</span>
    </div>
  )
}

// ── Color palette row ─────────────────────────────────────────────────────────

const COLOR_NAME_MAP: Record<string, string> = {
  black: '#111111', white: '#f8f8f8', navy: '#1e3a5f', grey: '#9ca3af',
  gray: '#9ca3af', red: '#ef4444', blue: '#3b82f6', green: '#22c55e',
  yellow: '#eab308', orange: '#f97316', pink: '#ec4899', purple: '#a855f7',
  brown: '#92400e', beige: '#d6c09a', cream: '#f5f0e8', khaki: '#c3b58e',
  olive: '#6b7280', teal: '#14b8a6', maroon: '#7f1d1d', gold: '#d97706',
  silver: '#cbd5e1', coral: '#fb7185', mint: '#6ee7b7', lavender: '#c4b5fd',
  camel: '#c09a6b', ivory: '#fffacd', charcoal: '#4b5563', indigo: '#6366f1',
}

function resolveColor(colorStr: string | undefined): string | null {
  if (!colorStr) return null
  const lower = colorStr.toLowerCase().trim()
  for (const [name, hex] of Object.entries(COLOR_NAME_MAP)) {
    if (lower.includes(name)) return hex
  }
  if (/^#[0-9a-f]{3,6}$/i.test(lower)) return lower
  return null
}

function ColorPaletteRow({ items }: { items: CanvasItem[] }) {
  if (items.length === 0) return null
  const colors = items
    .map(i => ({ name: i.color || '', hex: resolveColor(i.color), item: i.name }))
    .filter(c => c.hex)

  if (colors.length === 0) return null
  return (
    <div className="flex items-center gap-2 px-1">
      <Palette size={12} className="text-slate-400 flex-shrink-0" />
      <div className="flex items-center gap-1.5 flex-wrap">
        {colors.map((c, i) => (
          <div key={i} className="group relative">
            <div
              className="w-5 h-5 rounded-full border-2 border-white dark:border-slate-800 shadow-sm cursor-default"
              style={{ backgroundColor: c.hex! }}
              title={`${c.item} — ${c.name}`}
            />
            <div className="absolute bottom-6 left-1/2 -translate-x-1/2 hidden group-hover:block z-20 bg-slate-800 text-white text-[10px] rounded px-1.5 py-0.5 whitespace-nowrap shadow">
              {c.item}<br />{c.name}
            </div>
          </div>
        ))}
      </div>
      <span className="text-[10px] text-slate-400">
        {colors.length} colour{colors.length !== 1 ? 's' : ''}
      </span>
    </div>
  )
}

// ── Context bar ───────────────────────────────────────────────────────────────

interface ContextBarProps {
  occasion: string
  timeOfDay: TimeOfDay
  mood: Mood | null
  weather: { condition: string; temp_c: number } | null
  location: string
  fetchingWeather: boolean
}

function ContextBar({ occasion, timeOfDay, mood, weather, location, fetchingWeather }: ContextBarProps) {
  const time = TIME_OPTIONS.find(t => t.value === timeOfDay)
  const moodOpt = MOOD_OPTIONS.find(m => m.value === mood)
  return (
    <div className="flex flex-wrap items-center gap-2 text-[11px]">
      {/* Occasion */}
      <span className="flex items-center gap-1 rounded-full bg-brand-100 dark:bg-brand-500/15 text-brand-700 dark:text-brand-300 px-2.5 py-1 font-semibold capitalize">
        <Shirt size={11} /> {occasion}
      </span>
      {/* Time of day */}
      <span className="flex items-center gap-1 rounded-full bg-amber-50 dark:bg-amber-500/10 text-amber-700 dark:text-amber-300 px-2.5 py-1 font-semibold capitalize">
        {time?.icon} {time?.label}
      </span>
      {/* Mood */}
      {moodOpt && (
        <span className="flex items-center gap-1 rounded-full bg-brand-50 dark:bg-brand-500/10 text-brand-700 dark:text-brand-300 px-2.5 py-1 font-semibold">
          <span>{moodOpt.emoji}</span> {moodOpt.label}
        </span>
      )}
      {/* Weather */}
      {fetchingWeather && (
        <span className="flex items-center gap-1 rounded-full bg-sky-50 dark:bg-sky-500/10 text-sky-500 px-2.5 py-1">
          <Loader2 size={11} className="animate-spin" /> Getting weather…
        </span>
      )}
      {weather && !fetchingWeather && (
        <span className="flex items-center gap-1 rounded-full bg-sky-50 dark:bg-sky-500/10 text-sky-700 dark:text-sky-300 px-2.5 py-1 font-semibold">
          <WeatherIcon condition={weather.condition} />
          {weather.condition}
          {weather.temp_c !== 0 && ` · ${Math.round(weather.temp_c)}°C`}
          {location && <><MapPin size={10} className="ml-0.5" />{location}</>}
        </span>
      )}
    </div>
  )
}

// ── Outfit preview strip slots ────────────────────────────────────────────────

const PREVIEW_SLOTS: Array<{ categories: string[]; label: string; emoji: string }> = [
  { categories: ['outerwear'],        label: 'Outer',  emoji: '🧥' },
  { categories: ['tops', 'dresses'],  label: 'Top',    emoji: '👕' },
  { categories: ['bottoms'],          label: 'Bottom', emoji: '👖' },
  { categories: ['shoes'],            label: 'Shoes',  emoji: '👟' },
  { categories: ['accessories'],      label: 'Acc',    emoji: '👜' },
]

// ── Score helpers ──────────────────────────────────────────────────────────────

function scoreColor(score: number): string {
  if (score >= 85) return '#10b981'
  if (score >= 70) return '#f59e0b'
  if (score >= 50) return '#f97316'
  return '#ef4444'
}

function scoreLabel(score: number): string {
  if (score >= 90) return 'Excellent'
  if (score >= 75) return 'Great'
  if (score >= 60) return 'Good'
  if (score >= 45) return 'Fair'
  return 'Needs Work'
}

const SCORE_FACTORS: { key: keyof ScoreBreakdown; label: string; max: number }[] = [
  { key: 'color',      label: 'Color Compatibility', max: 25 },
  { key: 'occasion',   label: 'Occasion Match',       max: 25 },
  { key: 'fit',        label: 'Fit & Size Alignment', max: 20 },
  { key: 'style',      label: 'Style Consistency',    max: 13 },
  { key: 'weather',    label: 'Weather & Climate',     max: 12 },
  { key: 'preference', label: 'Preference Match',     max: 5  },
]

// ── Item image helper ─────────────────────────────────────────────────────────

function itemImage(item: ClosetItem, className = 'h-full w-full object-cover') {
  return item.image_url
    ? <img src={item.image_url} alt={item.name} className={className} />
    : <div className="flex h-full w-full items-center justify-center text-2xl">👕</div>
}

// ── Outfit preview strip ──────────────────────────────────────────────────────

function OutfitPreviewStrip({ items, score }: { items: CanvasItem[]; score?: number }) {
  if (items.length === 0) return null
  const allSlotCategories = PREVIEW_SLOTS.flatMap(s => s.categories)

  return (
    <div className="flex items-center gap-2 px-2 py-3 bg-gradient-to-b from-slate-50/80 dark:from-slate-800/40 to-transparent rounded-2xl">
      {/* Slot thumbnails */}
      <div className="flex items-end gap-2 flex-1 min-w-0 overflow-x-auto pb-0.5">
        {PREVIEW_SLOTS.map(slot => {
          const matched = items.find(i => slot.categories.includes(i.category))
          return (
            <div key={slot.label} className="flex flex-col items-center gap-1 flex-shrink-0">
              <div className={cn(
                'w-12 h-16 rounded-xl overflow-hidden',
                matched
                  ? 'border border-cream-200 dark:border-slate-700 shadow-sm'
                  : 'border-2 border-dashed border-slate-200 dark:border-slate-700 opacity-30',
              )}>
                {matched
                  ? itemImage(matched as ClosetItem, 'w-full h-full object-cover')
                  : <div className="w-full h-full flex items-center justify-center text-xl">{slot.emoji}</div>
                }
              </div>
              <span className="text-[9px] text-slate-400 dark:text-slate-500">{slot.label}</span>
            </div>
          )
        })}
        {/* Extra items (not in main slots) */}
        {items
          .filter(i => !allSlotCategories.includes(i.category))
          .map(item => (
            <div key={item.canvasId} className="flex flex-col items-center gap-1 flex-shrink-0">
              <div className="w-12 h-16 rounded-xl overflow-hidden border border-cream-200 dark:border-slate-700 shadow-sm">
                {itemImage(item as ClosetItem, 'w-full h-full object-cover')}
              </div>
              <span className="text-[9px] text-slate-400 capitalize">{item.category}</span>
            </div>
          ))
        }
      </div>

      {/* Summary */}
      <div className="flex-shrink-0 flex flex-col items-end gap-1 ml-2">
        <span className="text-[10px] text-slate-500 dark:text-slate-400">
          {items.length} piece{items.length !== 1 ? 's' : ''}
        </span>
        {score != null && (
          <span
            className="text-xs font-bold px-2 py-0.5 rounded-full text-white"
            style={{ backgroundColor: scoreColor(score) }}
          >
            {score}/100
          </span>
        )}
      </div>
    </div>
  )
}

// ── Closet draggable card ──────────────────────────────────────────────────────

function ClosetDraggableCard({ item, added, onAdd, onRemove }: { item: ClosetItem; added: boolean; onAdd: () => void; onRemove: () => void }) {
  const { attributes, listeners, setNodeRef, transform, isDragging } = useDraggable({
    id: `closet:${item.id}`,
    data: { item },
  })

  return (
    <div
      ref={setNodeRef}
      style={{ transform: transform ? CSS.Translate.toString(transform) : undefined, opacity: isDragging ? 0.45 : 1 }}
      className="group relative rounded-2xl border border-cream-200 bg-white shadow-card transition hover:-translate-y-0.5 hover:shadow-card-hover dark:border-white/10 dark:bg-white/[0.04]"
    >
      <div
        {...attributes}
        {...listeners}
        className="aspect-square overflow-hidden rounded-t-2xl bg-cream-100 dark:bg-slate-800 cursor-grab active:cursor-grabbing"
      >
        {itemImage(item)}
      </div>
      <div className="p-3 pb-2">
        <p className="truncate text-sm font-semibold text-slate-800 dark:text-white">{item.name}</p>
        <p className="text-xs capitalize text-slate-500 dark:text-white/40">{item.category}</p>
      </div>
      <div className="px-3 pb-3">
        {added ? (
          <button
            onClick={onRemove}
            className="group w-full flex items-center justify-center gap-1.5 rounded-xl py-1.5 text-[11px] font-semibold transition-all bg-emerald-50 dark:bg-emerald-500/10 border border-emerald-200 dark:border-emerald-500/30 text-emerald-600 dark:text-emerald-400 hover:bg-red-50 dark:hover:bg-red-500/10 hover:border-red-200 dark:hover:border-red-500/30 hover:text-red-500 dark:hover:text-red-400"
          >
            <Check size={11} className="group-hover:hidden" />
            <X size={11} className="hidden group-hover:block" />
            <span className="group-hover:hidden">Added</span>
            <span className="hidden group-hover:inline">Remove</span>
          </button>
        ) : (
          <button
            onClick={onAdd}
            className="w-full flex items-center justify-center gap-1.5 rounded-xl py-1.5 text-[11px] font-semibold transition-all bg-brand-50 text-brand-700 dark:bg-brand-500/15 dark:text-brand-300 hover:bg-brand-100 dark:hover:bg-brand-500/25 border border-brand-200 dark:border-brand-500/30"
          >
            <Plus size={11} /> Add
          </button>
        )}
      </div>
    </div>
  )
}

// ── Canvas droppable ───────────────────────────────────────────────────────────

function OutfitDroppable({ children }: { children: React.ReactNode }) {
  const { setNodeRef, isOver } = useDroppable({ id: 'outfit-canvas' })
  return (
    <div
      ref={setNodeRef}
      className={`min-h-40 rounded-3xl border-2 border-dashed p-3 transition ${
        isOver
          ? 'border-brand-500 bg-brand-50 dark:bg-brand-500/10'
          : 'border-cream-300 bg-white/70 dark:border-white/10 dark:bg-white/[0.04]'
      }`}
    >
      {children}
    </div>
  )
}

// ── Sortable image tile with match badges ─────────────────────────────────────

function SortableImageTile({
  item, onRemove, occasion, currentMonth, weatherCold,
}: {
  item: CanvasItem
  onRemove: (id: string) => void
  occasion: string
  currentMonth: number
  weatherCold: boolean
}) {
  const { attributes, listeners, setNodeRef, transform, transition, isDragging } = useSortable({ id: item.canvasId })
  const occasionOk = itemMatchesOccasion(item, occasion)
  const seasonOk = itemMatchesSeason(item, currentMonth)

  return (
    <div
      ref={setNodeRef}
      style={{ transform: CSS.Transform.toString(transform), transition, opacity: isDragging ? 0.4 : 1 }}
      className="relative group flex-shrink-0 w-[76px]"
    >
      {/* Remove button */}
      <button
        onClick={() => onRemove(item.canvasId)}
        className="absolute -top-1.5 -right-1.5 z-10 w-5 h-5 rounded-full bg-red-500 text-white flex items-center justify-center opacity-0 group-hover:opacity-100 transition-opacity shadow-sm"
        aria-label={`Remove ${item.name}`}
      >
        <X size={10} />
      </button>

      {/* Image */}
      <div
        {...attributes}
        {...listeners}
        className={cn(
          'w-[76px] h-[96px] rounded-xl overflow-hidden shadow-sm bg-cream-100 dark:bg-slate-800 cursor-grab active:cursor-grabbing',
          (!occasionOk || !seasonOk)
            ? 'border-2 border-amber-400 dark:border-amber-500'
            : 'border border-cream-200 dark:border-slate-700',
        )}
      >
        {itemImage(item)}

        {/* Weather cold badge — show a snowflake if item season is summer but weather cold */}
        {weatherCold && item.season && (Array.isArray(item.season) ? item.season : [item.season]).some(s => String(s).toLowerCase().includes('summer')) && (
          <div className="absolute bottom-1 right-1 w-4 h-4 rounded-full bg-blue-500/80 flex items-center justify-center">
            <CloudSnow size={9} className="text-white" />
          </div>
        )}
      </div>

      {/* Match badges row */}
      <div className="flex items-center justify-center gap-0.5 mt-1 mb-0.5">
        {/* Occasion match */}
        <div
          className={cn(
            'flex items-center gap-0.5 rounded-full px-1 py-0 text-[8px] font-bold',
            occasionOk
              ? 'bg-emerald-100 dark:bg-emerald-500/15 text-emerald-700 dark:text-emerald-400'
              : 'bg-amber-100 dark:bg-amber-500/15 text-amber-700 dark:text-amber-400',
          )}
          title={occasionOk ? `Suits ${occasion}` : `Not tagged for ${occasion}`}
        >
          {occasionOk ? <Check size={7} /> : '!'}
          <span className="capitalize truncate max-w-[30px]">{occasionOk ? occasion.slice(0, 3) : 'occ'}</span>
        </div>
        {/* Season match */}
        {!seasonOk && (
          <div
            className="flex items-center gap-0.5 rounded-full px-1 py-0 text-[8px] font-bold bg-orange-100 dark:bg-orange-500/15 text-orange-700 dark:text-orange-400"
            title="Season mismatch"
          >
            ⚠
          </div>
        )}
      </div>

      {/* Name */}
      <p className="text-[10px] text-center text-slate-600 dark:text-slate-400 leading-tight truncate px-0.5">
        {item.name}
      </p>
    </div>
  )
}

// ── Score circle ───────────────────────────────────────────────────────────────

function ScoreCircle({ score }: { score: number }) {
  const radius = 52
  const circumference = 2 * Math.PI * radius
  const filled = (score / 100) * circumference
  const color = scoreColor(score)
  return (
    <div className="relative flex flex-col items-center gap-1">
      <svg width={128} height={128} className="-rotate-90">
        <circle cx={64} cy={64} r={radius} fill="none" stroke="currentColor" strokeWidth={10}
          className="text-slate-100 dark:text-slate-700" />
        <circle cx={64} cy={64} r={radius} fill="none" stroke={color} strokeWidth={10}
          strokeLinecap="round"
          strokeDasharray={`${filled} ${circumference}`}
          style={{ transition: 'stroke-dasharray 0.8s ease' }} />
      </svg>
      <div className="absolute inset-0 flex flex-col items-center justify-center">
        <span className="text-3xl font-extrabold text-slate-800 dark:text-white">{score}</span>
        <span className="text-xs font-medium text-slate-500 dark:text-slate-400">/ 100</span>
      </div>
      <span className="text-xs font-bold uppercase tracking-widest" style={{ color }}>{scoreLabel(score)}</span>
    </div>
  )
}

// ── Score breakdown bars ───────────────────────────────────────────────────────

function ScoreBars({ breakdown }: { breakdown: ScoreBreakdown }) {
  return (
    <div className="space-y-2.5">
      {SCORE_FACTORS.map(({ key, label, max }) => {
        const val = breakdown[key] ?? 0
        const pct = Math.round((val / max) * 100)
        return (
          <div key={key}>
            <div className="mb-1 flex items-center justify-between">
              <span className="text-xs text-slate-600 dark:text-slate-400">{label}</span>
              <span className="text-xs font-semibold text-slate-700 dark:text-slate-300">{val}/{max}</span>
            </div>
            <div className="h-1.5 overflow-hidden rounded-full bg-slate-100 dark:bg-slate-700">
              <div
                className="h-full rounded-full transition-all duration-700"
                style={{ width: `${pct}%`, backgroundColor: scoreColor(Math.round((val / max) * 100)) }}
              />
            </div>
          </div>
        )
      })}
    </div>
  )
}

// ── Recommendation list ────────────────────────────────────────────────────────

function RecommendationSection({ icon, title, items, colorClass }: {
  icon: React.ReactNode; title: string; items: string[]; colorClass: string
}) {
  if (!items.length) return null
  return (
    <div>
      <div className={`mb-2 flex items-center gap-2 text-sm font-semibold ${colorClass}`}>
        {icon}
        {title}
      </div>
      <ul className="space-y-1.5">
        {items.map((text, i) => (
          <li key={i} className="flex gap-2 text-sm text-slate-600 dark:text-slate-400">
            <span className="mt-0.5 flex-shrink-0">•</span>
            <span>{text}</span>
          </li>
        ))}
      </ul>
    </div>
  )
}

// ── AI Analysis Panel ─────────────────────────────────────────────────────────

export function AIAnalysisPanel({ analysis, onClose }: {
  analysis: OutfitAnalysis
  onClose?: () => void
}) {
  const { outfit, missing_pieces, style_tips } = analysis
  const {
    matching_score, score_breakdown, recommendations, reasoning, confidence,
    fit_notes, fit_confidence, occasion_match, style_match, size_profile_match,
    body_profile_notes, why_it_works, what_to_improve,
  } = outfit
  const [tipsOpen, setTipsOpen] = useState(false)

  return (
    <div className="rounded-3xl border border-brand-200 bg-white/90 shadow-card-hover dark:border-brand-500/30 dark:bg-slate-900/90">
      <div className="flex items-center justify-between border-b border-slate-100 px-5 py-4 dark:border-slate-800">
        <div className="flex items-center gap-2">
          <Sparkles size={18} className="text-brand-500" />
          <span className="font-display text-base font-bold text-slate-800 dark:text-white">AI Outfit Analysis</span>
          {confidence != null && (
            <span className="rounded-full bg-slate-100 px-2 py-0.5 text-xs text-slate-500 dark:bg-slate-800 dark:text-slate-400">
              {Math.round(confidence * 100)}% confidence
            </span>
          )}
        </div>
        {onClose && (
          <button
            onClick={onClose}
            className="flex h-8 w-8 items-center justify-center rounded-lg text-slate-400 hover:bg-slate-100 hover:text-slate-600 dark:hover:bg-slate-800"
          >
            <X size={15} />
          </button>
        )}
      </div>

      <div className="p-5">
        <div className="grid gap-6 sm:grid-cols-[auto_1fr]">
          <ScoreCircle score={matching_score} />
          <ScoreBars breakdown={score_breakdown} />
        </div>

        {(fit_confidence != null || occasion_match || style_match || size_profile_match) && (
          <div className="mt-4 grid gap-2 sm:grid-cols-2">
            {fit_confidence != null && (
              <div className="rounded-2xl border border-slate-100 bg-white/80 px-4 py-3 dark:border-slate-800 dark:bg-slate-800/40">
                <span className="text-xs font-semibold text-slate-500 dark:text-slate-400">Fit confidence</span>
                <p className="text-lg font-bold text-slate-800 dark:text-white">{fit_confidence}%</p>
              </div>
            )}
            {occasion_match && (
              <div className="rounded-2xl border border-slate-100 bg-white/80 px-4 py-3 dark:border-slate-800 dark:bg-slate-800/40">
                <span className="text-xs font-semibold text-slate-500 dark:text-slate-400">Occasion match</span>
                <p className="font-semibold text-slate-800 dark:text-white">{occasion_match}</p>
              </div>
            )}
            {style_match && (
              <div className="rounded-2xl border border-slate-100 bg-white/80 px-4 py-3 dark:border-slate-800 dark:bg-slate-800/40">
                <span className="text-xs font-semibold text-slate-500 dark:text-slate-400">Style match</span>
                <p className="font-semibold text-slate-800 dark:text-white">{style_match}</p>
              </div>
            )}
            {size_profile_match && (
              <div className="rounded-2xl border border-slate-100 bg-white/80 px-4 py-3 dark:border-slate-800 dark:bg-slate-800/40">
                <span className="text-xs font-semibold text-slate-500 dark:text-slate-400">Size profile match</span>
                <p className="font-semibold text-slate-800 dark:text-white">{size_profile_match}</p>
              </div>
            )}
          </div>
        )}

        {reasoning && (
          <div className="mt-5 rounded-2xl border border-slate-100 bg-slate-50 px-4 py-3 text-sm text-slate-600 dark:border-slate-800 dark:bg-slate-800/60 dark:text-slate-400">
            <span className="font-semibold text-slate-700 dark:text-slate-300">Stylist&rsquo;s take: </span>
            {reasoning}
          </div>
        )}

        {(body_profile_notes || fit_notes) && (
          <div className="mt-3 flex items-start gap-2.5 rounded-2xl border border-brand-100 bg-brand-50/60 px-4 py-3 text-sm text-brand-700 dark:border-brand-500/20 dark:bg-brand-500/[0.07] dark:text-brand-300">
            <Ruler size={14} className="mt-0.5 flex-shrink-0 text-brand-500 dark:text-brand-400" />
            <div>
              <span className="font-semibold">Body profile notes: </span>
              {body_profile_notes || fit_notes}
            </div>
          </div>
        )}

        {why_it_works && (
          <div className="mt-3 rounded-2xl border border-slate-100 bg-slate-50 px-4 py-3 text-sm text-slate-600 dark:border-slate-800 dark:bg-slate-800/50 dark:text-slate-300">
            <span className="font-semibold text-slate-700 dark:text-slate-200">Why it works: </span>
            {why_it_works}
          </div>
        )}

        {what_to_improve && what_to_improve.length > 0 && (
          <div className="mt-3">
            <div className="mb-1 text-xs font-semibold text-slate-500 dark:text-slate-400">What to improve</div>
            <ul className="list-inside list-disc text-sm text-slate-600 dark:text-slate-300">
              {what_to_improve.map((w, i) => <li key={i}>{w}</li>)}
            </ul>
          </div>
        )}

        <div className="mt-5 grid gap-5 sm:grid-cols-3">
          <RecommendationSection
            icon={<AlertCircle size={15} />}
            title="Issues"
            items={recommendations.issues}
            colorClass="text-red-500"
          />
          <RecommendationSection
            icon={<TrendingUp size={15} />}
            title="Improvements"
            items={recommendations.improvements}
            colorClass="text-amber-500"
          />
          <RecommendationSection
            icon={<Lightbulb size={15} />}
            title="Styling Tips"
            items={recommendations.styling_tips}
            colorClass="text-brand-500"
          />
        </div>

        {missing_pieces.length > 0 && (
          <div className="mt-4 flex flex-wrap items-center gap-2">
            <span className="text-xs font-semibold text-slate-500 dark:text-slate-400">Missing pieces:</span>
            {missing_pieces.map((piece, i) => (
              <span
                key={i}
                className="rounded-full border border-dashed border-slate-300 px-2.5 py-0.5 text-xs capitalize text-slate-500 dark:border-slate-600 dark:text-slate-400"
              >
                + {piece}
              </span>
            ))}
          </div>
        )}

        {style_tips.length > 0 && (
          <div className="mt-4">
            <button
              onClick={() => setTipsOpen(o => !o)}
              className="flex items-center gap-1.5 text-xs font-semibold text-brand-500 hover:text-brand-600"
            >
              {tipsOpen ? <ChevronUp size={13} /> : <ChevronDown size={13} />}
              {tipsOpen ? 'Hide' : 'Show'} general style tips
            </button>
            {tipsOpen && (
              <ul className="mt-2 space-y-1">
                {style_tips.map((tip, i) => (
                  <li key={i} className="flex gap-2 text-sm text-slate-500 dark:text-slate-400">
                    <span className="mt-0.5 flex-shrink-0 text-brand-400">✦</span>
                    {tip}
                  </li>
                ))}
              </ul>
            )}
          </div>
        )}
      </div>
    </div>
  )
}

// ── Suggested Pairings Shelf ──────────────────────────────────────────────────

interface SuggestedPairingsShelfProps {
  pairings: SuggestedPairingItem[]
  alreadyAddedIds: Set<string>
  onAdd: (item: SuggestedPairingItem) => void
}

function SuggestedPairingsShelf({ pairings, alreadyAddedIds, onAdd }: SuggestedPairingsShelfProps) {
  if (pairings.length === 0) return null
  return (
    <div className="rounded-3xl border border-brand-200 bg-white/90 shadow-card dark:border-brand-500/30 dark:bg-slate-900/90">
      <div className="flex items-center gap-2 border-b border-slate-100 px-5 py-4 dark:border-slate-800">
        <div className="flex h-7 w-7 items-center justify-center rounded-lg bg-brand-100 dark:bg-brand-500/15">
          <Sparkles size={14} className="text-brand-600 dark:text-brand-400" />
        </div>
        <div>
          <p className="font-display text-sm font-bold text-slate-800 dark:text-white">AI-Suggested Pairings</p>
          <p className="text-[11px] text-slate-400">Closet items that complement this outfit</p>
        </div>
      </div>
      <div className="p-4">
        <div className="flex gap-3 overflow-x-auto pb-2" style={{ scrollbarWidth: 'none' }}>
          {pairings.map(item => {
            const added = alreadyAddedIds.has(item.id)
            return (
              <div
                key={item.id}
                className="group relative flex-shrink-0 w-[140px] rounded-2xl border border-cream-200 bg-white dark:border-white/10 dark:bg-slate-800 overflow-hidden shadow-sm hover:shadow-md transition-shadow"
              >
                <div className="relative aspect-[3/4] bg-cream-100 dark:bg-slate-700 overflow-hidden">
                  {item.image_url ? (
                    <img src={item.image_url} alt={item.name} className="w-full h-full object-cover group-hover:scale-105 transition-transform duration-300" />
                  ) : (
                    <div className="w-full h-full flex items-center justify-center text-3xl">
                      {item.category === 'shoes' ? '👟' : item.category === 'accessories' ? '👜' : item.category === 'outerwear' ? '🧥' : '👕'}
                    </div>
                  )}
                  <span className="absolute top-2 left-2 text-[9px] font-bold bg-black/50 text-white rounded-full px-2 py-0.5 capitalize">
                    {item.category}
                  </span>
                </div>
                <div className="px-2.5 pt-2 pb-1">
                  <p className="text-xs font-semibold text-slate-800 dark:text-white truncate leading-tight">{item.name}</p>
                  {item.brand && <p className="text-[10px] text-slate-400 truncate">{item.brand}</p>}
                </div>
                <div className="px-2.5 pb-2">
                  <p className="text-[10px] text-slate-500 dark:text-slate-400 leading-snug line-clamp-3">{item.reason}</p>
                </div>
                <div className="px-2.5 pb-2.5">
                  <button
                    onClick={() => !added && onAdd(item)}
                    disabled={added}
                    className={`w-full flex items-center justify-center gap-1.5 rounded-xl py-1.5 text-[11px] font-semibold transition-all ${
                      added
                        ? 'bg-emerald-50 text-emerald-600 dark:bg-emerald-500/10 dark:text-emerald-400 cursor-default border border-emerald-200 dark:border-emerald-500/30'
                        : 'bg-brand-50 text-brand-700 dark:bg-brand-500/15 dark:text-brand-300 hover:bg-brand-100 dark:hover:bg-brand-500/25 border border-brand-200 dark:border-brand-500/30'
                    }`}
                  >
                    {added ? <><Check size={11} /> Added</> : <><Plus size={11} /> Add to Outfit</>}
                  </button>
                </div>
              </div>
            )
          })}
        </div>
      </div>
    </div>
  )
}

// ── Smart Start Banner ────────────────────────────────────────────────────────

const SMART_START_SUGGESTIONS = [
  { label: 'Start with a Shirt',  category: 'tops',      emoji: '👔' },
  { label: 'Start with Pants',    category: 'bottoms',   emoji: '👖' },
  { label: 'Start with a Dress',  category: 'dresses',   emoji: '👗' },
  { label: 'Start with Shoes',    category: 'shoes',     emoji: '👟' },
  { label: 'Start with a Jacket', category: 'outerwear', emoji: '🧥' },
]

function SmartStartBanner({ onPick }: { onPick: (category: string) => void }) {
  return (
    <div className="rounded-2xl border border-brand-100 dark:border-brand-500/20 bg-brand-50/60 dark:bg-brand-500/[0.06] px-5 py-4">
      <div className="flex items-center gap-2 mb-3">
        <Shirt size={16} className="text-brand-500" />
        <p className="text-sm font-semibold text-slate-700 dark:text-slate-200">Start building your outfit</p>
      </div>
      <p className="text-xs text-slate-500 dark:text-slate-400 mb-3">
        Drag items from the closet panel, or pick a starting piece:
      </p>
      <div className="flex flex-wrap gap-2">
        {SMART_START_SUGGESTIONS.map(s => (
          <button
            key={s.category}
            type="button"
            onClick={() => onPick(s.category)}
            className="flex items-center gap-1.5 rounded-full border border-brand-200 dark:border-brand-500/30 bg-white dark:bg-slate-800 px-3 py-1.5 text-xs font-medium text-brand-700 dark:text-brand-300 hover:bg-brand-100 dark:hover:bg-brand-500/15 transition-colors"
          >
            <span>{s.emoji}</span>
            {s.label}
          </button>
        ))}
      </div>
    </div>
  )
}

// ── Shuffle Alternatives Shelf ────────────────────────────────────────────────

interface ShuffleShelfProps {
  alternatives: ShuffleAlternative[]
  onApply: (alt: ShuffleAlternative) => void
  onClose: () => void
}

function ShuffleAlternativesShelf({ alternatives, onApply, onClose }: ShuffleShelfProps) {
  if (alternatives.length === 0) return null
  return (
    <div className="rounded-3xl border border-emerald-200 dark:border-emerald-500/30 bg-white/90 dark:bg-slate-900/90 shadow-card">
      <div className="flex items-center justify-between border-b border-slate-100 dark:border-slate-800 px-5 py-4">
        <div className="flex items-center gap-2">
          <div className="flex h-7 w-7 items-center justify-center rounded-lg bg-emerald-100 dark:bg-emerald-500/15">
            <RefreshCw size={14} className="text-emerald-600 dark:text-emerald-400" />
          </div>
          <div>
            <p className="font-display text-sm font-bold text-slate-800 dark:text-white">Alternative Outfits</p>
            <p className="text-[11px] text-slate-400">
              {alternatives.length} fresh combination{alternatives.length > 1 ? 's' : ''} from your closet
            </p>
          </div>
        </div>
        <button
          onClick={onClose}
          className="flex h-7 w-7 items-center justify-center rounded-lg text-slate-400 hover:bg-slate-100 dark:hover:bg-slate-800"
        >
          <X size={14} />
        </button>
      </div>

      <div className="p-4 space-y-4">
        {alternatives.map((alt, idx) => (
          <div key={idx} className="rounded-2xl border border-slate-100 dark:border-slate-800 bg-slate-50/60 dark:bg-slate-800/40 p-4">
            <div className="flex items-center justify-between mb-3">
              <div className="flex items-center gap-2">
                <span className="font-semibold text-sm text-slate-800 dark:text-white">{alt.title}</span>
                <span className={`rounded-full px-2 py-0.5 text-xs font-bold text-white ${alt.matching_score >= 85 ? 'bg-emerald-500' : alt.matching_score >= 70 ? 'bg-brand-500' : 'bg-amber-500'}`}>
                  {alt.matching_score}%
                </span>
              </div>
              <button
                type="button"
                onClick={() => onApply(alt)}
                className="flex items-center gap-1.5 rounded-xl bg-emerald-500 hover:bg-emerald-600 text-white px-3 py-1.5 text-xs font-semibold transition-colors"
              >
                <Check size={11} /> Apply
              </button>
            </div>

            <div className="flex gap-2 overflow-x-auto pb-1">
              {alt.items.map((item, i) => (
                <div key={i} className="flex-shrink-0 flex flex-col items-center gap-1 w-14">
                  <div className="w-14 h-14 rounded-xl overflow-hidden bg-cream-100 dark:bg-slate-700 border border-cream-200 dark:border-slate-700 flex items-center justify-center">
                    {item.image_url ? (
                      <img src={item.image_url} alt={item.name} className="w-full h-full object-cover" />
                    ) : (
                      <span className="text-[10px] text-slate-400 text-center px-1 leading-tight">{item.category}</span>
                    )}
                  </div>
                  <span className="text-[9px] text-slate-500 text-center leading-tight max-w-[56px] truncate">{item.name}</span>
                </div>
              ))}
            </div>

            <p className="mt-2 text-xs text-slate-500 dark:text-slate-400 leading-snug">{alt.reasoning}</p>

            {alt.improvement_tips?.length > 0 && (
              <div className="mt-2 space-y-0.5">
                {alt.improvement_tips.map((tip, i) => (
                  <p key={i} className="text-xs text-emerald-600 dark:text-emerald-400 flex gap-1.5">
                    <span className="flex-shrink-0">→</span>{tip}
                  </p>
                ))}
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  )
}

// ── Main page ─────────────────────────────────────────────────────────────────

export default function OutfitBuilder() {
  const { closetItems, currentUser } = useApp()
  const [query, setQuery] = useState('')
  const [category, setCategory] = useState<(typeof CATEGORIES)[number]>('all')
  const [canvasItems, setCanvasItems] = useState<CanvasItem[]>([])
  const [activeItem, setActiveItem] = useState<ClosetItem | null>(null)
  const [name, setName] = useState('')
  const [occasion, setOccasion] = useState('casual')
  const [timeOfDay, setTimeOfDay] = useState<TimeOfDay>(() => {
    const h = new Date().getHours()
    if (h < 12) return 'morning'
    if (h < 18) return 'afternoon'
    if (h < 22) return 'evening'
    return 'night'
  })
  const [autoTime, setAutoTime] = useState(true)
  const [mood, setMood] = useState<Mood | null>(null)
  const [notes, setNotes] = useState('')
  const [browserOpen, setBrowserOpen] = useState(false)

  const [date, setDate] = useState('')
  const [location, setLocation] = useState('')
  const [weather, setWeather] = useState<{ condition: string; temp_c: number } | null>(null)
  const [fetchingWeather, setFetchingWeather] = useState(false)

  const currentMonth = new Date().getMonth() + 1 // 1-based
  const weatherCold = !!weather && weather.temp_c < 15

  // ── Auto-fetch weather from user's saved location ─────────────────────────
  useEffect(() => {
    const coords = currentUser?.permissions?.location_coords
    const label = currentUser?.permissions?.location_label
    if (!coords || !currentUser?.permissions?.location) return
    setFetchingWeather(true)
    fetchWeather(coords.lat, coords.lon)
      .then(w => {
        setWeather({ condition: w.current.condition, temp_c: w.current.temperature })
        if (label && !location) setLocation(label)
      })
      .catch(() => { /* silent — weather is optional */ })
      .finally(() => setFetchingWeather(false))
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [currentUser?.permissions?.location_coords?.lat, currentUser?.permissions?.location_coords?.lon])

  // AI analysis
  const [analyzing, setAnalyzing] = useState(false)
  const [analysis, setAnalysis] = useState<OutfitAnalysis | null>(null)
  const [analysisError, setAnalysisError] = useState<string | null>(null)

  // Suggested pairings
  const suggestedPairings = analysis?.suggested_pairings ?? []

  // Outfit shuffle
  const [shuffling, setShuffling] = useState(false)
  const [shuffleAlternatives, setShuffleAlternatives] = useState<ShuffleAlternative[]>([])
  const [shuffleError, setShuffleError] = useState<string | null>(null)

  // AI results drawer
  const [drawerOpen, setDrawerOpen] = useState(false)
  const [confirmClear, setConfirmClear] = useState(false)
  const [showContext, setShowContext] = useState(false)

  // MouseSensor for desktop (drag after a 6px move) + TouchSensor for mobile
  // (press-and-hold ~180ms to drag, so a quick swipe still scrolls the strip).
  const sensors = useSensors(
    useSensor(MouseSensor, { activationConstraint: { distance: 6 } }),
    useSensor(TouchSensor, { activationConstraint: { delay: 180, tolerance: 8 } }),
  )

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase()
    return closetItems.filter(item => {
      let matchesCategory = category === 'all'
      if (!matchesCategory) {
        if (category === 'other') {
          matchesCategory = item.category === 'other' || item.category === 'uncategorised' || !CANONICAL_TAB_CATEGORIES.has(item.category)
        } else {
          matchesCategory = item.category === category
        }
      }
      const matchesSearch = !q || item.name.toLowerCase().includes(q) || item.category.toLowerCase().includes(q)
      return matchesCategory && matchesSearch
    })
  }, [closetItems, query, category])

  const addedIds = new Set(canvasItems.map(item => item.id))
  const hasInsights = !!(analysis || shuffleAlternatives.length > 0 || analyzing || shuffling || analysisError || shuffleError)

  const handleSmartStart = (cat: string) => {
    setCategory(cat as (typeof CATEGORIES)[number])
    setBrowserOpen(true)
  }

  const shuffleCurrentOutfit = async () => {
    if (canvasItems.length === 0 || shuffling) return
    setShuffling(true)
    setShuffleError(null)
    setShuffleAlternatives([])
    setDrawerOpen(true)
    try {
      const alts = await shuffleOutfit({
        item_ids: canvasItems.map(i => i.id),
        occasion,
        location: location.trim() || null,
      })
      setShuffleAlternatives(alts)
      if (alts.length === 0) setShuffleError('No alternative combinations found — try adding more items to your closet.')
    } catch {
      setShuffleError('Shuffle failed. Please try again.')
    } finally {
      setShuffling(false)
    }
  }

  const applyShuffleAlternative = (alt: ShuffleAlternative) => {
    const newItems: CanvasItem[] = []
    for (const ai of alt.items) {
      const full = closetItems.find(ci => ci.id === ai.id)
      if (full) newItems.push({ ...full, canvasId: `${full.id}:${crypto.randomUUID()}` })
    }
    if (newItems.length > 0) {
      setCanvasItems(newItems)
      setAnalysis(null)
      setAnalysisError(null)
      setShuffleAlternatives([])
      setDrawerOpen(false)
    }
  }

  const addSuggestedToCanvas = (suggested: SuggestedPairingItem) => {
    const full = closetItems.find(ci => ci.id === suggested.id)
    if (!full || addedIds.has(suggested.id)) return
    setCanvasItems(prev => [...prev, { ...full, canvasId: `${full.id}:${crypto.randomUUID()}` }])
  }

  const handleDragStart = (event: DragStartEvent) => {
    const item = event.active.data.current?.item as ClosetItem | undefined
    setActiveItem(item ?? null)
  }

  const handleDragEnd = (event: DragEndEvent) => {
    setActiveItem(null)
    const { active, over } = event
    if (!over) return

    if (String(active.id).startsWith('closet:') && over.id === 'outfit-canvas') {
      const item = active.data.current?.item as ClosetItem | undefined
      if (item) {
        setCanvasItems(prev => [...prev, { ...item, canvasId: `${item.id}:${crypto.randomUUID()}` }])
        setAnalysis(null)
        setAnalysisError(null)
        setShuffleAlternatives([])
      }
      return
    }

    if (active.id !== over.id) {
      setCanvasItems(prev => {
        const oldIndex = prev.findIndex(item => item.canvasId === active.id)
        const newIndex = prev.findIndex(item => item.canvasId === over.id)
        return oldIndex >= 0 && newIndex >= 0 ? arrayMove(prev, oldIndex, newIndex) : prev
      })
    }
  }

  const clear = () => {
    setConfirmClear(false)
    setCanvasItems([])
    setName('')
    setOccasion('casual')
    setMood(null)
    setNotes('')
    setDate('')
    setLocation('')
    setWeather(null)
    setAnalysis(null)
    setAnalysisError(null)
    setShuffleAlternatives([])
    setShuffleError(null)
  }

  const save = async () => {
    if (!name.trim() || canvasItems.length === 0) return
    try {
      await outfitsApi.create({
        name: name.trim(),
        item_ids: canvasItems.map(item => item.id),
        occasion,
        notes: notes.trim() || undefined,
      })
      notificationStore.push({
        channel: 'closet',
        icon: '✨',
        title: 'Outfit saved!',
        body: `"${name.trim()}" is now in your saved outfits.`,
      })
      clear()
    } catch {
      toastStore.add({ variant: 'error', icon: '❌', title: 'Failed to save outfit', body: 'Please try again.' })
    }
  }

  const analyzeWithAI = async () => {
    if (canvasItems.length === 0) return
    setAnalyzing(true)
    setAnalysis(null)
    setAnalysisError(null)
    setDrawerOpen(true)
    try {
      // Build a rich context note so AI knows about time + mood
      const contextParts: string[] = []
      if (timeOfDay) contextParts.push(`Time of day: ${timeOfDay}`)
      if (mood) contextParts.push(`Mood: ${mood}`)
      const contextNote = contextParts.length
        ? `${notes.trim() ? notes.trim() + '\n' : ''}[Context: ${contextParts.join(', ')}]`
        : notes.trim()

      const payload: Parameters<typeof outfitsApi.analyze>[0] = {
        item_ids: canvasItems.map(item => item.id),
        occasion,
        ...(date && { date }),
        ...(location.trim() && { location: location.trim() }),
        ...(contextNote && { notes: contextNote }),
      }
      const result = await outfitsApi.analyze(payload)
      setAnalysis(result)
      toastStore.add({
        variant: 'success',
        icon: '✨',
        title: 'AI analysis complete',
        body: result.outfit?.matching_score != null ? `Score: ${result.outfit.matching_score}/100` : 'Your outfit has been analysed.',
      })
    } catch (err) {
      setAnalysisError(err instanceof Error ? err.message : 'AI analysis failed. Please try again.')
      toastStore.add({ variant: 'error', icon: '❌', title: 'AI analysis failed', body: 'Please try again.' })
    } finally {
      setAnalyzing(false)
    }
  }

  const closetBrowser = (
    <div className="space-y-4">
      <div className="relative">
        <Search size={15} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
        <input
          className="input pl-9"
          placeholder="Search closet..."
          value={query}
          onChange={event => setQuery(event.target.value)}
        />
      </div>
      <div className="flex flex-wrap gap-2">
        {CATEGORIES.map(value => (
          <button
            key={value}
            onClick={() => setCategory(value)}
            className={`min-h-[40px] rounded-full px-3 text-xs font-semibold capitalize transition ${
              category === value
                ? 'bg-brand-600 text-white'
                : 'bg-cream-100 text-slate-600 hover:bg-cream-200 dark:bg-slate-800 dark:text-slate-300 dark:hover:bg-slate-700'
            }`}
          >
            {value}
          </button>
        ))}
      </div>
      <div className="grid max-h-[560px] grid-cols-2 gap-3 overflow-y-auto pr-1">
        {filtered.map(item => (
          <ClosetDraggableCard
            key={item.id}
            item={item}
            added={addedIds.has(item.id)}
            onAdd={() => {
              setCanvasItems(prev => [...prev, { ...item, canvasId: `${item.id}:${crypto.randomUUID()}` }])
              setAnalysis(null)
              setAnalysisError(null)
            }}
            onRemove={() => {
              setCanvasItems(prev => prev.filter(c => c.id !== item.id))
              setAnalysis(null)
              setAnalysisError(null)
            }}
          />
        ))}
      </div>
    </div>
  )

  if (closetItems.length < 5) {
    return (
      <div className="flex max-w-2xl flex-col items-center gap-4 rounded-3xl border border-cream-200 bg-white/70 p-10 text-center shadow-card dark:border-white/10 dark:bg-white/[0.04]">
        <div className="flex h-14 w-14 items-center justify-center rounded-2xl bg-brand-50 text-brand-500 dark:bg-brand-500/10">
          <Wand2 size={26} />
        </div>
        <h3 className="font-display text-lg font-bold text-slate-800 dark:text-white">You need at least 5 items to generate outfits</h3>
        <p className="text-sm text-slate-500 dark:text-slate-400">Add a few more pieces so FANI can create better outfit combinations for your style, size, weather, and occasions.</p>
        <div className="flex gap-3">
          <a href="/upload" className="btn-primary">Add More Items</a>
          <a href="/closet" className="btn-secondary">View Closet</a>
        </div>
      </div>
    )
  }

  return (
    <div className="space-y-5">
      <BackButton fallback="/closet" label="Back to Closet" />
      <div>
        <h2 className="font-display text-xl font-bold text-slate-800 dark:text-slate-100">Outfit Builder</h2>
        <p className="text-sm text-slate-400">
          Drag pieces from your closet onto the canvas, then hit{' '}
          <span className="font-medium text-brand-500">Analyze with AI</span> for a detailed matching score.
        </p>
      </div>

      <DndContext
        sensors={sensors}
        collisionDetection={closestCenter}
        onDragStart={handleDragStart}
        onDragEnd={handleDragEnd}
      >
        <div className="grid gap-5 md:grid-cols-[minmax(0,0.4fr)_minmax(0,0.6fr)]">
          {/* Desktop closet sidebar */}
          <aside className="hidden rounded-3xl border border-cream-200 bg-white/70 p-4 shadow-card dark:border-white/10 dark:bg-white/[0.04] md:block">
            {closetBrowser}
          </aside>

          {/* Mobile closet toggle */}
          <div className="md:hidden">
            <button className="btn-secondary w-full" onClick={() => setBrowserOpen(o => !o)}>
              {browserOpen ? 'Hide Closet' : 'Browse Closet'}
            </button>
            {browserOpen && (
              <div className="mt-3 rounded-3xl border border-cream-200 bg-white/70 p-4 shadow-card dark:border-white/10 dark:bg-white/[0.04]">
                {closetBrowser}
              </div>
            )}
          </div>

          {/* Canvas + form */}
          <section className="space-y-4 rounded-3xl border border-cream-200 bg-white/70 p-4 shadow-card dark:border-white/10 dark:bg-white/[0.04]">

            {/* ── Context bar ──────────────────────────────────────────────── */}
            <ContextBar
              occasion={occasion}
              timeOfDay={timeOfDay}
              mood={mood}
              weather={weather}
              location={location}
              fetchingWeather={fetchingWeather}
            />

            {/* ── Outfit preview strip + completeness ring ─────────────────── */}
            {canvasItems.length > 0 && (
              <div className="flex items-start gap-3">
                <div className="flex-1 min-w-0">
                  <OutfitPreviewStrip
                    items={canvasItems}
                    score={analysis?.outfit?.matching_score}
                  />
                </div>
                <div className="relative flex-shrink-0 mt-1">
                  <CompletenessRing items={canvasItems} />
                </div>
              </div>
            )}

            {/* ── Color palette row ─────────────────────────────────────────── */}
            {canvasItems.length > 0 && (
              <ColorPaletteRow items={canvasItems} />
            )}

            {/* ── Droppable canvas ──────────────────────────────────────────── */}
            <OutfitDroppable>
              {canvasItems.length === 0 ? (
                <div aria-label="Outfit canvas — drag items here">
                  <SmartStartBanner onPick={handleSmartStart} />
                </div>
              ) : (
                <SortableContext
                  items={canvasItems.map(item => item.canvasId)}
                  strategy={rectSortingStrategy}
                >
                  <div className="flex flex-wrap gap-4 p-1">
                    {canvasItems.map(item => (
                      <SortableImageTile
                        key={item.canvasId}
                        item={item}
                        occasion={occasion}
                        currentMonth={currentMonth}
                        weatherCold={weatherCold}
                        onRemove={id => {
                          setCanvasItems(prev => prev.filter(i => i.canvasId !== id))
                          setAnalysis(null)
                          setAnalysisError(null)
                        }}
                      />
                    ))}
                  </div>
                </SortableContext>
              )}
            </OutfitDroppable>

            <div className="grid gap-3">
              <input
                className="input"
                placeholder="Outfit name"
                value={name}
                onChange={event => setName(event.target.value)}
              />

              {/* ── Occasion pills ─────────────────────────────────────────── */}
              <div>
                <label className="mb-1.5 block text-xs font-semibold text-slate-500 dark:text-slate-400 uppercase tracking-wide">Occasion</label>
                <div className="flex flex-wrap gap-2">
                  {OCCASIONS.map(occ => (
                    <button
                      key={occ}
                      type="button"
                      onClick={() => { setOccasion(occ); setAnalysis(null); setAnalysisError(null) }}
                      className={cn(
                        'rounded-full px-3 py-1.5 text-xs font-semibold capitalize transition-all',
                        occasion === occ
                          ? 'bg-brand-600 text-white shadow-sm'
                          : 'bg-slate-100 dark:bg-slate-800 text-slate-600 dark:text-slate-300 hover:bg-slate-200 dark:hover:bg-slate-700',
                      )}
                    >
                      {occ}
                    </button>
                  ))}
                </div>
              </div>

              {/* ── Context toggle ────────────────────────────────────────── */}
              <button
                type="button"
                onClick={() => setShowContext(v => !v)}
                className="flex items-center gap-2 self-start text-xs font-semibold text-slate-500 dark:text-slate-400 hover:text-brand-500 transition-colors"
              >
                {showContext ? <ChevronUp size={13} /> : <ChevronDown size={13} />}
                {showContext ? 'Hide context' : 'Add context'}
                {[mood, date.trim(), location.trim(), notes.trim()].filter(Boolean).length > 0 && (
                  <span className="rounded-full bg-brand-500 text-white text-[9px] px-1.5 py-0.5 leading-none">
                    {[mood, date.trim(), location.trim(), notes.trim()].filter(Boolean).length}
                  </span>
                )}
              </button>

              {showContext && (<>
              <div>
                <label className="mb-1.5 block text-xs font-semibold text-slate-500 dark:text-slate-400 uppercase tracking-wide">Time of Day</label>
                <div className="grid grid-cols-4 gap-2">
                  {TIME_OPTIONS.map(t => (
                    <button
                      key={t.value}
                      type="button"
                      onClick={() => { setTimeOfDay(t.value); setAutoTime(false) }}
                      title={t.hint}
                      className={cn(
                        'flex flex-col items-center gap-1 rounded-2xl border py-2 text-[11px] font-semibold transition-all',
                        timeOfDay === t.value
                          ? 'border-amber-400 bg-amber-50 dark:bg-amber-500/10 text-amber-700 dark:text-amber-300'
                          : 'border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 text-slate-500 dark:text-slate-400 hover:border-amber-300',
                      )}
                    >
                      <span className={timeOfDay === t.value ? 'text-amber-500' : 'text-slate-400'}>{t.icon}</span>
                      {t.label}
                      {timeOfDay === t.value && autoTime && (
                        <span className="text-[8px] text-amber-400 font-normal leading-none">auto</span>
                      )}
                    </button>
                  ))}
                </div>
              </div>

              {/* ── Mood ───────────────────────────────────────────────────── */}
              <div>
                <label className="mb-1.5 flex items-center gap-1.5 text-xs font-semibold text-slate-500 dark:text-slate-400 uppercase tracking-wide">
                  <Smile size={12} /> Mood <span className="font-normal normal-case text-slate-400">(optional)</span>
                </label>
                <div className="flex flex-wrap gap-2">
                  {MOOD_OPTIONS.map(m => (
                    <button
                      key={m.value}
                      type="button"
                      onClick={() => setMood(prev => prev === m.value ? null : m.value)}
                      className={cn(
                        'flex items-center gap-1.5 rounded-full px-3 py-1.5 text-xs font-semibold transition-all',
                        mood === m.value
                          ? 'bg-brand-600 text-white shadow-sm'
                          : 'bg-slate-100 dark:bg-slate-800 text-slate-600 dark:text-slate-300 hover:bg-brand-50 dark:hover:bg-brand-500/10 hover:text-brand-700 dark:hover:text-brand-300',
                      )}
                    >
                      <span>{m.emoji}</span>{m.label}
                    </button>
                  ))}
                </div>
              </div>

              {/* ── Date + Location ────────────────────────────────────────── */}
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="mb-1 block text-xs font-medium text-slate-500 dark:text-slate-400">Date (optional)</label>
                  <input
                    type="date"
                    className="input"
                    value={date}
                    onChange={event => { setDate(event.target.value); setAnalysis(null) }}
                  />
                </div>
                <div>
                  <label className="mb-1 block text-xs font-medium text-slate-500 dark:text-slate-400">Location (optional)</label>
                  <input
                    className="input"
                    placeholder="e.g. Tokyo"
                    value={location}
                    onChange={event => {
                      setLocation(event.target.value)
                      setWeather(null)
                      setAnalysis(null)
                      // manual entry — trigger a fetch
                    }}
                  />
                </div>
              </div>

              {/* Weather status pill */}
              {weather && location && !fetchingWeather && (
                <div className="flex items-center gap-2 rounded-xl border border-sky-200 bg-sky-50 px-3 py-2 text-xs text-sky-700 dark:border-sky-500/30 dark:bg-sky-500/10 dark:text-sky-300">
                  <CloudSun size={13} className="flex-shrink-0" />
                  <WeatherIcon condition={weather.condition} />
                  <span><strong>{weather.condition}</strong>{weather.temp_c !== 0 && ` · ${Math.round(weather.temp_c)}°C`}</span>
                  <span className="text-sky-500">for <strong>{location}</strong> — factored into AI analysis</span>
                </div>
              )}
              {!currentUser?.permissions?.location && !location && (
                <p className="text-[11px] text-slate-400 dark:text-slate-500 flex items-center gap-1">
                  <MapPin size={10} />
                  <a href="/profile?tab=settings" className="underline hover:text-brand-500 transition-colors">
                    Enable location in Profile
                  </a>
                  {' '}for automatic weather-aware styling
                </p>
              )}

              <textarea
                className="input min-h-16"
                placeholder="Notes (optional)"
                maxLength={500}
                value={notes}
                onChange={event => setNotes(event.target.value)}
              />
              </>)}

              {/* ── Mismatch warning ───────────────────────────────────────── */}
              {canvasItems.length > 0 && (() => {
                const mismatches = canvasItems.filter(i => !itemMatchesOccasion(i, occasion))
                if (mismatches.length === 0) return null
                return (
                  <div className="flex items-start gap-2 rounded-xl border border-amber-200 bg-amber-50 dark:border-amber-500/30 dark:bg-amber-500/10 px-3 py-2 text-xs text-amber-700 dark:text-amber-300">
                    <Zap size={13} className="mt-0.5 flex-shrink-0 text-amber-500" />
                    <span>
                      <strong>{mismatches.map(i => i.name).join(', ')}</strong>
                      {mismatches.length === 1 ? ' isn\'t' : ' aren\'t'} tagged for <strong>{occasion}</strong> — consider swapping or run AI analysis to confirm.
                    </span>
                  </div>
                )
              })()}

              {/* ── Action buttons ─────────────────────────────────────────── */}
              <div className="flex flex-wrap gap-3">
                <button
                  className="btn-primary"
                  disabled={!name.trim() || canvasItems.length === 0}
                  onClick={save}
                >
                  Save Outfit
                </button>

                <button
                  className="flex items-center gap-2 rounded-2xl bg-gradient-to-r from-brand-500 to-brand-600 px-4 py-2.5 text-sm font-semibold text-white shadow transition hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-50"
                  disabled={canvasItems.length === 0 || analyzing}
                  onClick={analyzeWithAI}
                >
                  {analyzing ? (
                    <><Loader2 size={15} className="animate-spin" /> Analyzing…</>
                  ) : (
                    <><Sparkles size={15} /> Analyze with AI</>
                  )}
                </button>

                <button
                  className="flex items-center gap-2 rounded-2xl border border-emerald-300 dark:border-emerald-500/40 bg-white dark:bg-slate-800 px-4 py-2.5 text-sm font-semibold text-emerald-700 dark:text-emerald-400 hover:bg-emerald-50 dark:hover:bg-emerald-500/10 transition disabled:opacity-40 disabled:cursor-not-allowed"
                  disabled={canvasItems.length === 0 || shuffling || analyzing}
                  onClick={shuffleCurrentOutfit}
                  title="Get alternative outfit combinations"
                >
                  {shuffling ? (
                    <><Loader2 size={15} className="animate-spin" /> Shuffling…</>
                  ) : (
                    <><RefreshCw size={15} /> Shuffle</>
                  )}
                </button>

                {confirmClear ? (
                  <>
                    <button
                      className="rounded-2xl bg-red-500 px-4 py-2.5 text-sm font-semibold text-white hover:bg-red-600 transition"
                      onClick={() => clear()}
                    >
                      Yes, clear
                    </button>
                    <button className="btn-secondary" onClick={() => setConfirmClear(false)}>
                      Cancel
                    </button>
                  </>
                ) : (
                  <button
                    className="btn-secondary"
                    onClick={() => canvasItems.length > 0 ? setConfirmClear(true) : clear()}
                  >
                    Clear
                  </button>
                )}
              </div>

              {/* View AI Insights button */}
              {hasInsights && !drawerOpen && (
                <button
                  onClick={() => setDrawerOpen(true)}
                  className="flex items-center justify-center gap-2 w-full rounded-2xl border border-brand-300 dark:border-brand-500/40 bg-brand-50 dark:bg-brand-900/20 px-4 py-2.5 text-sm font-semibold text-brand-700 dark:text-brand-400 hover:bg-brand-100 dark:hover:bg-brand-500/20 transition"
                >
                  <Sparkles size={15} />
                  View AI Insights
                  {analysis && (
                    <span
                      className="ml-1 rounded-full text-white text-xs px-2 py-0.5 font-bold"
                      style={{ backgroundColor: scoreColor(analysis.outfit.matching_score) }}
                    >
                      {analysis.outfit.matching_score}/100
                    </span>
                  )}
                </button>
              )}
            </div>
          </section>
        </div>

        <DragOverlay>
          {activeItem ? (
            <div className="w-36 rounded-2xl border border-cream-200 bg-white p-2 shadow-card-hover dark:border-white/10 dark:bg-slate-900">
              <div className="aspect-square overflow-hidden rounded-xl bg-cream-100 dark:bg-slate-800">
                {itemImage(activeItem)}
              </div>
              <p className="mt-2 truncate text-xs font-semibold">{activeItem.name}</p>
            </div>
          ) : null}
        </DragOverlay>
      </DndContext>


      {/* ── AI Results Drawer ─────────────────────────────────────────────── */}
      <>
        {/* Backdrop */}
        {drawerOpen && (
          <div
            className="fixed inset-0 bg-black/20 z-40"
            onClick={() => setDrawerOpen(false)}
          />
        )}

        {/* Slide-in panel */}
        <div
          className={cn(
            'fixed top-0 right-0 h-full w-full sm:w-[460px] max-w-[92vw]',
            'bg-white dark:bg-slate-900 shadow-2xl z-50 flex flex-col',
            'transition-transform duration-300 ease-out',
            drawerOpen ? 'translate-x-0' : 'translate-x-full',
          )}
        >
          {/* Drawer header */}
          <div className="flex items-center justify-between px-5 py-4 border-b border-slate-100 dark:border-slate-800 sticky top-0 bg-white dark:bg-slate-900 z-10 flex-shrink-0">
            <div className="flex items-center gap-2.5">
              <div className="w-8 h-8 rounded-xl bg-gradient-to-br from-brand-500 to-brand-600 flex items-center justify-center flex-shrink-0">
                <Sparkles size={15} className="text-white" />
              </div>
              <div>
                <p className="font-bold text-slate-800 dark:text-white text-sm">AI Outfit Insights</p>
                {analysis && (
                  <p className="text-[11px] text-slate-400">
                    Score: <span className="font-bold" style={{ color: scoreColor(analysis.outfit.matching_score) }}>
                      {analysis.outfit.matching_score}/100
                    </span>
                    {' · '}{scoreLabel(analysis.outfit.matching_score)}
                  </p>
                )}
              </div>
            </div>
            <button
              onClick={() => setDrawerOpen(false)}
              className="flex h-8 w-8 items-center justify-center rounded-lg text-slate-400 hover:bg-slate-100 dark:hover:bg-slate-800 transition-colors"
            >
              <X size={16} />
            </button>
          </div>

          {/* Drawer scrollable content */}
          <div className="flex-1 overflow-y-auto p-5 space-y-5">
            {/* Loading states */}
            {analyzing && (
              <div className="flex items-center gap-3 rounded-2xl border border-brand-200 bg-brand-50 px-4 py-3 text-sm text-brand-700 dark:border-brand-500/30 dark:bg-brand-500/10 dark:text-brand-300">
                <Loader2 size={15} className="animate-spin flex-shrink-0" />
                Analyzing your outfit with AI…
              </div>
            )}
            {shuffling && (
              <div className="flex items-center gap-3 rounded-2xl border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm text-emerald-700 dark:border-emerald-500/30 dark:bg-emerald-500/10 dark:text-emerald-300">
                <Loader2 size={15} className="animate-spin flex-shrink-0" />
                Finding alternative outfit combinations…
              </div>
            )}

            {/* Errors */}
            {analysisError && (
              <div className="flex items-start gap-2 rounded-2xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700 dark:border-red-500/30 dark:bg-red-500/10 dark:text-red-300">
                <AlertCircle size={15} className="mt-0.5 flex-shrink-0" />
                {analysisError}
              </div>
            )}
            {shuffleError && (
              <div className="flex items-start gap-2 rounded-2xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-700 dark:border-amber-500/30 dark:bg-amber-500/10 dark:text-amber-300">
                <AlertCircle size={15} className="mt-0.5 flex-shrink-0" />
                {shuffleError}
              </div>
            )}

            {/* Analysis panel */}
            {analysis && (
              <AIAnalysisPanel
                analysis={analysis}
                onClose={() => setAnalysis(null)}
              />
            )}

            {/* Suggested pairings */}
            {analysis?.suggested_pairings_error && suggestedPairings.length === 0 && (
              <p className="text-[11px] text-slate-400 dark:text-slate-500 flex items-center gap-1.5 px-1">
                <AlertCircle size={11} className="flex-shrink-0" />
                Could not load pairing suggestions — try again after re-analyzing.
              </p>
            )}
            {analysis && suggestedPairings.length > 0 && (
              <SuggestedPairingsShelf
                pairings={suggestedPairings}
                alreadyAddedIds={addedIds}
                onAdd={item => { addSuggestedToCanvas(item) }}
              />
            )}

            {/* Shuffle alternatives */}
            {shuffleAlternatives.length > 0 && (
              <ShuffleAlternativesShelf
                alternatives={shuffleAlternatives}
                onApply={alt => { applyShuffleAlternative(alt) }}
                onClose={() => setShuffleAlternatives([])}
              />
            )}

            {/* Empty state */}
            {!analyzing && !shuffling && !analysis && shuffleAlternatives.length === 0 && !analysisError && !shuffleError && (
              <div className="flex flex-col items-center justify-center gap-3 py-16 text-center">
                <div className="w-16 h-16 rounded-2xl bg-brand-50 dark:bg-brand-900/30 flex items-center justify-center">
                  <Sparkles size={28} className="text-brand-400" />
                </div>
                <p className="text-sm font-semibold text-slate-600 dark:text-slate-300">No insights yet</p>
                <p className="text-xs text-slate-400 max-w-[200px] leading-relaxed">
                  Build your outfit then hit "Analyze with AI" or "Shuffle" to get recommendations
                </p>
              </div>
            )}
          </div>
        </div>
      </>
    </div>
  )
}
