import { useState, useEffect, useCallback, useMemo } from 'react'
import { toastStore } from '@/store/notificationStore'
import { useNavigate } from 'react-router-dom'
import BackButton from '@/components/ui/BackButton'
import PageHeader from '@/components/ui/PageHeader'
import { motion, AnimatePresence } from 'framer-motion'
import {
  Heart, Shirt, Star, ChevronDown, ChevronUp, Calendar,
  Wand2, SlidersHorizontal, CheckCircle2,
  MessageSquare, X, Search, RefreshCw, Trash2, Loader2,
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

function scoreColor(score: number | null): string {
  if (!score) return 'text-slate-400'
  if (score >= 80) return 'text-emerald-500'
  if (score >= 60) return 'text-amber-500'
  return 'text-red-400'
}

function scoreBg(score: number | null): string {
  if (!score) return 'bg-slate-100 dark:bg-slate-800'
  if (score >= 80) return 'bg-emerald-50 dark:bg-emerald-900/20 border-emerald-200 dark:border-emerald-800'
  if (score >= 60) return 'bg-amber-50 dark:bg-amber-900/20 border-amber-200 dark:border-amber-800'
  return 'bg-red-50 dark:bg-red-900/20 border-red-200 dark:border-red-800'
}

const OCCASIONS = ['All', 'Casual', 'Smart Casual', 'Formal', 'Business', 'Party', 'Date', 'Sport', 'Travel']

// ── Outfit Card ───────────────────────────────────────────────────────────────

interface OutfitCardProps {
  record: OutfitHistoryRecord
  closetMap: Record<string, ClosetItem>
  onFeedback: (id: string, patch: { was_worn?: boolean; was_saved?: boolean; feedback?: string }) => void
  onDelete: (id: string) => void
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
      className={cn(
        'rounded-2xl border bg-white dark:bg-slate-900 shadow-sm overflow-hidden',
        scoreBg(record.matching_score),
      )}
    >
      {/* Header row */}
      <div className="px-4 pt-4 pb-3">
        <div className="flex items-start justify-between gap-3">
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2 flex-wrap">
              {record.occasion && (
                <span className="text-[10px] font-semibold px-2 py-0.5 rounded-full bg-brand-100 dark:bg-brand-900/30 text-brand-700 dark:text-brand-300 border border-brand-200 dark:border-brand-800 uppercase tracking-wide">
                  {record.occasion}
                </span>
              )}
              {record.was_worn && (
                <span className="flex items-center gap-1 text-[10px] px-2 py-0.5 rounded-full bg-emerald-100 dark:bg-emerald-900/20 text-emerald-700 dark:text-emerald-300 border border-emerald-200 dark:border-emerald-800">
                  <CheckCircle2 size={9} /> Worn
                </span>
              )}
              {record.was_saved && (
                <span className="flex items-center gap-1 text-[10px] px-2 py-0.5 rounded-full bg-rose-100 dark:bg-rose-900/20 text-rose-600 dark:text-rose-300 border border-rose-200 dark:border-rose-800">
                  <Heart size={9} className="fill-current" /> Saved
                </span>
              )}
            </div>
            <p className="mt-1.5 text-[11px] text-slate-400 dark:text-slate-500 flex items-center gap-1">
              <Calendar size={10} />
              {formatDate(record.created_at)}
              {record.weather_context?.weather && (
                <span className="ml-1 opacity-60">· {record.weather_context.weather}</span>
              )}
            </p>
          </div>

          {record.matching_score != null && (
            <div className="flex-shrink-0 text-center">
              <p className={cn('text-2xl font-bold tabular-nums', scoreColor(record.matching_score))}>
                {record.matching_score}
              </p>
              <p className="text-[9px] text-slate-400 uppercase tracking-wide">score</p>
            </div>
          )}
        </div>

        {/* Item thumbnails */}
        {items.length > 0 && (
          <div className="mt-3 flex gap-2 overflow-x-auto pb-1 scrollbar-none">
            {items.map(item => (
              <div key={item.id} className="flex-shrink-0 w-14 h-14 rounded-xl overflow-hidden border border-cream-200 dark:border-slate-700 bg-slate-100 dark:bg-slate-800">
                {item.image_url ? (
                  <img
                    src={item.image_url}
                    alt={item.name}
                    loading="lazy"
                    decoding="async"
                    className="w-full h-full object-cover"
                  />
                ) : (
                  <div className="w-full h-full flex items-center justify-center">
                    <Shirt size={20} className="text-slate-300 dark:text-slate-600" />
                  </div>
                )}
              </div>
            ))}
            {record.selected_item_ids.length > items.length && (
              <div className="flex-shrink-0 w-14 h-14 rounded-xl bg-slate-100 dark:bg-slate-800 border border-cream-200 dark:border-slate-700 flex items-center justify-center text-xs text-slate-400">
                +{record.selected_item_ids.length - items.length}
              </div>
            )}
          </div>
        )}
      </div>

      {/* Expandable details */}
      {record.recommendation_text && (
        <button
          onClick={() => setExpanded(v => !v)}
          className="w-full px-4 py-2 flex items-center gap-1.5 text-[11px] text-slate-500 dark:text-slate-400 hover:text-slate-700 dark:hover:text-slate-300 border-t border-cream-100 dark:border-slate-800 transition-colors"
        >
          {expanded ? <ChevronUp size={12} /> : <ChevronDown size={12} />}
          {expanded ? 'Hide details' : 'Show AI reasoning'}
        </button>
      )}

      <AnimatePresence>
        {expanded && record.recommendation_text && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: 'auto', opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            className="overflow-hidden"
          >
            <div className="px-4 pb-3 space-y-2">
              <p className="text-xs text-slate-600 dark:text-slate-300 leading-relaxed">
                {record.recommendation_text}
              </p>
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
              {record.user_feedback && (
                <div className="p-2 rounded-xl bg-slate-50 dark:bg-slate-800 border border-slate-200 dark:border-slate-700">
                  <p className="text-[10px] font-semibold text-slate-500 dark:text-slate-400 mb-0.5">Your note</p>
                  <p className="text-xs text-slate-600 dark:text-slate-300">{record.user_feedback}</p>
                </div>
              )}
            </div>
          </motion.div>
        )}
      </AnimatePresence>

      {/* Action bar */}
      <div className="px-4 pb-4 pt-2 flex items-center gap-2 border-t border-cream-100 dark:border-slate-800">
        <button
          onClick={wearAgain}
          className="flex items-center gap-1.5 px-3 py-1.5 rounded-xl bg-gradient-brand text-white text-[11px] font-semibold hover:opacity-90 active:scale-95 transition-all"
        >
          <Wand2 size={11} /> Wear Again
        </button>

        <button
          onClick={() => submitFeedback({ was_worn: !record.was_worn })}
          disabled={saving}
          title={record.was_worn ? 'Mark as not worn' : 'Mark as worn'}
          aria-label={record.was_worn ? 'Mark as not worn' : 'Mark as worn'}
          aria-pressed={record.was_worn}
          className={cn(
            'p-2 rounded-xl border text-[11px] transition-colors',
            record.was_worn
              ? 'bg-emerald-50 dark:bg-emerald-900/20 border-emerald-200 dark:border-emerald-800 text-emerald-600'
              : 'border-slate-200 dark:border-slate-700 text-slate-400 hover:border-emerald-300 hover:text-emerald-500',
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
            'p-2 rounded-xl border text-[11px] transition-colors',
            record.was_saved
              ? 'bg-rose-50 dark:bg-rose-900/20 border-rose-200 dark:border-rose-800 text-rose-500'
              : 'border-slate-200 dark:border-slate-700 text-slate-400 hover:border-rose-300 hover:text-rose-500',
          )}
        >
          <Heart size={14} className={record.was_saved ? 'fill-current' : ''} />
        </button>

        <button
          onClick={() => setFeedbackOpen(v => !v)}
          title="Add note"
          aria-label="Add a note"
          aria-expanded={feedbackOpen}
          className="p-2 rounded-xl border border-slate-200 dark:border-slate-700 text-slate-400 hover:border-brand-300 hover:text-brand-500 transition-colors"
        >
          <MessageSquare size={14} />
        </button>

        {/* Delete — pushed to the far right; two-tap confirm */}
        <button
          onClick={handleDelete}
          disabled={deleting}
          title={confirmingDelete ? 'Click again to confirm delete' : 'Delete outfit'}
          aria-label={confirmingDelete ? 'Confirm delete outfit' : 'Delete outfit'}
          className={cn(
            'ml-auto flex items-center gap-1.5 rounded-xl border px-2 py-2 text-[11px] font-semibold transition-colors disabled:opacity-50',
            confirmingDelete
              ? 'bg-red-500 border-red-500 text-white'
              : 'border-slate-200 dark:border-slate-700 text-slate-400 hover:border-red-300 hover:text-red-500',
          )}
        >
          {deleting ? <Loader2 size={14} className="animate-spin" /> : <Trash2 size={14} />}
          {confirmingDelete && <span>Delete?</span>}
        </button>
      </div>

      {/* Inline feedback note */}
      <AnimatePresence>
        {feedbackOpen && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: 'auto', opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            className="overflow-hidden border-t border-cream-100 dark:border-slate-800"
          >
            <div className="px-4 pb-4 pt-3 flex gap-2 items-end">
              <textarea
                rows={2}
                value={feedbackText}
                onChange={e => setFeedbackText(e.target.value)}
                placeholder="Add a note about this outfit…"
                className="flex-1 resize-none rounded-xl border border-cream-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-800 text-xs text-slate-800 dark:text-slate-100 placeholder-slate-400 px-3 py-2 focus:outline-none focus:ring-1 focus:ring-brand-400"
              />
              <div className="flex flex-col gap-1">
                <button
                  onClick={async () => { await submitFeedback({ feedback: feedbackText }); setFeedbackOpen(false) }}
                  disabled={saving}
                  className="px-3 py-1.5 rounded-xl bg-gradient-brand text-white text-[11px] font-semibold hover:opacity-90 disabled:opacity-50"
                >
                  Save
                </button>
                <button
                  onClick={() => { setFeedbackText(record.user_feedback ?? ''); setFeedbackOpen(false) }}
                  className="px-3 py-1.5 rounded-xl border border-slate-200 dark:border-slate-700 text-[11px] text-slate-400 hover:text-slate-600"
                >
                  Cancel
                </button>
              </div>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </motion.div>
  )
}

// ── Calendar heat-map strip ───────────────────────────────────────────────────

function CalendarStrip({ records }: { records: OutfitHistoryRecord[] }) {
  const days = useMemo(() => {
    const map: Record<string, number> = {}
    for (const r of records) {
      if (!r.created_at) continue
      const key = r.created_at.slice(0, 10)
      map[key] = (map[key] ?? 0) + 1
    }
    const result: { date: Date; key: string; count: number }[] = []
    for (let i = 29; i >= 0; i--) {
      const d = new Date()
      d.setDate(d.getDate() - i)
      const key = d.toISOString().slice(0, 10)
      result.push({ date: d, key, count: map[key] ?? 0 })
    }
    return result
  }, [records])

  return (
    <div className="rounded-2xl border border-cream-200 dark:border-slate-700 bg-white dark:bg-slate-900 p-4">
      <p className="text-xs font-semibold text-slate-500 dark:text-slate-400 mb-3 uppercase tracking-wide">Last 30 days</p>
      <div className="flex gap-1 flex-wrap">
        {days.map(({ date, key, count }) => (
          <div
            key={key}
            title={`${date.toLocaleDateString([], { month: 'short', day: 'numeric' })}: ${count} outfit${count !== 1 ? 's' : ''}`}
            className={cn(
              'w-7 h-7 rounded-lg border text-[9px] font-bold flex items-center justify-center transition-colors cursor-default',
              count === 0
                ? 'bg-slate-50 dark:bg-slate-800 border-slate-100 dark:border-slate-700 text-slate-300 dark:text-slate-600'
                : count === 1
                  ? 'bg-brand-100 dark:bg-brand-900/30 border-brand-200 dark:border-brand-800 text-brand-600 dark:text-brand-300'
                  : 'bg-gradient-brand border-transparent text-white',
            )}
          >
            {date.getDate()}
          </div>
        ))}
      </div>
      <div className="flex gap-4 mt-3 text-[10px] text-slate-400">
        <span className="flex items-center gap-1"><span className="w-3 h-3 rounded bg-slate-100 dark:bg-slate-800 border border-slate-200 dark:border-slate-700 inline-block" /> None</span>
        <span className="flex items-center gap-1"><span className="w-3 h-3 rounded bg-brand-100 dark:bg-brand-900/30 border border-brand-200 dark:border-brand-800 inline-block" /> 1 outfit</span>
        <span className="flex items-center gap-1"><span className="w-3 h-3 rounded bg-gradient-brand inline-block" /> 2+</span>
      </div>
    </div>
  )
}

// ── Stats bar ─────────────────────────────────────────────────────────────────

function StatsBar({ records }: { records: OutfitHistoryRecord[] }) {
  const saved = records.filter(r => r.was_saved).length
  const worn = records.filter(r => r.was_worn).length
  const avgScore = records.filter(r => r.matching_score).length
    ? Math.round(records.filter(r => r.matching_score).reduce((a, r) => a + (r.matching_score ?? 0), 0) / records.filter(r => r.matching_score).length)
    : null

  const stats = [
    { label: 'Total', value: records.length, icon: Shirt },
    { label: 'Saved', value: saved, icon: Heart },
    { label: 'Worn', value: worn, icon: CheckCircle2 },
    { label: 'Avg Score', value: avgScore != null ? `${avgScore}` : '—', icon: Star },
  ]

  return (
    <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
      {stats.map(({ label, value, icon: Icon }) => (
        <div key={label} className="rounded-2xl border border-cream-200 dark:border-slate-700 bg-white dark:bg-slate-900 p-3 text-center">
          <Icon size={16} className="mx-auto mb-1 text-brand-400" />
          <p className="text-xl font-bold text-slate-800 dark:text-white tabular-nums">{value}</p>
          <p className="text-[10px] text-slate-400 uppercase tracking-wide">{label}</p>
        </div>
      ))}
    </div>
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
  const [showFilters, setShowFilters] = useState(false)
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

  return (
    <div className="max-w-2xl mx-auto px-4 py-6 space-y-6">
      <BackButton fallback="/closet" label="Back to Closet" />
      {/* Page header */}
      <PageHeader
        icon={<Star size={18} />}
        title="Saved Outfits"
        subtitle="Your FANI-recommended outfit history"
        actions={
          <button
            onClick={() => fetchPage(0, true)}
            title="Refresh"
            className="p-2 rounded-xl border border-cream-200 dark:border-slate-700 text-slate-400 hover:text-brand-500 transition-colors"
          >
            <RefreshCw size={16} className={loading ? 'animate-spin' : ''} />
          </button>
        }
      />

      {/* Stats */}
      {records.length > 0 && <StatsBar records={records} />}

      {/* Calendar */}
      {records.length > 0 && <CalendarStrip records={records} />}

      {/* Filters */}
      <div className="space-y-3">
        <div className="flex items-center gap-2">
          {/* Saved / Worn / All tabs */}
          <div className="flex gap-1 bg-slate-100 dark:bg-slate-800 rounded-xl p-1" role="tablist" aria-label="Filter outfits">
            {(['all', 'saved', 'worn'] as const).map(f => (
              <button
                key={f}
                onClick={() => setFilter(f)}
                role="tab"
                aria-selected={filter === f}
                className={cn(
                  'px-3 py-1.5 rounded-lg text-xs font-semibold transition-colors capitalize',
                  filter === f
                    ? 'bg-white dark:bg-slate-700 text-slate-800 dark:text-white shadow-sm'
                    : 'text-slate-500 dark:text-slate-400',
                )}
              >
                {f === 'all' ? 'All' : f === 'saved' ? '❤️ Saved' : '✓ Worn'}
              </button>
            ))}
          </div>

          <button
            onClick={() => setShowFilters(v => !v)}
            className={cn(
              'flex items-center gap-1.5 px-3 py-2 rounded-xl border text-xs font-semibold transition-colors',
              showFilters
                ? 'bg-brand-50 dark:bg-brand-900/20 border-brand-300 dark:border-brand-700 text-brand-600 dark:text-brand-300'
                : 'border-cream-200 dark:border-slate-700 text-slate-500 dark:text-slate-400',
            )}
          >
            <SlidersHorizontal size={13} /> Filters
          </button>

          <div className="flex-1 relative">
            <Search size={13} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400 pointer-events-none" />
            <input
              value={search}
              onChange={e => setSearch(e.target.value)}
              placeholder="Search outfits…"
              className="w-full pl-8 pr-3 py-2 rounded-xl border border-cream-200 dark:border-slate-700 bg-white dark:bg-slate-800 text-xs text-slate-800 dark:text-slate-100 placeholder-slate-400 focus:outline-none focus:ring-1 focus:ring-brand-400"
            />
            {search && (
              <button onClick={() => setSearch('')} className="absolute right-2.5 top-1/2 -translate-y-1/2 text-slate-400 hover:text-slate-600">
                <X size={12} />
              </button>
            )}
          </div>
        </div>

        {/* Occasion filter row */}
        <AnimatePresence>
          {showFilters && (
            <motion.div
              initial={{ height: 0, opacity: 0 }}
              animate={{ height: 'auto', opacity: 1 }}
              exit={{ height: 0, opacity: 0 }}
              className="overflow-hidden"
            >
              <div className="flex gap-1.5 flex-wrap pb-1">
                {OCCASIONS.map(occ => (
                  <button
                    key={occ}
                    onClick={() => setOccasion(occ)}
                    className={cn(
                      'px-2.5 py-1 rounded-full text-[11px] font-semibold border transition-colors',
                      occasion === occ
                        ? 'bg-gradient-brand border-transparent text-white'
                        : 'border-cream-200 dark:border-slate-700 text-slate-500 dark:text-slate-400 hover:border-brand-300',
                    )}
                  >
                    {occ}
                  </button>
                ))}
              </div>
            </motion.div>
          )}
        </AnimatePresence>
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

      {/* Cards */}
      <div className="space-y-4">
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

      {/* Load more */}
      {hasMore && filtered.length > 0 && (
        <button
          onClick={loadMore}
          disabled={loading}
          className="w-full py-3 rounded-2xl border border-cream-200 dark:border-slate-700 text-sm text-slate-500 dark:text-slate-400 hover:border-brand-300 hover:text-brand-500 transition-colors disabled:opacity-40"
        >
          {loading ? 'Loading…' : 'Load more'}
        </button>
      )}

    </div>
  )
}
