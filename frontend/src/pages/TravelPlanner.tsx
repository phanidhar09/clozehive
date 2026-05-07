import { useState, useRef, useEffect } from 'react'
import {
  Plane, Calendar, MapPin, Loader2, ArrowLeft, CheckCircle2,
  ShoppingCart, Shirt, Star, BookmarkCheck, BookmarkPlus, Bookmark,
  ChevronRight, AlertCircle,
} from 'lucide-react'
import Button from '@/components/ui/Button'
import Input, { Select } from '@/components/ui/Input'
import Badge from '@/components/ui/Badge'
import GlassCard from '@/components/ui/GlassCard'
import { useApp } from '@/store'
import { tripsApi, outfitsApi } from '@/lib/api'
import { useAsyncError } from '@/hooks/useAsyncError'
import type { DailyOutfitPlan, PackingItem, PackingItemDetailed, PackingItemNeeded, PackingPlan, Trip } from '@/types'

const PURPOSE_OPTIONS = [
  { value: 'leisure', label: '🌴 Leisure / Holiday' },
  { value: 'business', label: '💼 Business' },
  { value: 'beach', label: '🏖️ Beach / Resort' },
  { value: 'formal', label: '🎩 Formal Event' },
  { value: 'adventure', label: '🏔️ Adventure / Hiking' },
]

const DESTINATIONS = [
  // Asia
  'Tokyo, Japan', 'Kyoto, Japan', 'Osaka, Japan', 'Seoul, South Korea', 'Busan, South Korea',
  'Bangkok, Thailand', 'Chiang Mai, Thailand', 'Phuket, Thailand', 'Koh Samui, Thailand',
  'Bali, Indonesia', 'Jakarta, Indonesia', 'Singapore', 'Kuala Lumpur, Malaysia',
  'Ho Chi Minh City, Vietnam', 'Hanoi, Vietnam', 'Hoi An, Vietnam', 'Da Nang, Vietnam',
  'Manila, Philippines', 'Cebu, Philippines', 'Boracay, Philippines',
  'Mumbai, India', 'Delhi, India', 'Bangalore, India', 'Goa, India', 'Jaipur, India',
  'Colombo, Sri Lanka', 'Kathmandu, Nepal', 'Dhaka, Bangladesh',
  'Beijing, China', 'Shanghai, China', 'Hong Kong', 'Macau', 'Guangzhou, China',
  'Taipei, Taiwan', 'Yangon, Myanmar', 'Phnom Penh, Cambodia', 'Siem Reap, Cambodia',
  'Vientiane, Laos', 'Ulaanbaatar, Mongolia', 'Almaty, Kazakhstan',
  'Dubai, UAE', 'Abu Dhabi, UAE', 'Doha, Qatar', 'Riyadh, Saudi Arabia',
  'Istanbul, Turkey', 'Ankara, Turkey', 'Beirut, Lebanon', 'Amman, Jordan', 'Tel Aviv, Israel',
  // Europe
  'Paris, France', 'Nice, France', 'Lyon, France', 'Marseille, France',
  'London, UK', 'Edinburgh, UK', 'Manchester, UK', 'Dublin, Ireland',
  'Rome, Italy', 'Milan, Italy', 'Florence, Italy', 'Venice, Italy', 'Naples, Italy',
  'Barcelona, Spain', 'Madrid, Spain', 'Seville, Spain', 'Valencia, Spain', 'Ibiza, Spain',
  'Lisbon, Portugal', 'Porto, Portugal', 'Faro, Portugal',
  'Amsterdam, Netherlands', 'Brussels, Belgium', 'Luxembourg City',
  'Berlin, Germany', 'Munich, Germany', 'Hamburg, Germany', 'Frankfurt, Germany',
  'Vienna, Austria', 'Salzburg, Austria', 'Zurich, Switzerland', 'Geneva, Switzerland', 'Bern, Switzerland',
  'Prague, Czech Republic', 'Budapest, Hungary', 'Warsaw, Poland', 'Krakow, Poland',
  'Athens, Greece', 'Santorini, Greece', 'Mykonos, Greece', 'Thessaloniki, Greece',
  'Stockholm, Sweden', 'Oslo, Norway', 'Copenhagen, Denmark', 'Helsinki, Finland', 'Reykjavik, Iceland',
  'Moscow, Russia', 'St. Petersburg, Russia', 'Kyiv, Ukraine',
  'Bucharest, Romania', 'Sofia, Bulgaria', 'Zagreb, Croatia', 'Dubrovnik, Croatia', 'Split, Croatia',
  'Ljubljana, Slovenia', 'Belgrade, Serbia', 'Sarajevo, Bosnia',
  // North America
  'New York, USA', 'Los Angeles, USA', 'Chicago, USA', 'Houston, USA', 'Miami, USA',
  'San Francisco, USA', 'Seattle, USA', 'Boston, USA', 'Washington DC, USA',
  'Las Vegas, USA', 'Orlando, USA', 'Nashville, USA', 'Austin, USA', 'Denver, USA',
  'Phoenix, USA', 'Portland, USA', 'Atlanta, USA', 'Dallas, USA', 'San Diego, USA',
  'Toronto, Canada', 'Vancouver, Canada', 'Montreal, Canada', 'Calgary, Canada',
  'Mexico City, Mexico', 'Cancun, Mexico', 'Guadalajara, Mexico', 'Playa del Carmen, Mexico',
  'Havana, Cuba', 'San Juan, Puerto Rico',
  // South America
  'Buenos Aires, Argentina', 'São Paulo, Brazil', 'Rio de Janeiro, Brazil', 'Brasília, Brazil',
  'Lima, Peru', 'Cusco, Peru', 'Machu Picchu, Peru', 'Bogotá, Colombia', 'Medellín, Colombia',
  'Cartagena, Colombia', 'Santiago, Chile', 'Valparaíso, Chile', 'Quito, Ecuador',
  'Montevideo, Uruguay', 'La Paz, Bolivia', 'Caracas, Venezuela', 'Asunción, Paraguay',
  // Africa
  'Cairo, Egypt', 'Marrakech, Morocco', 'Casablanca, Morocco', 'Tunis, Tunisia',
  'Nairobi, Kenya', 'Cape Town, South Africa', 'Johannesburg, South Africa', 'Durban, South Africa',
  'Lagos, Nigeria', 'Accra, Ghana', 'Addis Ababa, Ethiopia', 'Dar es Salaam, Tanzania',
  'Zanzibar, Tanzania', 'Kigali, Rwanda', 'Kampala, Uganda',
  // Oceania
  'Sydney, Australia', 'Melbourne, Australia', 'Brisbane, Australia', 'Perth, Australia',
  'Auckland, New Zealand', 'Wellington, New Zealand', 'Queenstown, New Zealand',
  'Fiji', 'Maldives', 'Papeete, French Polynesia',
]

// ── Destination combobox ──────────────────────────────────────────────────────

function DestinationInput({ value, onChange }: { value: string; onChange: (v: string) => void }) {
  const [open, setOpen] = useState(false)
  const [query, setQuery] = useState(value)
  const wrapRef = useRef<HTMLDivElement>(null)

  const matches = query.length >= 1
    ? DESTINATIONS.filter(d => d.toLowerCase().includes(query.toLowerCase())).slice(0, 8)
    : []

  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (wrapRef.current && !wrapRef.current.contains(e.target as Node)) setOpen(false)
    }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [])

  const select = (dest: string) => {
    setQuery(dest)
    onChange(dest)
    setOpen(false)
  }

  return (
    <div ref={wrapRef} className="relative">
      <label className="block text-xs font-semibold text-slate-700 dark:text-white/80 mb-1.5 uppercase tracking-wider">
        Destination *
      </label>
      <div className="relative">
        <MapPin size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400 pointer-events-none" />
        <input
          type="text"
          value={query}
          placeholder="e.g. Paris, Tokyo, Bali…"
          onChange={e => { setQuery(e.target.value); onChange(e.target.value); setOpen(true) }}
          onFocus={() => setOpen(true)}
          className="w-full pl-9 pr-3 py-2 rounded-lg border border-slate-300 dark:border-white/10 bg-white dark:bg-slate-900 text-slate-900 dark:text-white text-sm focus:outline-none focus:ring-2 focus:ring-brand-500 dark:focus:ring-brand-400"
        />
      </div>
      {open && matches.length > 0 && (
        <ul className="absolute z-50 mt-1 w-full bg-white dark:bg-slate-800 border border-slate-200 dark:border-white/10 rounded-xl shadow-lg overflow-hidden max-h-60 overflow-y-auto">
          {matches.map(dest => (
            <li
              key={dest}
              onMouseDown={() => select(dest)}
              className="flex items-center gap-2 px-3 py-2 text-sm cursor-pointer text-slate-800 dark:text-white hover:bg-brand-50 dark:hover:bg-brand-500/10"
            >
              <MapPin size={12} className="text-slate-400 flex-shrink-0" />
              {dest}
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}

// ── Packing result display (shared between new + saved planner views) ─────────

function PackingResult({
  packingList,
  closetItems,
  packedItems,
  setPackedItems,
  savedOutfits,
  savingOutfit,
  onSaveOutfit,
}: {
  packingList: PackingPlan
  closetItems: { id: string; name: string }[]
  packedItems: Record<string, boolean>
  setPackedItems: React.Dispatch<React.SetStateAction<Record<string, boolean>>>
  savedOutfits: Record<string, boolean>
  savingOutfit: Record<string, boolean>
  onSaveOutfit: (day: DailyOutfitPlan) => void
}) {
  const packingItems = [...(packingList.packing_list ?? []), ...(packingList.missing_items ?? [])]
  const groupedPacking = packingItems.reduce<Record<string, PackingItem[]>>((acc, item) => {
    const category = item.category || 'Other'
    acc[category] = acc[category] ?? []
    acc[category].push(item)
    return acc
  }, {})

  return (
    <div className="space-y-4">
      {packingList.summary && (
        <p className="text-sm text-slate-500 dark:text-white/50">{packingList.summary}</p>
      )}

      {packingList.closet_hint && (
        <div className="rounded-xl border border-brand-200/60 dark:border-brand-500/20 bg-gradient-to-r from-brand-500/[0.06] to-violet-500/[0.06] px-4 py-3 text-sm text-brand-700 dark:text-brand-300">
          {packingList.closet_hint}
        </div>
      )}

      {/* ── Take from your closet ──────────────────────────────────── */}
      {(packingList.take_from_your_closet?.length ?? 0) > 0 && (
        <GlassCard padding="lg">
          <h3 className="font-semibold text-slate-800 dark:text-white flex items-center gap-2 mb-4">
            <Shirt size={16} className="text-emerald-500" />
            Take from your closet
            <span className="ml-auto text-xs font-normal text-slate-400 dark:text-white/30">
              {packingList.take_from_your_closet!.length} item{packingList.take_from_your_closet!.length !== 1 ? 's' : ''}
            </span>
          </h3>
          <div className="space-y-2">
            {packingList.take_from_your_closet!.map((item: PackingItemDetailed) => {
              const key = item.item_id ?? `closet-${item.name}`
              return (
                <label key={key} className="flex items-start gap-3 p-3 rounded-xl bg-emerald-50/60 dark:bg-emerald-900/10 border border-emerald-200/60 dark:border-emerald-700/20 cursor-pointer">
                  <input
                    type="checkbox"
                    checked={Boolean(packedItems[key])}
                    onChange={e => setPackedItems(prev => ({ ...prev, [key]: e.target.checked }))}
                    className="mt-0.5 rounded border-emerald-300 accent-emerald-600"
                  />
                  <div className="flex-1 min-w-0">
                    <p className="text-sm font-medium text-slate-800 dark:text-white">{item.name}</p>
                    <p className="text-xs text-slate-500 dark:text-white/40 capitalize">{item.category}</p>
                    {item.reason && <p className="text-xs text-slate-400 dark:text-white/30 mt-0.5">{item.reason}</p>}
                    {item.recommended_days && item.recommended_days.length > 0 && (
                      <p className="text-xs text-emerald-600 dark:text-emerald-400 mt-0.5">
                        {item.recommended_days.join(' · ')}
                      </p>
                    )}
                  </div>
                  <CheckCircle2 size={14} className="flex-shrink-0 mt-0.5 text-emerald-500 dark:text-emerald-400" />
                </label>
              )
            })}
          </div>
        </GlassCard>
      )}

      {/* ── Daily outfit plan ────────────────────────────────────── */}
      {(packingList.daily_plan?.length ?? 0) > 0 && (
        <GlassCard padding="lg">
          <h3 className="font-semibold text-slate-800 dark:text-white flex items-center gap-2 mb-4">
            <Star size={16} className="text-violet-500" />
            Daily outfit plan
            <span className="ml-auto text-xs font-normal text-slate-400 dark:text-white/30">
              {packingList.daily_plan!.length} day{packingList.daily_plan!.length !== 1 ? 's' : ''}
            </span>
          </h3>
          <div className="space-y-3">
            {packingList.daily_plan!.map((day: DailyOutfitPlan) => {
              const key = day.date
              const isSaved = savedOutfits[key]
              const isSaving = savingOutfit[key]
              const resolvedCount = (day.item_ids?.filter(Boolean).length ?? 0) ||
                (day.items?.filter(name => closetItems.some(ci => ci.name.toLowerCase() === name.toLowerCase())).length ?? 0)
              const canSave = resolvedCount > 0

              return (
                <div
                  key={key}
                  className="flex items-start gap-3 p-3 rounded-xl bg-violet-50/60 dark:bg-violet-900/10 border border-violet-200/60 dark:border-violet-700/20"
                >
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 mb-1">
                      <p className="text-sm font-semibold text-slate-800 dark:text-white">
                        {day.outfit_name ?? day.day_label ?? day.date}
                      </p>
                      <span className="text-xs text-slate-400 dark:text-white/30">
                        {new Date(day.date + 'T00:00:00').toLocaleDateString(undefined, { month: 'short', day: 'numeric' })}
                      </span>
                    </div>
                    {day.items && day.items.length > 0 && (
                      <div className="flex flex-wrap gap-1 mt-1">
                        {day.items.map(item => (
                          <span key={item} className="text-xs px-2 py-0.5 rounded-full bg-violet-100 dark:bg-violet-800/30 text-violet-700 dark:text-violet-300">
                            {item}
                          </span>
                        ))}
                      </div>
                    )}
                  </div>
                  <button
                    onClick={() => onSaveOutfit(day)}
                    disabled={!canSave || isSaved || isSaving}
                    title={!canSave ? 'No closet items to save' : isSaved ? 'Already saved' : 'Save to your outfits'}
                    className={[
                      'flex-shrink-0 flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium transition-all',
                      isSaved
                        ? 'bg-emerald-100 dark:bg-emerald-900/30 text-emerald-700 dark:text-emerald-300 cursor-default'
                        : !canSave
                          ? 'bg-slate-100 dark:bg-white/5 text-slate-400 dark:text-white/30 cursor-not-allowed'
                          : 'bg-violet-100 dark:bg-violet-800/30 text-violet-700 dark:text-violet-300 hover:bg-violet-200 dark:hover:bg-violet-700/30 cursor-pointer',
                    ].join(' ')}
                  >
                    {isSaving ? (
                      <Loader2 size={12} className="animate-spin" />
                    ) : isSaved ? (
                      <BookmarkCheck size={12} />
                    ) : (
                      <Star size={12} />
                    )}
                    {isSaved ? 'Saved' : 'Save outfit'}
                  </button>
                </div>
              )
            })}
          </div>
        </GlassCard>
      )}

      {/* ── You might still need ──────────────────────────────────── */}
      {(packingList.you_might_still_need?.length ?? 0) > 0 && (
        <GlassCard padding="lg">
          <h3 className="font-semibold text-slate-800 dark:text-white flex items-center gap-2 mb-4">
            <ShoppingCart size={16} className="text-amber-500" />
            You might still need
            <span className="ml-auto text-xs font-normal text-slate-400 dark:text-white/30">
              {packingList.you_might_still_need!.length} item{packingList.you_might_still_need!.length !== 1 ? 's' : ''}
            </span>
          </h3>
          <div className="space-y-2">
            {packingList.you_might_still_need!.map((item: PackingItemNeeded) => {
              const key = `need-${item.name}`
              return (
                <label key={key} className="flex items-start gap-3 p-3 rounded-xl bg-amber-50/60 dark:bg-amber-900/10 border border-amber-200/60 dark:border-amber-700/20 cursor-pointer">
                  <input
                    type="checkbox"
                    checked={Boolean(packedItems[key])}
                    onChange={e => setPackedItems(prev => ({ ...prev, [key]: e.target.checked }))}
                    className="mt-0.5 rounded border-amber-300 accent-amber-600"
                  />
                  <div className="flex-1 min-w-0">
                    <p className="text-sm font-medium text-slate-800 dark:text-white">{item.name}</p>
                    <p className="text-xs text-slate-500 dark:text-white/40 capitalize">{item.category}</p>
                    {item.reason && <p className="text-xs text-slate-400 dark:text-white/30 mt-0.5">{item.reason}</p>}
                  </div>
                  <ShoppingCart size={14} className="flex-shrink-0 mt-0.5 text-amber-500 dark:text-amber-400" />
                </label>
              )
            })}
          </div>
        </GlassCard>
      )}

      {/* ── Essentials checklist ───────────────────────────────────── */}
      {Object.keys(groupedPacking).length > 0 && (
        <GlassCard padding="lg">
          <h3 className="font-semibold text-slate-800 dark:text-white mb-4">Full checklist</h3>
          <div className="space-y-4">
            {Object.entries(groupedPacking).map(([category, items]) => (
              <div key={category} className="space-y-2">
                <h4 className="text-xs font-semibold uppercase tracking-widest text-slate-500 dark:text-white/40">
                  {category}
                </h4>
                {items.map((item: PackingItem) => {
                  const key = item.closet_item_id ?? `${item.category}-${item.name}`
                  return (
                    <label key={key} className="flex items-center justify-between gap-3 p-3 rounded-xl bg-white/70 dark:bg-white/5 border border-slate-200 dark:border-white/10 cursor-pointer">
                      <div className="flex items-center gap-3">
                        <input
                          type="checkbox"
                          checked={Boolean(packedItems[key])}
                          onChange={e => setPackedItems(prev => ({ ...prev, [key]: e.target.checked }))}
                          className="rounded border-slate-300"
                        />
                        <div>
                          <p className="text-sm font-medium text-slate-800 dark:text-white">{item.name}</p>
                          <p className="text-xs text-slate-500 dark:text-white/40">Qty {item.quantity}</p>
                        </div>
                      </div>
                      <Badge variant={item.available_in_closet ? 'green' : 'gray'}>
                        {item.available_in_closet ? 'In your closet' : 'Need to buy'}
                      </Badge>
                    </label>
                  )
                })}
              </div>
            ))}
          </div>
        </GlassCard>
      )}
    </div>
  )
}

// ── Main page ─────────────────────────────────────────────────────────────────

export default function TravelPlanner() {
  const { closetItems } = useApp()
  const throwAsyncError = useAsyncError()

  // ── Create trip flow ──────────────────────────────────────────────────────
  const [form, setForm] = useState({ destination: '', start_date: '', end_date: '', purpose: 'leisure', notes: '' })
  const [loading, setLoading] = useState(false)
  const [trip, setTrip] = useState<Trip | null>(null)
  const [trips, setTrips] = useState<Trip[]>([])
  const [packingList, setPackingList] = useState<PackingPlan | null>(null)
  const [packingError, setPackingError] = useState<string | null>(null)
  const [packingLoading, setPackingLoading] = useState(false)
  const [packedItems, setPackedItems] = useState<Record<string, boolean>>({})
  const [savedOutfits, setSavedOutfits] = useState<Record<string, boolean>>({})
  const [savingOutfit, setSavingOutfit] = useState<Record<string, boolean>>({})
  const [showForm, setShowForm] = useState(true)
  const [formError, setFormError] = useState<string | null>(null)

  // ── Save planner state ────────────────────────────────────────────────────
  const [savingPlanner, setSavingPlanner] = useState(false)
  const [plannerSaved, setPlannerSaved] = useState(false)
  const [saveError, setSaveError] = useState<string | null>(null)

  // ── Saved planners tab ────────────────────────────────────────────────────
  const [activeTab, setActiveTab] = useState<'new' | 'saved'>('new')
  const [savedTrips, setSavedTrips] = useState<Trip[]>([])
  const [savedTripsLoading, setSavedTripsLoading] = useState(false)
  const [selectedSavedTrip, setSelectedSavedTrip] = useState<Trip | null>(null)
  const [selectedSavedPlan, setSelectedSavedPlan] = useState<PackingPlan | null>(null)
  const [savedPlanLoading, setSavedPlanLoading] = useState(false)
  const [savedPlanError, setSavedPlanError] = useState<string | null>(null)
  const [savedPackedItems, setSavedPackedItems] = useState<Record<string, boolean>>({})
  const [savedSavedOutfits, setSavedSavedOutfits] = useState<Record<string, boolean>>({})
  const [savedSavingOutfit, setSavedSavingOutfit] = useState<Record<string, boolean>>({})

  const loadTrips = async () => {
    try {
      const list = await tripsApi.list()
      setTrips(list)
    } catch (err) {
      throwAsyncError(err instanceof Error ? err : new Error('Failed to load trips'))
    }
  }

  const loadSavedTrips = async () => {
    setSavedTripsLoading(true)
    try {
      const list = await tripsApi.listSaved()
      setSavedTrips(list)
    } catch {
      // non-fatal
    } finally {
      setSavedTripsLoading(false)
    }
  }

  // Load trips list on mount so existing trips are visible after login/refresh
  useEffect(() => {
    loadTrips()
  }, [])

  useEffect(() => {
    if (activeTab === 'saved') loadSavedTrips()
  }, [activeTab])

  const handleSubmit = async () => {
    if (!form.destination || !form.start_date || !form.end_date) {
      setFormError('Please fill in all required fields')
      return
    }

    if (new Date(form.end_date) <= new Date(form.start_date)) {
      setFormError('End date must be after start date')
      return
    }

    setLoading(true)
    setFormError(null)
    setPackingError(null)
    setPlannerSaved(false)
    setSaveError(null)

    try {
      const response = await tripsApi.create({
        destination: form.destination,
        start_date: form.start_date,
        end_date: form.end_date,
        purpose: form.purpose,
        notes: form.notes || undefined,
      })
      setTrip(response.trip)
      setPlannerSaved(response.trip.is_saved)
      setShowForm(false)
      if (response.packing_plan) {
        setPackingList(response.packing_plan)
        setPackedItems({})
      } else if (response.packing_error) {
        setPackingError(response.packing_error)
        setPackingLoading(true)
        try {
          const packing = await tripsApi.getPackingList(response.trip.id)
          setPackingList(packing as unknown as PackingPlan)
          setPackedItems({})
        } catch {
          // packing unavailable
        } finally {
          setPackingLoading(false)
        }
      }
      await loadTrips()
    } catch (err) {
      throwAsyncError(err instanceof Error ? err : new Error('Failed to create trip'))
    } finally {
      setLoading(false)
    }
  }

  const handleSavePlanner = async () => {
    if (!trip || savingPlanner || plannerSaved) return
    setSavingPlanner(true)
    setSaveError(null)
    try {
      const result = await tripsApi.savePlanner(trip.id)
      setTrip(result.trip)
      setPackingList(result.packing_plan)
      setPlannerSaved(true)
      // Refresh saved trips list silently
      const saved = await tripsApi.listSaved()
      setSavedTrips(saved)
    } catch (err) {
      setSaveError(err instanceof Error ? err.message : 'Failed to save planner. Please try again.')
    } finally {
      setSavingPlanner(false)
    }
  }

  const handleViewSavedPlanner = async (t: Trip) => {
    setSelectedSavedTrip(t)
    setSelectedSavedPlan(null)
    setSavedPlanError(null)
    setSavedPackedItems({})
    setSavedSavedOutfits({})
    setSavedPlanLoading(true)
    try {
      const plan = await tripsApi.getPackingPlan(t.id)
      setSelectedSavedPlan(plan)
    } catch {
      setSavedPlanError('Could not load packing plan for this trip.')
    } finally {
      setSavedPlanLoading(false)
    }
  }

  const handleOpenTrip = async (t: Trip) => {
    setTrip(t)
    setShowForm(false)
    setPackingList(null)
    setPackedItems({})
    setSavedOutfits({})
    setPlannerSaved(t.is_saved)
    setSaveError(null)
    setPackingError(null)
    setPackingLoading(true)
    try {
      const plan = await tripsApi.getPackingPlan(t.id)
      setPackingList(plan)
    } catch {
      setPackingError('Could not load packing plan for this trip.')
    } finally {
      setPackingLoading(false)
    }
  }

  const handleDeleteTrip = async (tripId: string) => {
    try {
      await tripsApi.delete(tripId)
      setTrips(trips.filter(t => t.id !== tripId))
      if (trip?.id === tripId) {
        setTrip(null)
        setPackingList(null)
        setPackedItems({})
        setShowForm(true)
        setPlannerSaved(false)
      }
    } catch (err) {
      throwAsyncError(err instanceof Error ? err : new Error('Failed to delete trip'))
    }
  }

  const handleSaveOutfit = async (day: DailyOutfitPlan, currentTrip: Trip | null) => {
    const key = day.date
    if (savedOutfits[key] || savingOutfit[key]) return

    const resolvedIds: string[] = day.item_ids?.filter(Boolean) ?? []
    if (resolvedIds.length === 0 && day.items?.length) {
      const nameMap = new Map(closetItems.map(ci => [ci.name.toLowerCase(), ci.id]))
      for (const name of day.items) {
        const id = nameMap.get(name.toLowerCase())
        if (id) resolvedIds.push(id)
      }
    }

    if (resolvedIds.length === 0) return

    setSavingOutfit(prev => ({ ...prev, [key]: true }))
    try {
      await outfitsApi.create({
        name: day.outfit_name ?? `${currentTrip?.destination ?? 'Trip'} — ${day.day_label ?? day.date}`,
        item_ids: resolvedIds,
        occasion: currentTrip?.purpose ?? 'leisure',
        notes: `Saved from ${currentTrip?.destination ?? 'travel'} packing plan`,
      })
      setSavedOutfits(prev => ({ ...prev, [key]: true }))
    } catch {
      // silently fail
    } finally {
      setSavingOutfit(prev => ({ ...prev, [key]: false }))
    }
  }

  const handleSaveSavedOutfit = async (day: DailyOutfitPlan) => {
    const key = day.date
    if (savedSavedOutfits[key] || savedSavingOutfit[key]) return

    const resolvedIds: string[] = day.item_ids?.filter(Boolean) ?? []
    if (resolvedIds.length === 0 && day.items?.length) {
      const nameMap = new Map(closetItems.map(ci => [ci.name.toLowerCase(), ci.id]))
      for (const name of day.items) {
        const id = nameMap.get(name.toLowerCase())
        if (id) resolvedIds.push(id)
      }
    }

    if (resolvedIds.length === 0) return

    setSavedSavingOutfit(prev => ({ ...prev, [key]: true }))
    try {
      await outfitsApi.create({
        name: day.outfit_name ?? `${selectedSavedTrip?.destination ?? 'Trip'} — ${day.day_label ?? day.date}`,
        item_ids: resolvedIds,
        occasion: selectedSavedTrip?.purpose ?? 'leisure',
        notes: `Saved from ${selectedSavedTrip?.destination ?? 'travel'} packing plan`,
      })
      setSavedSavedOutfits(prev => ({ ...prev, [key]: true }))
    } catch {
      // silently fail
    } finally {
      setSavedSavingOutfit(prev => ({ ...prev, [key]: false }))
    }
  }

  const startDate = form.start_date ? new Date(form.start_date) : null
  const endDate = form.end_date ? new Date(form.end_date) : null
  const duration = startDate && endDate ? Math.ceil((endDate.getTime() - startDate.getTime()) / (1000 * 60 * 60 * 24)) : 0

  const tripDuration = (t: Trip) => {
    const s = new Date(t.start_date)
    const e = new Date(t.end_date)
    return Math.ceil((e.getTime() - s.getTime()) / (1000 * 60 * 60 * 24))
  }

  return (
    <div className="max-w-4xl space-y-6">
      {/* ── Header + tabs ───────────────────────────────────────────── */}
      <div className="flex items-start justify-between gap-4 flex-wrap">
        <div>
          <h2 className="font-display font-bold text-xl text-slate-800 dark:text-slate-100 flex items-center gap-2">
            <Plane size={20} className="text-brand-500" /> Travel Packing
          </h2>
          <p className="text-sm text-slate-400 mt-0.5">
            {closetItems.length > 0
              ? `Plan trips and organize packing lists from your ${closetItems.length} wardrobe items`
              : 'Create a trip to get started with travel packing'}
          </p>
        </div>
        <div className="flex rounded-xl border border-slate-200 dark:border-white/10 overflow-hidden text-sm font-medium">
          <button
            onClick={() => setActiveTab('new')}
            className={`px-4 py-2 transition-colors ${activeTab === 'new'
              ? 'bg-brand-500 text-white'
              : 'bg-white dark:bg-slate-900 text-slate-600 dark:text-white/60 hover:bg-slate-50 dark:hover:bg-white/5'}`}
          >
            New Trip
          </button>
          <button
            onClick={() => setActiveTab('saved')}
            className={`px-4 py-2 transition-colors flex items-center gap-1.5 ${activeTab === 'saved'
              ? 'bg-brand-500 text-white'
              : 'bg-white dark:bg-slate-900 text-slate-600 dark:text-white/60 hover:bg-slate-50 dark:hover:bg-white/5'}`}
          >
            <Bookmark size={13} /> Saved Planners
          </button>
        </div>
      </div>

      {/* ── NEW TRIP TAB ─────────────────────────────────────────────────── */}
      {activeTab === 'new' && (
        <>
          {closetItems.length === 0 && (
            <div className="card p-6 text-center space-y-3">
              <Plane size={32} className="mx-auto text-slate-300 dark:text-white/20" />
              <p className="font-semibold text-slate-700 dark:text-white">Build your wardrobe first</p>
              <p className="text-sm text-slate-500 dark:text-white/40">
                Add clothing items to your closet so ClosetIQ can create a personalized packing list tailored to your trip.
              </p>
              <div className="flex justify-center gap-3 pt-1">
                <a href="/upload" className="text-sm font-medium text-brand-600 dark:text-brand-400 hover:underline">Add Items</a>
                <a href="/closet" className="text-sm font-medium text-slate-500 dark:text-white/40 hover:underline">View Closet</a>
              </div>
            </div>
          )}

          {showForm ? (
            <div className="card p-6 space-y-4">
              <h3 className="font-semibold text-slate-800 dark:text-white mb-4">Create a New Trip</h3>

              {formError && (
                <div className="p-3 rounded-lg bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 text-red-700 dark:text-red-300 text-sm">
                  {formError}
                </div>
              )}

              <div className="grid sm:grid-cols-2 gap-4">
                <DestinationInput
                  value={form.destination}
                  onChange={v => setForm(f => ({ ...f, destination: v }))}
                />
                <Select
                  label="Trip purpose *"
                  options={PURPOSE_OPTIONS}
                  value={form.purpose}
                  onChange={e => setForm(f => ({ ...f, purpose: e.target.value }))}
                />
              </div>

              <div className="grid sm:grid-cols-2 gap-4">
                <Input
                  label="Start date *"
                  type="date"
                  value={form.start_date}
                  onChange={e => setForm(f => ({ ...f, start_date: e.target.value }))}
                  leftIcon={<Calendar size={14} />}
                />
                <Input
                  label="End date *"
                  type="date"
                  value={form.end_date}
                  onChange={e => setForm(f => ({ ...f, end_date: e.target.value }))}
                  leftIcon={<Calendar size={14} />}
                />
              </div>

              <div>
                <label className="block text-xs font-semibold text-slate-700 dark:text-white/80 mb-1.5 uppercase tracking-wider">
                  Notes (optional)
                </label>
                <textarea
                  value={form.notes}
                  onChange={e => setForm(f => ({ ...f, notes: e.target.value }))}
                  placeholder="e.g. Beach activities, formal dinners, hiking..."
                  className="w-full px-3 py-2 rounded-lg border border-slate-300 dark:border-white/10 bg-white dark:bg-slate-900 text-slate-900 dark:text-white text-sm focus:outline-none focus:ring-2 focus:ring-brand-500 dark:focus:ring-brand-400"
                  rows={3}
                />
              </div>

              <div className="flex gap-3 pt-4">
                <Button
                  variant="primary"
                  onClick={handleSubmit}
                  disabled={loading || !form.destination || !form.start_date || !form.end_date}
                  className="flex-1"
                >
                  {loading ? (
                    <>
                      <Loader2 size={16} className="animate-spin" /> Creating...
                    </>
                  ) : (
                    'Create Trip'
                  )}
                </Button>
              </div>
            </div>
          ) : trip ? (
            <div className="space-y-4">
              <div className="flex items-center gap-3">
                <Button
                  variant="ghost"
                  onClick={() => { setShowForm(true); setFormError(null); setPlannerSaved(false); setSaveError(null) }}
                  className="flex items-center gap-2"
                >
                  <ArrowLeft size={16} /> Create Another Trip
                </Button>
              </div>

              {/* Trip Summary */}
              <GlassCard padding="lg">
                <div className="flex items-start justify-between mb-4">
                  <div>
                    <h3 className="font-semibold text-lg text-slate-800 dark:text-white">{trip.destination}</h3>
                    <p className="text-sm text-slate-500 dark:text-white/40 mt-1">
                      {duration} days • {new Date(trip.start_date).toLocaleDateString()} to {new Date(trip.end_date).toLocaleDateString()}
                    </p>
                  </div>
                  <Badge>{trip.purpose}</Badge>
                </div>
                {trip.notes && (
                  <p className="text-sm text-slate-600 dark:text-white/60 mt-3">
                    {trip.notes}
                  </p>
                )}
              </GlassCard>

              {packingLoading && (
                <div className="card p-4 bg-blue-50 dark:bg-blue-900/20 border-blue-200 dark:border-blue-800 text-blue-700 dark:text-blue-300 text-sm">
                  Generating packing list from your closet...
                </div>
              )}

              {packingError && !packingList && (
                <div className="card p-4 bg-amber-50 dark:bg-amber-900/20 border-amber-200 dark:border-amber-800 text-amber-700 dark:text-amber-300 text-sm">
                  Packing plan unavailable right now. You can retry from the trip details.
                </div>
              )}

              {/* ── Save Complete Planner CTA ──────────────────────────── */}
              {packingList && (
                <div className="rounded-2xl border border-brand-200/60 dark:border-brand-500/20 bg-gradient-to-r from-brand-500/[0.07] to-violet-500/[0.07] p-5">
                  {plannerSaved ? (
                    <div className="flex items-center justify-between gap-4 flex-wrap">
                      <div className="flex items-center gap-3">
                        <div className="w-10 h-10 rounded-full bg-emerald-100 dark:bg-emerald-900/40 flex items-center justify-center flex-shrink-0">
                          <CheckCircle2 size={20} className="text-emerald-600 dark:text-emerald-400" />
                        </div>
                        <div>
                          <p className="font-semibold text-slate-800 dark:text-white text-sm">Planner saved successfully</p>
                          <p className="text-xs text-slate-500 dark:text-white/40 mt-0.5">
                            You can view it anytime under Saved Planners
                          </p>
                        </div>
                      </div>
                      <button
                        onClick={() => setActiveTab('saved')}
                        className="flex items-center gap-1.5 text-sm font-medium text-brand-600 dark:text-brand-400 hover:underline flex-shrink-0"
                      >
                        View Saved Planners <ChevronRight size={14} />
                      </button>
                    </div>
                  ) : (
                    <div className="flex items-center justify-between gap-4 flex-wrap">
                      <div className="flex items-center gap-3">
                        <div className="w-10 h-10 rounded-full bg-brand-100 dark:bg-brand-900/40 flex items-center justify-center flex-shrink-0">
                          <BookmarkPlus size={20} className="text-brand-600 dark:text-brand-400" />
                        </div>
                        <div>
                          <p className="font-semibold text-slate-800 dark:text-white text-sm">Save Complete Planner</p>
                          <p className="text-xs text-slate-500 dark:text-white/40 mt-0.5">
                            Persist your trip + packing plan to view later after logging back in
                          </p>
                        </div>
                      </div>
                      <div className="flex flex-col items-end gap-1 flex-shrink-0">
                        <Button
                          variant="primary"
                          onClick={handleSavePlanner}
                          disabled={savingPlanner}
                          className="flex items-center gap-2"
                        >
                          {savingPlanner ? (
                            <><Loader2 size={14} className="animate-spin" /> Saving…</>
                          ) : (
                            <><BookmarkPlus size={14} /> Save Complete Planner</>
                          )}
                        </Button>
                        {saveError && (
                          <p className="text-xs text-red-600 dark:text-red-400 flex items-center gap-1">
                            <AlertCircle size={11} /> {saveError}
                          </p>
                        )}
                      </div>
                    </div>
                  )}
                </div>
              )}

              {packingList && (
                <PackingResult
                  packingList={packingList}
                  closetItems={closetItems}
                  packedItems={packedItems}
                  setPackedItems={setPackedItems}
                  savedOutfits={savedOutfits}
                  savingOutfit={savingOutfit}
                  onSaveOutfit={day => handleSaveOutfit(day, trip)}
                />
              )}
            </div>
          ) : null}

          {/* List of Trips */}
          {trips.length > 0 && (
            <div>
              <h3 className="font-display font-semibold text-sm uppercase tracking-widest text-slate-500 dark:text-white/40 mb-3">
                Your Trips
              </h3>
              <div className="space-y-3">
                {trips.map(t => (
                  <GlassCard key={t.id} padding="md" hover>
                    <div className="flex items-start justify-between gap-3">
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2 flex-wrap">
                          <p className="font-semibold text-slate-800 dark:text-white">{t.destination}</p>
                          <Badge>{t.purpose}</Badge>
                          {t.is_saved && (
                            <span className="flex items-center gap-1 text-[10px] font-medium text-emerald-600 dark:text-emerald-400 bg-emerald-50 dark:bg-emerald-900/20 px-2 py-0.5 rounded-full">
                              <Bookmark size={9} /> Saved
                            </span>
                          )}
                        </div>
                        <p className="text-xs text-slate-500 dark:text-white/40 mt-1">
                          {new Date(t.start_date).toLocaleDateString()} to {new Date(t.end_date).toLocaleDateString()} · {tripDuration(t)} days
                        </p>
                      </div>
                      <div className="flex items-center gap-2 flex-shrink-0">
                        <Button
                          variant="ghost"
                          onClick={() => handleOpenTrip(t)}
                          className="flex items-center gap-1.5 text-xs"
                        >
                          View Planner <ChevronRight size={13} />
                        </Button>
                        <button
                          onClick={() => handleDeleteTrip(t.id)}
                          className="text-red-500 hover:text-red-700 dark:hover:text-red-300 text-xs font-medium"
                        >
                          Delete
                        </button>
                      </div>
                    </div>
                  </GlassCard>
                ))}
              </div>
            </div>
          )}
        </>
      )}

      {/* ── SAVED PLANNERS TAB ───────────────────────────────────────────── */}
      {activeTab === 'saved' && (
        <div className="space-y-4">
          {selectedSavedTrip ? (
            /* ── Saved planner detail view ─────────────────────────── */
            <div className="space-y-4">
              <div className="flex items-center gap-3">
                <Button
                  variant="ghost"
                  onClick={() => { setSelectedSavedTrip(null); setSelectedSavedPlan(null) }}
                  className="flex items-center gap-2"
                >
                  <ArrowLeft size={16} /> Back to Saved Planners
                </Button>
              </div>

              <GlassCard padding="lg">
                <div className="flex items-start justify-between mb-2">
                  <div>
                    <h3 className="font-semibold text-lg text-slate-800 dark:text-white">{selectedSavedTrip.destination}</h3>
                    <p className="text-sm text-slate-500 dark:text-white/40 mt-1">
                      {tripDuration(selectedSavedTrip)} days • {new Date(selectedSavedTrip.start_date).toLocaleDateString()} to {new Date(selectedSavedTrip.end_date).toLocaleDateString()}
                    </p>
                  </div>
                  <div className="flex items-center gap-2">
                    <Badge>{selectedSavedTrip.purpose}</Badge>
                    <span className="flex items-center gap-1 text-[10px] font-medium text-emerald-600 dark:text-emerald-400 bg-emerald-50 dark:bg-emerald-900/20 px-2 py-0.5 rounded-full">
                      <Bookmark size={9} /> Saved
                    </span>
                  </div>
                </div>
                {selectedSavedTrip.notes && (
                  <p className="text-sm text-slate-600 dark:text-white/60 mt-3">{selectedSavedTrip.notes}</p>
                )}
                <p className="text-xs text-slate-400 dark:text-white/30 mt-3">
                  Saved {new Date(selectedSavedTrip.updated_at).toLocaleDateString()}
                </p>
              </GlassCard>

              {savedPlanLoading && (
                <div className="card p-6 flex items-center justify-center gap-3 text-slate-500 dark:text-white/40 text-sm">
                  <Loader2 size={18} className="animate-spin" /> Loading packing plan…
                </div>
              )}

              {savedPlanError && (
                <div className="card p-4 bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 text-red-700 dark:text-red-300 text-sm flex items-center gap-2">
                  <AlertCircle size={14} /> {savedPlanError}
                </div>
              )}

              {selectedSavedPlan && (
                <PackingResult
                  packingList={selectedSavedPlan}
                  closetItems={closetItems}
                  packedItems={savedPackedItems}
                  setPackedItems={setSavedPackedItems}
                  savedOutfits={savedSavedOutfits}
                  savingOutfit={savedSavingOutfit}
                  onSaveOutfit={handleSaveSavedOutfit}
                />
              )}
            </div>
          ) : (
            /* ── Saved planners list ────────────────────────────────── */
            <>
              <div className="flex items-center justify-between">
                <h3 className="font-display font-semibold text-sm uppercase tracking-widest text-slate-500 dark:text-white/40">
                  Saved Planners
                </h3>
                {!savedTripsLoading && (
                  <button
                    onClick={loadSavedTrips}
                    className="text-xs text-slate-400 dark:text-white/30 hover:text-brand-500 dark:hover:text-brand-400 transition-colors"
                  >
                    Refresh
                  </button>
                )}
              </div>

              {savedTripsLoading ? (
                <div className="card p-6 flex items-center justify-center gap-3 text-slate-500 dark:text-white/40 text-sm">
                  <Loader2 size={18} className="animate-spin" /> Loading saved planners…
                </div>
              ) : savedTrips.length === 0 ? (
                <div className="card p-10 text-center space-y-4">
                  <Bookmark size={36} className="mx-auto text-slate-300 dark:text-white/20" />
                  <div>
                    <p className="font-semibold text-slate-700 dark:text-white">No saved planners yet</p>
                    <p className="text-sm text-slate-500 dark:text-white/40 mt-1 max-w-xs mx-auto">
                      Generate a trip packing planner and click "Save Complete Planner" to access it here later.
                    </p>
                  </div>
                  <button
                    onClick={() => setActiveTab('new')}
                    className="inline-flex items-center gap-2 text-sm font-medium text-brand-600 dark:text-brand-400 hover:underline"
                  >
                    <Plane size={14} /> Create Your First Trip
                  </button>
                </div>
              ) : (
                <div className="space-y-3">
                  {savedTrips.map(t => (
                    <GlassCard key={t.id} padding="md" hover>
                      <div className="flex items-start justify-between gap-4">
                        <div className="flex-1 min-w-0">
                          <div className="flex items-center gap-2 mb-1">
                            <p className="font-semibold text-slate-800 dark:text-white truncate">{t.destination}</p>
                            <Badge>{t.purpose}</Badge>
                          </div>
                          <p className="text-xs text-slate-500 dark:text-white/40">
                            {new Date(t.start_date).toLocaleDateString()} – {new Date(t.end_date).toLocaleDateString()} · {tripDuration(t)} days
                          </p>
                          <p className="text-xs text-slate-400 dark:text-white/30 mt-1">
                            Saved {new Date(t.updated_at).toLocaleDateString()}
                          </p>
                        </div>
                        <Button
                          variant="ghost"
                          onClick={() => handleViewSavedPlanner(t)}
                          className="flex items-center gap-1.5 flex-shrink-0 text-xs"
                        >
                          View Planner <ChevronRight size={13} />
                        </Button>
                      </div>
                    </GlassCard>
                  ))}
                </div>
              )}
            </>
          )}
        </div>
      )}
    </div>
  )
}
