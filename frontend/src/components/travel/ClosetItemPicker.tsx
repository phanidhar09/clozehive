/**
 * Closet item picker — a modal sheet for choosing wardrobe items when editing
 * a packing plan (swap an outfit item, add extras to the checklist).
 *
 * Deliberately dumb: it only picks ids. Every plan mutation is validated and
 * re-derived server-side, so this component never has to reason about whether a
 * choice is valid for the trip.
 */

import { useEffect, useMemo, useState } from 'react'
import { Search, X } from 'lucide-react'
import Button from '@/components/ui/Button'
import Input from '@/components/ui/Input'
import { cn } from '@/lib/utils'
import type { ClosetItem } from '@/types'
import { CATEGORY_EMOJI } from './constants'

const CATEGORY_FILTERS = ['all', 'tops', 'bottoms', 'dresses', 'outerwear', 'shoes', 'accessories'] as const

export function ClosetItemPicker({
  open,
  title,
  closetItems,
  excludeIds = [],
  initialCategory,
  multiple = false,
  confirmLabel = 'Add',
  busy = false,
  onConfirm,
  onClose,
}: {
  open: boolean
  title: string
  closetItems: ClosetItem[]
  /** Items already in the outfit/checklist — shown as unavailable. */
  excludeIds?: string[]
  /** Pre-select a category filter (e.g. the category of the item being swapped). */
  initialCategory?: string
  multiple?: boolean
  confirmLabel?: string
  busy?: boolean
  onConfirm: (itemIds: string[]) => void
  onClose: () => void
}) {
  const [query, setQuery] = useState('')
  const [category, setCategory] = useState<string>('all')
  const [selected, setSelected] = useState<string[]>([])

  // Reset per-open so a previous pick never leaks into the next edit.
  useEffect(() => {
    if (open) {
      setQuery('')
      setSelected([])
      setCategory(initialCategory && CATEGORY_FILTERS.includes(initialCategory as never) ? initialCategory : 'all')
    }
  }, [open, initialCategory])

  const excluded = useMemo(() => new Set(excludeIds), [excludeIds])

  const visible = useMemo(() => {
    const q = query.trim().toLowerCase()
    return closetItems.filter(item => {
      if (category !== 'all' && (item.category ?? '').toLowerCase() !== category) return false
      if (!q) return true
      return (
        item.name.toLowerCase().includes(q)
        || (item.color ?? '').toLowerCase().includes(q)
        || (item.brand ?? '').toLowerCase().includes(q)
      )
    })
  }, [closetItems, category, query])

  if (!open) return null

  const toggle = (id: string) => {
    if (excluded.has(id)) return
    setSelected(prev => (multiple ? (prev.includes(id) ? prev.filter(x => x !== id) : [...prev, id]) : [id]))
  }

  return (
    <div className="fixed inset-0 z-50 flex items-end sm:items-center justify-center">
      <button
        type="button"
        aria-label="Close picker"
        className="absolute inset-0 bg-slate-900/40 backdrop-blur-sm"
        onClick={onClose}
      />
      <div className="relative w-full sm:max-w-lg max-h-[85vh] flex flex-col rounded-t-3xl sm:rounded-3xl bg-white dark:bg-slate-900 border border-slate-200 dark:border-white/10 shadow-2xl">
        {/* Header */}
        <div className="flex items-center justify-between gap-3 px-5 pt-5 pb-3">
          <h3 className="text-base font-semibold text-slate-800 dark:text-white">{title}</h3>
          <button
            type="button"
            onClick={onClose}
            className="p-1.5 rounded-lg text-slate-400 hover:bg-slate-100 dark:hover:bg-white/10"
            aria-label="Close"
          >
            <X size={16} />
          </button>
        </div>

        {/* Search + category filters */}
        <div className="px-5 space-y-2.5">
          <div className="relative">
            <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400 pointer-events-none" />
            <Input
              value={query}
              onChange={e => setQuery(e.target.value)}
              placeholder="Search your closet…"
              className="pl-9"
            />
          </div>
          <div className="flex gap-1.5 overflow-x-auto pb-1 -mx-1 px-1">
            {CATEGORY_FILTERS.map(c => (
              <button
                key={c}
                type="button"
                onClick={() => setCategory(c)}
                className={cn(
                  'flex-none px-2.5 py-1 rounded-full text-xs font-medium capitalize transition-colors',
                  category === c
                    ? 'bg-brand-600 text-white'
                    : 'bg-slate-100 dark:bg-white/[0.06] text-slate-600 dark:text-white/60 hover:bg-slate-200 dark:hover:bg-white/10',
                )}
              >
                {c}
              </button>
            ))}
          </div>
        </div>

        {/* Item grid */}
        <div className="flex-1 overflow-y-auto px-5 py-3">
          {visible.length === 0 ? (
            <p className="text-center text-sm text-slate-400 dark:text-white/30 py-10">
              No matching items in your closet.
            </p>
          ) : (
            <div className="grid grid-cols-3 sm:grid-cols-4 gap-2.5">
              {visible.map(item => {
                const isExcluded = excluded.has(item.id)
                const isSelected = selected.includes(item.id)
                return (
                  <button
                    key={item.id}
                    type="button"
                    disabled={isExcluded}
                    onClick={() => toggle(item.id)}
                    className={cn(
                      'group text-left rounded-xl border p-1.5 transition-all',
                      isExcluded && 'opacity-40 cursor-not-allowed',
                      isSelected
                        ? 'border-brand-500 ring-2 ring-brand-500/30 bg-brand-50/60 dark:bg-brand-900/20'
                        : 'border-slate-200 dark:border-white/10 hover:border-brand-300 dark:hover:border-brand-700/40',
                    )}
                  >
                    <div className="aspect-square rounded-lg bg-cream-100 dark:bg-white/[0.06] overflow-hidden flex items-center justify-center mb-1">
                      {item.image_url ? (
                        <img src={item.image_url} alt={item.name} className="w-full h-full object-cover" />
                      ) : (
                        <span className="text-xl">{CATEGORY_EMOJI[(item.category ?? '').toLowerCase()] ?? '👔'}</span>
                      )}
                    </div>
                    <p className="text-[11px] font-medium leading-tight line-clamp-2 text-slate-700 dark:text-white/80">
                      {item.name}
                    </p>
                    {isExcluded && (
                      <p className="text-[9px] text-slate-400 dark:text-white/30 mt-0.5">Already packed</p>
                    )}
                  </button>
                )
              })}
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="flex items-center justify-between gap-3 px-5 py-4 border-t border-slate-200 dark:border-white/10">
          <span className="text-xs text-slate-400 dark:text-white/30">
            {selected.length > 0 ? `${selected.length} selected` : 'Pick an item'}
          </span>
          <div className="flex gap-2">
            <Button variant="ghost" size="sm" onClick={onClose} disabled={busy}>Cancel</Button>
            <Button
              size="sm"
              disabled={selected.length === 0 || busy}
              onClick={() => onConfirm(selected)}
            >
              {busy ? 'Saving…' : confirmLabel}
            </Button>
          </div>
        </div>
      </div>
    </div>
  )
}
