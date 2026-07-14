import { RefreshCw } from 'lucide-react'
import type { RewearStrategyItem } from '@/types'
import { CARD_SHADOW } from './constants'

// ── Rewear strategy panel ─────────────────────────────────────────────────

export function RewearStrategyPanel({ items }: { items: RewearStrategyItem[] }) {
  if (items.length === 0) return (
    <div className="text-center py-10 text-slate-400 dark:text-white/30 text-sm">
      No specific rewear strategy — each outfit uses distinct items.
    </div>
  )

  return (
    <div className="space-y-3">
      {/* Intro line */}
      <div className="flex items-center gap-2 px-1 text-xs font-semibold tracking-[0.14em] uppercase text-slate-400 dark:text-white/30">
        <RefreshCw size={12} className="text-teal-500" />
        {items.length} piece{items.length !== 1 ? 's' : ''} pull double duty
      </div>

      {items.map((item, i) => {
        const wearCount = item.worn_on_days.length
        return (
          <div
            key={i}
            className="rounded-2xl bg-white dark:bg-white/[0.05] border border-slate-200 dark:border-white/10 p-4 flex items-start gap-3.5"
            style={{ boxShadow: CARD_SHADOW }}
          >
            {/* Wear-count badge */}
            <div className="flex flex-col items-center gap-1 flex-none">
              <div className="w-10 h-10 rounded-xl bg-teal-50 dark:bg-teal-900/30 flex items-center justify-center">
                <RefreshCw size={16} className="text-teal-600 dark:text-teal-400" />
              </div>
              {wearCount > 1 && (
                <span className="text-[10px] font-bold text-teal-600 dark:text-teal-400">×{wearCount}</span>
              )}
            </div>

            <div className="flex-1 min-w-0">
              <p className="text-sm font-semibold text-slate-800 dark:text-white">{item.item_name}</p>

              {/* Day pills */}
              {item.worn_on_days.length > 0 && (
                <div className="flex flex-wrap gap-1.5 mt-2">
                  {item.worn_on_days.map((day, di) => (
                    <span
                      key={di}
                      className="px-2 py-0.5 rounded-full text-[11px] font-medium bg-teal-50 dark:bg-teal-900/20 text-teal-700 dark:text-teal-300 border border-teal-200/60 dark:border-teal-700/30"
                    >
                      {day}
                    </span>
                  ))}
                </div>
              )}

              {item.worn_for && item.worn_for.length > 0 && (
                <p className="text-xs text-slate-400 dark:text-white/30 mt-1.5">{item.worn_for.join(' · ')}</p>
              )}
              {item.reason && (
                <p className="text-xs text-slate-500 dark:text-white/40 mt-1 leading-relaxed">{item.reason}</p>
              )}
            </div>
          </div>
        )
      })}
    </div>
  )
}
