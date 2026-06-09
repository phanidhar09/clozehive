import { RefreshCw } from 'lucide-react'
import type { RewearStrategyItem } from '@/types'

// ── Rewear strategy panel ─────────────────────────────────────────────────

export function RewearStrategyPanel({ items }: { items: RewearStrategyItem[] }) {
  if (items.length === 0) return (
    <div className="text-center py-10 text-slate-400 dark:text-white/30 text-sm">
      No specific rewear strategy — each outfit uses distinct items.
    </div>
  )
  return (
    <div className="space-y-3">
      {items.map((item, i) => (
        <div key={i} className="flex items-start gap-3 p-3 rounded-xl bg-teal-50/60 dark:bg-teal-900/10 border border-teal-200/60 dark:border-teal-700/20">
          <div className="w-8 h-8 rounded-xl bg-teal-100 dark:bg-teal-900/30 flex items-center justify-center flex-shrink-0">
            <RefreshCw size={14} className="text-teal-600 dark:text-teal-400" />
          </div>
          <div className="flex-1 min-w-0">
            <p className="text-sm font-semibold text-slate-800 dark:text-white">{item.item_name}</p>
            {item.worn_on_days.length > 0 && (
              <p className="text-xs text-teal-700 dark:text-teal-400 mt-0.5">
                {item.worn_on_days.join(' · ')}
              </p>
            )}
            {item.worn_for && item.worn_for.length > 0 && (
              <p className="text-xs text-slate-400 mt-0.5">{item.worn_for.join(', ')}</p>
            )}
            {item.reason && (
              <p className="text-xs text-slate-500 dark:text-white/40 mt-1">{item.reason}</p>
            )}
          </div>
        </div>
      ))}
    </div>
  )
}
