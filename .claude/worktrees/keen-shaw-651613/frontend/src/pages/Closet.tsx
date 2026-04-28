import { useState, useMemo } from 'react'
import { Search, Filter, Grid3X3, List, SlidersHorizontal, Loader2, RefreshCw, Trash2 } from 'lucide-react'
import { useApp } from '@/store'
import { deleteItem } from '@/lib/api'
import ClosetItemCard from '@/components/closet/ClosetItemCard'
import ItemDetailModal from '@/components/closet/ItemDetailModal'
import Badge from '@/components/ui/Badge'
import type { ClosetItem, Category } from '@/types'
import { categoryIcon } from '@/lib/utils'

const CATEGORIES: { value: Category; label: string }[] = [
  { value: 'all', label: 'All' },
  { value: 'tops', label: 'Tops' },
  { value: 'bottoms', label: 'Bottoms' },
  { value: 'shoes', label: 'Shoes' },
  { value: 'outerwear', label: 'Outerwear' },
  { value: 'dresses', label: 'Dresses' },
  { value: 'accessories', label: 'Accessories' },
]

const SORT_OPTIONS = [
  { value: 'recent', label: 'Recently added' },
  { value: 'worn', label: 'Most worn' },
  { value: 'eco', label: 'Eco score' },
  { value: 'name', label: 'Name A–Z' },
]

export default function Closet() {
  const { closetItems, closetLoading, closetError, fetchClosetItems, removeClosetItem } = useApp()
  const [category, setCategory] = useState<Category>('all')
  const [search, setSearch] = useState('')
  const [sort, setSort] = useState('recent')
  const [selected, setSelected] = useState<ClosetItem | null>(null)
  const [view, setView] = useState<'grid' | 'list'>('grid')
  const [deleting, setDeleting] = useState<string | null>(null)

  const filtered = useMemo(() => {
    let items = closetItems
    if (category !== 'all') items = items.filter(i => i.category === category)
    if (search) items = items.filter(i =>
      i.name.toLowerCase().includes(search.toLowerCase()) ||
      (i.brand || '').toLowerCase().includes(search.toLowerCase()) ||
      (i.color || '').toLowerCase().includes(search.toLowerCase())
    )
    if (sort === 'worn') items = [...items].sort((a, b) => b.wear_count - a.wear_count)
    if (sort === 'eco') items = [...items].sort((a, b) => (b.eco_score ?? 0) - (a.eco_score ?? 0))
    if (sort === 'name') items = [...items].sort((a, b) => a.name.localeCompare(b.name))
    return items
  }, [closetItems, category, search, sort])

  const handleDelete = async (item: ClosetItem) => {
    if (!confirm(`Delete "${item.name}"?`)) return
    setDeleting(item.id)
    try {
      await deleteItem(item.id)
      removeClosetItem(item.id)
      if (selected?.id === item.id) setSelected(null)
    } catch (err) {
      console.error('Delete failed:', err)
      alert('Failed to delete item. Please try again.')
    } finally {
      setDeleting(null)
    }
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
    <div className="space-y-5 animate-slide-up">
      {/* Header */}
      <div className="flex items-start justify-between gap-4 flex-wrap">
        <div>
          <h2 className="font-display font-bold text-xl text-slate-800 dark:text-slate-100">My Closet</h2>
          <p className="text-sm text-slate-400 mt-0.5">
            {closetLoading
              ? 'Syncing…'
              : `${closetItems.length} items · ${filtered.length} showing`}
          </p>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={fetchClosetItems}
            disabled={closetLoading}
            className="btn-ghost p-2 rounded-xl"
            title="Refresh"
          >
            <RefreshCw size={15} className={closetLoading ? 'animate-spin text-brand-500' : ''} />
          </button>
          <button
            onClick={() => setView('grid')}
            className={`p-2 rounded-xl transition-colors ${view === 'grid' ? 'bg-brand-600 text-white' : 'btn-ghost'}`}
          ><Grid3X3 size={16} /></button>
          <button
            onClick={() => setView('list')}
            className={`p-2 rounded-xl transition-colors ${view === 'list' ? 'bg-brand-600 text-white' : 'btn-ghost'}`}
          ><List size={16} /></button>
        </div>
      </div>

      {/* Error banner */}
      {closetError && (
        <div className="card p-3 bg-red-50 dark:bg-red-900/20 border-red-200 dark:border-red-800 text-red-700 dark:text-red-300 text-sm flex items-center justify-between">
          <span>⚠️ {closetError}</span>
          <button onClick={fetchClosetItems} className="underline text-xs">Retry</button>
        </div>
      )}

      {/* Filters bar */}
      <div className="card p-4 space-y-3">
        <div className="flex gap-3 flex-wrap sm:flex-nowrap">
          <div className="relative flex-1 min-w-48">
            <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
            <input
              className="input pl-9"
              placeholder="Search by name, brand, color…"
              value={search}
              onChange={e => setSearch(e.target.value)}
            />
          </div>
          <div className="relative">
            <SlidersHorizontal size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
            <select
              className="input pl-9 pr-8 appearance-none min-w-40"
              value={sort}
              onChange={e => setSort(e.target.value)}
            >
              {SORT_OPTIONS.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
            </select>
          </div>
        </div>

        {/* Category pills */}
        <div className="flex gap-2 flex-wrap">
          {CATEGORIES.map(({ value, label }) => {
            const count = value === 'all'
              ? closetItems.length
              : closetItems.filter(i => i.category === value).length
            return (
              <button
                key={value}
                onClick={() => setCategory(value)}
                className={`flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs font-semibold transition-all ${
                  category === value
                    ? 'bg-brand-600 text-white shadow-sm'
                    : 'bg-cream-100 dark:bg-slate-800 text-slate-600 dark:text-slate-300 hover:bg-cream-200 dark:hover:bg-slate-700'
                }`}
              >
                <span>{categoryIcon(value)}</span>
                {label}
                <span className={`ml-0.5 text-[10px] ${category === value ? 'text-white/70' : 'text-slate-400'}`}>{count}</span>
              </button>
            )
          })}
        </div>
      </div>

      {/* Empty state */}
      {filtered.length === 0 && !closetLoading ? (
        <div className="card p-12 text-center">
          {closetItems.length === 0 ? (
            <>
              <div className="text-5xl mb-4">👗</div>
              <p className="font-semibold text-slate-600 dark:text-slate-400">Your wardrobe is empty</p>
              <p className="text-sm text-slate-400 mt-1 mb-4">Start by uploading your first clothing item</p>
              <a href="/upload" className="btn-primary inline-flex items-center gap-2 px-4 py-2 rounded-xl text-sm">
                + Add first item
              </a>
            </>
          ) : (
            <>
              <div className="text-4xl mb-3">🔍</div>
              <p className="font-semibold text-slate-600 dark:text-slate-400">No items found</p>
              <p className="text-sm text-slate-400 mt-1">Try adjusting your filters</p>
            </>
          )}
        </div>
      ) : (
        <div className={
          view === 'grid'
            ? 'grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 xl:grid-cols-5 gap-4'
            : 'space-y-2'
        }>
          {filtered.map(item =>
            view === 'grid' ? (
              <div key={item.id} className="relative group">
                <ClosetItemCard item={item} onClick={() => setSelected(item)} />
                <button
                  onClick={() => handleDelete(item)}
                  disabled={deleting === item.id}
                  className="absolute top-2 left-2 p-1.5 rounded-lg bg-red-500/80 text-white opacity-0 group-hover:opacity-100 transition-opacity hover:bg-red-600 z-10"
                  title="Delete item"
                >
                  {deleting === item.id
                    ? <Loader2 size={11} className="animate-spin" />
                    : <Trash2 size={11} />}
                </button>
              </div>
            ) : (
              <div
                key={item.id}
                className="card-hover flex items-center gap-4 p-3 group"
              >
                <div
                  className="w-12 h-12 rounded-xl overflow-hidden bg-cream-100 dark:bg-slate-700 flex-shrink-0 cursor-pointer"
                  onClick={() => setSelected(item)}
                >
                  {item.image_url
                    ? <img src={item.image_url} alt={item.name} className="w-full h-full object-cover" />
                    : <div className="w-full h-full flex items-center justify-center text-xl">👕</div>
                  }
                </div>
                <div className="flex-1 min-w-0 cursor-pointer" onClick={() => setSelected(item)}>
                  <p className="font-semibold text-sm truncate">{item.name}</p>
                  <p className="text-xs text-slate-400">{item.brand || item.category} · {item.color}</p>
                </div>
                <div className="flex items-center gap-2 flex-shrink-0">
                  <Badge variant="gray">{item.category}</Badge>
                  <span className="text-xs text-slate-400">{item.wear_count}× worn</span>
                  <button
                    onClick={() => handleDelete(item)}
                    disabled={deleting === item.id}
                    className="p-1.5 rounded-lg text-red-400 opacity-0 group-hover:opacity-100 hover:bg-red-50 dark:hover:bg-red-900/20 transition-all"
                  >
                    {deleting === item.id
                      ? <Loader2 size={13} className="animate-spin" />
                      : <Trash2 size={13} />}
                  </button>
                </div>
              </div>
            )
          )}
        </div>
      )}

      <ItemDetailModal item={selected} open={!!selected} onClose={() => setSelected(null)} />
    </div>
  )
}
