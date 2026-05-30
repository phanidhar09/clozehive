import React, { useMemo } from 'react'
import {
  Search, SlidersHorizontal, Loader2, RefreshCw, Trash2, X,
  Sparkles, Upload, ChevronRight, Clock, TrendingUp, Plus, Wand2, Shirt,
} from 'lucide-react'
import { Link } from 'react-router-dom'
import { useApp } from '@/store'
import { usePageState } from '@/hooks/usePageState'
import { useWindowScrollRestoration } from '@/hooks/useScrollRestoration'
import { closetApi } from '@/lib/api'
import ItemDetailModal from '@/components/closet/ItemDetailModal'
import RevealCard from '@/components/ui/RevealCard'
import PageHeader from '@/components/ui/PageHeader'
import { PageLoadingState } from '@/components/system/PageLoadingState'
import { InlineError } from '@/components/system/InlineError'
import { RetryButton } from '@/components/system/RetryButton'
import type { ClosetItem, Category } from '@/types'
import { cn } from '@/lib/utils'

// ── Constants ──────────────────────────────────────────────────────────────────

import {
  CANONICAL_TAB_CATEGORIES,
  CLOSET_CATEGORY_TABS,
  CLOSET_OCCASIONS,
  CLOSET_SEASONS,
  CLOSET_SORT_OPTIONS,
} from '@/features/closet/constants'
// ── Sub-components ─────────────────────────────────────────────────────────────

function CategoryTab({
  cat, active, count, onClick,
}: { cat: typeof CLOSET_CATEGORY_TABS[0]; active: boolean; count: number; onClick: () => void }) {
  return (
    <button
      onClick={onClick}
      className={cn(
        'flex flex-col items-center gap-1.5 px-4 py-2.5 rounded-2xl text-xs font-semibold transition-all duration-200 flex-shrink-0',
        active
          ? 'bg-gradient-to-br from-brand-500 to-brand-600 text-white shadow-lg shadow-brand-500/30 scale-105'
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
  const { closetItems, setClosetItems, closetLoading, closetError, fetchClosetItems, removeClosetItem } = useApp()

  // Persisted filter state — survives navigation, cleared on browser refresh
  const [category, setCategory]       = usePageState<Category>('closet-category', 'all')
  const [search,   setSearch]         = usePageState('closet-search', '')
  const [sort,     setSort]           = usePageState('closet-sort', 'recent')
  const [filtersOpen, setFiltersOpen] = usePageState('closet-filters-open', false)
  const [colorFilter,    setColorFilter]    = usePageState('closet-color', '')
  const [seasonFilter,   setSeasonFilter]   = usePageState('closet-season', '')
  const [occasionFilter, setOccasionFilter] = usePageState('closet-occasion', '')

  // Transient UI state (not persisted)
  const [selected, setSelected] = React.useState<ClosetItem | null>(null)
  const [deleting, setDeleting] = React.useState<string | null>(null)

  // Restore scroll position across navigations
  useWindowScrollRestoration('closet-scroll')

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
      items = items.filter(i => {
        const s = (i.season || '').toLowerCase()
        if (!s) return false
        if (s === want) return true
        return s.split(',').some(part => part.trim() === want)
      })
    }
    if (occasionFilter) items = items.filter(i => i.occasion?.includes(occasionFilter))
    if (sort === 'worn') items = [...items].sort((a, b) => b.wear_count - a.wear_count)
    if (sort === 'eco')  items = [...items].sort((a, b) => (b.eco_score ?? 0) - (a.eco_score ?? 0))
    if (sort === 'name') items = [...items].sort((a, b) => a.name.localeCompare(b.name))
    return items
  }, [closetItems, category, search, sort, colorFilter, seasonFilter, occasionFilter])

  const isFiltered = category !== 'all' || search.trim() !== '' || !!colorFilter || !!seasonFilter || !!occasionFilter

  const handleItemSaved = (updated: ClosetItem) => {
    setClosetItems(closetItems.map(i => i.id === updated.id ? updated : i))
    setSelected(updated)
  }

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
    setCategory('all'); setSearch(''); setSort('recent')
    setColorFilter(''); setSeasonFilter(''); setOccasionFilter('')
  }

  if (closetLoading && closetItems.length === 0) {
    return (
      <PageLoadingState
        title="Loading your wardrobe…"
        description="Fetching your items from CLOZEHIVE."
      />
    )
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
              ? `Showing ${filtered.length} of ${closetItems.length} items`
              : `${closetItems.length} items in your wardrobe`
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

      {/* ── Error banner ── */}
      {closetError && (
        <InlineError message={closetError}>
          <RetryButton onClick={() => { void fetchClosetItems() }} className="mt-2">
            Try again
          </RetryButton>
        </InlineError>
      )}

      {/* ── Closet actions strip ── */}
      <div className="grid grid-cols-2 gap-2.5">
        <Link
          to="/upload"
          className="flex items-center gap-3 px-4 py-3 rounded-2xl
                     bg-gradient-to-br from-brand-500 to-brand-700
                     text-white shadow-md shadow-brand-500/20
                     hover:shadow-brand-500/35 hover:-translate-y-0.5
                     transition-all duration-200"
        >
          <div className="w-8 h-8 rounded-xl bg-white/20 flex items-center justify-center flex-shrink-0">
            <Plus size={16} />
          </div>
          <div className="min-w-0">
            <p className="text-sm font-bold leading-tight">Add Items</p>
            <p className="text-[11px] text-white/70 leading-tight">Upload new clothing</p>
          </div>
        </Link>
        <Link
          to="/outfit-builder"
          className="flex items-center gap-3 px-4 py-3 rounded-2xl
                     bg-gradient-to-br from-pink-500 to-rose-600
                     text-white shadow-md shadow-pink-500/20
                     hover:shadow-pink-500/35 hover:-translate-y-0.5
                     transition-all duration-200"
        >
          <div className="w-8 h-8 rounded-xl bg-white/20 flex items-center justify-center flex-shrink-0">
            <Wand2 size={16} />
          </div>
          <div className="min-w-0">
            <p className="text-sm font-bold leading-tight">Build Outfit</p>
            <p className="text-[11px] text-white/70 leading-tight">Mix & match your closet</p>
          </div>
        </Link>
      </div>

      {/* ── Category tabs (horizontal scroll) ── */}
      <div className="relative">
        <div className="flex gap-2.5 overflow-x-auto pb-1 scrollbar-hide snap-x snap-mandatory">
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
        <div className="rounded-3xl border border-cream-200 dark:border-white/[0.07] bg-white dark:bg-white/[0.03] overflow-hidden">
          {/* Top hero */}
          <div className="flex flex-col items-center justify-center py-10 px-6 text-center gap-4 border-b border-cream-100 dark:border-white/[0.05]">
            <div className="text-6xl">👗</div>
            <div>
              <p className="font-display font-bold text-slate-800 dark:text-white text-xl">
                Your wardrobe is empty
              </p>
              <p className="text-sm text-slate-400 dark:text-slate-500 mt-1 max-w-xs mx-auto">
                Drop a photo and FANI will detect your items, remove backgrounds, and auto-tag everything for you.
              </p>
            </div>
            <Link
              to="/upload"
              className="flex items-center gap-2 px-6 py-2.5 rounded-xl text-sm font-semibold bg-gradient-to-r from-brand-500 to-brand-600 text-white shadow-md shadow-brand-500/20 hover:opacity-90 transition-opacity"
            >
              <Sparkles size={15} /> Add items with AI
            </Link>
          </div>

          {/* Feature callouts */}
          <div className="grid grid-cols-1 sm:grid-cols-3 divide-y sm:divide-y-0 sm:divide-x divide-cream-100 dark:divide-white/[0.05]">
            {[
              {
                icon: '📸',
                title: 'Bulk upload',
                desc: 'Drop up to 20 photos at once — AI analyses them all in one go.',
              },
              {
                icon: '🏷️',
                title: 'Auto-tagging',
                desc: 'Category, colour, pattern, season, and occasion — all detected automatically.',
              },
              {
                icon: '🔍',
                title: 'Duplicate detection',
                desc: 'FANI warns you before saving something you already own.',
              },
            ].map(({ icon, title, desc }) => (
              <div key={title} className="flex flex-col items-center text-center gap-2 px-5 py-5">
                <span className="text-2xl">{icon}</span>
                <p className="text-sm font-semibold text-slate-700 dark:text-slate-200">{title}</p>
                <p className="text-[11px] text-slate-400 dark:text-slate-500 leading-snug">{desc}</p>
              </div>
            ))}
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
                  {category === 'all' ? 'All Items' : CLOSET_CATEGORY_TABS.find(c => c.value === category)?.label ?? 'Items'}
                </h3>
              </div>
              <span className="text-[11px] text-slate-400">{filtered.length} items</span>
            </div>
          )}

          <div className="grid grid-cols-3 sm:grid-cols-4 md:grid-cols-5 lg:grid-cols-6 gap-3">
            {filtered.map(item => (
              <ClosetItemCard
                key={item.id}
                item={item}
                onOpen={setSelected}
                onDelete={handleDelete}
                deleting={deleting === item.id}
              />
            ))}
          </div>
        </section>
      )}

      {/* ── Floating Smart Upload banner (when closet has items) ── */}
      {closetItems.length > 0 && closetItems.length < 10 && (
        <div className="rounded-2xl bg-gradient-to-r from-brand-500/10 to-brand-600/10 border border-brand-200 dark:border-brand-800/50 p-4 flex items-center justify-between gap-4">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-brand-500 to-brand-600 flex items-center justify-center flex-shrink-0">
              <Sparkles size={18} className="text-white" />
            </div>
            <div>
              <p className="text-sm font-semibold text-slate-700 dark:text-slate-200">Grow your wardrobe faster</p>
              <p className="text-xs text-slate-400">Upload up to 20 photos — AI detects and categorises everything</p>
            </div>
          </div>
          <Link
            to="/upload"
            className="flex items-center gap-1.5 px-4 py-2 rounded-xl text-sm font-semibold bg-gradient-to-r from-brand-500 to-brand-600 text-white flex-shrink-0 hover:opacity-90 transition-opacity"
          >
            Add Items <ChevronRight size={14} />
          </Link>
        </div>
      )}

      <ItemDetailModal
        item={selected}
        open={!!selected}
        onClose={() => setSelected(null)}
        onDelete={handleDelete}
        onSaved={handleItemSaved}
      />
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
