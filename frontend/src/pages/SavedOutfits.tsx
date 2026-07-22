import { useState, useEffect, useCallback, useMemo } from 'react'
import { toastStore } from '@/store/notificationStore'
import { useNavigate } from 'react-router-dom'
import BackButton from '@/components/ui/BackButton'
import LazyImage from '@/components/ui/LazyImage'
import { motion, AnimatePresence } from 'framer-motion'
import {
  Heart, Shirt, Star, ChevronDown, Calendar,
  Wand2, CheckCircle2, MessageSquare, X, Search, RefreshCw, Trash2, Loader2,
} from 'lucide-react'
import { outfitHistoryApi, type OutfitHistoryRecord } from '@/lib/api'
import { useApp } from '@/store'
import { cn } from '@/lib/utils'
import type { ClosetItem } from '@/types'
import { PageStatePanel } from '@/components/system/PageStatePanel'

// ── Helpers ───────────────────────────────────────────────────────────────────

function formatDate(iso: string | null): string {
  if (!iso) return '—'
  const d = new Date(iso)
  return d.toLocaleDateString([], { weekday: 'short', month: 'short', day: 'numeric', year: 'numeric' })
}

/** Solid pill background for the score badge overlaid on the collage. */
function scoreBadgeBg(score: number | null): string {
  if (!score) return 'bg-slate-400'
  if (score >= 80) return 'bg-emerald-500'
  if (score >= 60) return 'bg-amber-500'
  return 'bg-rose-400'
}

const OCCASIONS = ['All', 'Casual', 'Smart Casual', 'Formal', 'Business', 'Party', 'Date', 'Sport', 'Travel']

// ── Outfit Card ───────────────────────────────────────────────────────────────

interface OutfitCardProps {
  record: OutfitHistoryRecord
  closetMap: Record<string, ClosetItem>
  onFeedback: (id: string, patch: { was_worn?: boolean; was_saved?: boolean; feedback?: string }) => void
  onDelete: (id: string) => void
}

function CollageTile({ item, className, children }: {
  item?: ClosetItem
  className?: string
  children?: React.ReactNode
}) {
  // Sized by the parent grid track (row/col spans), not by an aspect class —
  // lets 1/2/3-item outfits use bigger tiles instead of empty placeholders.
  return (
    <div className={cn('relative bg-cream-100 dark:bg-slate-800', className)}>
      <LazyImage
        src={item?.image_url}
        alt={item?.name ?? 'Wardrobe item'}
        aspect=""
        rounded="rounded-none"
        wrapperClassName="h-full w-full bg-transparent"
        fallback={<Shirt size={22} className="text-slate-300 dark:text-slate-600" />}
      />
      {children}
    </div>
  )
}

function OutfitCard({ record, closetMap, onFeedback, onDelete }: OutfitCardProps) {
  const navigate = useNavigate()
  const [expanded, setExpanded] = useState(false)
  const [feedbackOpen, setFeedbackOpen] = useState(false)
  const [feedbackText, setFeedbackText] = useState(record.user_feedback ?? '')
  const [saving, setSaving] = useState(false)
  const [deleting, setDeleting] = useState(false)
  const [confirmingDelete, setConfirmingDelete] = useState(false)

  const items = (record.selected_item_ids ?? [])
    .map(id => closetMap[id])
    .filter(Boolean) as ClosetItem[]

  const totalCount = record.selected_item_ids?.length ?? items.length
  const extra = totalCount - 4 // how many beyond the 4 collage tiles
  const hasDetail = !!record.recommendation_text || (record.improvement_tips?.length ?? 0) > 0 || !!record.user_feedback

  const submitFeedback = async (patch: { was_worn?: boolean; was_saved?: boolean; feedback?: string }) => {
    setSaving(true)
    try {
      await outfitHistoryApi.submitFeedback(record.id, patch)
      onFeedback(record.id, patch)
      if (patch.was_saved !== undefined) {
        toastStore.add({
          variant: 'success',
          icon: patch.was_saved ? '❤️' : '🤍',
          title: patch.was_saved ? 'Outfit saved' : 'Outfit unsaved',
        })
      } else if (patch.was_worn !== undefined) {
        toastStore.add({ variant: 'success', icon: '👗', title: patch.was_worn ? 'Marked as worn' : 'Unmarked as worn' })
      } else if (patch.feedback) {
        toastStore.add({ variant: 'success', icon: '💬', title: 'Feedback submitted' })
      }
    } catch {
      toastStore.add({ variant: 'error', icon: '❌', title: 'Action failed', body: 'Please try again.' })
    } finally { setSaving(false) }
  }

  const wearAgain = () => {
    navigate('/outfit-builder', {
      state: { preselectedIds: record.selected_item_ids, occasion: record.occasion },
    })
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
      await outfitHistoryApi.delete(record.id)
      onDelete(record.id)
      toastStore.add({ variant: 'success', icon: '🗑️', title: 'Outfit deleted' })
    } catch {
      setDeleting(false)
      toastStore.add({ variant: 'error', icon: '❌', title: 'Delete failed', body: 'Please try again.' })
    }
  }

  return (
    <motion.div
      layout
      initial={{ opacity: 0, y: 16 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: -8 }}
      className="group flex flex-col rounded-2xl border border-cream-200 dark:border-slate-700 bg-white dark:bg-slate-900 shadow-card hover:shadow-card-hover hover:-translate-y-0.5 transition-all overflow-hidden"
    >
      {/* Image collage */}
      <div className="relative">
        {/* Layout adapts to how many items resolved: 1 → hero, 2 → side-by-side,
            3 → tall lead + two stacked, 4+ → classic 2×2 with a +N overlay. */}
        <div className="grid grid-cols-2 grid-rows-2 gap-0.5 aspect-square bg-cream-100 dark:bg-slate-800">
          {items.length <= 1 ? (
            <CollageTile item={items[0]} className="col-span-2 row-span-2" />
          ) : items.length === 2 ? (
            <>
              <CollageTile item={items[0]} className="row-span-2" />
              <CollageTile item={items[1]} className="row-span-2" />
            </>
          ) : items.length === 3 ? (
            <>
              <CollageTile item={items[0]} className="row-span-2" />
              <CollageTile item={items[1]} />
              <CollageTile item={items[2]} />
            </>
          ) : (
            <>
              <CollageTile item={items[0]} />
              <CollageTile item={items[1]} />
              <CollageTile item={items[2]} />
              <CollageTile item={extra > 0 ? undefined : items[3]}>
                {extra > 0 && (
                  <div className="absolute inset-0 flex items-center justify-center bg-slate-900/55 text-white text-sm font-semibold">
                    +{extra}
                  </div>
                )}
              </CollageTile>
            </>
          )}
        </div>

        {/* Occasion badge */}
        {record.occasion && (
          <span className="absolute top-2.5 left-2.5 text-[10px] font-bold px-2.5 py-1 rounded-full bg-white/90 dark:bg-slate-900/85 text-brand-700 dark:text-brand-300 uppercase tracking-wide backdrop-blur-sm">
            {record.occasion}
          </span>
        )}

        {/* Score badge */}
        {record.matching_score != null && (
          <span
            className={cn(
              'absolute top-2.5 right-2.5 flex items-center gap-1 text-xs font-extrabold px-2.5 py-1 rounded-full text-white tabular-nums',
              scoreBadgeBg(record.matching_score),
            )}
          >
            <Star size={10} className="fill-current" />
            {record.matching_score}
          </span>
        )}

        {/* Saved / worn corner markers (bottom-left) */}
        <div className="absolute bottom-2.5 left-2.5 flex gap-1.5">
          {record.was_worn && (
            <span className="flex items-center justify-center w-6 h-6 rounded-full bg-emerald-500 text-white shadow-sm" title="Worn">
              <CheckCircle2 size={13} />
            </span>
          )}
          {record.was_saved && (
            <span className="flex items-center justify-center w-6 h-6 rounded-full bg-rose-500 text-white shadow-sm" title="Saved">
              <Heart size={12} className="fill-current" />
            </span>
          )}
        </div>
      </div>

      {/* Body */}
      <div className="flex flex-col flex-1 p-3.5">
        <div className="flex items-center justify-between gap-2">
          <p className="text-[11px] text-slate-400 dark:text-slate-500 flex items-center gap-1 min-w-0">
            <Calendar size={11} className="flex-shrink-0" />
            <span className="truncate">
              {formatDate(record.created_at)}
              {record.weather_context?.weather && (
                <span className="opacity-70"> · {record.weather_context.weather}</span>
              )}
            </span>
          </p>
          {hasDetail && (
            <button
              onClick={() => setExpanded(v => !v)}
              aria-expanded={expanded}
              className="flex-shrink-0 flex items-center gap-1 text-[11px] font-semibold text-brand-600 dark:text-brand-300 bg-brand-50 dark:bg-brand-900/25 rounded-lg px-2 py-1 hover:bg-brand-100 dark:hover:bg-brand-900/40 transition-colors"
            >
              Why this works
              <ChevronDown size={11} className={cn('transition-transform', expanded && 'rotate-180')} />
            </button>
          )}
        </div>

        {/* AI reasoning + note (expandable) */}
        <AnimatePresence initial={false}>
          {expanded && (
            <motion.div
              initial={{ height: 0, opacity: 0 }}
              animate={{ height: 'auto', opacity: 1 }}
              exit={{ height: 0, opacity: 0 }}
              className="overflow-hidden"
            >
              <div className="pt-3 space-y-2">
                {record.recommendation_text && (
                  <p className="text-xs text-slate-600 dark:text-slate-300 leading-relaxed">
                    {record.recommendation_text}
                  </p>
                )}
                {(record.improvement_tips ?? []).length > 0 && (
                  <div className="space-y-1">
                    <p className="text-[10px] font-semibold text-slate-500 dark:text-slate-400 uppercase tracking-wide">Tips</p>
                    {record.improvement_tips.map((tip, i) => (
                      <p key={i} className="text-[11px] text-slate-500 dark:text-slate-400 flex gap-1.5">
                        <Star size={9} className="mt-0.5 flex-shrink-0 text-amber-400" />
                        {tip}
                      </p>
                    ))}
                  </div>
                )}
                {record.user_feedback && !feedbackOpen && (
                  <div className="p-2 rounded-xl bg-cream-50 dark:bg-slate-800 border border-cream-200 dark:border-slate-700">
                    <p className="text-[10px] font-semibold text-slate-500 dark:text-slate-400 mb-0.5">Your note</p>
                    <p className="text-xs text-slate-600 dark:text-slate-300">{record.user_feedback}</p>
                  </div>
                )}
              </div>
            </motion.div>
          )}
        </AnimatePresence>

        {/* Inline note editor */}
        <AnimatePresence initial={false}>
          {feedbackOpen && (
            <motion.div
              initial={{ height: 0, opacity: 0 }}
              animate={{ height: 'auto', opacity: 1 }}
              exit={{ height: 0, opacity: 0 }}
              className="overflow-hidden"
            >
              <div className="pt-3 flex flex-col gap-2">
                <textarea
                  rows={2}
                  value={feedbackText}
                  onChange={e => setFeedbackText(e.target.value)}
                  placeholder="Add a note about this outfit…"
                  className="resize-none rounded-xl border border-cream-200 dark:border-slate-700 bg-cream-50 dark:bg-slate-800 text-xs text-slate-800 dark:text-slate-100 placeholder-slate-400 px-3 py-2 focus:outline-none focus:ring-1 focus:ring-brand-400"
                />
                <div className="flex gap-2">
                  <button
                    onClick={async () => { await submitFeedback({ feedback: feedbackText }); setFeedbackOpen(false) }}
                    disabled={saving}
                    className="px-3 py-1.5 rounded-xl bg-gradient-brand text-white text-[11px] font-semibold hover:opacity-90 disabled:opacity-50"
                  >
                    Save note
                  </button>
                  <button
                    onClick={() => { setFeedbackText(record.user_feedback ?? ''); setFeedbackOpen(false) }}
                    className="px-3 py-1.5 rounded-xl border border-cream-200 dark:border-slate-700 text-[11px] text-slate-400 hover:text-slate-600"
                  >
                    Cancel
                  </button>
                </div>
              </div>
            </motion.div>
          )}
        </AnimatePresence>

        {/* Action row */}
        <div className="mt-auto pt-3 flex items-center gap-1.5">
          <button
            onClick={wearAgain}
            className="flex-1 flex items-center justify-center gap-1.5 px-3 py-2 rounded-xl bg-gradient-brand text-white text-[11px] font-semibold hover:opacity-90 active:scale-95 transition-all"
          >
            <Wand2 size={12} /> Wear again
          </button>

          <button
            onClick={() => submitFeedback({ was_worn: !record.was_worn })}
            disabled={saving}
            title={record.was_worn ? 'Mark as not worn' : 'Mark as worn'}
            aria-label={record.was_worn ? 'Mark as not worn' : 'Mark as worn'}
            aria-pressed={record.was_worn}
            className={cn(
              'p-2 rounded-xl border transition-colors',
              record.was_worn
                ? 'bg-emerald-50 dark:bg-emerald-900/20 border-emerald-200 dark:border-emerald-800 text-emerald-600'
                : 'border-cream-200 dark:border-slate-700 text-slate-400 hover:border-emerald-300 hover:text-emerald-500',
            )}
          >
            <CheckCircle2 size={14} />
          </button>

          <button
            onClick={() => submitFeedback({ was_saved: !record.was_saved })}
            disabled={saving}
            title={record.was_saved ? 'Unsave' : 'Save'}
            aria-label={record.was_saved ? 'Unsave outfit' : 'Save outfit'}
            aria-pressed={record.was_saved}
            className={cn(
              'p-2 rounded-xl border transition-colors',
              record.was_saved
                ? 'bg-rose-50 dark:bg-rose-900/20 border-rose-200 dark:border-rose-800 text-rose-500'
                : 'border-cream-200 dark:border-slate-700 text-slate-400 hover:border-rose-300 hover:text-rose-500',
            )}
          >
            <Heart size={14} className={record.was_saved ? 'fill-current' : ''} />
          </button>

          <button
            onClick={() => { setFeedbackOpen(v => !v); if (!feedbackOpen) setExpanded(false) }}
            title="Add note"
            aria-label="Add a note"
            aria-expanded={feedbackOpen}
            className={cn(
              'p-2 rounded-xl border transition-colors',
              feedbackOpen
                ? 'bg-brand-50 dark:bg-brand-900/20 border-brand-300 dark:border-brand-700 text-brand-500'
                : 'border-cream-200 dark:border-slate-700 text-slate-400 hover:border-brand-300 hover:text-brand-500',
            )}
          >
            <MessageSquare size={14} />
          </button>

          <button
            onClick={handleDelete}
            disabled={deleting}
            title={confirmingDelete ? 'Click again to confirm delete' : 'Delete outfit'}
            aria-label={confirmingDelete ? 'Confirm delete outfit' : 'Delete outfit'}
            className={cn(
              'flex items-center gap-1.5 rounded-xl border px-2 py-2 text-[11px] font-semibold transition-colors disabled:opacity-50',
              confirmingDelete
                ? 'bg-red-500 border-red-500 text-white'
                : 'border-cream-200 dark:border-slate-700 text-slate-400 hover:border-red-300 hover:text-red-500',
            )}
          >
            {deleting ? <Loader2 size={14} className="animate-spin" /> : <Trash2 size={14} />}
            {confirmingDelete && <span>Delete?</span>}
          </button>
        </div>
      </div>
    </motion.div>
  )
}

// ── Main page ─────────────────────────────────────────────────────────────────

export default function SavedOutfits() {
  const { closetItems } = useApp()
  const [records, setRecords] = useState<OutfitHistoryRecord[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [filter, setFilter] = useState<'all' | 'saved' | 'worn'>('all')
  const [occasion, setOccasion] = useState('All')
  const [search, setSearch] = useState('')
  const [page, setPage] = useState(0)
  const [hasMore, setHasMore] = useState(true)
  const [isOffline, setIsOffline] = useState(typeof navigator !== 'undefined' ? !navigator.onLine : false)

  const PAGE = 20

  const closetMap = useMemo(() => {
    const m: Record<string, ClosetItem> = {}
    for (const item of closetItems) m[item.id] = item
    return m
  }, [closetItems])

  const fetchPage = useCallback(async (pageNum: number, replace = false) => {
    setLoading(true)
    setError(null)
    try {
      const res = await outfitHistoryApi.list(PAGE, pageNum * PAGE)
      setRecords(prev => replace ? res.results : [...prev, ...res.results])
      setHasMore(res.results.length === PAGE)
    } catch {
      setError('Could not load saved outfits.')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    fetchPage(0, true)
  }, [fetchPage])

  useEffect(() => {
    const update = () => setIsOffline(!navigator.onLine)
    window.addEventListener('online', update)
    window.addEventListener('offline', update)
    return () => {
      window.removeEventListener('online', update)
      window.removeEventListener('offline', update)
    }
  }, [])

  const handleFeedback = (id: string, patch: { was_worn?: boolean; was_saved?: boolean; feedback?: string }) => {
    setRecords(prev => prev.map(r =>
      r.id === id
        ? {
            ...r,
            was_worn: patch.was_worn ?? r.was_worn,
            was_saved: patch.was_saved ?? r.was_saved,
            user_feedback: patch.feedback ?? r.user_feedback,
          }
        : r,
    ))
  }

  const handleDelete = (id: string) => {
    setRecords(prev => prev.filter(r => r.id !== id))
  }

  const loadMore = () => {
    const next = page + 1
    setPage(next)
    fetchPage(next)
  }

  const filtered = useMemo(() => {
    let list = records
    if (filter === 'saved') list = list.filter(r => r.was_saved)
    if (filter === 'worn') list = list.filter(r => r.was_worn)
    if (occasion !== 'All') list = list.filter(r => r.occasion?.toLowerCase().includes(occasion.toLowerCase()))
    if (search.trim()) {
      const q = search.toLowerCase()
      list = list.filter(r =>
        r.occasion?.toLowerCase().includes(q) ||
        r.recommendation_text?.toLowerCase().includes(q) ||
        r.user_feedback?.toLowerCase().includes(q) ||
        r.weather_context?.weather?.toLowerCase().includes(q),
      )
    }
    return list
  }, [records, filter, occasion, search])

  // Header stats (from loaded records)
  const stats = useMemo(() => {
    const saved = records.filter(r => r.was_saved).length
    const worn = records.filter(r => r.was_worn).length
    const scored = records.filter(r => r.matching_score)
    const avg = scored.length
      ? Math.round(scored.reduce((a, r) => a + (r.matching_score ?? 0), 0) / scored.length)
      : null
    return { total: records.length, saved, worn, avg }
  }, [records])

  return (
    <div className="max-w-6xl mx-auto px-4 py-6 space-y-5">
      <BackButton fallback="/closet" label="Back to Closet" />

      {/* Header — title + inline stats, search, filter toggle, refresh */}
      <div className="flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
        <div className="flex items-center gap-3.5">
          <span className="w-11 h-11 rounded-2xl bg-gradient-brand text-white flex items-center justify-center shadow-glow-sm flex-shrink-0">
            <Heart size={20} className="fill-current" />
          </span>
          <div>
            <h1 className="font-display font-bold text-2xl text-slate-800 dark:text-white">Saved Outfits</h1>
            <p className="mt-0.5 text-[13px] text-slate-400 dark:text-slate-500">
              {stats.total} outfit{stats.total !== 1 ? 's' : ''}
              {stats.avg != null && (
                <> · <span className="text-brand-600 dark:text-brand-400 font-semibold">{stats.avg} avg score</span></>
              )}
              {' '}· {stats.saved} saved · {stats.worn} worn
            </p>
          </div>
        </div>

        <div className="flex items-center gap-2">
          <div className="flex-1 lg:flex-initial relative lg:w-64">
            <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400 pointer-events-none" />
            <input
              value={search}
              onChange={e => setSearch(e.target.value)}
              placeholder="Search occasion, notes, weather…"
              className="w-full pl-9 pr-8 py-2.5 rounded-xl border border-cream-200 dark:border-slate-700 bg-white dark:bg-slate-900 text-[13px] text-slate-800 dark:text-slate-100 placeholder-slate-400 focus:outline-none focus:ring-1 focus:ring-brand-400"
            />
            {search && (
              <button onClick={() => setSearch('')} className="absolute right-2.5 top-1/2 -translate-y-1/2 text-slate-400 hover:text-slate-600">
                <X size={13} />
              </button>
            )}
          </div>

          <div className="flex gap-1 bg-white dark:bg-slate-900 border border-cream-200 dark:border-slate-700 rounded-xl p-1" role="tablist" aria-label="Filter outfits">
            {(['all', 'saved', 'worn'] as const).map(f => (
              <button
                key={f}
                onClick={() => setFilter(f)}
                role="tab"
                aria-selected={filter === f}
                className={cn(
                  'px-3.5 py-1.5 rounded-lg text-xs font-semibold transition-colors capitalize whitespace-nowrap',
                  filter === f
                    ? 'bg-gradient-brand text-white'
                    : 'text-slate-500 dark:text-slate-400 hover:text-brand-500',
                )}
              >
                {f}
              </button>
            ))}
          </div>

          <button
            onClick={() => fetchPage(0, true)}
            title="Refresh"
            aria-label="Refresh"
            className="p-2.5 rounded-xl border border-cream-200 dark:border-slate-700 bg-white dark:bg-slate-900 text-slate-400 hover:text-brand-500 hover:border-brand-200 transition-colors"
          >
            <RefreshCw size={15} className={loading ? 'animate-spin' : ''} />
          </button>
        </div>
      </div>

      {/* Occasion pills */}
      <div className="flex gap-2 overflow-x-auto pb-1 scrollbar-none">
        {OCCASIONS.map(occ => (
          <button
            key={occ}
            onClick={() => setOccasion(occ)}
            className={cn(
              'flex-shrink-0 px-3.5 py-1.5 rounded-full text-xs font-semibold border transition-colors',
              occasion === occ
                ? 'bg-gradient-brand border-transparent text-white'
                : 'border-cream-200 dark:border-slate-700 bg-white dark:bg-slate-900 text-slate-500 dark:text-slate-400 hover:border-brand-300 hover:text-brand-500',
            )}
          >
            {occ === 'All' ? 'All occasions' : occ}
          </button>
        ))}
      </div>

      <PageStatePanel
        loading={loading && records.length === 0}
        loadingTitle="Loading saved outfits..."
        loadingDescription="Fetching your outfit history from FANI."
        offline={isOffline && records.length === 0}
        error={records.length === 0 ? error : null}
        errorTitle="Couldn't load saved outfits"
        onRetry={() => { void fetchPage(0, true) }}
        empty={!loading && filtered.length === 0 && !error}
        emptyIcon={<Heart size={28} />}
        emptyTitle="No outfits yet"
        emptyDescription="Ask FANI for outfit recommendations and they will appear here automatically."
        emptyPrimaryAction={{ label: 'Ask FANI', href: '/ai-stylist' }}
      />

      {/* Gallery grid */}
      {filtered.length > 0 && (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
          <AnimatePresence mode="popLayout">
            {filtered.map(record => (
              <OutfitCard
                key={record.id}
                record={record}
                closetMap={closetMap}
                onFeedback={handleFeedback}
                onDelete={handleDelete}
              />
            ))}
          </AnimatePresence>
        </div>
      )}

      {/* Load more */}
      {hasMore && filtered.length > 0 && (
        <button
          onClick={loadMore}
          disabled={loading}
          className="mx-auto block px-8 py-2.5 rounded-xl border border-dashed border-cream-400 dark:border-slate-600 text-sm font-medium text-slate-500 dark:text-slate-400 hover:border-brand-300 hover:text-brand-500 transition-colors disabled:opacity-40"
        >
          {loading ? 'Loading…' : 'Load 20 more'}
        </button>
      )}
    </div>
  )
}
