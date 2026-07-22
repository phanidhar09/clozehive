import { useState } from 'react'
import { ChevronDown, ChevronUp, RefreshCw, Sparkles, Thermometer } from 'lucide-react'
import { cn } from '@/lib/utils'
import type { RichDayPlan } from '@/types'
import { CARD_SHADOW, CATEGORY_EMOJI } from './constants'

// ── Outfit item tile ──────────────────────────────────────────────────────

function OutfitItemTile({ item }: { item: RichDayPlan['outfits'][0]['items'][0] }) {
  const emoji = CATEGORY_EMOJI[item.category?.toLowerCase() ?? ''] ?? '👔'
  const sourceDot =
    item.source === 'from_closet' ? 'bg-emerald-500' :
    item.source === 'missing_recommended' ? 'bg-highlight-400' :
    'bg-slate-300 dark:bg-white/20'

  return (
    <div className="flex flex-col gap-1 min-w-0">
      <div className="aspect-square rounded-xl bg-cream-100 dark:bg-white/[0.06] border border-slate-200 dark:border-white/10 flex items-center justify-center overflow-hidden">
        {item.image_url ? (
          <img
            src={item.image_url}
            alt={item.item_name}
            className="w-full h-full object-cover"
            onError={e => {
              const t = e.target as HTMLImageElement
              t.style.display = 'none'
              t.parentElement?.insertAdjacentText('afterbegin', emoji)
            }}
          />
        ) : (
          <span className="text-2xl">{emoji}</span>
        )}
      </div>
      <div className="text-[11px] font-medium text-slate-700 dark:text-white/80 leading-tight line-clamp-2">
        {item.item_name}
      </div>
      <div className="flex items-center gap-1 text-[10px] text-slate-400 dark:text-white/30 capitalize">
        <span className={cn('w-1.5 h-1.5 rounded-full flex-none', sourceDot)} />
        {item.category}
      </div>
    </div>
  )
}

// ── Day plan card ─────────────────────────────────────────────────────────

export function DayPlanCard({ day }: { day: RichDayPlan }) {
  const [expanded, setExpanded] = useState(day.day_number <= 3)
  const dateStr = day.date
    ? new Date(day.date + 'T00:00:00').toLocaleDateString(undefined, { weekday: 'short', month: 'short', day: 'numeric' })
    : `Day ${day.day_number}`

  const slotEmoji: Record<string, string> = {
    morning: '🌅', afternoon: '☀️', evening: '🌆', night: '🌙', full_day: '🕐',
  }

  return (
    <div
      className="rounded-2xl bg-white dark:bg-white/[0.05] border border-slate-200 dark:border-white/10 overflow-hidden"
      style={{ boxShadow: CARD_SHADOW }}
    >
      {/* Day header */}
      <button
        type="button"
        onClick={() => setExpanded(v => !v)}
        className="w-full flex items-center justify-between gap-3 px-5 py-3.5 text-left hover:bg-slate-50/60 dark:hover:bg-white/[0.03] transition-colors"
      >
        <div className="flex items-center gap-2.5 min-w-0">
          <span className="px-2.5 py-1 rounded-lg bg-brand-50 dark:bg-brand-900/40 text-brand-700 dark:text-brand-300 text-xs font-display font-bold flex-none">
            DAY {day.day_number}
          </span>
          <span className="text-sm font-semibold text-slate-800 dark:text-white truncate">{dateStr}</span>
        </div>
        <div className="flex items-center gap-2 flex-none">
          {day.weather_note && (
            <span className="text-xs text-slate-400 dark:text-white/30 hidden sm:block max-w-[160px] truncate">
              {day.weather_note}
            </span>
          )}
          <span className="text-xs font-medium text-slate-500 dark:text-white/50 bg-slate-100 dark:bg-white/[0.06] px-2 py-0.5 rounded-full">
            {day.outfits.length} outfit{day.outfits.length !== 1 ? 's' : ''}
          </span>
          {expanded
            ? <ChevronUp size={14} className="text-slate-400" />
            : <ChevronDown size={14} className="text-slate-400" />}
        </div>
      </button>

      {/* Day content */}
      {expanded && (
        <div className="px-5 pb-5 space-y-4">
          {/* Activity bullets */}
          {day.activities.length > 0 && (
            <div className="flex flex-col gap-1.5">
              {day.activities.map((act, ai) => (
                <div key={ai} className="flex items-center gap-2 text-sm text-slate-600 dark:text-white/60">
                  <span className="w-1.5 h-1.5 rounded-full bg-brand-400 flex-none" />
                  {act}
                </div>
              ))}
            </div>
          )}

          {/* Outfits per slot */}
          {day.outfits.map((outfit, oi) => (
            <div key={oi} className="space-y-2.5">
              {/* Slot + activity label */}
              <div className="flex items-center gap-2 flex-wrap">
                <div className="text-[11px] font-semibold tracking-[0.14em] text-slate-400 dark:text-white/30 uppercase flex items-center gap-1.5">
                  <span>{slotEmoji[outfit.slot] ?? '👔'}</span>
                  <span>{outfit.slot.replace('_', ' ')}</span>
                  {outfit.activity && outfit.activity !== 'General' && (
                    <>
                      <span className="opacity-40">·</span>
                      <span className="text-brand-600 dark:text-brand-400 normal-case tracking-normal">
                        {outfit.activity}
                      </span>
                    </>
                  )}
                </div>
              </div>

              {outfit.outfit_name && (
                <p className="text-sm font-semibold text-slate-700 dark:text-slate-200">{outfit.outfit_name}</p>
              )}

              {/* Outfit item grid */}
              {outfit.items.length > 0 && (
                <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
                  {outfit.items.map((item, ii) => (
                    <OutfitItemTile key={ii} item={item} />
                  ))}
                </div>
              )}

              {/* Notes */}
              <div className="space-y-1.5">
                {outfit.styling_notes && (
                  <div className="flex items-start gap-2 text-xs text-slate-600 dark:text-white/50 bg-brand-50/50 dark:bg-brand-900/10 rounded-lg px-2.5 py-1.5">
                    <Sparkles size={11} className="text-brand-500 flex-shrink-0 mt-0.5" />
                    <span>{outfit.styling_notes}</span>
                  </div>
                )}
                {outfit.rewear_notes && (
                  <div className="flex items-center gap-1.5 text-xs font-medium text-brand-700 dark:text-brand-300">
                    <RefreshCw size={11} className="flex-shrink-0" />
                    <span>{outfit.rewear_notes}</span>
                  </div>
                )}
                {outfit.comfort_notes && (
                  <div className="flex items-start gap-2 text-xs text-slate-400 dark:text-white/30 px-0.5">
                    <Thermometer size={11} className="text-sky-400 flex-shrink-0 mt-0.5" />
                    <span>{outfit.comfort_notes}</span>
                  </div>
                )}
              </div>

              {oi < day.outfits.length - 1 && (
                <div className="border-t border-dashed border-slate-200 dark:border-white/[0.06]" />
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
