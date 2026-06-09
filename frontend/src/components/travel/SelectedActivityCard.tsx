import { useState } from 'react'
import { ChevronDown, ChevronUp, X } from 'lucide-react'
import { cn } from '@/lib/utils'
import type { TripActivity } from '@/types'
import { ACTIVITY_PRESETS, FORMALITY_OPTS, TIME_OF_DAY_OPTS, type ActivityDraft } from './constants'

// ── Selected activity inline editor ──────────────────────────────────────

export function SelectedActivityCard({
  activity, tripDays, onUpdate, onRemove,
}: {
  activity: ActivityDraft
  tripDays: number
  onUpdate: (patch: Partial<ActivityDraft>) => void
  onRemove: () => void
}) {
  const [expanded, setExpanded] = useState(false)
  const preset = ACTIVITY_PRESETS.find(p => p.name === activity.name)

  return (
    <div className={cn(
      'rounded-xl border transition-all',
      activity.is_fixed
        ? 'border-amber-200 dark:border-amber-700/40 bg-amber-50/60 dark:bg-amber-900/10'
        : 'border-slate-200 dark:border-white/10 bg-white dark:bg-white/5',
    )}>
      {/* Header row */}
      <div className="flex items-center gap-3 px-3 py-2.5">
        <span className="text-lg">{preset?.emoji ?? '📌'}</span>
        <div className="flex-1 min-w-0">
          <p className="text-sm font-semibold text-slate-800 dark:text-white truncate">{activity.name}</p>
          <p className="text-xs text-slate-400 mt-0.5">
            {activity.day_number ? `Day ${activity.day_number}` : 'Day TBD'}
            {activity.time_of_day ? ` · ${activity.time_of_day}` : ''}
            {activity.formality ? ` · ${activity.formality.replace('_', ' ')}` : ''}
            {activity.is_fixed ? ' · 📌 Booked' : ''}
          </p>
        </div>
        <div className="flex items-center gap-1.5 flex-shrink-0">
          <button
            type="button"
            onClick={() => setExpanded(v => !v)}
            className="p-1 rounded-lg text-slate-400 hover:text-brand-500 hover:bg-brand-50 dark:hover:bg-brand-900/20 transition-colors"
          >
            {expanded ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
          </button>
          <button
            type="button"
            onClick={onRemove}
            className="p-1 rounded-lg text-slate-400 hover:text-red-500 hover:bg-red-50 dark:hover:bg-red-900/20 transition-colors"
          >
            <X size={14} />
          </button>
        </div>
      </div>

      {/* Expanded fields */}
      {expanded && (
        <div className="px-3 pb-3 pt-0 grid grid-cols-2 sm:grid-cols-3 gap-2 border-t border-current/10">
          {/* Day number */}
          <div>
            <label className="block text-[10px] font-semibold text-slate-500 dark:text-white/40 uppercase tracking-wider mb-1">Day</label>
            <select
              value={activity.day_number ?? ''}
              onChange={e => onUpdate({ day_number: e.target.value ? Number(e.target.value) : null })}
              className="w-full px-2 py-1.5 text-xs rounded-lg border border-slate-300 dark:border-white/10 bg-white dark:bg-slate-900 text-slate-900 dark:text-white focus:outline-none focus:ring-1 focus:ring-brand-500"
            >
              <option value="">Any day</option>
              {Array.from({ length: Math.min(tripDays, 14) }, (_, i) => i + 1).map(d => (
                <option key={d} value={d}>Day {d}</option>
              ))}
            </select>
          </div>
          {/* Time of day */}
          <div>
            <label className="block text-[10px] font-semibold text-slate-500 dark:text-white/40 uppercase tracking-wider mb-1">Time</label>
            <select
              value={activity.time_of_day ?? ''}
              onChange={e => onUpdate({ time_of_day: e.target.value as TripActivity['time_of_day'] || null })}
              className="w-full px-2 py-1.5 text-xs rounded-lg border border-slate-300 dark:border-white/10 bg-white dark:bg-slate-900 text-slate-900 dark:text-white focus:outline-none focus:ring-1 focus:ring-brand-500"
            >
              <option value="">Any time</option>
              {TIME_OF_DAY_OPTS.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
            </select>
          </div>
          {/* Formality */}
          <div>
            <label className="block text-[10px] font-semibold text-slate-500 dark:text-white/40 uppercase tracking-wider mb-1">Dress Code</label>
            <select
              value={activity.formality ?? ''}
              onChange={e => onUpdate({ formality: e.target.value as TripActivity['formality'] || null })}
              className="w-full px-2 py-1.5 text-xs rounded-lg border border-slate-300 dark:border-white/10 bg-white dark:bg-slate-900 text-slate-900 dark:text-white focus:outline-none focus:ring-1 focus:ring-brand-500"
            >
              <option value="">Any formality</option>
              {FORMALITY_OPTS.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
            </select>
          </div>
          {/* Booked toggle */}
          <div className="col-span-2 sm:col-span-1 flex items-center gap-2 pt-1">
            <button
              type="button"
              onClick={() => onUpdate({ is_fixed: !activity.is_fixed })}
              className={cn(
                'flex items-center gap-2 px-2.5 py-1.5 rounded-lg border text-xs font-medium transition-all',
                activity.is_fixed
                  ? 'bg-amber-50 dark:bg-amber-900/20 border-amber-300 dark:border-amber-700/40 text-amber-700 dark:text-amber-400'
                  : 'border-slate-200 dark:border-white/10 text-slate-500 dark:text-white/40 hover:border-amber-300',
              )}
            >
              📌 {activity.is_fixed ? 'Booked/Fixed' : 'Mark as Booked'}
            </button>
          </div>
          {/* Notes */}
          <div className="col-span-2 sm:col-span-3">
            <label className="block text-[10px] font-semibold text-slate-500 dark:text-white/40 uppercase tracking-wider mb-1">Notes (optional)</label>
            <input
              type="text"
              value={activity.notes ?? ''}
              onChange={e => onUpdate({ notes: e.target.value || null })}
              placeholder="e.g. Booked beach club, dress code applies…"
              className="w-full px-2.5 py-1.5 text-xs rounded-lg border border-slate-300 dark:border-white/10 bg-white dark:bg-slate-900 text-slate-900 dark:text-white focus:outline-none focus:ring-1 focus:ring-brand-500"
            />
          </div>
        </div>
      )}
    </div>
  )
}
