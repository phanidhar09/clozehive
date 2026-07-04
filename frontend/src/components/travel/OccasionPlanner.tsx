import { useState } from 'react'
import {
  AlertCircle, ArrowLeft, Calendar, Check, Loader2,
  MapPin, Package, Shirt, Sparkles, Star,
} from 'lucide-react'
import Button from '@/components/ui/Button'
import Input from '@/components/ui/Input'
import { FaniLoader } from '@/components/system/FaniLoader'
import { tripsApi } from '@/lib/api'
import { cn } from '@/lib/utils'
import type { PackingPlan, Trip, TripActivity } from '@/types'
import { FORMALITY_OPTS, TIME_OF_DAY_OPTS, tripApiErr } from './constants'
import { DayPlanCard } from './DayPlanCard'
import { MissingItemsPanel } from './MissingItemsPanel'

// ── Occasion types ────────────────────────────────────────────────────────

interface OccasionType {
  id: string
  emoji: string
  label: string
  desc: string
  formality: TripActivity['formality']
  time_of_day: TripActivity['time_of_day']
  purpose: string
  dressCodeHint: string
  notesPlaceholder: string
}

const OCCASION_TYPES: OccasionType[] = [
  {
    id: 'wedding',
    emoji: '💒',
    label: 'Wedding (Guest)',
    desc: 'Ceremony + reception, semi-formal to formal',
    formality: 'formal',
    time_of_day: 'afternoon',
    purpose: 'formal',
    dressCodeHint: 'Cocktail attire or formal. Avoid white/ivory. Floor-length or midi typically safe.',
    notesPlaceholder: 'Garden ceremony, outdoor reception, summer. I want to stand out but not upstage the bride.',
  },
  {
    id: 'interview',
    emoji: '💼',
    label: 'Job Interview',
    desc: 'Make a confident first impression',
    formality: 'business',
    time_of_day: 'morning',
    purpose: 'business',
    dressCodeHint: 'Business professional or smart casual depending on industry. Polished, minimal distractions.',
    notesPlaceholder: 'Startup company, creative industry, in-person interview.',
  },
  {
    id: 'first_date',
    emoji: '💖',
    label: 'First Date',
    desc: 'Confident, stylish, true to yourself',
    formality: 'smart_casual',
    time_of_day: 'evening',
    purpose: 'leisure',
    dressCodeHint: 'Smart casual — put-together but relaxed. Show your personality.',
    notesPlaceholder: 'Rooftop restaurant, warm evening, I want to look effortless but polished.',
  },
  {
    id: 'night_out',
    emoji: '🎉',
    label: 'Night Out',
    desc: 'Dinner, bars or clubs with friends',
    formality: 'smart_casual',
    time_of_day: 'night',
    purpose: 'leisure',
    dressCodeHint: 'Elevated casual to smart. Go bold if that\'s your vibe.',
    notesPlaceholder: 'Dinner then dancing. I want to look great but still be comfortable.',
  },
  {
    id: 'formal_event',
    emoji: '🥂',
    label: 'Formal Event',
    desc: 'Gala, award night, or black-tie occasion',
    formality: 'formal',
    time_of_day: 'evening',
    purpose: 'formal',
    dressCodeHint: 'Formal or black tie. Floor-length gown or sharp tuxedo. Dress to impress.',
    notesPlaceholder: 'Charity gala at a hotel ballroom. Want to look elegant and polished.',
  },
  // Sentinel — triggers custom input UI, not passed to the API directly
  {
    id: 'custom',
    emoji: '✏️',
    label: 'Something else',
    desc: 'Describe your own occasion',
    formality: 'smart_casual',
    time_of_day: 'evening',
    purpose: 'leisure',
    dressCodeHint: '',
    notesPlaceholder: 'Describe the event, vibe, venue, and any dress code details.',
  },
]

// ── Occasion Planner ──────────────────────────────────────────────────────

interface OccForm {
  eventDate: string
  venueCity: string
  notes: string
  // custom-occasion fields
  customLabel: string
  customFormality: TripActivity['formality']
  customTimeOfDay: TripActivity['time_of_day']
}

export function OccasionPlanner({ closetItems }: { closetItems: { id: string }[] }) {
  const today = new Date().toISOString().split('T')[0]

  const [selected, setSelected] = useState<OccasionType | null>(null)
  const [form, setForm] = useState<OccForm>({
    eventDate: '', venueCity: '', notes: '',
    customLabel: '', customFormality: 'smart_casual', customTimeOfDay: 'evening',
  })
  const [formError, setFormError] = useState<string | null>(null)
  const [loading, setLoading]     = useState(false)
  const [genError, setGenError]   = useState<string | null>(null)
  const [trip, setTrip]           = useState<Trip | null>(null)
  const [plan, setPlan]           = useState<PackingPlan | null>(null)
  const [showResult, setShowResult] = useState(false)

  const isCustom = selected?.id === 'custom'

  // Resolved values — use custom fields when the custom card is active
  const resolvedLabel    = isCustom ? form.customLabel.trim()   : selected?.label      ?? ''
  const resolvedFormality = isCustom ? form.customFormality      : selected?.formality  ?? 'smart_casual'
  const resolvedTimeOfDay = isCustom ? form.customTimeOfDay      : selected?.time_of_day ?? 'evening'
  const resolvedPurpose  = isCustom ? 'leisure'                 : selected?.purpose    ?? 'leisure'
  const resolvedHint     = isCustom ? ''                        : selected?.dressCodeHint ?? ''

  const handleGenerate = async () => {
    if (!selected) { setFormError('Pick an occasion first.'); return }
    if (isCustom && !form.customLabel.trim()) { setFormError('Give your occasion a name.'); return }
    setFormError(null)
    setGenError(null)
    setLoading(true)
    const eventDate = form.eventDate || today

    const contextNotes = [
      `Occasion: ${resolvedLabel}.`,
      resolvedHint,
      form.notes ? `User context: ${form.notes}` : '',
      'This is a single-event outfit request, not a multi-day trip.',
      'Build one complete outfit. Prioritise items already in the wardrobe.',
      'If key items are missing, call them out as things to buy or borrow.',
    ].filter(Boolean).join(' ')

    try {
      const res = await tripsApi.create({
        destination: form.venueCity.trim() || 'Local Event',
        start_date:  eventDate,
        end_date:    eventDate,
        purpose:     resolvedPurpose,
        notes:       contextNotes,
        trip_style:  null,
        bag_size:    null,
        activities:  [{
          name:        resolvedLabel,
          day_number:  1,
          date:        null,
          time_of_day: resolvedTimeOfDay,
          formality:   resolvedFormality,
          is_fixed:    true,
          notes:       form.notes || null,
        }],
      })
      setTrip(res.trip)
      let p = res.packing_plan ?? null
      if (!p && res.trip) {
        try { p = await tripsApi.getPackingPlan(res.trip.id) } catch { /* use null */ }
      }
      setPlan(p)
      setShowResult(true)
      window.scrollTo({ top: 0, behavior: 'smooth' })
    } catch (err) {
      setGenError(tripApiErr(err, 'Failed to generate outfit. Please try again.'))
    } finally {
      setLoading(false)
    }
  }

  const handleReset = () => {
    setSelected(null)
    setForm({ eventDate: '', venueCity: '', notes: '', customLabel: '', customFormality: 'smart_casual', customTimeOfDay: 'evening' })
    setPlan(null)
    setTrip(null)
    setGenError(null)
    setShowResult(false)
  }

  // ── Result view ────────────────────────────────────────────────────────────
  if (showResult && trip) {
    return (
      <div className="space-y-5">
        <button
          onClick={handleReset}
          className="flex items-center gap-1.5 text-sm text-slate-500 hover:text-slate-700 dark:hover:text-white/70 transition-colors"
        >
          <ArrowLeft size={15} /> Try another occasion
        </button>

        {/* Occasion summary */}
        {selected && (
          <div className="rounded-2xl border border-brand-200/60 dark:border-brand-500/20 bg-gradient-to-br from-brand-500/[0.06] to-transparent p-4 space-y-2">
            <div className="flex items-center gap-3">
              <span className="text-3xl">{selected.emoji}</span>
              <div>
                <h3 className="font-display font-bold text-lg text-slate-800 dark:text-white leading-tight">
                  {resolvedLabel || selected.label}
                </h3>
                <p className="text-sm text-slate-500 dark:text-white/40">
                  {form.eventDate
                    ? new Date(form.eventDate + 'T00:00:00').toLocaleDateString(undefined, { weekday: 'long', month: 'long', day: 'numeric' })
                    : 'Today'}
                  {form.venueCity ? ` · ${form.venueCity}` : ''}
                </p>
              </div>
            </div>
            {resolvedHint && (
              <div className="flex items-start gap-2 text-sm text-brand-700 dark:text-brand-300 bg-brand-50/60 dark:bg-brand-900/20 rounded-xl px-3 py-2 border border-brand-200/50 dark:border-brand-700/30">
                <Star size={13} className="text-brand-500 flex-shrink-0 mt-0.5" />
                {resolvedHint}
              </div>
            )}
            {plan?.trip_style_direction && (
              <div className="flex items-start gap-2 text-sm text-slate-600 dark:text-white/60 pt-1">
                <Sparkles size={13} className="text-brand-500 flex-shrink-0 mt-0.5" />
                {plan.trip_style_direction}
              </div>
            )}
          </div>
        )}

        {/* Loading */}
        {loading && (
          <div className="card p-8">
            <FaniLoader
              size="md"
              messages={['Scanning your closet…', 'Matching the dress code…', 'Styling the look…']}
              subline="FANI is finding your perfect outfit"
            />
          </div>
        )}

        {/* Error */}
        {genError && !loading && (
          <div className="card p-4 bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 text-red-700 dark:text-red-300 text-sm flex items-center gap-2">
            <AlertCircle size={14} /> {genError}
          </div>
        )}

        {/* Outfit plan */}
        {plan && !loading && (
          <div className="space-y-3">
            {(plan.day_plans_rich ?? []).length > 0
              ? plan.day_plans_rich.map(day => (
                  <DayPlanCard key={day.day_number} day={day} />
                ))
              : (
                <div className="card p-8 text-center text-slate-400 dark:text-white/30 text-sm">
                  <Package size={28} className="mx-auto mb-3 opacity-40" />
                  No outfit plan was returned. Try regenerating.
                </div>
              )
            }
            {(plan.you_might_still_need ?? []).length > 0 && (
              <MissingItemsPanel items={plan.you_might_still_need} />
            )}
          </div>
        )}
      </div>
    )
  }

  // ── Picker + form ──────────────────────────────────────────────────────────
  return (
    <div className="space-y-5">

      {/* Empty closet notice */}
      {closetItems.length === 0 && (
        <div className="card p-5 text-center space-y-3">
          <Shirt size={28} className="mx-auto text-slate-300 dark:text-white/20" />
          <div>
            <p className="font-semibold text-slate-700 dark:text-white">Your closet is empty</p>
            <p className="text-sm text-slate-500 dark:text-white/40 mt-1">
              Add items so FANI can recommend outfits from what you actually own.
            </p>
          </div>
          <a href="/upload" className="inline-block text-sm font-medium text-brand-600 dark:text-brand-400 hover:underline">
            Add Items →
          </a>
        </div>
      )}

      <div className="card p-6 space-y-5">
        <div>
          <h3 className="font-semibold text-slate-800 dark:text-white">Choose Your Occasion</h3>
          <p className="text-sm text-slate-400 dark:text-white/40 mt-0.5">
            FANI will pick a complete outfit from your closet for this specific event.
          </p>
        </div>

        {formError && (
          <div className="p-3 rounded-xl bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 text-red-700 dark:text-red-300 text-sm flex items-center gap-2">
            <AlertCircle size={14} /> {formError}
          </div>
        )}

        {/* Occasion grid */}
        <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-2.5">
          {OCCASION_TYPES.map(occ => (
            <button
              key={occ.id}
              type="button"
              onClick={() => setSelected(prev => prev?.id === occ.id ? null : occ)}
              className={cn(
                'relative flex flex-col items-start gap-1.5 p-3 rounded-xl border text-left transition-all',
                selected?.id === occ.id
                  ? 'bg-brand-50 dark:bg-brand-900/30 border-brand-400 dark:border-brand-600 shadow-sm'
                  : 'bg-white dark:bg-white/5 border-slate-200 dark:border-white/10 hover:border-brand-300 dark:hover:border-brand-700',
              )}
            >
              {selected?.id === occ.id && (
                <span className="absolute top-2 right-2">
                  <Check size={11} className="text-brand-500" />
                </span>
              )}
              <span className="text-2xl">{occ.emoji}</span>
              <div>
                <p className={cn(
                  'text-sm font-semibold leading-tight',
                  selected?.id === occ.id ? 'text-brand-700 dark:text-brand-300' : 'text-slate-800 dark:text-white',
                )}>
                  {occ.label}
                </p>
                <p className="text-[10px] text-slate-400 dark:text-white/30 mt-0.5 leading-snug line-clamp-2">
                  {occ.desc}
                </p>
              </div>
            </button>
          ))}
        </div>

        {/* Dress code hint — preset only */}
        {selected && !isCustom && (
          <div className="flex items-start gap-2 text-sm text-brand-700 dark:text-brand-300 bg-brand-50 dark:bg-brand-900/20 rounded-xl px-3 py-2.5 border border-brand-200 dark:border-brand-700/40">
            <Star size={14} className="text-brand-500 flex-shrink-0 mt-0.5" />
            <span>{selected.dressCodeHint}</span>
          </div>
        )}
      </div>

      {/* Context form — shown after picking an occasion */}
      {selected && (
        <div className="card p-6 space-y-4">
          <h3 className="font-semibold text-slate-800 dark:text-white text-sm">
            {isCustom ? 'Describe Your Occasion' : 'Event Details'}
            {!isCustom && <span className="ml-1 text-xs font-normal text-slate-400">(all optional)</span>}
          </h3>

          {/* Custom occasion fields */}
          {isCustom && (
            <div className="space-y-3">
              <div>
                <label className="block text-xs font-semibold text-slate-700 dark:text-white/80 mb-1.5 uppercase tracking-wider">
                  Occasion name *
                </label>
                <input
                  type="text"
                  value={form.customLabel}
                  onChange={e => setForm(f => ({ ...f, customLabel: e.target.value }))}
                  placeholder="e.g. Engagement party, Retirement dinner, Gallery opening…"
                  className="w-full px-3 py-2.5 rounded-xl border border-slate-300 dark:border-white/10 bg-white dark:bg-slate-900 text-slate-900 dark:text-white text-sm focus:outline-none focus:ring-2 focus:ring-brand-500"
                />
              </div>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                <div>
                  <label className="block text-xs font-semibold text-slate-700 dark:text-white/80 mb-1.5 uppercase tracking-wider">
                    Dress code
                  </label>
                  <select
                    value={form.customFormality ?? 'smart_casual'}
                    onChange={e => setForm(f => ({ ...f, customFormality: e.target.value as TripActivity['formality'] }))}
                    className="w-full px-3 py-2.5 rounded-xl border border-slate-300 dark:border-white/10 bg-white dark:bg-slate-900 text-slate-900 dark:text-white text-sm focus:outline-none focus:ring-2 focus:ring-brand-500 appearance-none"
                  >
                    {FORMALITY_OPTS.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
                  </select>
                </div>
                <div>
                  <label className="block text-xs font-semibold text-slate-700 dark:text-white/80 mb-1.5 uppercase tracking-wider">
                    Time of day
                  </label>
                  <select
                    value={form.customTimeOfDay ?? 'evening'}
                    onChange={e => setForm(f => ({ ...f, customTimeOfDay: e.target.value as TripActivity['time_of_day'] }))}
                    className="w-full px-3 py-2.5 rounded-xl border border-slate-300 dark:border-white/10 bg-white dark:bg-slate-900 text-slate-900 dark:text-white text-sm focus:outline-none focus:ring-2 focus:ring-brand-500 appearance-none"
                  >
                    {TIME_OF_DAY_OPTS.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
                  </select>
                </div>
              </div>
            </div>
          )}

          <div className="grid sm:grid-cols-2 gap-4">
            <Input
              label="Event date"
              type="date"
              value={form.eventDate}
              onChange={e => setForm(f => ({ ...f, eventDate: e.target.value }))}
              leftIcon={<Calendar size={14} />}
            />
            <Input
              label="City / venue"
              value={form.venueCity}
              onChange={e => setForm(f => ({ ...f, venueCity: e.target.value }))}
              placeholder="e.g. London, rooftop venue, church"
              leftIcon={<MapPin size={14} />}
            />
          </div>

          <div>
            <label className="block text-xs font-semibold text-slate-700 dark:text-white/80 mb-1.5 uppercase tracking-wider">
              Notes for FANI <span className="font-normal text-slate-400 normal-case">(optional)</span>
            </label>
            <textarea
              value={form.notes}
              onChange={e => setForm(f => ({ ...f, notes: e.target.value }))}
              placeholder={isCustom ? selected.notesPlaceholder : selected.notesPlaceholder}
              className="w-full px-3 py-2 rounded-xl border border-slate-300 dark:border-white/10 bg-white dark:bg-slate-900 text-slate-900 dark:text-white text-sm focus:outline-none focus:ring-2 focus:ring-brand-500 resize-none"
              rows={2}
            />
          </div>

          {genError && (
            <div className="p-3 rounded-xl bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 text-red-700 dark:text-red-300 text-sm flex items-center gap-2">
              <AlertCircle size={14} /> {genError}
            </div>
          )}

          <Button
            variant="primary"
            onClick={handleGenerate}
            disabled={loading || (isCustom && !form.customLabel.trim())}
            className="w-full"
            icon={loading ? <Loader2 size={15} className="animate-spin" /> : <Sparkles size={15} />}
          >
            {loading ? 'Finding your outfit…' : `Find My ${isCustom ? (form.customLabel.trim() || 'Custom') : selected.label} Outfit`}
          </Button>
        </div>
      )}
    </div>
  )
}
