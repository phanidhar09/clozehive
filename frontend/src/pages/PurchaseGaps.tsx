import { useEffect, useMemo, useState } from 'react'
import {
  ShoppingBag, CheckCircle, CheckCircle2, AlertCircle, Loader2,
  RefreshCw, Trash2, ExternalLink, Filter,
} from 'lucide-react'
import { FaniLoader } from '@/components/system/FaniLoader'
import BackButton from '@/components/ui/BackButton'
import PageHeader from '@/components/ui/PageHeader'
import { purchaseGapsApi, type PurchaseGap } from '@/lib/api'
import { cn } from '@/lib/utils'

type Level = 'high' | 'medium' | 'low'

const PRIORITY: Record<Level, {
  label: string
  dot: string
  bar: string
  pill: string
  badge: string
}> = {
  high: {
    label: 'High',
    dot:   'bg-red-500',
    bar:   'bg-red-500',
    pill:  'bg-red-50 text-red-700 dark:bg-red-900/30 dark:text-red-300',
    badge: 'bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-300',
  },
  medium: {
    label: 'Medium',
    dot:   'bg-highlight-500',
    bar:   'bg-highlight-500',
    pill:  'bg-highlight-50 text-highlight-600 dark:bg-amber-900/30 dark:text-amber-300',
    badge: 'bg-highlight-100 text-highlight-600 dark:bg-amber-900/30 dark:text-amber-300',
  },
  low: {
    label: 'Low',
    dot:   'bg-slate-400',
    bar:   'bg-slate-400',
    pill:  'bg-slate-100 text-slate-600 dark:bg-white/10 dark:text-white/60',
    badge: 'bg-slate-100 text-slate-600 dark:bg-white/10 dark:text-white/60',
  },
}

const GAP_TYPE_LABEL: Record<PurchaseGap['gap_type'], string> = {
  outfit:       'Outfit gap',
  trip_packing: 'Trip packing',
  seasonal:     'Seasonal',
  occasion:     'Occasion',
  structural:   'Wardrobe structure',
  proportion:   'Proportion balance',
}

function priorityLabel(score: number | null): Level {
  if (score == null) return 'low'
  if (score >= 7) return 'high'
  if (score >= 4) return 'medium'
  return 'low'
}

const GENERIC_ATTR = new Set(['versatile', 'all-season', 'all', 'any', 'general'])

function gapItem(gap: PurchaseGap): string {
  const item = gap.suggested_attributes?.item
  if (typeof item === 'string' && item.trim()) return item.trim()
  return gap.missing_category || 'Unknown item'
}

function gapOutfitType(gap: PurchaseGap): string | null {
  const fromAttrs = gap.suggested_attributes?.outfit_type
  if (typeof fromAttrs === 'string' && fromAttrs.trim() && !GENERIC_ATTR.has(fromAttrs.trim().toLowerCase())) {
    return fromAttrs.trim()
  }
  if (gap.missing_occasion && !GENERIC_ATTR.has(gap.missing_occasion.trim().toLowerCase())) {
    return gap.missing_occasion.trim()
  }
  return null
}

/** Human meta line under the item: color · season. */
function metaLine(gap: PurchaseGap): string {
  return [gap.missing_color, gap.missing_season]
    .filter((p): p is string => Boolean(p) && !GENERIC_ATTR.has(String(p).toLowerCase()))
    .join(' · ')
}

/**
 * Build a natural-language product search from a gap's attributes so the user can
 * go find the missing item. Prefer the particular item phrase over bare category.
 */
function buildShopQuery(gap: PurchaseGap): string {
  const attrs = gap.suggested_attributes ?? {}
  const item = typeof attrs.item === 'string' ? attrs.item : null
  const color = typeof attrs.color === 'string' ? attrs.color : gap.missing_color
  const outfitType = gapOutfitType(gap)
  const parts = [
    item,
    !item ? color : null,
    !item ? gap.missing_category : null,
    outfitType,
    gap.missing_season ? `${gap.missing_season} wear` : null,
  ].filter((p): p is string => {
    if (typeof p !== 'string' || !p.trim()) return false
    return !GENERIC_ATTR.has(p.toLowerCase().trim())
  })
  return Array.from(new Set(parts.map(p => p.toLowerCase().trim()))).join(' ')
}

function shopUrl(gap: PurchaseGap): string {
  return `https://www.google.com/search?tbm=shop&q=${encodeURIComponent(buildShopQuery(gap))}`
}

/** Small stat tile in the summary strip. */
function StatTile({ value, label, dot }: { value: number; label: string; dot: string }) {
  return (
    <div className="rounded-2xl border border-cream-200/70 dark:border-white/[0.08] bg-white/70 dark:bg-white/[0.04] backdrop-blur-xl p-4 transition-all duration-200 hover:-translate-y-0.5 hover:border-cream-300 dark:hover:border-white/[0.14]">
      <div className="font-display font-bold text-2xl sm:text-[27px] leading-none text-slate-800 dark:text-white tabular-nums">
        {value}
      </div>
      <div className="flex items-center gap-2 mt-2.5">
        <span className={cn('w-1.5 h-1.5 rounded-full shrink-0', dot)} />
        <span className="text-xs text-slate-400 dark:text-white/40">{label}</span>
      </div>
    </div>
  )
}

function GapCard({ gap, onResolve, onDelete }: { gap: PurchaseGap; onResolve: (id: string) => void; onDelete: (id: string) => void }) {
  const [resolving, setResolving] = useState(false)
  const [deleting, setDeleting] = useState(false)
  const [confirmingDelete, setConfirmingDelete] = useState(false)
  const level = priorityLabel(gap.priority_score)
  const p = PRIORITY[level]
  const meta = metaLine(gap)

  const handleResolve = async () => {
    setResolving(true)
    try {
      await purchaseGapsApi.resolve(gap.id)
      onResolve(gap.id)
    } catch {
      setResolving(false)
    }
  }

  const handleDelete = async () => {
    if (!confirmingDelete) {
      setConfirmingDelete(true)
      setTimeout(() => setConfirmingDelete(false), 3000)
      return
    }
    setConfirmingDelete(false)
    setDeleting(true)
    try {
      await purchaseGapsApi.delete(gap.id)
      onDelete(gap.id)
    } catch {
      setDeleting(false)
    }
  }

  const itemLabel = gapItem(gap)
  const outfitType = gapOutfitType(gap)
  const attrs = gap.suggested_attributes
    ? Object.entries(gap.suggested_attributes).filter(([k, v]) => {
        if (v == null || String(v).length === 0) return false
        if (k === 'item' || k === 'outfit_type' || k === 'occasion') return false
        return !GENERIC_ATTR.has(String(v).toLowerCase())
      })
    : []

  return (
    <div className="group relative flex flex-col gap-3 overflow-hidden rounded-2xl border border-cream-200/70 dark:border-white/[0.08] bg-white/70 dark:bg-white/[0.04] backdrop-blur-xl p-4 sm:p-[18px] transition-all duration-300 hover:-translate-y-0.5 hover:border-cream-300 dark:hover:border-white/[0.14]">
      {/* priority accent bar */}
      <span className={cn('absolute left-0 top-0 bottom-0 w-[3px]', p.bar)} />

      {/* context label */}
      <div className="text-[10.5px] font-bold uppercase tracking-[0.09em] text-slate-400 dark:text-white/30">
        {GAP_TYPE_LABEL[gap.gap_type] ?? 'Wardrobe gap'}
        {gap.missing_category ? ` · ${gap.missing_category}` : ''}
      </div>

      {/* title + priority pill */}
      <div className="flex items-start justify-between gap-2.5">
        <div className="min-w-0">
          <p className="font-display font-semibold text-base sm:text-[16.5px] text-slate-800 dark:text-white capitalize leading-snug">
            {itemLabel}
          </p>
          {outfitType && (
            <p className="text-xs sm:text-[12.5px] text-brand-700 dark:text-brand-300 mt-1 font-medium capitalize">
              For {outfitType} outfits
            </p>
          )}
          {meta && (
            <p className="text-xs sm:text-[12.5px] text-slate-400 dark:text-white/40 mt-0.5 capitalize">{meta}</p>
          )}
        </div>
        <span className={cn('inline-flex items-center gap-1.5 text-[11px] font-semibold px-2.5 py-1 rounded-full whitespace-nowrap', p.pill)}>
          <span className={cn('w-1.5 h-1.5 rounded-full', p.dot)} />
          {p.label}
          {gap.priority_score != null && (
            <span className="opacity-65 tabular-nums">· {gap.priority_score.toFixed(1)}</span>
          )}
        </span>
      </div>

      {/* reason */}
      {gap.reason && (
        <p className="text-[13px] leading-relaxed text-slate-600 dark:text-white/60 text-pretty">{gap.reason}</p>
      )}

      {/* suggested attribute chips */}
      {attrs.length > 0 && (
        <div className="flex flex-wrap gap-1.5">
          {attrs.map(([k, v]) => (
            <span key={k} className="text-[11px] font-medium px-2 py-0.5 rounded-full bg-brand-50 dark:bg-brand-900/30 text-brand-700 dark:text-brand-300 capitalize">
              {k}: {String(v)}
            </span>
          ))}
        </div>
      )}

      {/* actions */}
      <div className="flex items-center gap-2 mt-0.5">
        <a
          href={shopUrl(gap)}
          target="_blank"
          rel="noopener noreferrer"
          className="mr-auto inline-flex items-center gap-1.5 text-[12.5px] font-semibold px-3.5 py-2 rounded-[10px]
                     text-white bg-gradient-to-r from-brand-500 to-brand-700
                     transition-all hover:brightness-110"
          title={`Search shops for "${buildShopQuery(gap)}"`}
        >
          <ShoppingBag size={13} />
          Shop this gap
          <ExternalLink size={12} className="opacity-70" />
        </a>
        <button
          onClick={handleResolve}
          disabled={resolving}
          title="Mark resolved"
          aria-label="Mark gap resolved"
          className="w-9 h-9 rounded-[10px] flex items-center justify-center border border-cream-300 dark:border-white/[0.1]
                     bg-white/60 dark:bg-white/[0.03] text-slate-400 dark:text-white/40
                     hover:bg-emerald-50 dark:hover:bg-emerald-900/20 hover:text-emerald-600 dark:hover:text-emerald-400 hover:border-emerald-200 dark:hover:border-emerald-800
                     transition-colors disabled:opacity-50"
        >
          {resolving ? <Loader2 size={15} className="animate-spin" /> : <CheckCircle2 size={15} />}
        </button>
        <button
          onClick={handleDelete}
          disabled={deleting}
          title={confirmingDelete ? 'Confirm delete' : 'Delete gap'}
          aria-label={confirmingDelete ? 'Confirm delete gap' : 'Delete gap'}
          className={cn(
            'w-9 h-9 rounded-[10px] flex items-center justify-center border transition-colors disabled:opacity-50',
            confirmingDelete
              ? 'bg-red-500 border-red-500 text-white'
              : 'border-cream-300 dark:border-white/[0.1] bg-white/60 dark:bg-white/[0.03] text-slate-400 dark:text-white/40 hover:bg-red-50 dark:hover:bg-red-900/20 hover:text-red-500 hover:border-red-200 dark:hover:border-red-800',
          )}
        >
          {deleting ? <Loader2 size={15} className="animate-spin" /> : <Trash2 size={15} />}
        </button>
      </div>
    </div>
  )
}

/** Priority section header: dot + label + count + divider. */
function SectionHeader({ level, count }: { level: Level; count: number }) {
  const p = PRIORITY[level]
  return (
    <div className="flex items-center gap-3 mb-4">
      <span className={cn('w-2.5 h-2.5 rounded-full', p.dot)} />
      <span className="font-display font-semibold text-[15px] text-slate-700 dark:text-white/80">{p.label} priority</span>
      <span className={cn('text-[11.5px] font-semibold px-2 py-0.5 rounded-full tabular-nums', p.badge)}>{count}</span>
      <span className="flex-1 h-px bg-cream-300/70 dark:bg-white/[0.08]" />
    </div>
  )
}

export default function PurchaseGaps() {
  const [gaps, setGaps] = useState<PurchaseGap[]>([])
  const [showResolved, setShowResolved] = useState(false)
  const [category, setCategory] = useState<string>('all')
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const load = async (resolved: boolean) => {
    setLoading(true)
    setError(null)
    try {
      const data = await purchaseGapsApi.list(resolved)
      setGaps(data.gaps)
    } catch {
      setError('Failed to load wardrobe gaps.')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    load(showResolved)
  }, [showResolved])

  const handleResolve = (id: string) => setGaps(prev => prev.filter(g => g.id !== id))
  const handleDelete = (id: string) => setGaps(prev => prev.filter(g => g.id !== id))

  // Summary counts across the full (unfiltered) set.
  const stats = useMemo(() => {
    const s = { total: gaps.length, high: 0, medium: 0, low: 0 }
    for (const g of gaps) s[priorityLabel(g.priority_score)]++
    return s
  }, [gaps])

  // Category filter options with counts.
  const categories = useMemo(() => {
    const counts = new Map<string, number>()
    for (const g of gaps) {
      const c = (g.missing_category || 'other').toLowerCase()
      counts.set(c, (counts.get(c) ?? 0) + 1)
    }
    return Array.from(counts.entries()).sort((a, b) => b[1] - a[1])
  }, [gaps])

  const visible = useMemo(
    () => (category === 'all'
      ? gaps
      : gaps.filter(g => (g.missing_category || 'other').toLowerCase() === category)),
    [gaps, category],
  )

  // Group the visible gaps by priority, preserving score order within each.
  const grouped = useMemo(() => {
    const g: Record<Level, PurchaseGap[]> = { high: [], medium: [], low: [] }
    for (const gap of [...visible].sort((a, b) => (b.priority_score ?? 0) - (a.priority_score ?? 0))) {
      g[priorityLabel(gap.priority_score)].push(gap)
    }
    return g
  }, [visible])

  const chipBase = 'text-[13px] font-medium px-3 py-1.5 rounded-full border transition-colors cursor-pointer'
  const chipOn = 'bg-brand-600 border-brand-600 text-white'
  const chipOff = 'bg-white/60 dark:bg-white/[0.04] border-cream-300 dark:border-white/[0.1] text-slate-500 dark:text-white/50 hover:border-cream-400 dark:hover:border-white/20 hover:text-slate-700 dark:hover:text-white/80'

  return (
    <div className="w-full space-y-6 animate-slide-up">
      <BackButton fallback="/dashboard" label="Back to Dashboard" />

      <PageHeader
        icon={<ShoppingBag size={18} />}
        chipClassName="bg-gradient-warm"
        iconColor="text-white"
        title="Wardrobe Gaps"
        subtitle="Particular pieces to buy — and which outfit types they unlock"
        actions={
          <>
            <label className="flex items-center gap-2 text-sm text-slate-600 dark:text-white/60 cursor-pointer select-none">
              <input
                type="checkbox"
                checked={showResolved}
                onChange={e => setShowResolved(e.target.checked)}
                className="rounded accent-brand-600"
              />
              Show resolved
            </label>
            <button
              onClick={() => load(showResolved)}
              className="w-9 h-9 rounded-lg flex items-center justify-center border border-cream-300 dark:border-white/[0.1] text-slate-400 hover:text-slate-700 dark:hover:text-white bg-white/60 dark:bg-white/[0.03] hover:bg-cream-100 dark:hover:bg-white/10 transition-colors"
              title="Refresh"
            >
              <RefreshCw size={16} />
            </button>
          </>
        }
      />

      {loading ? (
        <div className="flex items-center justify-center py-20">
          <FaniLoader
            size="md"
            messages={[
              'Reviewing your wardrobe…',
              'Spotting the gaps…',
              'Pulling together suggestions…',
            ]}
            subline="FANI is checking what's missing"
          />
        </div>
      ) : error ? (
        <div className="rounded-2xl border border-red-200 dark:border-red-900/40 bg-red-50/70 dark:bg-red-900/20 p-6 flex items-center gap-3 text-red-600 dark:text-red-400">
          <AlertCircle size={20} />
          <p className="text-sm">{error}</p>
        </div>
      ) : gaps.length === 0 ? (
        <div className="rounded-2xl border border-cream-200/70 dark:border-white/[0.08] bg-white/70 dark:bg-white/[0.04] backdrop-blur-xl p-10 text-center space-y-3">
          <CheckCircle size={36} className="mx-auto text-emerald-500" />
          <p className="font-display font-semibold text-slate-700 dark:text-white">
            {showResolved ? 'No resolved gaps found.' : 'Your wardrobe looks complete!'}
          </p>
          <p className="text-sm text-slate-500 dark:text-white/50 max-w-md mx-auto">
            {showResolved
              ? 'Gaps you mark as resolved will appear here.'
              : 'As you build outfits and pack for trips, any missing items will appear here.'}
          </p>
        </div>
      ) : (
        <>
          {/* summary strip */}
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 sm:gap-3.5">
            <StatTile value={stats.total}  label="Total gaps"      dot="bg-brand-500" />
            <StatTile value={stats.high}    label="High priority"   dot={PRIORITY.high.dot} />
            <StatTile value={stats.medium}  label="Medium priority" dot={PRIORITY.medium.dot} />
            <StatTile value={stats.low}     label="Low priority"    dot={PRIORITY.low.dot} />
          </div>

          {/* category filters */}
          {categories.length > 1 && (
            <div className="flex items-center gap-2 flex-wrap">
              <span className="inline-flex items-center gap-1.5 text-xs font-semibold text-slate-400 dark:text-white/40 mr-1">
                <Filter size={14} />
                Category
              </span>
              <button
                onClick={() => setCategory('all')}
                className={cn(chipBase, category === 'all' ? chipOn : chipOff)}
              >
                All<span className="opacity-50 ml-1.5 tabular-nums">{gaps.length}</span>
              </button>
              {categories.map(([c, n]) => (
                <button
                  key={c}
                  onClick={() => setCategory(c)}
                  className={cn(chipBase, 'capitalize', category === c ? chipOn : chipOff)}
                >
                  {c}<span className="opacity-50 ml-1.5 tabular-nums">{n}</span>
                </button>
              ))}
            </div>
          )}

          {/* filtered-empty state */}
          {visible.length === 0 ? (
            <div className="rounded-2xl border border-cream-200/70 dark:border-white/[0.08] bg-white/70 dark:bg-white/[0.04] p-11 text-center">
              <p className="font-display font-semibold text-slate-700 dark:text-white/90">No gaps in this category</p>
              <p className="text-[13.5px] text-slate-400 dark:text-white/40 mt-1.5">Try another filter, or your wardrobe already covers it.</p>
            </div>
          ) : (
            <div className="space-y-7">
              {(['high', 'medium', 'low'] as Level[]).map(level =>
                grouped[level].length > 0 ? (
                  <section key={level}>
                    <SectionHeader level={level} count={grouped[level].length} />
                    <div className="grid gap-3.5 sm:grid-cols-2 xl:grid-cols-3">
                      {grouped[level].map(gap => (
                        <GapCard key={gap.id} gap={gap} onResolve={handleResolve} onDelete={handleDelete} />
                      ))}
                    </div>
                  </section>
                ) : null,
              )}
            </div>
          )}
        </>
      )}
    </div>
  )
}
