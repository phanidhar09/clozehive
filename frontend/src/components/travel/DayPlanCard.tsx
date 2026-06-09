import { useState } from 'react'
import { ChevronDown, ChevronUp, RefreshCw, Sparkles, Sun, Thermometer } from 'lucide-react'
import Badge from '@/components/ui/Badge'
import { cn } from '@/lib/utils'
import type { RichDayPlan } from '@/types'
import { CATEGORY_EMOJI, SOURCE_BADGE } from './constants'

// ── Outfit item card (inside day plan) ────────────────────────────────────

function OutfitItemCard({ item }: { item: RichDayPlan['outfits'][0]['items'][0] }) {
  const badgeCfg = SOURCE_BADGE[item.source] ?? SOURCE_BADGE.optional
  const emoji = CATEGORY_EMOJI[item.category?.toLowerCase() ?? ''] ?? '👔'

  return (
    <div className={cn(
      'flex items-center gap-2 p-2 rounded-xl border text-xs',
      item.source === 'from_closet'
        ? 'bg-emerald-50/60 dark:bg-emerald-900/10 border-emerald-200/60 dark:border-emerald-700/20'
        : item.source === 'missing_recommended'
          ? 'bg-amber-50/60 dark:bg-amber-900/10 border-amber-200/60 dark:border-amber-700/20'
          : 'bg-slate-50/60 dark:bg-white/[0.03] border-slate-200/60 dark:border-white/[0.06]',
    )}>
      {/* Thumbnail */}
      {item.image_url ? (
        <img
          src={item.image_url}
          alt={item.item_name}
          className="w-9 h-10 object-cover rounded-lg flex-shrink-0 bg-slate-100 dark:bg-slate-800"
          onError={e => { (e.target as HTMLImageElement).style.display = 'none' }}
        />
      ) : (
        <div className="w-9 h-10 rounded-lg flex-shrink-0 bg-slate-100 dark:bg-slate-800 flex items-center justify-center text-lg">
          {emoji}
        </div>
      )}
      <div className="flex-1 min-w-0">
        <p className="font-semibold text-slate-800 dark:text-white truncate">{item.item_name}</p>
        <p className="text-slate-400 capitalize truncate">{item.category}</p>
      </div>
      <Badge variant={badgeCfg.variant} className="flex-shrink-0 text-[9px]">
        {badgeCfg.label}
      </Badge>
    </div>
  )
}

// ── Day plan card ─────────────────────────────────────────────────────────

export function DayPlanCard({ day }: { day: RichDayPlan }) {
  const [expanded, setExpanded] = useState(day.day_number <= 3)
  const dateStr = day.date
    ? new Date(day.date + 'T00:00:00').toLocaleDateString(undefined, { weekday: 'short', month: 'short', day: 'numeric' })
    : `Day ${day.day_number}`

  const slotColors: Record<string, string> = {
    morning: 'bg-amber-50 dark:bg-amber-900/10 border-amber-200/60 dark:border-amber-700/20 text-amber-700 dark:text-amber-400',
    afternoon: 'bg-sky-50 dark:bg-sky-900/10 border-sky-200/60 dark:border-sky-700/20 text-sky-700 dark:text-sky-400',
    evening: 'bg-brand-50 dark:bg-brand-900/10 border-brand-200/60 dark:border-brand-700/20 text-brand-700 dark:text-brand-400',
    night: 'bg-brand-50 dark:bg-brand-900/10 border-brand-200/60 dark:border-brand-700/20 text-brand-700 dark:text-brand-400',
    full_day: 'bg-teal-50 dark:bg-teal-900/10 border-teal-200/60 dark:border-teal-700/20 text-teal-700 dark:text-teal-400',
  }
  const slotEmoji: Record<string, string> = {
    morning: '🌅', afternoon: '☀️', evening: '🌆', night: '🌙', full_day: '🕐',
  }

  return (
    <div className="rounded-2xl border border-slate-200 dark:border-white/[0.08] bg-white dark:bg-white/[0.02] overflow-hidden shadow-sm">
      {/* Day header */}
      <button
        type="button"
        onClick={() => setExpanded(v => !v)}
        className="w-full flex items-center justify-between gap-3 px-4 py-3 bg-slate-50 dark:bg-white/[0.04] border-b border-slate-200 dark:border-white/[0.06] text-left hover:bg-slate-100 dark:hover:bg-white/[0.06] transition-colors"
      >
        <div className="flex items-center gap-3">
          <div className="w-9 h-9 rounded-xl bg-brand-100 dark:bg-brand-900/30 flex items-center justify-center flex-shrink-0">
            <span className="text-sm font-bold text-brand-600 dark:text-brand-400">{day.day_number}</span>
          </div>
          <div>
            <p className="font-semibold text-slate-800 dark:text-white text-sm">{dateStr}</p>
            {day.activities.length > 0 && (
              <p className="text-xs text-slate-400 mt-0.5 truncate max-w-[200px]">
                {day.activities.join(' · ')}
              </p>
            )}
          </div>
        </div>
        <div className="flex items-center gap-2 flex-shrink-0">
          {day.weather_note && (
            <span className="text-xs text-slate-400 dark:text-white/30 hidden sm:block max-w-[180px] truncate">
              {day.weather_note}
            </span>
          )}
          <span className="text-xs font-medium text-slate-500 bg-slate-100 dark:bg-white/[0.06] px-2 py-0.5 rounded-full">
            {day.outfits.length} outfit{day.outfits.length !== 1 ? 's' : ''}
          </span>
          {expanded ? <ChevronUp size={14} className="text-slate-400" /> : <ChevronDown size={14} className="text-slate-400" />}
        </div>
      </button>

      {/* Day content */}
      {expanded && (
        <div className="p-4 space-y-4">
          {day.weather_note && (
            <div className="flex items-center gap-2 text-xs text-slate-500 dark:text-white/40 bg-slate-50 dark:bg-white/[0.03] rounded-xl px-3 py-2 border border-slate-100 dark:border-white/[0.06]">
              <Sun size={12} className="text-amber-500 flex-shrink-0" />
              {day.weather_note}
            </div>
          )}

          {day.outfits.map((outfit, oi) => (
            <div key={oi} className="space-y-2.5">
              {/* Slot header */}
              <div className={cn(
                'flex items-center gap-2 px-3 py-1.5 rounded-lg border text-xs font-semibold w-fit',
                slotColors[outfit.slot] ?? slotColors.morning,
              )}>
                <span>{slotEmoji[outfit.slot] ?? '👔'}</span>
                <span className="capitalize">{outfit.slot.replace('_', ' ')}</span>
                {outfit.activity && outfit.activity !== 'General' && (
                  <>
                    <span className="opacity-50">·</span>
                    <span>{outfit.activity}</span>
                  </>
                )}
              </div>

              {outfit.outfit_name && (
                <p className="text-sm font-semibold text-slate-700 dark:text-slate-200 px-0.5">{outfit.outfit_name}</p>
              )}

              {/* Outfit items */}
              {outfit.items.length > 0 && (
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
                  {outfit.items.map((item, ii) => (
                    <OutfitItemCard key={ii} item={item} />
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
                  <div className="flex items-start gap-2 text-xs text-slate-500 dark:text-white/40 bg-teal-50/50 dark:bg-teal-900/10 rounded-lg px-2.5 py-1.5">
                    <RefreshCw size={11} className="text-teal-500 flex-shrink-0 mt-0.5" />
                    <span>{outfit.rewear_notes}</span>
                  </div>
                )}
                {outfit.comfort_notes && (
                  <div className="flex items-start gap-2 text-xs text-slate-400 dark:text-white/30 px-2.5 py-1">
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
