/**
 * TravelPlanner — activity-aware travel outfit planner powered by FANI AI Stylist.
 * Step 1: Trip basics → Step 2: Activities → Step 3: Day-by-day outfit result
 *
 * Sub-components and shared constants live in @/components/travel.
 */

import { useMemo, useState } from 'react'
import { notificationStore, toastStore } from '@/store/notificationStore'
import BackButton from '@/components/ui/BackButton'
import PageHeader from '@/components/ui/PageHeader'
import { FaniLoader } from '@/components/system/FaniLoader'
import { usePageState } from '@/hooks/usePageState'
import {
  AlertCircle, ArrowLeft, Bookmark, BookmarkPlus, Calendar, Check,
  CheckCircle2, ChevronRight, Loader2, Package, Plane, Plus,
  RefreshCw, Shirt, Sparkles,
} from 'lucide-react'
import Button from '@/components/ui/Button'
import Input, { Select } from '@/components/ui/Input'
import { useApp } from '@/store'
import { tripsApi } from '@/lib/api'
import { cn } from '@/lib/utils'
import type { PackingPlan, Trip, TripActivity } from '@/types'
import {
  ACTIVITY_PRESETS, BAG_SIZE_OPTS, PURPOSE_OPTIONS, TRIP_STYLE_OPTS,
  tripApiErr, type ActivityDraft,
} from '@/components/travel/constants'
import { ActivityChip } from '@/components/travel/ActivityChip'
import { DayPlanCard } from '@/components/travel/DayPlanCard'
import { DestinationInput } from '@/components/travel/DestinationInput'
import { MissingItemsPanel } from '@/components/travel/MissingItemsPanel'
import { OccasionPlanner } from '@/components/travel/OccasionPlanner'
import { PackingChecklistPanel } from '@/components/travel/PackingChecklistPanel'
import { RewearStrategyPanel } from '@/components/travel/RewearStrategyPanel'
import { SavedPlannersTab } from '@/components/travel/SavedPlannersTab'
import { SelectedActivityCard } from '@/components/travel/SelectedActivityCard'
import { StepIndicator } from '@/components/travel/StepIndicator'
import { TripSummaryBanner } from '@/components/travel/TripSummaryBanner'

// ── Main TravelPlanner page ───────────────────────────────────────────────

export default function TravelPlanner() {
  const { closetItems } = useApp()

  // Step state
  const [step, setStep] = useState<1 | 2 | 3>(1)
  const [activeTab, setActiveTab] = useState<'new' | 'occasion' | 'saved'>('new')

  // Step 1: Trip basics — persisted so form survives navigating away and back
  const [form, setForm] = usePageState('travel-form', {
    destination: '', start_date: '', end_date: '',
    purpose: 'leisure', trip_style: '', bag_size: '', notes: '',
  })
  const [formError, setFormError] = useState<string | null>(null)

  // Step 2: Activities
  const [activities, setActivities] = useState<ActivityDraft[]>([])
  const [customActivityName, setCustomActivityName] = useState('')

  // Step 3: Results
  const [trip, setTrip] = useState<Trip | null>(null)
  const [packingPlan, setPackingPlan] = useState<PackingPlan | null>(null)
  const [loading, setLoading] = useState(false)
  const [genError, setGenError] = useState<string | null>(null)
  const [planTab, setPlanTab] = useState<'days' | 'rewear' | 'checklist'>('days')
  const [packedState, setPackedState] = useState<Record<string, boolean>>({})

  // Save state
  const [savingPlanner, setSavingPlanner] = useState(false)
  const [plannerSaved, setPlannerSaved] = useState(false)
  const [saveError, setSaveError] = useState<string | null>(null)

  const tripDays = useMemo(() => {
    if (!form.start_date || !form.end_date) return 7
    return Math.max(1, Math.ceil((new Date(form.end_date).getTime() - new Date(form.start_date).getTime()) / 86_400_000))
  }, [form.start_date, form.end_date])

  // ── Step 1 → Step 2 ─────────────────────────────────────────────────────

  const handleStep1Continue = () => {
    if (!form.destination || !form.start_date || !form.end_date) {
      setFormError('Please fill in destination and travel dates.')
      return
    }
    if (new Date(form.end_date) <= new Date(form.start_date)) {
      setFormError('End date must be after start date.')
      return
    }
    setFormError(null)
    setStep(2)
    window.scrollTo({ top: 0, behavior: 'smooth' })
  }

  // ── Activity management ─────────────────────────────────────────────────

  const togglePresetActivity = (preset: typeof ACTIVITY_PRESETS[0]) => {
    const exists = activities.find(a => a.name === preset.name)
    if (exists) {
      setActivities(prev => prev.filter(a => a.name !== preset.name))
    } else {
      setActivities(prev => [...prev, {
        _id: crypto.randomUUID(),
        name: preset.name,
        day_number: null,
        date: null,
        time_of_day: preset.time_of_day as TripActivity['time_of_day'],
        formality: preset.formality as TripActivity['formality'],
        is_fixed: false,
        notes: null,
      }])
    }
  }

  const addCustomActivity = () => {
    const name = customActivityName.trim()
    if (!name) return
    setActivities(prev => [...prev, {
      _id: crypto.randomUUID(),
      name,
      day_number: null,
      date: null,
      time_of_day: null,
      formality: 'casual' as TripActivity['formality'],
      is_fixed: false,
      notes: null,
    }])
    setCustomActivityName('')
  }

  const updateActivity = (_id: string, patch: Partial<ActivityDraft>) => {
    setActivities(prev => prev.map(a => a._id === _id ? { ...a, ...patch } : a))
  }

  // ── Generate packing plan (Step 2 → Step 3) ──────────────────────────────

  const handleGenerate = async () => {
    setLoading(true)
    setGenError(null)
    setPlannerSaved(false)
    setSaveError(null)
    try {
      const acts: TripActivity[] = activities.map(({ _id: _unused, ...rest }) => rest)
      const response = await tripsApi.create({
        destination: form.destination,
        start_date: form.start_date,
        end_date: form.end_date,
        purpose: form.purpose,
        notes: form.notes || undefined,
        trip_style: form.trip_style || null,
        bag_size: form.bag_size || null,
        activities: acts,
      })
      setTrip(response.trip)
      notificationStore.push({
        channel: 'ai',
        icon: '✈️',
        title: 'Trip plan ready!',
        body: `Your packing plan for ${form.destination} is ready to review.`,
      })
      if (response.packing_plan) {
        setPackingPlan(response.packing_plan)
        // Seed packed state from checklist_state
        setPackedState(response.packing_plan.checklist_state || {})
      } else if (response.packing_error) {
        // Plan generation failed — try fetching
        if (response.trip) {
          try {
            const plan = await tripsApi.getPackingPlan(response.trip.id)
            setPackingPlan(plan)
            setPackedState(plan.checklist_state || {})
          } catch {
            setGenError('Packing plan generation failed. You can regenerate from the trip view.')
          }
        }
      }
      setStep(3)
      window.scrollTo({ top: 0, behavior: 'smooth' })
    } catch (err: unknown) {
      const msg = tripApiErr(err, 'Failed to create trip and generate plan. Please try again.')
      setGenError(msg)
      toastStore.add({ variant: 'error', icon: '✈️', title: 'Trip creation failed', body: msg })
    } finally {
      setLoading(false)
    }
  }

  // ── Checklist toggle ─────────────────────────────────────────────────────

  const handleChecklistToggle = async (key: string, val: boolean) => {
    setPackedState(prev => ({ ...prev, [key]: val }))
    if (trip) {
      try { await tripsApi.updateChecklistItem(trip.id, key, val) } catch { /* quiet */ }
    }
  }

  // ── Save planner ─────────────────────────────────────────────────────────

  const handleSavePlanner = async () => {
    if (!trip || savingPlanner || plannerSaved) return
    setSavingPlanner(true)
    setSaveError(null)
    try {
      const result = await tripsApi.savePlanner(trip.id)
      setTrip(result.trip)
      setPackingPlan(result.packing_plan)
      setPlannerSaved(true)
      notificationStore.push({
        channel: 'ai',
        icon: '📋',
        title: 'Planner saved!',
        body: `Your packing planner for ${trip.destination} has been saved.`,
      })
    } catch (err: unknown) {
      const msg = tripApiErr(err, 'Failed to save planner.')
      setSaveError(msg)
      toastStore.add({ variant: 'error', icon: '📋', title: 'Save failed', body: msg })
    } finally {
      setSavingPlanner(false)
    }
  }

  // ── Regenerate ────────────────────────────────────────────────────────────

  const handleRegenerate = async () => {
    if (!trip) return
    setLoading(true)
    setGenError(null)
    try {
      const plan = await tripsApi.regeneratePacking(trip.id)
      setPackingPlan(plan)
      setPackedState(plan.checklist_state || {})
      setPlannerSaved(false)
    } catch (err: unknown) {
      setGenError(tripApiErr(err, 'Failed to regenerate plan.'))
    } finally {
      setLoading(false)
    }
  }

  // ── Reset ─────────────────────────────────────────────────────────────────

  const handleStartOver = () => {
    setStep(1)
    setTrip(null)
    setPackingPlan(null)
    setActivities([])
    setPackedState({})
    setPlannerSaved(false)
    setSaveError(null)
    setGenError(null)
    setForm({ destination: '', start_date: '', end_date: '', purpose: 'leisure', trip_style: '', bag_size: '', notes: '' })
  }

  return (
    <div className="max-w-4xl space-y-6">
      <BackButton fallback="/dashboard" label="Back to Dashboard" />

      {/* ── Header + tabs ─────────────────────────────────────────────── */}
      <PageHeader
        icon={<Plane size={18} />}
        title="Travel Packing Planner"
        subtitle="AI-powered day-by-day outfit plans from your closet"
        stackActionsOnMobile
        actions={
          <div className="flex rounded-xl border border-slate-200 dark:border-white/10 overflow-hidden text-sm font-medium">
            <button
              onClick={() => setActiveTab('new')}
              className={`px-4 py-2 transition-colors ${activeTab === 'new' ? 'bg-brand-500 text-white' : 'bg-white dark:bg-slate-900 text-slate-600 dark:text-white/60 hover:bg-slate-50 dark:hover:bg-white/5'}`}
            >
              ✈️ Trip
            </button>
            <button
              onClick={() => setActiveTab('occasion')}
              className={`px-4 py-2 transition-colors flex items-center gap-1.5 border-l border-slate-200 dark:border-white/10 ${activeTab === 'occasion' ? 'bg-brand-500 text-white' : 'bg-white dark:bg-slate-900 text-slate-600 dark:text-white/60 hover:bg-slate-50 dark:hover:bg-white/5'}`}
            >
              🎯 Occasion
            </button>
            <button
              onClick={() => setActiveTab('saved')}
              className={`px-4 py-2 transition-colors flex items-center gap-1.5 border-l border-slate-200 dark:border-white/10 ${activeTab === 'saved' ? 'bg-brand-500 text-white' : 'bg-white dark:bg-slate-900 text-slate-600 dark:text-white/60 hover:bg-slate-50 dark:hover:bg-white/5'}`}
            >
              <Bookmark size={13} /> Saved
            </button>
          </div>
        }
      />

      {/* ── OCCASION TAB ─────────────────────────────────────────────────── */}
      {activeTab === 'occasion' && <OccasionPlanner closetItems={closetItems} />}

      {/* ── SAVED TAB ────────────────────────────────────────────────────── */}
      {activeTab === 'saved' && <SavedPlannersTab />}

      {/* ── NEW TRIP TAB ──────────────────────────────────────────────────── */}
      {activeTab === 'new' && (
        <>
          {/* Step indicator (shown during steps 1-2) */}
          {step < 3 && (
            <StepIndicator step={step} />
          )}

          {/* No closet warning */}
          {closetItems.length === 0 && step === 1 && (
            <div className="card p-5 text-center space-y-3">
              <Shirt size={28} className="mx-auto text-slate-300 dark:text-white/20" />
              <div>
                <p className="font-semibold text-slate-700 dark:text-white">Build your wardrobe first</p>
                <p className="text-sm text-slate-500 dark:text-white/40 mt-1 max-w-sm mx-auto">
                  Add items to your closet so FANI can create personalized outfit plans from your real wardrobe.
                </p>
              </div>
              <div className="flex justify-center gap-4">
                <a href="/upload" className="text-sm font-medium text-brand-600 dark:text-brand-400 hover:underline">Add Items →</a>
                <a href="/closet" className="text-sm font-medium text-slate-500 dark:text-white/40 hover:underline">View Closet</a>
              </div>
            </div>
          )}

          {/* ═══ STEP 1: TRIP DETAILS ════════════════════════════════════════ */}
          {step === 1 && (
            <div className="card p-6 space-y-5">
              <h3 className="font-semibold text-slate-800 dark:text-white">Trip Details</h3>

              {formError && (
                <div className="p-3 rounded-xl bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 text-red-700 dark:text-red-300 text-sm flex items-center gap-2">
                  <AlertCircle size={14} /> {formError}
                </div>
              )}

              <div className="grid sm:grid-cols-2 gap-4">
                <DestinationInput value={form.destination} onChange={v => setForm(f => ({ ...f, destination: v }))} />
                <Select
                  label="Trip purpose *"
                  options={PURPOSE_OPTIONS}
                  value={form.purpose}
                  onChange={e => setForm(f => ({ ...f, purpose: e.target.value }))}
                />
              </div>

              <div className="grid sm:grid-cols-2 gap-4">
                <Input label="Start date *" type="date" value={form.start_date}
                  onChange={e => setForm(f => ({ ...f, start_date: e.target.value }))}
                  leftIcon={<Calendar size={14} />} />
                <Input label="End date *" type="date" value={form.end_date}
                  onChange={e => setForm(f => ({ ...f, end_date: e.target.value }))}
                  leftIcon={<Calendar size={14} />} />
              </div>

              {/* Trip style chips */}
              <div>
                <label className="block text-xs font-semibold text-slate-700 dark:text-white/80 mb-2 uppercase tracking-wider">
                  Trip style (optional)
                </label>
                <div className="flex flex-wrap gap-2">
                  {TRIP_STYLE_OPTS.map(s => (
                    <button
                      key={s.value}
                      type="button"
                      onClick={() => setForm(f => ({ ...f, trip_style: f.trip_style === s.value ? '' : s.value }))}
                      className={cn(
                        'flex items-center gap-1.5 px-3 py-1.5 rounded-xl border text-xs font-medium transition-all',
                        form.trip_style === s.value
                          ? 'bg-brand-50 dark:bg-brand-900/30 border-brand-300 dark:border-brand-600 text-brand-700 dark:text-brand-300'
                          : 'bg-white dark:bg-white/5 border-slate-200 dark:border-white/10 text-slate-600 dark:text-slate-300 hover:border-brand-300',
                      )}
                    >
                      <span>{s.emoji}</span> {s.label}
                    </button>
                  ))}
                </div>
              </div>

              {/* Bag size */}
              <div>
                <label className="block text-xs font-semibold text-slate-700 dark:text-white/80 mb-2 uppercase tracking-wider">
                  Bag / luggage size (optional)
                </label>
                <div className="grid sm:grid-cols-2 gap-2">
                  {BAG_SIZE_OPTS.map(b => (
                    <button
                      key={b.value}
                      type="button"
                      onClick={() => setForm(f => ({ ...f, bag_size: f.bag_size === b.value ? '' : b.value }))}
                      className={cn(
                        'flex items-start gap-2.5 px-3 py-2.5 rounded-xl border text-left transition-all',
                        form.bag_size === b.value
                          ? 'bg-brand-50 dark:bg-brand-900/20 border-brand-300 dark:border-brand-600'
                          : 'bg-white dark:bg-white/5 border-slate-200 dark:border-white/10 hover:border-brand-300',
                      )}
                    >
                      <span className="text-lg">{b.label.split(' ')[0]}</span>
                      <div className="min-w-0">
                        <p className={cn('text-xs font-semibold truncate', form.bag_size === b.value ? 'text-brand-700 dark:text-brand-300' : 'text-slate-700 dark:text-slate-200')}>
                          {b.label.slice(b.label.indexOf(' ') + 1)}
                        </p>
                        <p className="text-[10px] text-slate-400 dark:text-white/30 mt-0.5">{b.desc}</p>
                      </div>
                      {form.bag_size === b.value && <Check size={13} className="text-brand-500 flex-shrink-0 ml-auto mt-0.5" />}
                    </button>
                  ))}
                </div>
              </div>

              {/* Notes */}
              <div>
                <label className="block text-xs font-semibold text-slate-700 dark:text-white/80 mb-1.5 uppercase tracking-wider">
                  Notes (optional)
                </label>
                <textarea
                  value={form.notes}
                  onChange={e => setForm(f => ({ ...f, notes: e.target.value }))}
                  placeholder="e.g. Attending a rooftop dinner, casual beach days, need formal for one night…"
                  className="w-full px-3 py-2 rounded-xl border border-slate-300 dark:border-white/10 bg-white dark:bg-slate-900 text-slate-900 dark:text-white text-sm focus:outline-none focus:ring-2 focus:ring-brand-500 resize-none"
                  rows={2}
                />
              </div>

              <div className="flex gap-3 pt-2">
                <Button
                  variant="primary"
                  onClick={handleStep1Continue}
                  disabled={!form.destination || !form.start_date || !form.end_date}
                  className="flex-1"
                  icon={<ChevronRight size={15} />}
                >
                  Continue to Activities
                </Button>
              </div>
            </div>
          )}

          {/* ═══ STEP 2: ACTIVITIES ═══════════════════════════════════════════ */}
          {step === 2 && (
            <div className="space-y-5">
              <div className="card p-6 space-y-5">
                <div className="flex items-start justify-between gap-3 flex-wrap">
                  <div>
                    <h3 className="font-semibold text-slate-800 dark:text-white">Plan Your Activities</h3>
                    <p className="text-sm text-slate-400 mt-0.5">
                      Select your planned activities so FANI can build outfit-specific plans.
                      <span className="text-brand-500 font-medium"> Optional — but the more you add, the smarter the plan.</span>
                    </p>
                  </div>
                  <button
                    type="button"
                    onClick={() => setStep(1)}
                    className="flex items-center gap-1.5 text-xs text-slate-400 hover:text-slate-600 dark:hover:text-white/60 transition-colors"
                  >
                    <ArrowLeft size={13} /> Back
                  </button>
                </div>

                {/* Activity chip grid */}
                <div>
                  <p className="text-xs font-semibold text-slate-500 dark:text-white/40 uppercase tracking-wider mb-2">
                    Common activities — tap to select
                  </p>
                  <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-2">
                    {ACTIVITY_PRESETS.map(preset => (
                      <ActivityChip
                        key={preset.id}
                        preset={preset}
                        selected={activities.some(a => a.name === preset.name)}
                        onClick={() => togglePresetActivity(preset)}
                      />
                    ))}
                  </div>
                </div>

                {/* Custom activity input */}
                <div>
                  <p className="text-xs font-semibold text-slate-500 dark:text-white/40 uppercase tracking-wider mb-2">
                    Add custom activity
                  </p>
                  <div className="flex gap-2">
                    <input
                      type="text"
                      value={customActivityName}
                      onChange={e => setCustomActivityName(e.target.value)}
                      onKeyDown={e => e.key === 'Enter' && addCustomActivity()}
                      placeholder="e.g. Cooking class, Wine tour, Yoga retreat…"
                      className="flex-1 px-3 py-2 rounded-xl border border-slate-300 dark:border-white/10 bg-white dark:bg-slate-900 text-sm text-slate-900 dark:text-white focus:outline-none focus:ring-2 focus:ring-brand-500"
                    />
                    <Button
                      variant="secondary"
                      onClick={addCustomActivity}
                      disabled={!customActivityName.trim()}
                      icon={<Plus size={14} />}
                    >
                      Add
                    </Button>
                  </div>
                </div>
              </div>

              {/* Selected activities with inline editing */}
              {activities.length > 0 && (
                <div className="card p-4 space-y-3">
                  <div className="flex items-center justify-between">
                    <p className="text-sm font-semibold text-slate-700 dark:text-white">
                      {activities.length} activit{activities.length === 1 ? 'y' : 'ies'} selected
                    </p>
                    <p className="text-xs text-slate-400">Tap ▾ to set day, time, and dress code</p>
                  </div>
                  {activities.map(act => (
                    <SelectedActivityCard
                      key={act._id}
                      activity={act}
                      tripDays={tripDays}
                      onUpdate={patch => updateActivity(act._id, patch)}
                      onRemove={() => setActivities(prev => prev.filter(a => a._id !== act._id))}
                    />
                  ))}
                </div>
              )}

              {/* Generate button */}
              {genError && (
                <div className="p-3 rounded-xl bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 text-red-700 dark:text-red-300 text-sm flex items-center gap-2">
                  <AlertCircle size={14} /> {genError}
                </div>
              )}

              <div className="flex flex-col sm:flex-row gap-3">
                <Button
                  variant="primary"
                  onClick={handleGenerate}
                  disabled={loading}
                  className="flex-1"
                  icon={loading ? <Loader2 size={15} className="animate-spin" /> : <Sparkles size={15} />}
                >
                  {loading
                    ? `Generating plan… this may take up to ${activities.length > 5 ? '60' : '30'}s`
                    : activities.length > 0
                      ? `Generate Plan with ${activities.length} Activit${activities.length === 1 ? 'y' : 'ies'}`
                      : 'Generate Packing Plan'}
                </Button>
                {activities.length === 0 && (
                  <p className="text-xs text-slate-400 text-center sm:text-left self-center">
                    No activities? That's fine — FANI will use your trip purpose and destination.
                  </p>
                )}
              </div>
            </div>
          )}

          {/* ═══ STEP 3: PACKING PLAN RESULT ═════════════════════════════════ */}
          {step === 3 && trip && (
            <div className="space-y-4">
              {/* Back + regenerate */}
              <div className="flex items-center gap-3 flex-wrap">
                <Button variant="ghost" onClick={handleStartOver} className="flex items-center gap-2">
                  <ArrowLeft size={15} /> New Trip
                </Button>
                <Button
                  variant="secondary"
                  onClick={handleRegenerate}
                  disabled={loading}
                  className="flex items-center gap-2 ml-auto"
                  icon={loading ? <Loader2 size={13} className="animate-spin" /> : <RefreshCw size={13} />}
                >
                  Regenerate Plan
                </Button>
              </div>

              {/* Trip summary */}
              {packingPlan && <TripSummaryBanner trip={trip} plan={packingPlan} />}

              {/* Loading state */}
              {loading && (
                <div className="card p-8 flex justify-center">
                  <FaniLoader
                    messages={[
                      'Reading your closet…',
                      'Checking the weather…',
                      'Planning outfits by activity…',
                      'Packing your bag…',
                      'Almost there…',
                    ]}
                    subline="FANI is building your travel wardrobe"
                  />
                </div>
              )}

              {genError && !loading && !packingPlan && (
                <div className="card p-4 bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 text-red-700 dark:text-red-300 text-sm flex items-center gap-2">
                  <AlertCircle size={14} /> {genError}
                </div>
              )}

              {packingPlan && !loading && (
                <>
                  {/* Save CTA */}
                  <div className="rounded-2xl border border-brand-200/60 dark:border-brand-500/20 bg-gradient-to-r from-brand-500/[0.07] to-brand-600/[0.07] p-4">
                    {plannerSaved ? (
                      <div className="flex items-center justify-between gap-4 flex-wrap">
                        <div className="flex items-center gap-3">
                          <div className="w-9 h-9 rounded-full bg-emerald-100 dark:bg-emerald-900/40 flex items-center justify-center">
                            <CheckCircle2 size={18} className="text-emerald-600 dark:text-emerald-400" />
                          </div>
                          <div>
                            <p className="font-semibold text-slate-800 dark:text-white text-sm">Planner saved ✓</p>
                            <p className="text-xs text-slate-500 dark:text-white/40 mt-0.5">Available in Saved Planners tab anytime</p>
                          </div>
                        </div>
                        <button
                          onClick={() => setActiveTab('saved')}
                          className="flex items-center gap-1.5 text-sm font-medium text-brand-600 dark:text-brand-400 hover:underline"
                        >
                          View Saved <ChevronRight size={14} />
                        </button>
                      </div>
                    ) : (
                      <div className="flex items-center justify-between gap-4 flex-wrap">
                        <div className="flex items-center gap-3">
                          <div className="w-9 h-9 rounded-full bg-brand-100 dark:bg-brand-900/40 flex items-center justify-center">
                            <BookmarkPlus size={18} className="text-brand-600 dark:text-brand-400" />
                          </div>
                          <div>
                            <p className="font-semibold text-slate-800 dark:text-white text-sm">Save this planner</p>
                            <p className="text-xs text-slate-500 dark:text-white/40 mt-0.5">Persist outfits + checklist — access after logging back in</p>
                          </div>
                        </div>
                        <div className="flex flex-col items-end gap-1 flex-shrink-0">
                          <Button variant="primary" onClick={handleSavePlanner} disabled={savingPlanner}
                            icon={savingPlanner ? <Loader2 size={13} className="animate-spin" /> : <BookmarkPlus size={13} />}>
                            {savingPlanner ? 'Saving…' : 'Save Planner'}
                          </Button>
                          {saveError && <p className="text-xs text-red-500 flex items-center gap-1"><AlertCircle size={11} />{saveError}</p>}
                        </div>
                      </div>
                    )}
                  </div>

                  {/* Tab bar */}
                  <div className="flex gap-1 p-1 rounded-xl bg-slate-100 dark:bg-white/[0.06] self-start overflow-x-auto">
                    {([
                      { id: 'days', label: '📅 Day Plans', count: packingPlan.day_plans_rich?.length ?? 0 },
                      { id: 'rewear', label: '🔄 Rewear Strategy', count: packingPlan.rewear_strategy?.length ?? 0 },
                      { id: 'checklist', label: '✅ Packing Checklist', count: packingPlan.packing_checklist?.length ?? 0 },
                    ] as const).map(tab => (
                      <button
                        key={tab.id}
                        onClick={() => setPlanTab(tab.id)}
                        className={cn(
                          'flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold transition-all whitespace-nowrap',
                          planTab === tab.id
                            ? 'bg-white dark:bg-white/[0.12] text-slate-800 dark:text-white shadow-sm'
                            : 'text-slate-500 dark:text-slate-400 hover:text-slate-700 dark:hover:text-white/60',
                        )}
                      >
                        {tab.label}
                        {tab.count > 0 && (
                          <span className={cn(
                            'text-[10px] font-bold px-1.5 py-0.5 rounded-full',
                            planTab === tab.id ? 'bg-brand-100 dark:bg-brand-900/40 text-brand-600 dark:text-brand-400' : 'bg-slate-200 dark:bg-white/10 text-slate-500 dark:text-white/30',
                          )}>
                            {tab.count}
                          </span>
                        )}
                      </button>
                    ))}
                  </div>

                  {/* ── Day Plans Tab ──────────────────────────────────────── */}
                  {planTab === 'days' && (
                    <div className="space-y-3">
                      {(packingPlan.day_plans_rich ?? []).length > 0
                        ? packingPlan.day_plans_rich.map(day => (
                            <DayPlanCard key={day.day_number} day={day} />
                          ))
                        : (
                          <div className="card p-8 text-center text-slate-400 dark:text-white/30 text-sm">
                            <Package size={28} className="mx-auto mb-3 opacity-40" />
                            Day-by-day outfit plans are being generated. Regenerate if this persists.
                          </div>
                        )
                      }
                      {/* Missing items */}
                      {packingPlan.you_might_still_need.length > 0 && (
                        <MissingItemsPanel items={packingPlan.you_might_still_need} />
                      )}
                    </div>
                  )}

                  {/* ── Rewear Strategy Tab ────────────────────────────────── */}
                  {planTab === 'rewear' && (
                    <RewearStrategyPanel items={packingPlan.rewear_strategy ?? []} />
                  )}

                  {/* ── Checklist Tab ──────────────────────────────────────── */}
                  {planTab === 'checklist' && (
                    <PackingChecklistPanel
                      items={packingPlan.packing_checklist ?? []}
                      packedState={packedState}
                      onToggle={handleChecklistToggle}
                    />
                  )}
                </>
              )}
            </div>
          )}
        </>
      )}
    </div>
  )
}
