import { useCallback, useEffect, useState } from 'react'
import { AlertCircle, ArrowLeft, Bookmark, ChevronRight, Loader2 } from 'lucide-react'
import Badge from '@/components/ui/Badge'
import Button from '@/components/ui/Button'
import GlassCard from '@/components/ui/GlassCard'
import { tripsApi } from '@/lib/api'
import { cn } from '@/lib/utils'
import type { PackingPlan, Trip } from '@/types'
import { DayPlanCard } from './DayPlanCard'
import { PackingChecklistPanel } from './PackingChecklistPanel'
import { RewearStrategyPanel } from './RewearStrategyPanel'
import { TripSummaryBanner } from './TripSummaryBanner'

// ── Saved planners tab ────────────────────────────────────────────────────

export function SavedPlannersTab() {
  const [savedTrips, setSavedTrips] = useState<Trip[]>([])
  const [loading, setLoading] = useState(false)
  const [selected, setSelected] = useState<Trip | null>(null)
  const [plan, setPlan] = useState<PackingPlan | null>(null)
  const [planLoading, setPlanLoading] = useState(false)
  const [planError, setPlanError] = useState<string | null>(null)
  const [planTab, setPlanTab] = useState<'days' | 'rewear' | 'checklist'>('days')
  const [packedState, setPackedState] = useState<Record<string, boolean>>({})

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const list = await tripsApi.listSaved()
      setSavedTrips(list)
    } catch { /* quiet */ }
    finally { setLoading(false) }
  }, [])

  useEffect(() => { void load() }, [load])

  const openTrip = async (t: Trip) => {
    setSelected(t); setPlan(null); setPlanError(null); setPackedState({})
    setPlanTab('days'); setPlanLoading(true)
    try {
      const p = await tripsApi.getPackingPlan(t.id)
      setPlan(p)
      const state: Record<string, boolean> = {}
      if (p.checklist_state) Object.assign(state, p.checklist_state)
      setPackedState(state)
    } catch { setPlanError('Could not load packing plan.') }
    finally { setPlanLoading(false) }
  }

  const handleToggle = async (key: string, val: boolean) => {
    setPackedState(prev => ({ ...prev, [key]: val }))
    if (selected) {
      try { await tripsApi.updateChecklistItem(selected.id, key, val) } catch { /* quiet */ }
    }
  }

  const dur = (t: Trip) => Math.ceil((new Date(t.end_date).getTime() - new Date(t.start_date).getTime()) / 86_400_000)

  if (selected) return (
    <div className="space-y-4">
      <Button variant="ghost" onClick={() => { setSelected(null); setPlan(null) }} className="flex items-center gap-2">
        <ArrowLeft size={15} /> Back to Saved Planners
      </Button>
      {plan && <TripSummaryBanner trip={selected} plan={plan} />}
      {planLoading && (
        <div className="card p-6 flex items-center justify-center gap-3 text-slate-500 dark:text-white/40 text-sm">
          <Loader2 size={16} className="animate-spin" /> Loading packing plan…
        </div>
      )}
      {planError && (
        <div className="card p-4 bg-red-50 dark:bg-red-900/20 text-red-700 dark:text-red-300 text-sm flex items-center gap-2">
          <AlertCircle size={14} /> {planError}
        </div>
      )}
      {plan && (
        <>
          {/* Tab bar */}
          <div className="flex gap-1 p-1 rounded-xl bg-slate-100 dark:bg-white/[0.06] self-start">
            {(['days', 'rewear', 'checklist'] as const).map(t => (
              <button key={t} onClick={() => setPlanTab(t)}
                className={cn('px-3 py-1.5 rounded-lg text-xs font-semibold transition-all',
                  planTab === t ? 'bg-white dark:bg-white/[0.12] text-slate-800 dark:text-white shadow-sm' : 'text-slate-500 dark:text-slate-400')}>
                {t === 'days' ? '📅 Day Plans' : t === 'rewear' ? '🔄 Rewear' : '✅ Checklist'}
              </button>
            ))}
          </div>
          {planTab === 'days' && (
            <div className="space-y-3">
              {(plan.day_plans_rich ?? []).length > 0
                ? (plan.day_plans_rich).map(d => <DayPlanCard key={d.day_number} day={d} />)
                : <p className="text-sm text-slate-400 dark:text-white/30 py-4">No day plans found in this saved planner.</p>}
            </div>
          )}
          {planTab === 'rewear' && <RewearStrategyPanel items={plan.rewear_strategy ?? []} />}
          {planTab === 'checklist' && (
            <PackingChecklistPanel
              items={plan.packing_checklist ?? []}
              packedState={packedState}
              onToggle={handleToggle}
            />
          )}
        </>
      )}
    </div>
  )

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h3 className="font-display font-semibold text-sm uppercase tracking-widest text-slate-500 dark:text-white/40">Saved Planners</h3>
        <button onClick={load} className="text-xs text-slate-400 hover:text-brand-500 transition-colors">Refresh</button>
      </div>
      {loading ? (
        <div className="card p-6 flex items-center justify-center gap-3 text-slate-500 dark:text-white/40 text-sm">
          <Loader2 size={16} className="animate-spin" /> Loading…
        </div>
      ) : savedTrips.length === 0 ? (
        <div className="card p-10 text-center space-y-3">
          <Bookmark size={32} className="mx-auto text-slate-300 dark:text-white/20" />
          <div>
            <p className="font-semibold text-slate-700 dark:text-white">No saved planners yet</p>
            <p className="text-sm text-slate-500 dark:text-white/40 mt-1">Create a trip and save your packing planner to access it here.</p>
          </div>
        </div>
      ) : (
        <div className="space-y-3">
          {savedTrips.map(t => (
            <GlassCard key={t.id} padding="md" hover>
              <div className="flex items-start justify-between gap-4">
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 mb-1 flex-wrap">
                    <p className="font-semibold text-slate-800 dark:text-white truncate">{t.destination}</p>
                    <Badge>{t.purpose}</Badge>
                    {t.trip_style && <Badge variant="purple">{t.trip_style.replace('_', ' ')}</Badge>}
                  </div>
                  <p className="text-xs text-slate-500 dark:text-white/40">
                    {new Date(t.start_date + 'T00:00:00').toLocaleDateString()} – {new Date(t.end_date + 'T00:00:00').toLocaleDateString()} · {dur(t)} days
                  </p>
                  {t.activities.length > 0 && (
                    <p className="text-xs text-slate-400 dark:text-white/30 mt-0.5 truncate">
                      {t.activities.slice(0, 3).map(a => a.name).join(' · ')}
                      {t.activities.length > 3 ? ` +${t.activities.length - 3} more` : ''}
                    </p>
                  )}
                </div>
                <Button variant="ghost" onClick={() => openTrip(t)} className="flex items-center gap-1.5 flex-shrink-0 text-xs">
                  View Planner <ChevronRight size={13} />
                </Button>
              </div>
            </GlassCard>
          ))}
        </div>
      )}
    </div>
  )
}
