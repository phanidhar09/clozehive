import { AlertTriangle, Luggage, MapPin, Sparkles, Sun } from 'lucide-react'
import Badge from '@/components/ui/Badge'
import { cn } from '@/lib/utils'
import type { BagCapacitySummary, PackingPlan, Trip } from '@/types'
import { BAG_SIZE_OPTS } from './constants'

// ── Trip summary banner ───────────────────────────────────────────────────

export function TripSummaryBanner({ trip, plan }: { trip: Trip; plan: PackingPlan }) {
  const duration = Math.ceil((new Date(trip.end_date).getTime() - new Date(trip.start_date).getTime()) / 86_400_000)
  const bagLabel = BAG_SIZE_OPTS.find(b => b.value === trip.bag_size)?.label ?? ''
  const bagCap = plan.bag_capacity_summary as BagCapacitySummary | null | undefined
  const statusColor = bagCap?.packing_status === 'fits' ? 'text-emerald-600 dark:text-emerald-400' :
    bagCap?.packing_status === 'tight' ? 'text-amber-600 dark:text-amber-400' :
    'text-red-600 dark:text-red-400'

  return (
    <div className="rounded-2xl border border-brand-200/60 dark:border-brand-500/20 bg-gradient-to-br from-brand-500/[0.06] via-brand-500/[0.04] to-transparent p-4 space-y-3">
      <div className="flex items-start gap-3 flex-wrap">
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <h3 className="font-display font-bold text-lg text-slate-800 dark:text-white">{trip.destination}</h3>
            <Badge>{trip.purpose}</Badge>
            {trip.trip_style && <Badge variant="purple">{trip.trip_style.replace('_', ' ')}</Badge>}
          </div>
          <p className="text-sm text-slate-500 dark:text-white/40 mt-0.5">
            {new Date(trip.start_date + 'T00:00:00').toLocaleDateString(undefined, { month: 'short', day: 'numeric' })}
            {' – '}
            {new Date(trip.end_date + 'T00:00:00').toLocaleDateString(undefined, { month: 'short', day: 'numeric' })}
            {' · '}{duration} day{duration !== 1 ? 's' : ''}
          </p>
        </div>
        {bagLabel && (
          <div className="flex items-center gap-1.5 text-xs font-medium text-slate-600 dark:text-white/60 bg-white/80 dark:bg-white/[0.06] px-3 py-1.5 rounded-xl border border-slate-200 dark:border-white/[0.1]">
            <Luggage size={13} className="text-brand-500" />
            {bagLabel}
            {bagCap && <span className={cn('ml-1 font-bold', statusColor)}>· {bagCap.packing_status}</span>}
          </div>
        )}
      </div>

      {/* Style direction */}
      {plan.trip_style_direction && (
        <div className="flex items-start gap-2 text-sm text-slate-600 dark:text-white/60">
          <Sparkles size={14} className="text-brand-500 flex-shrink-0 mt-0.5" />
          <p className="leading-relaxed">{plan.trip_style_direction}</p>
        </div>
      )}

      {/* Climate */}
      {(plan.climate_summary || plan.weather_summary) && (
        <div className="flex items-center gap-2 text-xs text-slate-500 dark:text-white/40">
          <Sun size={12} className="text-amber-500 flex-shrink-0" />
          {plan.climate_summary
            ? plan.climate_summary
            : `${plan.weather_summary?.dominant_condition ?? ''}, avg ${plan.weather_summary?.avg_high?.toFixed(0) ?? '?'}°C / ${plan.weather_summary?.avg_low?.toFixed(0) ?? '?'}°C`
          }
        </div>
      )}

      {/* Local dress notes */}
      {plan.location_etiquette && (
        <div className="flex items-start gap-2 text-xs text-slate-500 dark:text-white/40">
          <MapPin size={12} className="text-brand-500 flex-shrink-0 mt-0.5" />
          <p className="leading-relaxed">{plan.location_etiquette}</p>
        </div>
      )}

      {/* Bag optimization notes */}
      {bagCap?.optimization_notes && bagCap.optimization_notes.length > 0 && (
        <div className="flex flex-wrap gap-1.5">
          {bagCap.optimization_notes.map((note, i) => (
            <span key={i} className="text-[10px] px-2 py-0.5 rounded-full bg-white/80 dark:bg-white/[0.06] border border-slate-200 dark:border-white/[0.08] text-slate-500 dark:text-white/40">
              {note}
            </span>
          ))}
        </div>
      )}

      {/* Alerts */}
      {plan.alerts.length > 0 && (
        <div className="space-y-1">
          {plan.alerts.map((alert, i) => (
            <div key={i} className="flex items-start gap-2 text-xs text-amber-700 dark:text-amber-400 bg-amber-50 dark:bg-amber-900/10 rounded-lg px-2.5 py-1.5">
              <AlertTriangle size={11} className="flex-shrink-0 mt-0.5" />
              {alert}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
