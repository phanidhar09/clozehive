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
import PageHeader from '@/components/ui/PageHeader'
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
    if (w >= 1280) return 6
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
          <span className="font-semibold">{item.wear_count}×</span>
        )}
        {item.eco_score != null && item.eco_score >= 7 && (
          <span className="font-bold text-emerald-500">🌱{item.eco_score}</span>
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

// ── Favourites section ─────────────────────────────────────────────────────────

function FavouritesSection({
  items, onOpen, onDelete, onEdit, onSetAvailability, deleting,
}: { items: ClosetItem[]; onOpen: (i: ClosetItem) => void; onDelete: (i: ClosetItem) => void; onEdit: (i: ClosetItem) => void; onSetAvailability: (i: ClosetItem, s: AvailabilityStatus) => void; deleting: string | null }) {
  const favs = useMemo(() => items.filter(i => i.is_favorite), [items])
  if (favs.length === 0) return null

  return (
    <section>
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2">
          <Heart size={14} className="text-pink-500 fill-pink-500" />
          <h3 className="font-semibold text-sm text-slate-700 dark:text-slate-200">Favourites</h3>
        </div>
        <span className="text-[11px] text-slate-400">{favs.length} item{favs.length !== 1 ? 's' : ''}</span>
      </div>
      {/* Horizontal scroll strip */}
      <div className="flex gap-3 overflow-x-auto pb-1 scrollbar-hide">
        {favs.map(item => (
          <div key={item.id} className="flex-shrink-0 w-[120px]">
            <ClosetItemCard item={item} onOpen={onOpen} onDelete={onDelete} onEdit={onEdit} onSetAvailability={onSetAvailability} deleting={deleting === item.id} />
          </div>
        ))}
      </div>
    </section>
  )
}

// ── Sub-components ─────────────────────────────────────────────────────────────

function CategoryTab({
  cat, active, count, onClick,
}: { cat: typeof CLOSET_CATEGORY_TABS[0]; active: boolean; count: number; onClick: () => void }) {
  return (
    <button
      onClick={onClick}
      role="tab"
      aria-selected={active}
      aria-label={`${cat.label}${count > 0 ? ` (${count})` : ''}`}
      className={cn(
        'flex flex-col items-center gap-1.5 px-4 py-2.5 rounded-2xl text-xs font-semibold transition-colors duration-200 flex-shrink-0',
        active
          ? 'bg-brand-500 text-white shadow-sm'
          : 'bg-white/60 dark:bg-white/5 text-slate-600 dark:text-slate-300 hover:bg-white dark:hover:bg-white/10 border border-white/80 dark:border-white/10',
      )}
    >
      <span className="text-lg leading-none">{cat.emoji}</span>
      <span>{cat.label}</span>
      {count > 0 && (
        <span className={cn(
          'text-[9px] font-bold rounded-full px-1.5 py-0.5 min-w-[16px] text-center',
          active ? 'bg-white/25 text-white' : 'bg-brand-100 dark:bg-brand-900/40 text-brand-600 dark:text-brand-300',
        )}>
          {count}
        </span>
      )}
    </button>
  )
}

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
  item, onOpen, onDelete, onEdit, onSetAvailability, deleting,
}: { item: ClosetItem; onOpen: (i: ClosetItem) => void; onDelete: (i: ClosetItem) => void; onEdit: (i: ClosetItem) => void; onSetAvailability: (i: ClosetItem, s: AvailabilityStatus) => void; deleting: boolean }) {
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

        {/* Eco badge */}
        {item.eco_score != null && item.eco_score >= 7 && (
          <div className="absolute top-2 right-2 z-20 rounded-full bg-emerald-500/90 backdrop-blur-sm px-1.5 py-0.5 text-[9px] font-bold text-white">
            🌱 {item.eco_score}/10
          </div>
        )}

        {/* Wear count */}
        {item.wear_count > 0 && (
          <div className="absolute bottom-2 right-2 z-20 rounded-full bg-black/40 backdrop-blur-sm px-1.5 py-0.5 text-[9px] font-semibold text-white">
            {item.wear_count}×
          </div>
        )}

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

      {/* Item name + at-a-glance metadata */}
      <div className="mt-1.5 px-0.5 flex-1 flex flex-col">
        <p className="text-xs font-semibold truncate text-slate-700 dark:text-slate-200">{item.name}</p>
        {item.brand && <p className="text-[10px] text-slate-400 truncate">{item.brand}</p>}
        {/* Color swatch — at-a-glance color without hovering */}
        {item.color && (
          <div className="flex items-center gap-1 mt-0.5">
            {item.color_hex
              ? <span className="w-2.5 h-2.5 rounded-full border border-slate-300 dark:border-white/20 flex-shrink-0" style={{ backgroundColor: item.color_hex }} />
              : <span className="flex h-2.5 w-2.5 items-center justify-center rounded-full border border-slate-300 dark:border-white/20 text-[6px] font-bold uppercase text-slate-400 flex-shrink-0">{item.color.charAt(0)}</span>
            }
            <span className="text-[10px] text-slate-400 truncate capitalize">{item.color}</span>
          </div>
        )}
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
    closetTotal,
    closetHasMore,
    fetchClosetItems,
    loadMoreClosetItems,
    removeClosetItem,
  } = useApp()

  // Persisted filter state — survives navigation, cleared on browser refresh
  const [category, setCategory]       = usePageState<Category>('closet-category', 'all')
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
    if (sort === 'eco')  items = [...items].sort((a, b) => (b.eco_score ?? 0) - (a.eco_score ?? 0))
    if (sort === 'name') items = [...items].sort((a, b) => a.name.localeCompare(b.name))
    return items
  }, [closetItems, category, search, sort, colorFilter, seasonFilter, occasionFilter])

  const isFiltered = category !== 'all' || search.trim() !== '' || !!colorFilter || !!seasonFilter || !!occasionFilter

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

  const handleDelete = async (item: ClosetItem) => {
    setDeleting(item.id)
    try {
      await closetApi.delete(item.id)
      removeClosetItem(item.id)
      if (selected?.id === item.id) setSelected(null)
    } catch (err: unknown) {
      // A 404 means the item is already gone on the server (e.g. a double-click,
      // a stale list, or a second tab). That's the desired end state of a delete,
      // so treat it as success and drop it from the list rather than alarming the
      // user with a "couldn't delete" error.
      const status = (err as { response?: { status?: number } })?.response?.status
      if (status === 404) {
        removeClosetItem(item.id)
        if (selected?.id === item.id) setSelected(null)
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
    setCategory('all'); setSearch(''); setSort('recent')
    setColorFilter(''); setSeasonFilter(''); setOccasionFilter('')
  }

  return (
    <div className="space-y-5">

      {/* ── Header ── */}
      <PageHeader
        icon={<Shirt size={18} />}
        title="My Closet"
        subtitle={
          closetLoading
            ? 'Syncing…'
            : isFiltered
              ? `Showing ${filtered.length} of ${closetItems.length} loaded (${closetTotal} total)`
              : `Showing ${closetItems.length} of ${closetTotal || closetItems.length} items`
        }
        actions={
          <button
            onClick={fetchClosetItems}
            disabled={closetLoading}
            className="btn-ghost p-2 min-h-[44px] min-w-[44px] rounded-xl"
            title="Refresh wardrobe"
          >
            <RefreshCw size={15} className={closetLoading ? 'animate-spin text-brand-500' : ''} />
          </button>
        }
      />

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

      {/* ── Closet actions strip — single consistent treatment, one accent ── */}
      <div className="flex items-center gap-2">
        <Link
          to="/upload"
          className="flex items-center gap-1.5 px-3 py-2 rounded-xl text-xs font-semibold bg-brand-500 text-white shadow-sm hover:bg-brand-600 transition-colors"
        >
          <Plus size={13} /> Add Items
        </Link>
        <Link
          to="/closet-match"
          className="flex items-center gap-1.5 px-3 py-2 rounded-xl text-xs font-semibold bg-brand-50 dark:bg-brand-900/20 text-brand-600 dark:text-brand-300 border border-brand-200 dark:border-brand-700 hover:bg-brand-100 dark:hover:bg-brand-800/40 transition-colors"
        >
          <Wand2 size={13} /> Fit Match
        </Link>
      </div>

      {/* ── Category tabs — hidden when closet is empty ── */}
      {closetItems.length > 0 && <div className="relative">
        <div className="flex gap-2.5 overflow-x-auto pb-1 scrollbar-hide" role="tablist" aria-label="Filter by category">
          {CLOSET_CATEGORY_TABS.map(cat => {
            const count = cat.value === 'all'
              ? closetItems.length
              : cat.value === 'other'
                ? closetItems.filter(i =>
                    i.category === 'other'
                    || i.category === 'uncategorised'
                    || !CANONICAL_TAB_CATEGORIES.has(i.category),
                  ).length
                : closetItems.filter(i => i.category === cat.value).length
            return (
              <CategoryTab
                key={cat.value}
                cat={cat}
                active={category === cat.value}
                count={count}
                onClick={() => setCategory(cat.value)}
              />
            )
          })}
        </div>
      </div>}

      {/* ── Search + Filters bar — hidden when closet is empty ── */}
      {closetItems.length > 0 &&
      <div className="backdrop-blur-sm bg-white/60 dark:bg-white/5 border border-white/80 dark:border-white/10 rounded-2xl p-4 space-y-3">
        <div className="flex gap-3 flex-wrap sm:flex-nowrap">
          <div className="relative flex-1 min-w-48">
            <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
            <input
              className="input pl-9 pr-9 bg-white/70 dark:bg-slate-800/70"
              placeholder="Search by name, brand, color…"
              value={search}
              onChange={e => setSearch(e.target.value)}
              aria-label="Search your closet"
            />
            {search && (
              <button
                onClick={() => setSearch('')}
                aria-label="Clear search"
                className="absolute right-2 top-1/2 -translate-y-1/2 p-1 rounded-full text-slate-400 hover:text-slate-600 dark:hover:text-slate-200 hover:bg-slate-100 dark:hover:bg-white/10 transition-colors"
              >
                <X size={13} />
              </button>
            )}
          </div>

          <div className="flex gap-2">
            <div className="relative">
              <ArrowUpDown size={13} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400 pointer-events-none" />
              <select
                className="input pl-8 pr-8 appearance-none text-sm min-h-[44px]"
                value={sort}
                onChange={e => setSort(e.target.value)}
              >
                {CLOSET_SORT_OPTIONS.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
              </select>
            </div>

            <button
              onClick={() => setFiltersOpen(v => !v)}
              className={cn(
                'flex items-center gap-1.5 px-3 py-2 rounded-xl text-sm font-semibold transition-all min-h-[44px]',
                filtersOpen || (colorFilter || seasonFilter || occasionFilter)
                  ? 'bg-brand-100 dark:bg-brand-900/40 text-brand-600 dark:text-brand-300 border border-brand-300 dark:border-brand-700'
                  : 'btn-secondary',
              )}
            >
              <SlidersHorizontal size={14} />
              Filters
              {(colorFilter || seasonFilter || occasionFilter) && (
                <span className="w-2 h-2 rounded-full bg-brand-500 ml-0.5" />
              )}
            </button>

            {/* Grid / List toggle */}
            <div className="flex rounded-xl border border-slate-200 dark:border-white/10 overflow-hidden flex-shrink-0 min-h-[44px]">
              <button
                onClick={() => setViewMode('grid')}
                title="Grid view"
                aria-label="Grid view"
                aria-pressed={viewMode === 'grid'}
                className={cn(
                  'px-3 flex items-center justify-center transition-colors',
                  viewMode === 'grid'
                    ? 'bg-brand-500 text-white'
                    : 'bg-white dark:bg-slate-800/60 text-slate-400 hover:text-slate-600 dark:hover:text-slate-200',
                )}
              >
                <LayoutGrid size={15} />
              </button>
              <button
                onClick={() => setViewMode('list')}
                title="List view"
                aria-label="List view"
                aria-pressed={viewMode === 'list'}
                className={cn(
                  'px-3 flex items-center justify-center transition-colors border-l border-slate-200 dark:border-white/10',
                  viewMode === 'list'
                    ? 'bg-brand-500 text-white'
                    : 'bg-white dark:bg-slate-800/60 text-slate-400 hover:text-slate-600 dark:hover:text-slate-200',
                )}
              >
                <List size={15} />
              </button>
            </div>
          </div>
        </div>

        {/* ── Advanced filters (animated collapsible) ── */}
        <div className={cn(
          'overflow-hidden transition-all duration-200 ease-in-out',
          filtersOpen ? 'max-h-72 opacity-100' : 'max-h-0 opacity-0 pointer-events-none',
        )}>
          <div className="flex gap-3 flex-wrap pt-3 border-t border-slate-200 dark:border-white/10">
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
                          active
                            ? 'border-brand-500 ring-2 ring-brand-300/50 scale-110'
                            : 'border-white dark:border-slate-600 hover:scale-105 shadow-sm',
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
              <select
                className="input text-sm py-1.5 px-3 w-36 appearance-none"
                value={seasonFilter}
                onChange={e => setSeasonFilter(e.target.value)}
              >
                <option value="">All seasons</option>
                {CLOSET_SEASONS.map(s => <option key={s} value={s} className="capitalize">{s.charAt(0).toUpperCase() + s.slice(1)}</option>)}
              </select>
            </div>

            <div className="flex flex-col gap-1">
              <label className="text-[10px] font-semibold text-slate-500 uppercase tracking-wide">Occasion</label>
              <select
                className="input text-sm py-1.5 px-3 w-36 appearance-none"
                value={occasionFilter}
                onChange={e => setOccasionFilter(e.target.value)}
              >
                <option value="">All occasions</option>
                {CLOSET_OCCASIONS.map(o => <option key={o} value={o} className="capitalize">{o.charAt(0).toUpperCase() + o.slice(1)}</option>)}
              </select>
            </div>

            {(colorFilter || seasonFilter || occasionFilter) && (
              <div className="flex items-end">
                <button
                  onClick={() => { setColorFilter(''); setSeasonFilter(''); setOccasionFilter('') }}
                  className="flex items-center gap-1 text-xs text-slate-400 hover:text-slate-600 dark:hover:text-slate-200 transition-colors py-1.5"
                >
                  <X size={12} /> Clear filters
                </button>
              </div>
            )}
          </div>
        </div>

        {/* Active filter pills */}
        {isFiltered && (
          <div className="flex items-center gap-2 flex-wrap">
            <span className="text-xs text-slate-400">Active:</span>
            {category !== 'all' && (
              <FilterPill label={`Category: ${category}`} onRemove={() => setCategory('all')} />
            )}
            {search && <FilterPill label={`"${search}"`} onRemove={() => setSearch('')} />}
            {colorFilter && <FilterPill label={`Color: ${colorFilter}`} onRemove={() => setColorFilter('')} />}
            {seasonFilter && <FilterPill label={`Season: ${seasonFilter}`} onRemove={() => setSeasonFilter('')} />}
            {occasionFilter && <FilterPill label={`Occasion: ${occasionFilter}`} onRemove={() => setOccasionFilter('')} />}
            <button onClick={clearFilters} className="text-xs text-brand-500 hover:text-brand-700 font-medium transition-colors">
              Clear all
            </button>
          </div>
        )}
      </div>}

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

      {/* ── Favourites pinned section ── */}
      {!isFiltered && (
        <FavouritesSection
          items={closetItems}
          onOpen={setSelected}
          onDelete={handleDelete}
          onEdit={setEditItem}
          onSetAvailability={handleSetAvailability}
          deleting={deleting}
        />
      )}


      {/* ── Main grid / list ── */}
      {filtered.length > 0 && (
        <section>
          <div className="flex items-center justify-between mb-3">
            <div className="flex items-center gap-2">
              <LayoutGrid size={15} className="text-brand-500" />
              <h3 className="font-semibold text-sm text-slate-700 dark:text-slate-200">
                {isFiltered
                  ? `${filtered.length} result${filtered.length !== 1 ? 's' : ''}`
                  : category === 'all' ? 'All Items' : CLOSET_CATEGORY_TABS.find(c => c.value === category)?.label ?? 'Items'}
              </h3>
            </div>
            {/* Load more lives here now — only relevant for the full (unfiltered) closet */}
            {!isFiltered && closetHasMore && (
              <button
                type="button"
                onClick={() => { void loadMoreClosetItems() }}
                disabled={closetLoading}
                className="text-xs font-semibold text-brand-600 dark:text-brand-400 hover:underline disabled:opacity-50"
              >
                {closetLoading ? 'Loading…' : 'Load more'}
              </button>
            )}
          </div>

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
                  <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 xl:grid-cols-6 gap-3 pb-3">
                    {rows[vRow.index].map(item => (
                      <ClosetItemCard
                        key={item.id}
                        item={item}
                        onOpen={setSelected}
                        onDelete={handleDelete}
                        onEdit={setEditItem}
                        onSetAvailability={handleSetAvailability}
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
