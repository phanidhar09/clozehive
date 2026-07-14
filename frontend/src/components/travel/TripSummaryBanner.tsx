import { AlertTriangle, MapPin, Sparkles, Sun } from 'lucide-react'
import { cn } from '@/lib/utils'
import type { BagCapacitySummary, PackingPlan, Trip } from '@/types'
import { BAG_SIZE_OPTS } from './constants'

// ── Trip summary banner — "Postcard Dossier" hero ─────────────────────────

export function TripSummaryBanner({ trip, plan }: { trip: Trip; plan: PackingPlan }) {
  const duration = Math.max(
    1,
    Math.ceil((new Date(trip.end_date).getTime() - new Date(trip.start_date).getTime()) / 86_400_000),
  )
  const bagLabel = BAG_SIZE_OPTS.find(b => b.value === trip.bag_size)?.label ?? ''
  const bagCap = plan.bag_capacity_summary as BagCapacitySummary | null | undefined
  const statusColor =
    bagCap?.packing_status === 'fits' ? 'text-emerald-600 dark:text-emerald-400' :
    bagCap?.packing_status === 'tight' ? 'text-amber-600 dark:text-amber-400' :
    'text-red-600 dark:text-red-400'

  // Stable dossier number derived from the trip id (charm, not fake data).
  const dossierNo = String(
    Array.from(trip.id).reduce((acc, ch) => (acc * 31 + ch.charCodeAt(0)) % 1000, 7),
  ).padStart(3, '0')

  const fmtLong = (d: string) =>
    new Date(d + 'T00:00:00').toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' })
  const fmtShort = (d: string) =>
    new Date(d + 'T00:00:00').toLocaleDateString(undefined, { month: 'short', day: 'numeric' })
  const dateRange = `${fmtShort(trip.start_date)} – ${fmtLong(trip.end_date)}`

  const weatherText = plan.climate_summary
    ? plan.climate_summary
    : plan.weather_summary
      ? `${plan.weather_summary.dominant_condition ?? 'Mixed'} · ${plan.weather_summary.avg_high?.toFixed(0) ?? '?'}°C`
      : null

  // Hero chips — only render what we actually have.
  const chips: { label: string; withSun?: boolean }[] = [
    { label: `${duration} day${duration !== 1 ? 's' : ''}` },
    { label: trip.purpose },
  ]
  if (trip.trip_style) chips.push({ label: trip.trip_style.replace('_', ' ') })
  if (weatherText) chips.push({ label: weatherText, withSun: true })
  if (bagLabel) chips.push({ label: bagLabel })

  // Save-row stats.
  const itemCount = plan.packing_checklist?.length ?? 0
  const outfitCount = plan.day_plans_rich?.reduce((n, d) => n + d.outfits.length, 0) ?? 0
  const rewearCount = plan.rewear_strategy?.length ?? 0

  return (
    <div className="space-y-3">
      {/* ── Hero postcard ─────────────────────────────────────────────── */}
      <div
        className="rounded-3xl p-6 relative overflow-hidden text-white shadow-glow"
        style={{ background: 'linear-gradient(135deg,#0F766E 0%,#0D9488 45%,#059669 100%)' }}
      >
        {/* soft orbs */}
        <div
          className="absolute rounded-full pointer-events-none"
          style={{ width: 220, height: 220, top: -90, right: -70, background: 'rgba(255,255,255,0.10)', filter: 'blur(40px)' }}
        />
        <div
          className="absolute rounded-full pointer-events-none"
          style={{ width: 180, height: 180, bottom: -80, left: -60, background: 'rgba(94,234,212,0.18)', filter: 'blur(36px)' }}
        />

        <div className="relative">
          <div className="flex items-start justify-between gap-3">
            <div className="text-[11px] font-semibold tracking-[0.18em] text-white/70">
              TRIP DOSSIER · Nº {dossierNo}
            </div>
            {/* wax-stamp flourish */}
            <div
              className="w-11 h-12 rounded-md flex items-center justify-center rotate-3 flex-none"
              style={{ border: '1.5px dashed rgba(255,255,255,0.45)' }}
              aria-hidden="true"
            >
              <Sparkles size={16} className="text-white/80" />
            </div>
          </div>

          <h3
            className="font-display font-bold"
            style={{ fontSize: 40, lineHeight: 1.05, margin: '10px 0 4px' }}
          >
            {trip.destination}
          </h3>
          <div className="flex items-center gap-1.5 text-white/80 text-sm">
            <MapPin size={14} className="flex-none" />
            <span>{dateRange}</span>
          </div>

          <div className="flex flex-wrap gap-2 mt-5">
            {chips.map((chip, i) => (
              <span
                key={i}
                className="px-3 py-1.5 rounded-full text-xs font-medium bg-white/15 backdrop-blur-sm flex items-center gap-1.5 capitalize"
              >
                {chip.withSun && <Sun size={12} className="text-highlight-400 flex-none" />}
                {chip.label}
              </span>
            ))}
          </div>
        </div>
      </div>

      {/* ── Stats row ─────────────────────────────────────────────────── */}
      <div className="flex items-center justify-between gap-3 px-1">
        <div className="text-xs text-slate-500 dark:text-white/40">
          {itemCount > 0 && <>{itemCount} item{itemCount !== 1 ? 's' : ''}</>}
          {outfitCount > 0 && <> · {outfitCount} outfit{outfitCount !== 1 ? 's' : ''}</>}
          {rewearCount > 0 && <> · {rewearCount} rewear{rewearCount !== 1 ? 's' : ''}</>}
        </div>
        {bagCap && (
          <span className={cn('text-xs font-bold flex-none', statusColor)}>
            Bag: {bagCap.packing_status}
          </span>
        )}
      </div>

      {/* ── Informational callouts (preserve all real plan data) ──────── */}
      {(plan.trip_style_direction || plan.location_etiquette ||
        (bagCap?.optimization_notes?.length ?? 0) > 0 || plan.alerts.length > 0) && (
        <div className="rounded-2xl border border-brand-200/60 dark:border-brand-500/20 bg-gradient-to-br from-brand-500/[0.06] via-brand-500/[0.04] to-transparent p-4 space-y-3">
          {plan.trip_style_direction && (
            <div className="flex items-start gap-2 text-sm text-slate-600 dark:text-white/60">
              <Sparkles size={14} className="text-brand-500 flex-shrink-0 mt-0.5" />
              <p className="leading-relaxed">{plan.trip_style_direction}</p>
            </div>
          )}

          {plan.location_etiquette && (
            <div className="flex items-start gap-2 text-xs text-slate-500 dark:text-white/40">
              <MapPin size={12} className="text-brand-500 flex-shrink-0 mt-0.5" />
              <p className="leading-relaxed">{plan.location_etiquette}</p>
            </div>
          )}

          {bagCap?.optimization_notes && bagCap.optimization_notes.length > 0 && (
            <div className="flex flex-wrap gap-1.5">
              {bagCap.optimization_notes.map((note, i) => (
                <span
                  key={i}
                  className="text-[10px] px-2 py-0.5 rounded-full bg-white/80 dark:bg-white/[0.06] border border-slate-200 dark:border-white/[0.08] text-slate-500 dark:text-white/40"
                >
                  {note}
                </span>
              ))}
            </div>
          )}

          {plan.alerts.length > 0 && (
            <div className="space-y-1">
              {plan.alerts.map((alert, i) => (
                <div
                  key={i}
                  className="flex items-start gap-2 text-xs text-amber-700 dark:text-amber-400 bg-amber-50 dark:bg-amber-900/10 rounded-lg px-2.5 py-1.5"
                >
                  <AlertTriangle size={11} className="flex-shrink-0 mt-0.5" />
                  {alert}
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  )
}
