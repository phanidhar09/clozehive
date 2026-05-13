import { useMemo, useState } from 'react'
import {
  closestCenter,
  DndContext,
  DragOverlay,
  PointerSensor,
  useDraggable,
  useDroppable,
  useSensor,
  useSensors,
  type DragEndEvent,
  type DragStartEvent,
} from '@dnd-kit/core'
import {
  arrayMove,
  SortableContext,
  useSortable,
  horizontalListSortingStrategy,
} from '@dnd-kit/sortable'
import { CSS } from '@dnd-kit/utilities'
import {
  AlertCircle,
  Check,
  ChevronDown,
  ChevronUp,
  CloudSun,
  Lightbulb,
  Loader2,
  Ruler,
  Search,
  Sparkles,
  TrendingUp,
  Wand2,
  X,
} from 'lucide-react'
import { useApp } from '@/store'
import { outfitsApi } from '@/lib/api'
import type { ClosetItem, OutfitAnalysis, ScoreBreakdown } from '@/types'

const CANONICAL_TAB_CATEGORIES = new Set([
  'tops', 'bottoms', 'shoes', 'outerwear', 'dresses', 'accessories',
])

const CATEGORIES = ['all', 'tops', 'bottoms', 'shoes', 'outerwear', 'dresses', 'accessories', 'other'] as const
const OCCASIONS = ['casual', 'business', 'formal', 'sport', 'beach', 'date-night']

type CanvasItem = ClosetItem & { canvasId: string }

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
  { key: 'style',      label: 'Style Consistency',    max: 15 },
  { key: 'weather',    label: 'Weather Suitability',  max: 10 },
  { key: 'preference', label: 'Preference Match',     max: 5  },
]

// ── Small reusable components ──────────────────────────────────────────────────

function itemImage(item: ClosetItem, className = 'h-full w-full object-cover') {
  return item.image_url
    ? <img src={item.image_url} alt={item.name} className={className} />
    : <div className="flex h-full w-full items-center justify-center text-2xl">👕</div>
}

function ClosetDraggableCard({ item, added }: { item: ClosetItem; added: boolean }) {
  const { attributes, listeners, setNodeRef, transform, isDragging } = useDraggable({
    id: `closet:${item.id}`,
    data: { item },
  })

  return (
    <button
      ref={setNodeRef}
      {...attributes}
      {...listeners}
      className="relative rounded-2xl border border-cream-200 bg-white text-left shadow-card transition hover:-translate-y-0.5 hover:shadow-card-hover dark:border-white/10 dark:bg-white/[0.04]"
      style={{ transform: transform ? CSS.Translate.toString(transform) : undefined, opacity: isDragging ? 0.45 : 1 }}
    >
      <div className="aspect-square overflow-hidden rounded-t-2xl bg-cream-100 dark:bg-slate-800">
        {itemImage(item)}
      </div>
      <div className="p-3">
        <p className="truncate text-sm font-semibold text-slate-800 dark:text-white">{item.name}</p>
        <p className="text-xs capitalize text-slate-500 dark:text-white/40">{item.category}</p>
      </div>
      {added && (
        <div className="absolute right-2 top-2 rounded-full bg-emerald-500 p-1 text-white shadow">
          <Check size={14} />
        </div>
      )}
    </button>
  )
}

function OutfitDroppable({ children }: { children: React.ReactNode }) {
  const { setNodeRef, isOver } = useDroppable({ id: 'outfit-canvas' })
  return (
    <div
      ref={setNodeRef}
      className={`min-h-48 rounded-3xl border-2 border-dashed p-4 transition ${
        isOver
          ? 'border-brand-500 bg-brand-50 dark:bg-brand-500/10'
          : 'border-cream-300 bg-white/70 dark:border-white/10 dark:bg-white/[0.04]'
      }`}
    >
      {children}
    </div>
  )
}

function SortableChip({ item, onRemove }: { item: CanvasItem; onRemove: (id: string) => void }) {
  const { attributes, listeners, setNodeRef, transform, transition, isDragging } = useSortable({ id: item.canvasId })
  return (
    <div
      ref={setNodeRef}
      style={{ transform: CSS.Transform.toString(transform), transition, opacity: isDragging ? 0.5 : 1 }}
      className="flex items-center gap-2 rounded-2xl border border-cream-200 bg-white p-2 shadow-card dark:border-white/10 dark:bg-slate-900"
    >
      <button {...attributes} {...listeners} className="flex min-w-0 flex-1 items-center gap-2 text-left">
        <div className="h-10 w-10 flex-shrink-0 overflow-hidden rounded-xl bg-cream-100 dark:bg-slate-800">
          {itemImage(item)}
        </div>
        <span className="truncate text-sm font-medium text-slate-800 dark:text-white">{item.name}</span>
      </button>
      <button
        onClick={() => onRemove(item.canvasId)}
        className="flex h-8 w-8 items-center justify-center rounded-lg text-slate-400 hover:bg-red-50 hover:text-red-500 dark:hover:bg-red-500/10"
        aria-label={`Remove ${item.name}`}
      >
        <X size={15} />
      </button>
    </div>
  )
}

// ── Score circle (SVG arc) ─────────────────────────────────────────────────────

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

function RecommendationSection({
  icon,
  title,
  items,
  colorClass,
}: {
  icon: React.ReactNode
  title: string
  items: string[]
  colorClass: string
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

export function AIAnalysisPanel({
  analysis,
  onClose,
}: {
  analysis: OutfitAnalysis
  onClose: () => void
}) {
  const { outfit, missing_pieces, style_tips } = analysis
  const {
    matching_score,
    score_breakdown,
    recommendations,
    reasoning,
    confidence,
    fit_notes,
    fit_confidence,
    occasion_match,
    style_match,
    size_profile_match,
    body_profile_notes,
    why_it_works,
    what_to_improve,
  } = outfit
  const [tipsOpen, setTipsOpen] = useState(false)

  return (
    <div className="rounded-3xl border border-brand-200 bg-white/90 shadow-card-hover dark:border-brand-500/30 dark:bg-slate-900/90">
      {/* Header */}
      <div className="flex items-center justify-between border-b border-slate-100 px-5 py-4 dark:border-slate-800">
        <div className="flex items-center gap-2">
          <Sparkles size={18} className="text-brand-500" />
          <span className="font-display text-base font-bold text-slate-800 dark:text-white">
            AI Outfit Analysis
          </span>
          {confidence != null && (
            <span className="rounded-full bg-slate-100 px-2 py-0.5 text-xs text-slate-500 dark:bg-slate-800 dark:text-slate-400">
              {Math.round(confidence * 100)}% confidence
            </span>
          )}
        </div>
        <button
          onClick={onClose}
          className="flex h-8 w-8 items-center justify-center rounded-lg text-slate-400 hover:bg-slate-100 hover:text-slate-600 dark:hover:bg-slate-800"
          aria-label="Close analysis"
        >
          <X size={15} />
        </button>
      </div>

      <div className="p-5">
        {/* Score + breakdown grid */}
        <div className="grid gap-6 sm:grid-cols-[auto_1fr]">
          <ScoreCircle score={matching_score} />
          <ScoreBars breakdown={score_breakdown} />
        </div>

        {(fit_confidence != null ||
          occasion_match ||
          style_match ||
          size_profile_match) && (
          <div className="mt-4 grid gap-2 sm:grid-cols-2">
            {fit_confidence != null && (
              <div className="rounded-2xl border border-slate-100 bg-white/80 px-4 py-3 text-sm dark:border-slate-800 dark:bg-slate-800/40">
                <span className="text-xs font-semibold text-slate-500 dark:text-slate-400">Fit confidence</span>
                <p className="text-lg font-bold text-slate-800 dark:text-white">{fit_confidence}%</p>
              </div>
            )}
            {occasion_match && (
              <div className="rounded-2xl border border-slate-100 bg-white/80 px-4 py-3 text-sm dark:border-slate-800 dark:bg-slate-800/40">
                <span className="text-xs font-semibold text-slate-500 dark:text-slate-400">Occasion match</span>
                <p className="font-semibold text-slate-800 dark:text-white">{occasion_match}</p>
              </div>
            )}
            {style_match && (
              <div className="rounded-2xl border border-slate-100 bg-white/80 px-4 py-3 text-sm dark:border-slate-800 dark:bg-slate-800/40">
                <span className="text-xs font-semibold text-slate-500 dark:text-slate-400">Style match</span>
                <p className="font-semibold text-slate-800 dark:text-white">{style_match}</p>
              </div>
            )}
            {size_profile_match && (
              <div className="rounded-2xl border border-slate-100 bg-white/80 px-4 py-3 text-sm dark:border-slate-800 dark:bg-slate-800/40">
                <span className="text-xs font-semibold text-slate-500 dark:text-slate-400">Size profile match</span>
                <p className="font-semibold text-slate-800 dark:text-white">{size_profile_match}</p>
              </div>
            )}
          </div>
        )}

        {/* Reasoning */}
        {reasoning && (
          <div className="mt-5 rounded-2xl border border-slate-100 bg-slate-50 px-4 py-3 text-sm text-slate-600 dark:border-slate-800 dark:bg-slate-800/60 dark:text-slate-400">
            <span className="font-semibold text-slate-700 dark:text-slate-300">Stylist&rsquo;s take: </span>
            {reasoning}
          </div>
        )}

        {(body_profile_notes || fit_notes) && (
          <div className="mt-3 flex items-start gap-2.5 rounded-2xl border border-brand-100 bg-brand-50/60 px-4 py-3 text-sm text-brand-700 dark:border-brand-500/20 dark:bg-brand-500/[0.07] dark:text-brand-300">
            <Ruler size={14} className="mt-0.5 flex-shrink-0 text-brand-500 dark:text-brand-400" aria-hidden="true" />
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
              {what_to_improve.map((w, i) => (
                <li key={i}>{w}</li>
              ))}
            </ul>
          </div>
        )}

        {/* Recommendations */}
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

        {/* Missing pieces */}
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

        {/* General style tips (collapsible) */}
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

// ── Main page ─────────────────────────────────────────────────────────────────

export default function OutfitBuilder() {
  const { closetItems } = useApp()
  const [query, setQuery] = useState('')
  const [category, setCategory] = useState<(typeof CATEGORIES)[number]>('all')
  const [canvasItems, setCanvasItems] = useState<CanvasItem[]>([])
  const [activeItem, setActiveItem] = useState<ClosetItem | null>(null)
  const [name, setName] = useState('')
  const [occasion, setOccasion] = useState('casual')
  const [notes, setNotes] = useState('')
  const [browserOpen, setBrowserOpen] = useState(false)
  const [toast, setToast] = useState<{ type: 'success' | 'error'; message: string } | null>(null)

  const [date, setDate] = useState('')
  const [location, setLocation] = useState('')
  const [weather, setWeather] = useState<{ condition: string; temp_c: number } | null>(null)

  // AI analysis state
  const [analyzing, setAnalyzing] = useState(false)
  const [analysis, setAnalysis] = useState<OutfitAnalysis | null>(null)
  const [analysisError, setAnalysisError] = useState<string | null>(null)

  const sensors = useSensors(useSensor(PointerSensor, { activationConstraint: { distance: 6 } }))

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase()
    return closetItems.filter(item => {
      let matchesCategory = category === 'all'
      if (!matchesCategory) {
        if (category === 'other') {
          matchesCategory =
            item.category === 'other'
            || item.category === 'uncategorised'
            || !CANONICAL_TAB_CATEGORIES.has(item.category)
        } else {
          matchesCategory = item.category === category
        }
      }
      const matchesSearch = !q || item.name.toLowerCase().includes(q) || item.category.toLowerCase().includes(q)
      return matchesCategory && matchesSearch
    })
  }, [closetItems, query, category])

  const addedIds = new Set(canvasItems.map(item => item.id))

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
        // Clear previous analysis whenever the canvas changes.
        setAnalysis(null)
        setAnalysisError(null)
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
    setCanvasItems([])
    setName('')
    setOccasion('casual')
    setNotes('')
    setDate('')
    setLocation('')
    setWeather(null)
    setAnalysis(null)
    setAnalysisError(null)
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
      setToast({ type: 'success', message: 'Outfit saved!' })
      clear()
    } catch {
      setToast({ type: 'error', message: 'Failed to save outfit. Please try again.' })
    }
  }

  const analyzeWithAI = async () => {
    if (canvasItems.length === 0) return
    setAnalyzing(true)
    setAnalysis(null)
    setAnalysisError(null)
    setWeather(null)
    try {
      const payload: Parameters<typeof outfitsApi.analyze>[0] = {
        item_ids: canvasItems.map(item => item.id),
        occasion,
        ...(date && { date }),
        ...(location.trim() && { location: location.trim() }),
      }
      const result = await outfitsApi.analyze(payload)
      setAnalysis(result)
      // Surface the weather that was used so the user knows what context the AI had
      if (location.trim()) {
        setWeather({ condition: 'Live weather used', temp_c: 0 })
      }
    } catch (err) {
      setAnalysisError(err instanceof Error ? err.message : 'AI analysis failed. Please try again.')
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
        {filtered.map(item => <ClosetDraggableCard key={item.id} item={item} added={addedIds.has(item.id)} />)}
      </div>
    </div>
  )

  // Gate: require at least 5 items before the builder is useful
  if (closetItems.length < 5) {
    return (
      <div className="flex max-w-2xl flex-col items-center gap-4 rounded-3xl border border-cream-200 bg-white/70 p-10 text-center shadow-card dark:border-white/10 dark:bg-white/[0.04]">
        <div className="flex h-14 w-14 items-center justify-center rounded-2xl bg-brand-50 text-brand-500 dark:bg-brand-500/10">
          <Wand2 size={26} />
        </div>
        <h3 className="font-display text-lg font-bold text-slate-800 dark:text-white">You need at least 5 items to generate outfits</h3>
        <p className="text-sm text-slate-500 dark:text-slate-400">Add a few more pieces so CLOZEHIVE can create better outfit combinations for your style, size, weather, and occasions.</p>
        <div className="flex gap-3">
          <a href="/upload" className="btn-primary">Add More Items</a>
          <a href="/closet" className="btn-secondary">View Closet</a>
        </div>
      </div>
    )
  }

  return (
    <div className="space-y-5">
      <div>
        <h2 className="font-display text-xl font-bold text-slate-800 dark:text-slate-100">Outfit Builder</h2>
        <p className="text-sm text-slate-400">
          Drag pieces from your closet onto the canvas, then hit{' '}
          <span className="font-medium text-brand-500">Analyze with AI</span> for a detailed matching score.
        </p>
      </div>

      {toast && (
        <div
          className={`rounded-2xl border p-3 text-sm ${
            toast.type === 'success'
              ? 'border-emerald-200 bg-emerald-50 text-emerald-700 dark:border-emerald-500/30 dark:bg-emerald-500/10 dark:text-emerald-300'
              : 'border-red-200 bg-red-50 text-red-700 dark:border-red-500/30 dark:bg-red-500/10 dark:text-red-300'
          }`}
        >
          {toast.message}
        </div>
      )}

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
            <OutfitDroppable>
              {canvasItems.length === 0 ? (
                <div
                  className="flex min-h-40 flex-col items-center justify-center gap-2 rounded-2xl border border-dashed border-slate-200 dark:border-white/10 py-8 text-center"
                  aria-label="Outfit canvas — drag items here"
                >
                  <Sparkles size={22} className="text-brand-400/60 dark:text-brand-500/40" aria-hidden="true" />
                  <p className="text-sm font-medium text-slate-500 dark:text-white/40">
                    Drag pieces from your closet to build a look
                  </p>
                  <p className="text-xs text-slate-400 dark:text-white/25">
                    Mix and match — then hit <span className="font-semibold text-brand-500">Analyze with AI</span>
                  </p>
                </div>
              ) : (
                <SortableContext
                  items={canvasItems.map(item => item.canvasId)}
                  strategy={horizontalListSortingStrategy}
                >
                  <div className="flex flex-wrap gap-3">
                    {canvasItems.map(item => (
                      <SortableChip
                        key={item.canvasId}
                        item={item}
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
              <select
                className="input"
                value={occasion}
                onChange={event => {
                  setOccasion(event.target.value)
                  setAnalysis(null)
                  setAnalysisError(null)
                }}
              >
                {OCCASIONS.map(value => <option key={value} value={value}>{value}</option>)}
              </select>

              {/* Date + Location for weather-aware analysis */}
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="mb-1 block text-xs font-medium text-slate-500 dark:text-slate-400">
                    Date (optional)
                  </label>
                  <input
                    type="date"
                    className="input"
                    value={date}
                    onChange={event => { setDate(event.target.value); setAnalysis(null) }}
                  />
                </div>
                <div>
                  <label className="mb-1 block text-xs font-medium text-slate-500 dark:text-slate-400">
                    Location (optional)
                  </label>
                  <input
                    className="input"
                    placeholder="e.g. Tokyo"
                    value={location}
                    onChange={event => { setLocation(event.target.value); setWeather(null); setAnalysis(null) }}
                  />
                </div>
              </div>

              {/* Weather badge shown after analysis when location was provided */}
              {weather && location && (
                <div className="flex items-center gap-2 rounded-xl border border-sky-200 bg-sky-50 px-3 py-2 text-xs text-sky-700 dark:border-sky-500/30 dark:bg-sky-500/10 dark:text-sky-300">
                  <CloudSun size={13} className="flex-shrink-0" />
                  Live weather for <span className="font-semibold">{location}</span> was used for this analysis
                </div>
              )}

              <textarea
                className="input min-h-24"
                placeholder="Notes (optional)"
                maxLength={500}
                value={notes}
                onChange={event => setNotes(event.target.value)}
              />

              {/* Action buttons */}
              <div className="flex flex-wrap gap-3">
                <button
                  className="btn-primary"
                  disabled={!name.trim() || canvasItems.length === 0}
                  onClick={save}
                >
                  Save Outfit
                </button>

                <button
                  className="flex items-center gap-2 rounded-2xl bg-gradient-to-r from-brand-500 to-violet-500 px-4 py-2.5 text-sm font-semibold text-white shadow transition hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-50"
                  disabled={canvasItems.length === 0 || analyzing}
                  onClick={analyzeWithAI}
                >
                  {analyzing ? (
                    <>
                      <Loader2 size={15} className="animate-spin" />
                      Analyzing…
                    </>
                  ) : (
                    <>
                      <Sparkles size={15} />
                      Analyze with AI
                    </>
                  )}
                </button>

                <button className="btn-secondary" onClick={clear}>
                  Clear
                </button>
              </div>
            </div>

            {/* Inline error */}
            {analysisError && (
              <div className="flex items-start gap-2 rounded-2xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700 dark:border-red-500/30 dark:bg-red-500/10 dark:text-red-300">
                <AlertCircle size={15} className="mt-0.5 flex-shrink-0" />
                {analysisError}
              </div>
            )}
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

      {/* AI Analysis Panel — rendered below the builder when available */}
      {analysis && (
        <AIAnalysisPanel analysis={analysis} onClose={() => setAnalysis(null)} />
      )}
    </div>
  )
}
