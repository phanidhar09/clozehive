import React, { useMemo, useRef, useState, useEffect, useLayoutEffect } from 'react'
import {
  Search, SlidersHorizontal, ArrowUpDown, Loader2, RefreshCw, Trash2, X,
  Plus, Wand2, Shirt, Pencil, Check,
  Heart, LayoutGrid, List, Droplets, Sparkles, Handshake,
} from 'lucide-react'
import { useWindowVirtualizer } from '@tanstack/react-virtual'
import { Link } from 'react-router-dom'
import { useApp } from '@/store'
import { usePageState } from '@/hooks/usePageState'
import { useWindowScrollRestoration } from '@/hooks/useScrollRestoration'
import { closetApi } from '@/lib/api'
import { toastStore } from '@/store/notificationStore'
import ItemDetailModal from '@/components/closet/ItemDetailModal'
import EditItemModal from '@/components/closet/EditItemModal'
import RevealCard from '@/components/ui/RevealCard'
import { PageStatePanel } from '@/components/system/PageStatePanel'
import type { AvailabilityStatus, ClosetItem, Category } from '@/types'
import { AVAILABILITY_LABELS } from '@/types'
import { cn } from '@/lib/utils'

// ── Constants ──────────────────────────────────────────────────────────────────

import {
  CANONICAL_TAB_CATEGORIES,
  CLOSET_CATEGORY_TABS,
  CLOSET_OCCASIONS,
  CLOSET_SEASONS,
  CLOSET_SORT_OPTIONS,
} from '@/features/closet/constants'
// ── Column count hook (maps Tailwind breakpoints to grid columns) ─────────────

function useColumnCount(): number {
  const getCount = () => {
    if (typeof window === 'undefined') return 2
    const w = window.innerWidth
    if (w >= 1024) return 5
    if (w >= 768)  return 4
    if (w >= 640)  return 3
    return 2
  }
  const [cols, setCols] = useState(getCount)
  useEffect(() => {
    const h = () => setCols(getCount())
    window.addEventListener('resize', h, { passive: true })
    return () => window.removeEventListener('resize', h)
  }, [])
  return cols
}

// ── Shared helpers ─────────────────────────────────────────────────────────────

const CATEGORY_EMOJI_MAP: Record<string, string> = {
  tops: '👕', bottoms: '👖', shoes: '👟', outerwear: '🧥',
  dresses: '👗', accessories: '👜', other: '📦',
}

// ── List-view row ──────────────────────────────────────────────────────────────

function ClosetListRow({
  item, onOpen, onEdit, onDelete, deleting,
}: { item: ClosetItem; onOpen: (i: ClosetItem) => void; onEdit: (i: ClosetItem) => void; onDelete: (i: ClosetItem) => void; deleting: boolean }) {
  const [confirmingDelete, setConfirmingDelete] = React.useState(false)

  const handleDeleteClick = (e: React.MouseEvent) => {
    e.stopPropagation()
    if (confirmingDelete) { setConfirmingDelete(false); onDelete(item) }
    else { setConfirmingDelete(true); setTimeout(() => setConfirmingDelete(false), 3000) }
  }

  return (
    <div
      role="button"
      tabIndex={0}
      aria-label={`View details for ${item.name}`}
      className="flex items-center gap-3 px-3 py-2.5 rounded-2xl bg-white dark:bg-white/[0.03] border border-cream-200 dark:border-white/[0.07] hover:border-brand-200 dark:hover:border-brand-500/30 hover:shadow-sm transition-all group cursor-pointer focus:outline-none focus-visible:ring-2 focus-visible:ring-brand-500/50"
      onClick={() => onOpen(item)}
      onKeyDown={(e) => {
        if (e.key === 'Enter' || e.key === ' ') {
          e.preventDefault()
          onOpen(item)
        }
      }}
    >
      {/* Thumbnail */}
      <div className="w-11 h-14 rounded-xl overflow-hidden flex-shrink-0 bg-slate-100 dark:bg-slate-800">
        {item.image_url ? (
          <img src={item.image_url} alt={item.name} className="w-full h-full object-cover" loading="lazy" />
        ) : (
          <div className="w-full h-full flex items-center justify-center text-xl">
            {CATEGORY_EMOJI_MAP[item.category] ?? '👕'}
          </div>
        )}
      </div>

      {/* Main info */}
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-1.5">
          <p className="text-sm font-semibold text-slate-800 dark:text-white truncate">{item.name}</p>
          {item.is_favorite && <Heart size={11} className="text-pink-500 fill-pink-500 flex-shrink-0" />}
        </div>
        <div className="flex items-center gap-2 mt-0.5 flex-wrap">
          {item.brand && <span className="text-[11px] text-slate-400">{item.brand}</span>}
          <span className="text-[10px] px-1.5 py-0.5 rounded-full bg-slate-100 dark:bg-white/[0.06] text-slate-500 dark:text-slate-400 capitalize">{item.category}</span>
          {item.color && (
            <span className="flex items-center gap-1 text-[10px] text-slate-400 capitalize">
              {item.color_hex && (
                <span className="w-2.5 h-2.5 rounded-full border border-white/30 flex-shrink-0" style={{ backgroundColor: item.color_hex }} />
              )}
              {item.color}
            </span>
          )}
        </div>
      </div>

      {/* Stats — visible on sm+ */}
      <div className="hidden sm:flex items-center gap-3 flex-shrink-0 text-[11px] text-slate-400">
        {item.wear_count > 0 && (
          <span className="font-semibold">{item.wear_count}× worn</span>
        )}
        {item.season && item.season.length > 0 && (
          <span className="capitalize hidden md:inline">{item.season[0]}</span>
        )}
      </div>

      {/* Actions */}
      <div className="flex gap-1 flex-shrink-0" onClick={e => e.stopPropagation()}>
        <button
          onClick={() => onEdit(item)}
          className="p-2 rounded-lg bg-slate-100 dark:bg-white/[0.06] text-slate-400 hover:bg-amber-50 dark:hover:bg-amber-900/20 hover:text-amber-600 transition-colors"
          title="Edit"
        >
          <Pencil size={13} />
        </button>
        <button
          onClick={handleDeleteClick}
          disabled={deleting}
          className={cn(
            'flex items-center gap-1 rounded-lg p-2 text-[10px] font-semibold transition-colors disabled:opacity-40',
            confirmingDelete
              ? 'bg-red-500 text-white px-2'
              : 'bg-slate-100 dark:bg-white/[0.06] text-slate-400 hover:bg-red-50 dark:hover:bg-red-900/20 hover:text-red-500',
          )}
          title={confirmingDelete ? 'Click again to confirm delete' : 'Delete'}
          aria-label={confirmingDelete ? `Confirm delete ${item.name}` : `Delete ${item.name}`}
        >
          {deleting ? <Loader2 size={12} className="animate-spin" />
            : confirmingDelete ? <><Trash2 size={12} />Delete?</>
            : <Trash2 size={13} />}
        </button>
      </div>
    </div>
  )
}

// ── Sub-components ─────────────────────────────────────────────────────────────

const AVAILABILITY_BADGE: Record<Exclude<AvailabilityStatus, 'available'>, { icon: typeof Droplets; classes: string }> = {
  in_laundry:  { icon: Droplets,  classes: 'bg-sky-500/90' },
  at_cleaners: { icon: Sparkles,  classes: 'bg-violet-500/90' },
  lent_out:    { icon: Handshake, classes: 'bg-amber-500/90' },
}

function AvailabilityMenu({
  item, onSetAvailability, onClose,
}: { item: ClosetItem; onSetAvailability: (i: ClosetItem, s: AvailabilityStatus) => void; onClose: () => void }) {
  const current = item.availability ?? 'available'
  return (
    <div
      className="absolute top-10 left-2 z-40 w-40 rounded-xl border border-slate-200 dark:border-white/10
                 bg-white dark:bg-slate-800 shadow-xl py-1"
      onClick={e => e.stopPropagation()}
    >
      {(Object.keys(AVAILABILITY_LABELS) as AvailabilityStatus[]).map(status => (
        <button
          key={status}
          onClick={() => { onSetAvailability(item, status); onClose() }}
          className={cn(
            'w-full flex items-center gap-2 px-3 py-1.5 text-left text-xs transition-colors',
            'hover:bg-slate-50 dark:hover:bg-white/5',
            current === status ? 'font-semibold text-brand-600 dark:text-brand-400' : 'text-slate-600 dark:text-slate-300',
          )}
        >
          {current === status && <Check size={11} className="flex-shrink-0" />}
          <span className={current === status ? '' : 'pl-[19px]'}>{AVAILABILITY_LABELS[status]}</span>
        </button>
      ))}
    </div>
  )
}

function ClosetItemCard({
  item, onOpen, onDelete, onEdit, onSetAvailability, onToggleFavorite, deleting,
}: { item: ClosetItem; onOpen: (i: ClosetItem) => void; onDelete: (i: ClosetItem) => void; onEdit: (i: ClosetItem) => void; onSetAvailability: (i: ClosetItem, s: AvailabilityStatus) => void; onToggleFavorite: (i: ClosetItem) => void; deleting: boolean }) {
  const isTransparent = item.image_url?.endsWith('.png')
  const [confirmingDelete, setConfirmingDelete] = React.useState(false)
  const [availabilityOpen, setAvailabilityOpen] = React.useState(false)
  const unavailable = item.availability != null && item.availability !== 'available'

  const handleDeleteClick = (e: React.MouseEvent) => {
    e.stopPropagation()
    if (confirmingDelete) {
      setConfirmingDelete(false)
      onDelete(item)
    } else {
      setConfirmingDelete(true)
      setTimeout(() => setConfirmingDelete(false), 3000)
    }
  }

  return (
    <div className="group relative flex flex-col">
      {/* checkerboard bg for transparent images */}
      <div
        className={cn(
          'relative aspect-[4/5] rounded-2xl overflow-hidden cursor-pointer transition-all duration-300',
          'hover:-translate-y-1 hover:shadow-xl hover:shadow-slate-900/15',
          isTransparent
            ? '[background-image:repeating-conic-gradient(#e5e7eb_0%_25%,transparent_0%_50%)] [background-size:16px_16px] dark:[background-image:repeating-conic-gradient(#1e293b_0%_25%,transparent_0%_50%)]'
            : 'bg-gradient-to-br from-slate-100 to-slate-200 dark:from-slate-800 dark:to-slate-900',
        )}
      >
        <div className={cn('absolute inset-0', unavailable && 'opacity-45 saturate-50')}>
          <RevealCard item={item} onOpen={onOpen} onEdit={onEdit} className="absolute inset-0 rounded-2xl" />
        </div>

        {/* Availability badge — FANI skips these items until marked available */}
        {unavailable && (() => {
          const { icon: Icon, classes } = AVAILABILITY_BADGE[item.availability as Exclude<AvailabilityStatus, 'available'>]
          return (
            <div className={cn('absolute bottom-2 left-2 z-20 flex items-center gap-1 rounded-full backdrop-blur-sm px-2 py-0.5 text-[9px] font-bold text-white', classes)}>
              <Icon size={10} /> {AVAILABILITY_LABELS[item.availability as AvailabilityStatus]}
            </div>
          )
        })()}

        {/* Favourite heart — top-right, always visible (mock) */}
        <button
          onClick={e => { e.stopPropagation(); onToggleFavorite(item) }}
          aria-pressed={!!item.is_favorite}
          aria-label={item.is_favorite ? `Remove ${item.name} from favourites` : `Add ${item.name} to favourites`}
          title={item.is_favorite ? 'Remove from favourites' : 'Add to favourites'}
          className={cn(
            'absolute top-2 right-2 z-30 grid place-items-center w-7 h-7 rounded-full backdrop-blur-sm shadow-sm transition-all',
            item.is_favorite
              ? 'bg-white/90 dark:bg-slate-900/80'
              : 'bg-white/70 dark:bg-slate-900/60 opacity-100 sm:opacity-0 sm:group-hover:opacity-100 sm:focus-within:opacity-100',
          )}
        >
          <Heart size={14} className={cn('transition-colors', item.is_favorite ? 'text-pink-500 fill-pink-500' : 'text-slate-500 dark:text-slate-300')} />
        </button>

        {/* Quick actions — Edit & Delete. View = tap the card.
            Always visible on touch; reveal on hover/focus on desktop (sm+). */}
        <div className="absolute top-2 left-2 z-30 flex gap-1
                        opacity-100 sm:opacity-0 sm:group-hover:opacity-100 sm:focus-within:opacity-100
                        transition-opacity duration-200">
          <button
            onClick={e => { e.stopPropagation(); onEdit(item) }}
            className="p-1.5 rounded-lg bg-black/45 backdrop-blur-sm text-white hover:bg-black/65 transition-colors"
            title="Edit item"
            aria-label={`Edit ${item.name}`}
          >
            <Pencil size={13} />
          </button>
          <button
            onClick={e => { e.stopPropagation(); setAvailabilityOpen(o => !o) }}
            className={cn(
              'p-1.5 rounded-lg backdrop-blur-sm text-white transition-colors',
              unavailable ? 'bg-sky-500/80 hover:bg-sky-500' : 'bg-black/45 hover:bg-black/65',
            )}
            title={`Availability: ${AVAILABILITY_LABELS[item.availability ?? 'available']}`}
            aria-label={`Set availability for ${item.name}`}
          >
            <Droplets size={13} />
          </button>
          <button
            onClick={handleDeleteClick}
            disabled={deleting}
            className={cn(
              'flex items-center gap-1 rounded-lg px-1.5 py-1.5 text-[10px] font-semibold backdrop-blur-sm transition-colors disabled:opacity-40',
              confirmingDelete ? 'bg-red-500 text-white' : 'bg-black/45 text-white hover:bg-red-500/80',
            )}
            title={confirmingDelete ? 'Click again to confirm delete' : 'Delete item'}
            aria-label={confirmingDelete ? `Confirm delete ${item.name}` : `Delete ${item.name}`}
          >
            {deleting ? <Loader2 size={13} className="animate-spin" />
              : confirmingDelete ? <><Trash2 size={12} />Delete?</>
              : <Trash2 size={13} />}
          </button>
        </div>

        {availabilityOpen && (
          <AvailabilityMenu item={item} onSetAvailability={onSetAvailability} onClose={() => setAvailabilityOpen(false)} />
        )}
      </div>

      {/* Item name + at-a-glance metadata (mock: name · worn, brand) */}
      <div className="mt-2 px-0.5 flex-1 flex flex-col">
        <div className="flex items-baseline justify-between gap-2">
          <p className="text-sm font-semibold truncate text-slate-800 dark:text-slate-100">{item.name}</p>
          {item.wear_count > 0 && (
            <span className="text-[11px] text-slate-400 whitespace-nowrap">{item.wear_count}× worn</span>
          )}
        </div>
        {item.brand
          ? <p className="text-xs text-slate-400 truncate">{item.brand}</p>
          : item.color && <p className="text-xs text-slate-400 truncate capitalize">{item.color}</p>}
      </div>
    </div>
  )
}


// ── Main page ──────────────────────────────────────────────────────────────────

export default function Closet() {
  const {
    closetItems,
    setClosetItems,
    closetLoading,
    closetError,
    closetHasMore,
    fetchClosetItems,
    loadMoreClosetItems,
    removeClosetItem,
  } = useApp()

  // Persisted filter state — survives navigation, cleared on browser refresh
  const [category, setCategory]       = usePageState<Category>('closet-category', 'all')
  const [favOnly,  setFavOnly]        = usePageState('closet-fav-only', false)
  const [search,   setSearch]         = usePageState('closet-search', '')
  const [sort,     setSort]           = usePageState('closet-sort', 'recent')
  const [filtersOpen, setFiltersOpen] = usePageState('closet-filters-open', false)
  const [colorFilter,    setColorFilter]    = usePageState('closet-color', '')
  const [seasonFilter,   setSeasonFilter]   = usePageState('closet-season', '')
  const [occasionFilter, setOccasionFilter] = usePageState('closet-occasion', '')

  // Transient UI state (not persisted)
  const [selected,  setSelected]  = React.useState<ClosetItem | null>(null)
  const [editItem,  setEditItem]   = React.useState<ClosetItem | null>(null)
  const [deleting,  setDeleting]   = React.useState<string | null>(null)
  const [viewMode,  setViewMode]   = usePageState<'grid' | 'list'>('closet-view', 'grid')
  const [isOffline, setIsOffline] = useState(typeof navigator !== 'undefined' ? !navigator.onLine : false)

  // Restore scroll position across navigations
  useWindowScrollRestoration('closet-scroll')

  useEffect(() => {
    const update = () => setIsOffline(!navigator.onLine)
    window.addEventListener('online', update)
    window.addEventListener('offline', update)
    return () => {
      window.removeEventListener('online', update)
      window.removeEventListener('offline', update)
    }
  }, [])

  // Virtualizer setup
  const cols = useColumnCount()
  const gridRef  = useRef<HTMLDivElement>(null)
  const listRef  = useRef<HTMLDivElement>(null)
  const loadMoreRef = useRef<HTMLDivElement>(null)
  const [gridScrollMargin, setGridScrollMargin] = useState(0)
  const [listScrollMargin, setListScrollMargin] = useState(0)

  const filtered = useMemo(() => {
    let items = closetItems
    if (favOnly) items = items.filter(i => i.is_favorite)
    if (category !== 'all') {
      if (category === 'other') {
        items = items.filter(i =>
          i.category === 'other'
          || i.category === 'uncategorised'
          || !CANONICAL_TAB_CATEGORIES.has(i.category),
        )
      } else {
        items = items.filter(i => i.category === category)
      }
    }
    if (search)  items = items.filter(i =>
      i.name.toLowerCase().includes(search.toLowerCase()) ||
      (i.brand   || '').toLowerCase().includes(search.toLowerCase()) ||
      (i.color   || '').toLowerCase().includes(search.toLowerCase()),
    )
    if (colorFilter)    items = items.filter(i => (i.color || '').toLowerCase().includes(colorFilter.toLowerCase()))
    if (seasonFilter) {
      const want = seasonFilter.toLowerCase()
      items = items.filter(i =>
        (Array.isArray(i.season) ? i.season : []).some(s => s.toLowerCase() === want)
      )
    }
    if (occasionFilter) items = items.filter(i => i.occasion?.includes(occasionFilter))
    if (sort === 'worn') items = [...items].sort((a, b) => b.wear_count - a.wear_count)
    if (sort === 'name') items = [...items].sort((a, b) => a.name.localeCompare(b.name))
    return items
  }, [closetItems, favOnly, category, search, sort, colorFilter, seasonFilter, occasionFilter])

  const isFiltered = favOnly || category !== 'all' || search.trim() !== '' || !!colorFilter || !!seasonFilter || !!occasionFilter
  const favCount = useMemo(() => closetItems.filter(i => i.is_favorite).length, [closetItems])

  // Distinct colors present in the wardrobe (for the swatch filter), most common first
  const colorOptions = useMemo(() => {
    const map = new Map<string, { name: string; hex: string | null; count: number }>()
    for (const i of closetItems) {
      const raw = (i.color || '').trim()
      if (!raw) continue
      const key = raw.toLowerCase()
      const existing = map.get(key)
      if (existing) {
        existing.count++
        if (!existing.hex && i.color_hex) existing.hex = i.color_hex
      } else {
        map.set(key, { name: raw, hex: i.color_hex || null, count: 1 })
      }
    }
    return [...map.values()].sort((a, b) => b.count - a.count)
  }, [closetItems])

  // Rows for the virtual grid (group filtered items by column count)
  const rows = useMemo(() => {
    const out: ClosetItem[][] = []
    for (let i = 0; i < filtered.length; i += cols) {
      out.push(filtered.slice(i, i + cols))
    }
    return out
  }, [filtered, cols])

  // Capture container offsets after layout so virtualizers position items
  // correctly. These intentionally run every render and self-guard against
  // re-renders (no deps array) so they track layout shifts from any source.
  // eslint-disable-next-line react-hooks/exhaustive-deps
  useLayoutEffect(() => {
    const gm = gridRef.current?.offsetTop ?? 0
    if (gm !== gridScrollMargin) setGridScrollMargin(gm)
  })
  // eslint-disable-next-line react-hooks/exhaustive-deps
  useLayoutEffect(() => {
    const lm = listRef.current?.offsetTop ?? 0
    if (lm !== listScrollMargin) setListScrollMargin(lm)
  })

  const gridVirtualizer = useWindowVirtualizer({
    count: rows.length,
    estimateSize: () => 320,
    overscan: 2,
    scrollMargin: gridScrollMargin,
  })

  const listVirtualizer = useWindowVirtualizer({
    count: filtered.length,
    estimateSize: () => 72,
    overscan: 5,
    scrollMargin: listScrollMargin,
  })

  // Auto-load the next page when the sentinel scrolls into view.
  // Only for the full (unfiltered) closet — filtering works on already-loaded items.
  useEffect(() => {
    const el = loadMoreRef.current
    if (!el || isFiltered || !closetHasMore) return
    const io = new IntersectionObserver(
      entries => {
        if (entries[0]?.isIntersecting && closetHasMore && !closetLoading && !isFiltered) {
          void loadMoreClosetItems()
        }
      },
      { rootMargin: '600px 0px' },
    )
    io.observe(el)
    return () => io.disconnect()
  }, [isFiltered, closetHasMore, closetLoading, loadMoreClosetItems])

  const handleItemSaved = (updated: ClosetItem) => {
    setClosetItems(closetItems.map(i => i.id === updated.id ? updated : i))
    setSelected(updated)
  }

  const handleItemEdited = (updated: ClosetItem) => {
    setClosetItems(closetItems.map(i => i.id === updated.id ? updated : i))
    setEditItem(null)
  }

  const handleSetAvailability = async (item: ClosetItem, availability: AvailabilityStatus) => {
    try {
      const updated = await closetApi.update(item.id, { availability })
      setClosetItems(closetItems.map(i => i.id === updated.id ? updated : i))
      if (availability !== 'available') {
        toastStore.add({
          title: AVAILABILITY_LABELS[availability],
          body: `FANI won't suggest "${item.name}" until it's back.`,
          variant: 'default',
        })
      }
    } catch {
      toastStore.add({
        title: 'Update failed',
        body: `Couldn't update availability for "${item.name}". Please try again.`,
        variant: 'error',
      })
    }
  }

  const handleToggleFavorite = async (item: ClosetItem) => {
    const next = !item.is_favorite
    // Optimistic — reflect the heart immediately, roll back to this snapshot on failure.
    const snapshot = closetItems
    const optimistic = closetItems.map(i => i.id === item.id ? { ...i, is_favorite: next } : i)
    setClosetItems(optimistic)
    try {
      const updated = await closetApi.update(item.id, { is_favorite: next })
      setClosetItems(optimistic.map(i => i.id === updated.id ? updated : i))
    } catch {
      setClosetItems(snapshot)
      toastStore.add({
        title: 'Update failed',
        body: `Couldn't update favourite for "${item.name}". Please try again.`,
        variant: 'error',
      })
    }
  }

  const handleDelete = async (item: ClosetItem) => {
    setDeleting(item.id)
    try {
      await closetApi.delete(item.id)
      removeClosetItem(item.id)
      if (selected?.id === item.id) setSelected(null)
      // Re-fetch so we don't keep a ghost row from a stale list cache.
      void fetchClosetItems()
    } catch (err: unknown) {
      // A 404 means the item is already gone on the server (e.g. a double-click,
      // a stale list, or a second tab). That's the desired end state of a delete,
      // so treat it as success and drop it from the list rather than alarming the
      // user with a "couldn't delete" error.
      const status = (err as { response?: { status?: number } })?.response?.status
      if (status === 404) {
        removeClosetItem(item.id)
        if (selected?.id === item.id) setSelected(null)
        void fetchClosetItems()
      } else {
        toastStore.add({
          title: 'Delete failed',
          body: `Couldn't delete "${item.name}". Please try again.`,
          variant: 'error',
        })
      }
    } finally {
      setDeleting(null)
    }
  }

  const clearFilters = () => {
    setCategory('all'); setFavOnly(false); setSearch(''); setSort('recent')
    setColorFilter(''); setSeasonFilter(''); setOccasionFilter('')
  }

  return (
    <div className="space-y-5">

      {/* Contained panel — the mock's clean floating card look */}
      <div className="rounded-3xl border border-cream-200 dark:border-white/[0.08] bg-white/80 dark:bg-white/[0.02] shadow-card p-5 sm:p-7 lg:p-8 space-y-6">

      {/* ── Header (mock: title · count/favourites, search, filter, add items) ── */}
      <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
        <div className="min-w-0">
          <h1 className="text-3xl sm:text-4xl font-display font-bold text-slate-800 dark:text-slate-100">My Closet</h1>
          <p className="text-sm text-slate-500 dark:text-slate-400 mt-1">
            {closetLoading && closetItems.length === 0
              ? 'Syncing…'
              : <>{closetItems.length} item{closetItems.length === 1 ? '' : 's'}{favCount > 0 && ` · ${favCount} favourite${favCount === 1 ? '' : 's'}`}</>}
          </p>
        </div>

        {closetItems.length > 0 && (
          <div className="flex items-center gap-2">
            {/* Search pill */}
            <div className="relative flex-1 lg:flex-none lg:w-64">
              <Search size={15} className="absolute left-3.5 top-1/2 -translate-y-1/2 text-slate-400 pointer-events-none" />
              <input
                className="w-full h-11 pl-10 pr-9 rounded-full text-sm bg-white dark:bg-white/[0.05] border border-cream-300 dark:border-white/10 text-slate-800 dark:text-white placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-brand-500/40 focus:border-brand-400 transition-all"
                placeholder="Search closet"
                value={search}
                onChange={e => setSearch(e.target.value)}
                aria-label="Search your closet"
              />
              {search && (
                <button
                  onClick={() => setSearch('')}
                  aria-label="Clear search"
                  className="absolute right-2.5 top-1/2 -translate-y-1/2 p-1 rounded-full text-slate-400 hover:text-slate-600 dark:hover:text-slate-200 hover:bg-slate-100 dark:hover:bg-white/10 transition-colors"
                >
                  <X size={13} />
                </button>
              )}
            </div>

            {/* Filter button (opens sort / view / advanced filters) */}
            <button
              onClick={() => setFiltersOpen(v => !v)}
              aria-pressed={filtersOpen}
              aria-label="Filters and sort"
              title="Filters & sort"
              className={cn(
                'relative grid place-items-center w-11 h-11 rounded-full border transition-colors shrink-0',
                filtersOpen || colorFilter || seasonFilter || occasionFilter || sort !== 'recent'
                  ? 'bg-brand-50 dark:bg-brand-900/30 border-brand-300 dark:border-brand-700 text-brand-600 dark:text-brand-300'
                  : 'bg-white dark:bg-white/[0.05] border-cream-300 dark:border-white/10 text-slate-500 dark:text-slate-300 hover:border-cream-400 dark:hover:border-white/20',
              )}
            >
              <SlidersHorizontal size={16} />
              {(colorFilter || seasonFilter || occasionFilter) && (
                <span className="absolute -top-0.5 -right-0.5 w-2.5 h-2.5 rounded-full bg-brand-500 ring-2 ring-cream-100 dark:ring-slate-950" />
              )}
            </button>

            {/* Refresh */}
            <button
              onClick={fetchClosetItems}
              disabled={closetLoading}
              className="grid place-items-center w-11 h-11 rounded-full border bg-white dark:bg-white/[0.05] border-cream-300 dark:border-white/10 text-slate-500 dark:text-slate-300 hover:border-cream-400 dark:hover:border-white/20 transition-colors shrink-0"
              title="Refresh wardrobe"
              aria-label="Refresh wardrobe"
            >
              <RefreshCw size={15} className={closetLoading ? 'animate-spin text-brand-500' : ''} />
            </button>

            {/* Add items */}
            <Link
              to="/upload"
              className="flex items-center gap-1.5 h-11 px-4 sm:px-5 rounded-full text-sm font-semibold bg-gradient-to-r from-brand-600 to-brand-700 text-white shadow-glow-sm hover:shadow-glow-md transition-all shrink-0"
            >
              <Plus size={16} /> <span className="hidden sm:inline">Add items</span>
            </Link>
          </div>
        )}
      </div>

      {/* ── Unified loading/error/empty/offline ── */}
      <PageStatePanel
        loading={closetLoading && closetItems.length === 0}
        loadingTitle="Loading your wardrobe..."
        loadingDescription="Hang tight while we fetch your closet items."
        offline={isOffline && closetItems.length === 0}
        error={closetItems.length === 0 ? closetError : null}
        errorTitle="Couldn't load your closet"
        onRetry={() => { void fetchClosetItems() }}
        empty={closetItems.length === 0 && !closetLoading && !closetError}
        emptyIcon={<Shirt size={28} />}
        emptyTitle="Your wardrobe is empty"
        emptyDescription="Drop a photo and FANI will detect your items, remove backgrounds, and auto-tag everything for you."
        emptyPrimaryAction={{ label: 'Add items with AI', href: '/upload' }}
      />

      {/* ── Text tabs (mock: All · Favourites · categories) + Fit Match ── */}
      {closetItems.length > 0 && (
        <div className="flex items-end justify-between gap-3 border-b border-cream-200 dark:border-white/10">
          <div className="flex items-center gap-5 overflow-x-auto scrollbar-hide" role="tablist" aria-label="Filter closet">
            {(() => {
              const otherCount = closetItems.filter(i =>
                i.category === 'other' || i.category === 'uncategorised' || !CANONICAL_TAB_CATEGORIES.has(i.category),
              ).length
              const tabs: { key: string; label: string; count: number; active: boolean; onClick: () => void }[] = [
                { key: 'all', label: 'All', count: closetItems.length, active: !favOnly && category === 'all', onClick: () => { setFavOnly(false); setCategory('all') } },
              ]
              if (favCount > 0) tabs.push({ key: 'fav', label: 'Favourites', count: favCount, active: favOnly, onClick: () => { setFavOnly(true); setCategory('all') } })
              for (const cat of CLOSET_CATEGORY_TABS) {
                if (cat.value === 'all') continue
                const count = cat.value === 'other' ? otherCount : closetItems.filter(i => i.category === cat.value).length
                if (count === 0) continue
                tabs.push({ key: cat.value, label: cat.label, count, active: !favOnly && category === cat.value, onClick: () => { setFavOnly(false); setCategory(cat.value) } })
              }
              return tabs.map(t => (
                <button
                  key={t.key}
                  role="tab"
                  aria-selected={t.active}
                  onClick={t.onClick}
                  className={cn(
                    'relative pb-2.5 text-sm font-semibold whitespace-nowrap transition-colors',
                    t.active ? 'text-brand-600 dark:text-brand-400' : 'text-slate-500 dark:text-slate-400 hover:text-slate-800 dark:hover:text-slate-200',
                  )}
                >
                  {t.label}
                  <span className={cn('ml-1 text-xs font-medium', t.active ? 'text-brand-400 dark:text-brand-500' : 'text-slate-400 dark:text-slate-500')}>{t.count}</span>
                  {t.active && <span className="absolute -bottom-px left-0 right-0 h-0.5 rounded-full bg-brand-500" />}
                </button>
              ))
            })()}
          </div>
          <Link
            to="/closet-match"
            className="shrink-0 flex items-center gap-1.5 pb-2.5 text-sm font-semibold text-brand-600 dark:text-brand-400 hover:text-brand-700 dark:hover:text-brand-300 transition-colors"
          >
            <Wand2 size={14} /> <span className="hidden sm:inline">Fit Match</span>
          </Link>
        </div>
      )}

      {/* ── Filters & sort panel (opened from the header filter button) ── */}
      {closetItems.length > 0 && filtersOpen && (
        <div className="rounded-2xl border border-cream-200 dark:border-white/10 bg-white/70 dark:bg-white/[0.03] p-4 flex flex-wrap items-start gap-x-6 gap-y-4">
          <div className="flex flex-col gap-1">
            <label className="text-[10px] font-semibold text-slate-500 uppercase tracking-wide">Sort</label>
            <div className="relative">
              <ArrowUpDown size={13} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400 pointer-events-none" />
              <select
                className="input pl-8 pr-8 appearance-none text-sm py-1.5 w-44"
                value={sort}
                onChange={e => setSort(e.target.value)}
              >
                {CLOSET_SORT_OPTIONS.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
              </select>
            </div>
          </div>

          <div className="flex flex-col gap-1">
            <label className="text-[10px] font-semibold text-slate-500 uppercase tracking-wide">View</label>
            <div className="flex rounded-xl border border-cream-300 dark:border-white/10 overflow-hidden w-fit">
              <button
                onClick={() => setViewMode('grid')}
                title="Grid view" aria-label="Grid view" aria-pressed={viewMode === 'grid'}
                className={cn('px-3 py-1.5 flex items-center justify-center transition-colors',
                  viewMode === 'grid' ? 'bg-brand-500 text-white' : 'bg-white dark:bg-slate-800/60 text-slate-400 hover:text-slate-600 dark:hover:text-slate-200')}
              >
                <LayoutGrid size={15} />
              </button>
              <button
                onClick={() => setViewMode('list')}
                title="List view" aria-label="List view" aria-pressed={viewMode === 'list'}
                className={cn('px-3 py-1.5 flex items-center justify-center transition-colors border-l border-cream-300 dark:border-white/10',
                  viewMode === 'list' ? 'bg-brand-500 text-white' : 'bg-white dark:bg-slate-800/60 text-slate-400 hover:text-slate-600 dark:hover:text-slate-200')}
              >
                <List size={15} />
              </button>
            </div>
          </div>

          <div className="flex flex-col gap-1">
            <label className="text-[10px] font-semibold text-slate-500 uppercase tracking-wide">Color</label>
            {colorOptions.length === 0 ? (
              <span className="text-xs text-slate-400 py-1.5">No colours tagged yet</span>
            ) : (
              <div className="flex flex-wrap gap-1.5 max-w-[280px] pt-0.5">
                {colorOptions.map(c => {
                  const active = colorFilter.toLowerCase() === c.name.toLowerCase()
                  return (
                    <button
                      key={c.name}
                      type="button"
                      onClick={() => setColorFilter(active ? '' : c.name)}
                      title={`${c.name} · ${c.count} item${c.count !== 1 ? 's' : ''}`}
                      aria-label={`Filter by ${c.name}`}
                      aria-pressed={active}
                      className={cn(
                        'w-7 h-7 rounded-full border-2 flex items-center justify-center transition-all',
                        active ? 'border-brand-500 ring-2 ring-brand-300/50 scale-110' : 'border-white dark:border-slate-600 hover:scale-105 shadow-sm',
                      )}
                      style={{ backgroundColor: c.hex || '#cbd5e1' }}
                    >
                      {active && <Check size={12} className="text-white drop-shadow-[0_1px_1px_rgba(0,0,0,0.5)]" />}
                    </button>
                  )
                })}
              </div>
            )}
          </div>

          <div className="flex flex-col gap-1">
            <label className="text-[10px] font-semibold text-slate-500 uppercase tracking-wide">Season</label>
            <select className="input text-sm py-1.5 px-3 w-36 appearance-none" value={seasonFilter} onChange={e => setSeasonFilter(e.target.value)}>
              <option value="">All seasons</option>
              {CLOSET_SEASONS.map(s => <option key={s} value={s} className="capitalize">{s.charAt(0).toUpperCase() + s.slice(1)}</option>)}
            </select>
          </div>

          <div className="flex flex-col gap-1">
            <label className="text-[10px] font-semibold text-slate-500 uppercase tracking-wide">Occasion</label>
            <select className="input text-sm py-1.5 px-3 w-36 appearance-none" value={occasionFilter} onChange={e => setOccasionFilter(e.target.value)}>
              <option value="">All occasions</option>
              {CLOSET_OCCASIONS.map(o => <option key={o} value={o} className="capitalize">{o.charAt(0).toUpperCase() + o.slice(1)}</option>)}
            </select>
          </div>

          {(colorFilter || seasonFilter || occasionFilter) && (
            <div className="flex flex-col gap-1 justify-end">
              <span className="text-[10px] font-semibold text-transparent uppercase tracking-wide select-none">Clear</span>
              <button
                onClick={() => { setColorFilter(''); setSeasonFilter(''); setOccasionFilter('') }}
                className="flex items-center gap-1 text-xs text-slate-400 hover:text-slate-600 dark:hover:text-slate-200 transition-colors py-1.5"
              >
                <X size={12} /> Clear filters
              </button>
            </div>
          )}
        </div>
      )}

      {/* Active filter pills */}
      {closetItems.length > 0 && isFiltered && (
        <div className="flex items-center gap-2 flex-wrap">
          <span className="text-xs text-slate-400">Active:</span>
          {favOnly && <FilterPill label="Favourites" onRemove={() => setFavOnly(false)} />}
          {category !== 'all' && <FilterPill label={`Category: ${category}`} onRemove={() => setCategory('all')} />}
          {search && <FilterPill label={`"${search}"`} onRemove={() => setSearch('')} />}
          {colorFilter && <FilterPill label={`Color: ${colorFilter}`} onRemove={() => setColorFilter('')} />}
          {seasonFilter && <FilterPill label={`Season: ${seasonFilter}`} onRemove={() => setSeasonFilter('')} />}
          {occasionFilter && <FilterPill label={`Occasion: ${occasionFilter}`} onRemove={() => setOccasionFilter('')} />}
          <button onClick={clearFilters} className="text-xs text-brand-500 hover:text-brand-700 font-medium transition-colors">
            Clear all
          </button>
        </div>
      )}

      {/* ── No filter results / per-category empty state ── */}
      {closetItems.length > 0 && filtered.length === 0 && !closetLoading && (
        category !== 'all' && !search && !colorFilter && !seasonFilter && !occasionFilter
          ? /* Per-category contextual empty */
            <div className="flex flex-col items-center justify-center py-16 gap-3 text-center">
              <span className="text-5xl">{CLOSET_CATEGORY_TABS.find(c => c.value === category)?.emoji ?? '👕'}</span>
              <p className="font-semibold text-slate-700 dark:text-slate-200">
                No {CLOSET_CATEGORY_TABS.find(c => c.value === category)?.label ?? category} yet
              </p>
              <p className="text-xs text-slate-400 max-w-xs">
                Upload a photo and AI will detect and categorise your {(CLOSET_CATEGORY_TABS.find(c => c.value === category)?.label ?? category).toLowerCase()} automatically.
              </p>
              <Link
                to="/upload"
                className="flex items-center gap-2 mt-1 px-5 py-2 rounded-xl text-sm font-semibold bg-gradient-to-r from-brand-500 to-brand-600 text-white hover:opacity-90 transition-opacity"
              >
                <Plus size={14} /> Add {CLOSET_CATEGORY_TABS.find(c => c.value === category)?.label}
              </Link>
            </div>
          : /* Generic no-results */
            <div className="flex flex-col items-center justify-center py-16 gap-4">
              <div className="text-5xl">🔍</div>
              <div className="text-center">
                <p className="font-semibold text-slate-600 dark:text-slate-400">No items match your filters</p>
                <p className="text-xs text-slate-400 mt-1">Try adjusting or clearing your filters</p>
              </div>
              <button onClick={clearFilters} className="btn-primary px-5 py-2 rounded-xl text-sm">Clear filters</button>
            </div>
      )}

      {/* ── Main grid / list (airy, header-less like the mock) ── */}
      {filtered.length > 0 && (
        <section>

          {viewMode === 'grid' ? (
            <div
              ref={gridRef}
              style={{ height: `${gridVirtualizer.getTotalSize()}px`, position: 'relative' }}
            >
              {gridVirtualizer.getVirtualItems().map(vRow => (
                <div
                  key={vRow.key}
                  data-index={vRow.index}
                  ref={gridVirtualizer.measureElement}
                  style={{
                    position: 'absolute',
                    top: 0,
                    left: 0,
                    width: '100%',
                    transform: `translateY(${vRow.start - gridVirtualizer.options.scrollMargin}px)`,
                  }}
                >
                  <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 gap-x-5 gap-y-7 pb-7">
                    {rows[vRow.index].map(item => (
                      <ClosetItemCard
                        key={item.id}
                        item={item}
                        onOpen={setSelected}
                        onDelete={handleDelete}
                        onEdit={setEditItem}
                        onSetAvailability={handleSetAvailability}
                        onToggleFavorite={handleToggleFavorite}
                        deleting={deleting === item.id}
                      />
                    ))}
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <div
              ref={listRef}
              style={{ height: `${listVirtualizer.getTotalSize()}px`, position: 'relative' }}
            >
              {listVirtualizer.getVirtualItems().map(vRow => (
                <div
                  key={vRow.key}
                  data-index={vRow.index}
                  ref={listVirtualizer.measureElement}
                  style={{
                    position: 'absolute',
                    top: 0,
                    left: 0,
                    width: '100%',
                    transform: `translateY(${vRow.start - listVirtualizer.options.scrollMargin}px)`,
                    paddingBottom: '8px',
                  }}
                >
                  <ClosetListRow
                    item={filtered[vRow.index]}
                    onOpen={setSelected}
                    onEdit={setEditItem}
                    onDelete={handleDelete}
                    deleting={deleting === filtered[vRow.index].id}
                  />
                </div>
              ))}
            </div>
          )}
        </section>
      )}

      {/* Infinite-scroll sentinel — auto-loads the next page near the bottom */}
      {!isFiltered && closetHasMore && (
        <div ref={loadMoreRef} className="flex items-center justify-center py-6 text-xs text-slate-400">
          {closetLoading ? <Loader2 size={16} className="animate-spin text-brand-500" /> : 'Scroll for more'}
        </div>
      )}

      </div>{/* /contained panel */}

      <ItemDetailModal
        item={selected}
        open={!!selected}
        onClose={() => setSelected(null)}
        onDelete={handleDelete}
        onSaved={handleItemSaved}
      />

      {editItem && (
        <EditItemModal
          item={editItem}
          open={!!editItem}
          onClose={() => setEditItem(null)}
          onSaved={handleItemEdited}
        />
      )}
    </div>
  )
}

// ── Filter pill ────────────────────────────────────────────────────────────────

function FilterPill({ label, onRemove }: { label: string; onRemove: () => void }) {
  return (
    <span className="inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-[11px] font-semibold bg-brand-100 dark:bg-brand-900/40 text-brand-700 dark:text-brand-300 border border-brand-200 dark:border-brand-700">
      {label}
      <button onClick={onRemove} className="hover:text-brand-900 dark:hover:text-white ml-0.5">
        <X size={10} />
      </button>
    </span>
  )
}
