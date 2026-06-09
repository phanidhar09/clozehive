import { ShoppingCart } from 'lucide-react'
import Badge from '@/components/ui/Badge'
import GlassCard from '@/components/ui/GlassCard'
import { cn } from '@/lib/utils'

// ── Missing items panel ───────────────────────────────────────────────────

export type MissingItem = { name?: string; item_name?: string; category: string; needed_for?: string; priority?: string; reason?: string }

export function MissingItemsPanel({ items }: { items: MissingItem[] }) {
  if (items.length === 0) return null
  return (
    <GlassCard padding="lg">
      <h3 className="font-semibold text-slate-800 dark:text-white flex items-center gap-2 mb-4">
        <ShoppingCart size={16} className="text-amber-500" />
        Items to buy / borrow
        <span className="ml-auto text-xs font-normal text-slate-400 dark:text-white/30">{items.length} item{items.length !== 1 ? 's' : ''}</span>
      </h3>
      <div className="space-y-2">
        {items.map((item, i) => {
          const displayName = item.item_name ?? item.name ?? ''
          const priority = item.priority ?? 'recommended'
          const priorityColor = priority === 'essential' ? 'bg-red-50 dark:bg-red-900/10 border-red-200/60 dark:border-red-700/20' :
            priority === 'recommended' ? 'bg-amber-50/60 dark:bg-amber-900/10 border-amber-200/60 dark:border-amber-700/20' :
            'bg-slate-50 dark:bg-white/[0.03] border-slate-200 dark:border-white/[0.07]'
          return (
            <div key={i} className={cn('flex items-start gap-3 p-3 rounded-xl border', priorityColor)}>
              <ShoppingCart size={14} className="flex-shrink-0 mt-0.5 text-amber-500" />
              <div className="flex-1 min-w-0">
                <p className="text-sm font-medium text-slate-800 dark:text-white">{displayName}</p>
                {item.needed_for && <p className="text-xs text-slate-500 dark:text-white/40 capitalize">{item.needed_for}</p>}
                {item.reason && <p className="text-xs text-slate-400 dark:text-white/30 mt-0.5">{item.reason}</p>}
              </div>
              <Badge variant={priority === 'essential' ? 'red' : priority === 'recommended' ? 'amber' : 'gray'} className="flex-shrink-0 text-[9px]">
                {priority}
              </Badge>
            </div>
          )
        })}
      </div>
    </GlassCard>
  )
}
