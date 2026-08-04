import { useMemo } from 'react'
import { Check, Plus, RefreshCw, Sparkles, X } from 'lucide-react'
import Badge from '@/components/ui/Badge'
import Button from '@/components/ui/Button'
import { cn } from '@/lib/utils'
import type { ClosetSuggestion, PackingChecklistItem } from '@/types'
import { CARD_SHADOW, CATEGORY_EMOJI, SOURCE_BADGE } from './constants'

// ── Packing checklist panel ───────────────────────────────────────────────

const CHECKLIST_CATEGORY_ORDER = [
  'tops', 'bottoms', 'dresses', 'outerwear', 'shoes', 'accessories',
  'innerwear', 'sleepwear', 'toiletries', 'travel_essentials', 'essentials', 'general',
]

export function PackingChecklistPanel({
  items, packedState, onToggle, editable = false, busy = false,
  suggestions = [], onAddItems, onAddSuggestion, onRemoveItem,
}: {
  items: PackingChecklistItem[]
  packedState: Record<string, boolean>
  onToggle: (key: string, val: boolean) => void
  /** Enables the add/remove affordances and the suggestions strip. */
  editable?: boolean
  busy?: boolean
  /** Items the user already owns that would fill a gap in the plan. */
  suggestions?: ClosetSuggestion[]
  onAddItems?: () => void
  onAddSuggestion?: (closetItemId: string) => void
  onRemoveItem?: (key: string) => void
}) {
  // Group by category
  const grouped = useMemo(() => {
    const map: Record<string, PackingChecklistItem[]> = {}
    for (const item of items) {
      const cat = item.category?.toLowerCase() || 'general'
      map[cat] = map[cat] ?? []
      map[cat].push(item)
    }
    return map
  }, [items])

  const orderedCategories = [
    ...CHECKLIST_CATEGORY_ORDER.filter(c => grouped[c]),
    ...Object.keys(grouped).filter(c => !CHECKLIST_CATEGORY_ORDER.includes(c)),
  ]

  const total = items.length
  const packed = items.filter(i => {
    const key = i.closet_item_id || i.item_name.toLowerCase()
    return packedState[key] ?? i.is_packed
  }).length
  const pct = total > 0 ? Math.round((packed / total) * 100) : 0

  if (items.length === 0) return (
    <div className="text-center py-10 text-slate-400 dark:text-white/30 text-sm">
      Save the planner to generate your packing checklist.
    </div>
  )

  return (
    <div className="space-y-4">
      {/* Sticky progress card */}
      <div
        className="sticky top-2 z-10 rounded-2xl bg-white dark:bg-white/[0.05] border border-slate-200 dark:border-white/10 p-4"
        style={{ boxShadow: CARD_SHADOW }}
      >
        <div className="flex items-center justify-between mb-2">
          <span className="text-sm font-semibold text-slate-800 dark:text-white">
            {packed === total ? 'All packed 🎉' : 'Packing progress'}
          </span>
          <span className="text-xs font-bold text-emerald-600 dark:text-emerald-400">
            {packed}/{total} · {pct}%
          </span>
        </div>
        <div className="h-2 rounded-full bg-slate-100 dark:bg-white/10 overflow-hidden">
          <div
            className="h-full rounded-full bg-gradient-to-r from-emerald-500 to-teal-500 transition-all duration-500"
            style={{ width: `${pct}%` }}
          />
        </div>
        {editable && (
          <Button
            variant="secondary"
            size="sm"
            className="w-full mt-3"
            disabled={busy}
            onClick={onAddItems}
          >
            <Plus size={13} className="mr-1.5" />
            Add from your closet
          </Button>
        )}
      </div>

      {/* Closet gap suggestions — items the user already owns */}
      {editable && suggestions.length > 0 && (
        <div className="rounded-2xl border border-brand-200/70 dark:border-brand-700/30 bg-brand-50/50 dark:bg-brand-900/10 p-4">
          <div className="flex items-center gap-1.5 mb-2.5">
            <Sparkles size={12} className="text-brand-500" />
            <h4 className="text-xs font-bold uppercase tracking-widest text-brand-700 dark:text-brand-300">
              Also in your closet
            </h4>
          </div>
          <p className="text-xs text-slate-500 dark:text-white/40 mb-3">
            Your bag has room for these and they suit the trip.
          </p>
          <div className="space-y-1.5">
            {suggestions.map(s => (
              <div
                key={s.closet_item_id}
                className="flex items-center gap-2.5 p-2 rounded-xl bg-white dark:bg-white/[0.04] border border-slate-200 dark:border-white/[0.07]"
              >
                {s.image_url ? (
                  <img src={s.image_url} alt={s.item_name ?? ''} className="w-8 h-9 object-cover rounded-lg flex-shrink-0" />
                ) : (
                  <div className="w-8 h-9 rounded-lg bg-cream-100 dark:bg-slate-800 flex items-center justify-center text-base flex-shrink-0">
                    {CATEGORY_EMOJI[s.category] ?? '📦'}
                  </div>
                )}
                <div className="flex-1 min-w-0">
                  <p className="text-sm font-medium text-slate-800 dark:text-white truncate">{s.item_name}</p>
                  <p className="text-[10px] text-slate-400 dark:text-white/30 line-clamp-1">{s.reason}</p>
                </div>
                <button
                  type="button"
                  disabled={busy}
                  onClick={() => onAddSuggestion?.(s.closet_item_id)}
                  className="flex-shrink-0 p-1.5 rounded-lg text-brand-600 dark:text-brand-400 hover:bg-brand-100 dark:hover:bg-brand-900/30 transition-colors disabled:opacity-50"
                  aria-label={`Pack ${s.item_name}`}
                  title={`Pack ${s.item_name}`}
                >
                  <Plus size={15} />
                </button>
              </div>
            ))}
          </div>
        </div>
      )}

      {orderedCategories.map(cat => {
        const catPacked = grouped[cat].filter(i => {
          const key = i.closet_item_id || i.item_name.toLowerCase()
          return packedState[key] ?? i.is_packed
        }).length

        return (
          <div key={cat}>
            <div className="flex items-center gap-2 mb-2 px-0.5">
              <span className="text-base">{CATEGORY_EMOJI[cat] ?? '📦'}</span>
              <h4 className="text-xs font-bold uppercase tracking-widest text-slate-500 dark:text-white/40 capitalize">
                {cat.replace('_', ' ')}
              </h4>
              <span className="text-[10px] text-slate-400 dark:text-white/30 ml-auto">
                {catPacked}/{grouped[cat].length}
              </span>
            </div>
            <div className="space-y-1.5">
              {grouped[cat].map((item, i) => {
                const key = item.closet_item_id || item.item_name.toLowerCase()
                const isPacked = packedState[key] ?? item.is_packed
                const badgeCfg = SOURCE_BADGE[item.source] ?? SOURCE_BADGE.optional

                return (
                  <label
                    key={i}
                    className={cn(
                      'flex items-center gap-3 p-2.5 rounded-xl border cursor-pointer transition-all',
                      isPacked
                        ? 'bg-emerald-50/80 dark:bg-emerald-900/10 border-emerald-200/60 dark:border-emerald-700/20'
                        : 'bg-white dark:bg-white/[0.03] border-slate-200 dark:border-white/[0.07] hover:border-brand-300 dark:hover:border-brand-700/40',
                    )}
                  >
                    {/* Custom checkbox */}
                    <div className="relative flex-shrink-0">
                      <input
                        type="checkbox"
                        checked={isPacked}
                        onChange={e => onToggle(key, e.target.checked)}
                        className="peer sr-only"
                      />
                      <div className={cn(
                        'w-5 h-5 rounded-md border-2 flex items-center justify-center transition-all',
                        isPacked
                          ? 'bg-emerald-500 border-emerald-500'
                          : 'border-slate-300 dark:border-white/20 bg-white dark:bg-transparent',
                      )}>
                        {isPacked && <Check size={13} className="text-white" strokeWidth={3} />}
                      </div>
                    </div>

                    {/* Thumbnail */}
                    {item.image_url ? (
                      <img
                        src={item.image_url}
                        alt={item.item_name}
                        className={cn(
                          'w-9 h-10 object-cover rounded-lg flex-shrink-0 bg-cream-100 dark:bg-slate-800 transition-opacity',
                          isPacked && 'opacity-60',
                        )}
                        onError={e => { (e.target as HTMLImageElement).style.display = 'none' }}
                      />
                    ) : (
                      <div className={cn(
                        'w-9 h-10 rounded-lg bg-cream-100 dark:bg-slate-800 flex items-center justify-center text-lg flex-shrink-0',
                        isPacked && 'opacity-60',
                      )}>
                        {CATEGORY_EMOJI[cat] ?? '📦'}
                      </div>
                    )}

                    <div className="flex-1 min-w-0">
                      <p className={cn(
                        'text-sm font-medium truncate',
                        isPacked ? 'line-through text-slate-400 dark:text-white/30' : 'text-slate-800 dark:text-white',
                      )}>
                        {item.item_name}
                        {item.quantity > 1 && (
                          <span className="ml-1 text-xs text-slate-400">×{item.quantity}</span>
                        )}
                      </p>
                      <div className="flex flex-wrap gap-1 mt-0.5">
                        {item.planned_days.length > 0 && (
                          <span className="text-[10px] text-slate-400 dark:text-white/30">{item.planned_days.slice(0, 3).join(', ')}</span>
                        )}
                        {item.rewear_count > 1 && (
                          <span className="text-[10px] text-teal-500 flex items-center gap-0.5">
                            <RefreshCw size={8} />×{item.rewear_count}
                          </span>
                        )}
                        {item.activities.length > 0 && (
                          <span className="text-[10px] text-slate-400 dark:text-white/30 truncate max-w-[100px]">
                            {item.activities.slice(0, 2).join(', ')}
                          </span>
                        )}
                      </div>
                    </div>

                    <Badge variant={badgeCfg.variant} className="flex-shrink-0 text-[9px] hidden sm:flex">
                      {badgeCfg.label}
                    </Badge>

                    {editable && (
                      <button
                        type="button"
                        disabled={busy}
                        // Inside a <label>: stop the click from toggling the checkbox.
                        onClick={e => { e.preventDefault(); e.stopPropagation(); onRemoveItem?.(key) }}
                        className="flex-shrink-0 p-1 rounded-lg text-slate-300 dark:text-white/20 hover:text-rose-500 hover:bg-rose-50 dark:hover:bg-rose-900/20 transition-colors disabled:opacity-50"
                        aria-label={`Remove ${item.item_name} from the list`}
                        title="Remove from list"
                      >
                        <X size={13} />
                      </button>
                    )}
                  </label>
                )
              })}
            </div>
          </div>
        )
      })}
    </div>
  )
}
