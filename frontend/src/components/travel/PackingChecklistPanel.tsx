import { useMemo } from 'react'
import { Check, RefreshCw } from 'lucide-react'
import Badge from '@/components/ui/Badge'
import { cn } from '@/lib/utils'
import type { PackingChecklistItem } from '@/types'
import { CARD_SHADOW, CATEGORY_EMOJI, SOURCE_BADGE } from './constants'

// ── Packing checklist panel ───────────────────────────────────────────────

const CHECKLIST_CATEGORY_ORDER = [
  'tops', 'bottoms', 'dresses', 'outerwear', 'shoes', 'accessories',
  'innerwear', 'sleepwear', 'toiletries', 'travel_essentials', 'essentials', 'general',
]

export function PackingChecklistPanel({
  items, packedState, onToggle,
}: {
  items: PackingChecklistItem[]
  packedState: Record<string, boolean>
  onToggle: (key: string, val: boolean) => void
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
      </div>

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
