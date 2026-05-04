import { useEffect, useMemo, useRef, useState, type RefObject } from 'react'
import { useVirtualizer } from '@tanstack/react-virtual'
import {
  Search, SlidersHorizontal, Loader2, RefreshCw, Trash2, X,
  Sparkles, Upload, ChevronRight, Star, Clock, TrendingUp,
} from 'lucide-react'
import { useApp } from '@/store'
import { closetApi } from '@/lib/api'
import ItemDetailModal from '@/components/closet/ItemDetailModal'
import Badge from '@/components/ui/Badge'
import RevealCard from '@/components/ui/RevealCard'
import type { ClosetItem, Category } from '@/types'
import { categoryIcon, cn } from '@/lib/utils'

// ── Constants ──────────────────────────────────────────────────────────────────

const CATEGORIES: { value: Category; label: string; emoji: string }[] = [
  { value: 'all',        label: 'All',         emoji: '✨' },
  { value: 'tops',       label: 'Tops',        emoji: '👕' },
  { value: 'bottoms',    label: 'Bottoms',     emoji: '👖' },
  { value: 'shoes',      label: 'Shoes',       emoji: '👟' },
  { value: 'outerwear',  label: 'Outerwear',   emoji: '🧥' },
  { value: 'dresses',    label: 'Dresses',     emoji: '👗' },
  { value: 'accessories',label: 'Accessories', emoji: '👜' },
]

const SORT_OPTIONS = [
  { value: 'recent', label: 'Recently added' },
  { value: 'worn',   label: 'Most worn' },
  { value: 'eco',    label: 'Eco score' },
  { value: 'name',   label: 'Name A–Z' },
]

const SEASONS  = ['spring', 'summer', 'fall', 'winter']
const OCCASIONS = ['casual', 'formal', 'work', 'sport', 'evening', 'travel']

// ── Grid helpers ───────────────────────────────────────────────────────────────

function columnsForWidth(width: number) {
  if (width >= 1280) return 5
  if (width >= 1024) return 4
  if (width >= 640)  return 3
  return 2
}

function useColumnCount(ref: RefObject<HTMLElement>) {
  const [columns, setColumns] = useState(2)
  useEffect(() => {
    const node = ref.current
    if (!node) return
    const update = () => setColumns(columnsForWidth(node.clientWidth))
    update()
    const ro = new ResizeObserver(update)
    ro.observe(node)
    return () => ro.disconnect()
  }, [ref])
  return columns
}

// ── Sub-components ─────────────────────────────────────────────────────────────

function CategoryTab({
  cat, active, count, onClick,
}: { cat: typeof CATEGORIES[0]; active: boolean; count: number; onClick: () => void }) {
  return (
    <button
      onClick={onClick}
      className={cn(
        'flex flex-col items-center gap-1.5 px-4 py-2.5 rounded-2xl text-xs font-semibold transition-all duration-200 flex-shrink-0',
        active
          ? 'bg-gradient-to-br from-brand-500 to-violet-500 text-white shadow-lg shadow-brand-500/30 scale-105'
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

function ClosetItemCard({
  item, onOpen, onDelete, deleting,
}: { item: ClosetItem; onOpen: (i: ClosetItem) => void; onDelete: (i: ClosetItem) => void; deleting: boolean }) {
  const isTransparent = item.image_url?.endsWith('.png')

  return (
    <div className="group relative">
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
        <RevealCard item={item} onOpen={onOpen} className="absolute inset-0 rounded-2xl" />

        {/* Delete button */}
        <button
          onClick={e => { e.stopPropagation(); onDelete(item) }}
          disabled={deleting}
          className="absolute top-2 left-2 p-1.5 rounded-lg bg-black/50 text-white opacity-0 group-hover:opacity-100 transition-opacity hover:bg-red-500 z-20 backdrop-blur-sm"
          title="Delete"
        >
          {deleting ? <Loader2 size={11} className="animate-spin" /> : <Trash2 size={11} />}
        </button>

        {/* Eco badge */}
        {item.eco_score != null && item.eco_score >= 7 && (
          <div className="absolute top-2 right-2 z-20 rounded-full bg-emerald-500/90 backdrop-blur-sm px-1.5 py-0.5 text-[9px] font-bold text-white">
            🌱 {item.eco_score}/10
          </div>
        )}

        {/* Wear count */}
        {item.wear_count > 0 && (
          <div className="absolute bottom-10 right-2 z-20 rounded-full bg-black/40 backdrop-blur-sm px-1.5 py-0.5 text-[9px] font-semibold text-white">
            {item.wear_count}×
          </div>
        )}
      </div>

      {/* Item name below card */}
      <div className="mt-1.5 px-0.5">
        <p className="text-xs font-semibold truncate text-slate-700 dark:text-slate-200">{item.name}</p>
        {item.brand && <p className="text-[10px] text-slate-400 truncate">{item.brand}</p>}
      </div>
    </div>
  )
}

function RecentlyAddedSection({
  items, onOpen, onDelete, deleting,
}: { items: ClosetItem[]; onOpen: (i: ClosetItem) => void; onDelete: (i: ClosetItem) => void; deleting: string | null }) {
  const recent = useMemo(() =>
    [...items].sort((a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime()).slice(0, 6)
  , [items])

  if (recent.length === 0) return null

  return (
    <section>
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2">
          <Clock size={15} className="text-brand-500" />
          <h3 className="font-semibold text-sm text-slate-700 dark:text-slate-200">Recently Added</h3>
        </div>
        <span className="text-[11px] text-slate-400">{recent.length} items</span>
      </div>
      <div className="grid grid-cols-3 sm:grid-cols-4 md:grid-cols-5 lg:grid-cols-6 gap-3">
        {recent.map(item => (
          <ClosetItemCard
            key={item.id}
            item={item}
            onOpen={onOpen}
            onDelete={onDelete}
            deleting={deleting === item.id}
          />
        ))}
      </div>
    </section>
  )
}

// ── Main page ──────────────────────────────────────────────────────────────────

export default function Closet() {
  const { closetItems, closetLoading, closetError, fetchClosetItems, removeClosetItem } = useApp()
  const scrollRef = useRef<HTMLDivElement>(null)
  const columnCount = useColumnCount(scrollRef)

  const [category, setCategory]     = useState<Category>('all')
  const [search,   setSearch]       = useState('')
  const [sort,     setSort]         = useState('recent')
  const [selected, setSelected]     = useState<ClosetItem | null>(null)
  const [deleting, setDeleting]     = useState<string | null>(null)
  const [filtersOpen, setFiltersOpen] = useState(false)
  const [colorFilter,    setColorFilter]    = useState('')
  const [seasonFilter,   setSeasonFilter]   = useState('')
  const [occasionFilter, setOccasionFilter] = useState('')

  const filtered = useMemo(() => {
    let items = closetItems
    if (category !== 'all') items = items.filter(i => i.category === category)
    if (search)  items = items.filter(i =>
      i.name.toLowerCase().includes(search.toLowerCase()) ||
      (i.brand   || '').toLowerCase().includes(search.toLowerCase()) ||
      (i.color   || '').toLowerCase().includes(search.toLowerCase()),
    )
    if (colorFilter)    items = items.filter(i => (i.color || '').toLowerCase().includes(colorFilter.toLowerCase()))
    if (seasonFilter)   items = items.filter(i => i.season?.toLowerCase() === seasonFilter)
    if (occasionFilter) items = items.filter(i => i.occasion?.includes(occasionFilter))
    if (sort === 'worn') items = [...items].sort((a, b) => b.wear_count - a.wear_count)
    if (sort === 'eco')  items = [...items].sort((a, b) => (b.eco_score ?? 0) - (a.eco_score ?? 0))
    if (sort === 'name') items = [...items].sort((a, b) => a.name.localeCompare(b.name))
    return items
  }, [closetItems, category, search, sort, colorFilter, seasonFilter, occasionFilter])

  const isFiltered = category !== 'all' || search.trim() !== '' || !!colorFilter || !!seasonFilter || !!occasionFilter
  const rowCount   = Math.ceil(filtered.length / columnCount)

  const rowVirtualizer = useVirtualizer({
    count:           rowCount,
    getScrollElement: () => scrollRef.current,
    estimateSize:    () => 280,
    overscan:        3,
  })

  const handleDelete = async (item: ClosetItem) => {
    if (!confirm(`Delete "${item.name}"?`)) return
    setDeleting(item.id)
    try {
      await closetApi.delete(item.id)
      removeClosetItem(item.id)
      if (selected?.id === item.id) setSelected(null)
    } catch {
      alert('Failed to delete item. Please try again.')
    } finally {
      setDeleting(null)
    }
  }

  const clearFilters = () => {
    setCategory('all'); setSearch(''); setColorFilter(''); setSeasonFilter(''); setOccasionFilter('')
  }

  if (closetLoading && closetItems.length === 0) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="text-center space-y-3">
          <Loader2 size={32} className="animate-spin text-brand-500 mx-auto" />
          <p className="text-slate-500 dark:text-slate-400 text-sm">Loading your wardrobe…</p>
        </div>
      </div>
    )
  }

  return (
    <div className="space-y-5">

      {/* ── Header ── */}
      <div className="flex items-start justify-between gap-4 flex-wrap">
        <div>
          <h2 className="font-display font-bold text-xl text-slate-800 dark:text-slate-100">My Closet</h2>
          <p className="text-sm text-slate-400 mt-0.5">
            {closetLoading
              ? 'Syncing…'
              : isFiltered
                ? `Showing ${filtered.length} of ${closetItems.length} items`
                : `${closetItems.length} items in your wardrobe`}
          </p>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={fetchClosetItems}
            disabled={closetLoading}
            className="btn-ghost p-2 min-h-[44px] min-w-[44px] rounded-xl"
            title="Refresh"
          >
            <RefreshCw size={15} className={closetLoading ? 'animate-spin text-brand-500' : ''} />
          </button>
          {/* Smart Upload CTA */}
          <a
            href="/smart-upload"
            className="flex items-center gap-2 px-4 py-2 rounded-xl text-sm font-semibold bg-gradient-to-r from-brand-500 to-violet-500 text-white shadow-md shadow-brand-500/25 hover:shadow-brand-500/40 hover:-translate-y-0.5 transition-all duration-200"
          >
            <Sparkles size={14} />
            AI Upload
          </a>
          <a
            href="/upload"
            className="flex items-center gap-2 px-3 py-2 rounded-xl text-sm font-semibold btn-secondary min-h-[44px]"
          >
            <Upload size={14} />
            <span className="hidden sm:inline">Add Item</span>
          </a>
        </div>
      </div>

      {/* ── Error banner ── */}
      {closetError && (
        <div className="card p-3 bg-red-50 dark:bg-red-900/20 border-red-200 dark:border-red-800 text-red-700 dark:text-red-300 text-sm flex items-center justify-between">
          <span>⚠️ {closetError}</span>
          <button onClick={fetchClosetItems} className="underline text-xs">Retry</button>
        </div>
      )}

      {/* ── Category tabs (horizontal scroll) ── */}
      <div className="relative">
        <div className="flex gap-2.5 overflow-x-auto pb-1 scrollbar-hide snap-x snap-mandatory">
          {CATEGORIES.map(cat => {
            const count = cat.value === 'all'
              ? closetItems.length
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
      </div>

      {/* ── Search + Filters bar ── */}
      <div className="backdrop-blur-sm bg-white/60 dark:bg-white/5 border border-white/80 dark:border-white/10 rounded-2xl p-4 space-y-3">
        <div className="flex gap-3 flex-wrap sm:flex-nowrap">
          <div className="relative flex-1 min-w-48">
            <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
            <input
              className="input pl-9 bg-white/70 dark:bg-slate-800/70"
              placeholder="Search by name, brand, color…"
              value={search}
              onChange={e => setSearch(e.target.value)}
            />
          </div>

          <div className="flex gap-2">
            <div className="relative">
              <SlidersHorizontal size={13} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
              <select
                className="input pl-8 pr-8 appearance-none text-sm min-h-[44px]"
                value={sort}
                onChange={e => setSort(e.target.value)}
              >
                {SORT_OPTIONS.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
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
          </div>
        </div>

        {/* ── Advanced filters (collapsible) ── */}
        {filtersOpen && (
          <div className="flex gap-3 flex-wrap pt-1 border-t border-slate-200 dark:border-white/10">
            <div className="flex flex-col gap-1">
              <label className="text-[10px] font-semibold text-slate-500 uppercase tracking-wide">Color</label>
              <input
                className="input text-sm py-1.5 px-3 w-36"
                placeholder="e.g. blue, red…"
                value={colorFilter}
                onChange={e => setColorFilter(e.target.value)}
              />
            </div>

            <div className="flex flex-col gap-1">
              <label className="text-[10px] font-semibold text-slate-500 uppercase tracking-wide">Season</label>
              <select
                className="input text-sm py-1.5 px-3 w-36 appearance-none"
                value={seasonFilter}
                onChange={e => setSeasonFilter(e.target.value)}
              >
                <option value="">All seasons</option>
                {SEASONS.map(s => <option key={s} value={s} className="capitalize">{s.charAt(0).toUpperCase() + s.slice(1)}</option>)}
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
                {OCCASIONS.map(o => <option key={o} value={o} className="capitalize">{o.charAt(0).toUpperCase() + o.slice(1)}</option>)}
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
        )}

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
      </div>

      {/* ── Empty state ── */}
      {closetItems.length === 0 && !closetLoading && (
        <div className="flex flex-col items-center justify-center py-20 gap-5">
          <div className="text-7xl">👗</div>
          <div className="text-center">
            <p className="font-bold text-slate-700 dark:text-slate-200 text-lg">Your wardrobe is empty</p>
            <p className="text-sm text-slate-400 mt-1">Start by adding your first clothing items</p>
          </div>
          <div className="flex gap-3">
            <a
              href="/smart-upload"
              className="flex items-center gap-2 px-5 py-2.5 rounded-xl text-sm font-semibold bg-gradient-to-r from-brand-500 to-violet-500 text-white shadow-md"
            >
              <Sparkles size={15} /> AI Bulk Upload
            </a>
            <a
              href="/upload"
              className="flex items-center gap-2 px-5 py-2.5 rounded-xl text-sm font-semibold btn-secondary"
            >
              <Upload size={15} /> Add Single Item
            </a>
          </div>
        </div>
      )}

      {/* ── No filter results ── */}
      {closetItems.length > 0 && filtered.length === 0 && !closetLoading && (
        <div className="flex flex-col items-center justify-center py-16 gap-4">
          <div className="text-5xl">🔍</div>
          <div className="text-center">
            <p className="font-semibold text-slate-600 dark:text-slate-400">No items match your filters</p>
            <p className="text-xs text-slate-400 mt-1">Try adjusting or clearing your filters</p>
          </div>
          <button onClick={clearFilters} className="btn-primary px-5 py-2 rounded-xl text-sm">Clear filters</button>
        </div>
      )}

      {/* ── Recently Added section (only when showing all unfiltered) ── */}
      {!isFiltered && closetItems.length > 0 && (
        <RecentlyAddedSection
          items={closetItems}
          onOpen={setSelected}
          onDelete={handleDelete}
          deleting={deleting}
        />
      )}

      {/* ── Main grid ── */}
      {filtered.length > 0 && (
        <section>
          {!isFiltered && (
            <div className="flex items-center justify-between mb-3">
              <div className="flex items-center gap-2">
                <TrendingUp size={15} className="text-brand-500" />
                <h3 className="font-semibold text-sm text-slate-700 dark:text-slate-200">
                  {category === 'all' ? 'All Items' : CATEGORIES.find(c => c.value === category)?.label ?? 'Items'}
                </h3>
              </div>
              <span className="text-[11px] text-slate-400">{filtered.length} items</span>
            </div>
          )}

          <div ref={scrollRef} className="h-[calc(100vh-260px)] overflow-y-auto overflow-x-hidden pr-1">
            <div className="relative w-full" style={{ height: `${rowVirtualizer.getTotalSize()}px` }}>
              {rowVirtualizer.getVirtualItems().map(virtualRow => {
                const start    = virtualRow.index * columnCount
                const rowItems = filtered.slice(start, start + columnCount)
                return (
                  <div
                    key={virtualRow.key}
                    className="absolute left-0 top-0 grid w-full gap-3"
                    style={{
                      gridTemplateColumns: `repeat(${columnCount}, minmax(0, 1fr))`,
                      transform: `translateY(${virtualRow.start}px)`,
                    }}
                  >
                    {rowItems.map(item => (
                      <ClosetItemCard
                        key={item.id}
                        item={item}
                        onOpen={setSelected}
                        onDelete={handleDelete}
                        deleting={deleting === item.id}
                      />
                    ))}
                  </div>
                )
              })}
            </div>
          </div>
        </section>
      )}

      {/* ── Floating Smart Upload banner (when closet has items) ── */}
      {closetItems.length > 0 && closetItems.length < 10 && (
        <div className="rounded-2xl bg-gradient-to-r from-brand-500/10 to-violet-500/10 border border-brand-200 dark:border-brand-800/50 p-4 flex items-center justify-between gap-4">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-brand-500 to-violet-500 flex items-center justify-center flex-shrink-0">
              <Sparkles size={18} className="text-white" />
            </div>
            <div>
              <p className="text-sm font-semibold text-slate-700 dark:text-slate-200">Grow your wardrobe faster</p>
              <p className="text-xs text-slate-400">Upload up to 20 photos — AI detects and categorises everything</p>
            </div>
          </div>
          <a
            href="/smart-upload"
            className="flex items-center gap-1.5 px-4 py-2 rounded-xl text-sm font-semibold bg-gradient-to-r from-brand-500 to-violet-500 text-white flex-shrink-0 hover:opacity-90 transition-opacity"
          >
            Try AI Upload <ChevronRight size={14} />
          </a>
        </div>
      )}

      <ItemDetailModal item={selected} open={!!selected} onClose={() => setSelected(null)} />
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
