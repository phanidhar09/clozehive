import { useState } from 'react'
import { Plane, AlertTriangle, Calendar, MapPin, Loader2, ArrowLeft } from 'lucide-react'
import Button from '@/components/ui/Button'
import Input, { Select } from '@/components/ui/Input'
import Badge from '@/components/ui/Badge'
import GlassCard from '@/components/ui/GlassCard'
import { useApp } from '@/store'
import { tripsApi } from '@/lib/api'
import { useAsyncError } from '@/hooks/useAsyncError'
import type { PackingItem, PackingResult, Trip } from '@/types'

const PURPOSE_OPTIONS = [
  { value: 'leisure', label: '🌴 Leisure / Holiday' },
  { value: 'business', label: '💼 Business' },
  { value: 'beach', label: '🏖️ Beach / Resort' },
  { value: 'formal', label: '🎩 Formal Event' },
  { value: 'adventure', label: '🏔️ Adventure / Hiking' },
]

export default function TravelPlanner() {
  const { closetItems } = useApp()
  const throwAsyncError = useAsyncError()
  const [form, setForm] = useState({ destination: '', start_date: '', end_date: '', purpose: 'leisure', notes: '' })
  const [loading, setLoading] = useState(false)
  const [trip, setTrip] = useState<Trip | null>(null)
  const [trips, setTrips] = useState<Trip[]>([])
  const [packingList, setPackingList] = useState<PackingResult | null>(null)
  const [packingLoading, setPackingLoading] = useState(false)
  const [packedItems, setPackedItems] = useState<Record<string, boolean>>({})
  const [showForm, setShowForm] = useState(true)
  const [formError, setFormError] = useState<string | null>(null)

  const loadTrips = async () => {
    try {
      const list = await tripsApi.list()
      setTrips(list)
    } catch (err) {
      throwAsyncError(err instanceof Error ? err : new Error('Failed to load trips'))
    }
  }

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

    try {
      const newTrip = await tripsApi.create({
        destination: form.destination,
        start_date: form.start_date,
        end_date: form.end_date,
        purpose: form.purpose,
        notes: form.notes || undefined,
      })
      setTrip(newTrip)
      setShowForm(false)
      setPackingLoading(true)
      try {
        const packing = await tripsApi.getPackingList(newTrip.id)
        setPackingList(packing)
        setPackedItems({})
      } finally {
        setPackingLoading(false)
      }
      await loadTrips()
    } catch (err) {
      throwAsyncError(err instanceof Error ? err : new Error('Failed to create trip'))
    } finally {
      setLoading(false)
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
      }
    } catch (err) {
      throwAsyncError(err instanceof Error ? err : new Error('Failed to delete trip'))
    }
  }

  const startDate = form.start_date ? new Date(form.start_date) : null
  const endDate = form.end_date ? new Date(form.end_date) : null
  const duration = startDate && endDate ? Math.ceil((endDate.getTime() - startDate.getTime()) / (1000 * 60 * 60 * 24)) : 0
  const packingItems = [...(packingList?.packing_list ?? packingList?.items ?? []), ...(packingList?.missing_items ?? [])]
  const groupedPacking = packingItems.reduce<Record<string, PackingItem[]>>((acc, item) => {
    const category = item.category || 'Other'
    acc[category] = acc[category] ?? []
    acc[category].push(item)
    return acc
  }, {})

  return (
    <div className="max-w-4xl space-y-6">
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

      {closetItems.length === 0 && (
        <div className="card p-3 bg-amber-50 dark:bg-amber-900/20 border-amber-200 dark:border-amber-800 text-amber-700 dark:text-amber-300 text-sm flex items-center gap-2">
          <AlertTriangle size={15} />
          Your closet is empty. Add some items to get better packing recommendations.
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
            <Input
              label="Destination *"
              placeholder="e.g. Bali, Indonesia"
              value={form.destination}
              onChange={e => setForm(f => ({ ...f, destination: e.target.value }))}
              leftIcon={<MapPin size={14} />}
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
              onClick={() => { setShowForm(true); setFormError(null) }}
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

          {packingList && (
            <GlassCard padding="lg">
              <div className="space-y-4">
                <div>
                  <h3 className="font-semibold text-lg text-slate-800 dark:text-white">Packing List</h3>
                  {packingList.summary && (
                    <p className="text-sm text-slate-500 dark:text-white/50 mt-1">{packingList.summary}</p>
                  )}
                </div>

                {Object.entries(groupedPacking).map(([category, items]) => (
                  <div key={category} className="space-y-2">
                    <h4 className="text-xs font-semibold uppercase tracking-widest text-slate-500 dark:text-white/40">
                      {category}
                    </h4>
                    {items.map(item => {
                      const key = item.closet_item_id ?? `${item.category}-${item.name}`
                      return (
                        <label key={key} className="flex items-center justify-between gap-3 p-3 rounded-xl bg-white/70 dark:bg-white/5 border border-slate-200 dark:border-white/10">
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
                <div className="flex items-start justify-between">
                  <div className="flex-1">
                    <p className="font-semibold text-slate-800 dark:text-white">{t.destination}</p>
                    <p className="text-xs text-slate-500 dark:text-white/40 mt-1">
                      {new Date(t.start_date).toLocaleDateString()} to {new Date(t.end_date).toLocaleDateString()}
                    </p>
                  </div>
                  <button
                    onClick={() => handleDeleteTrip(t.id)}
                    className="text-red-500 hover:text-red-700 dark:hover:text-red-300 text-xs font-medium ml-2"
                  >
                    Delete
                  </button>
                </div>
              </GlassCard>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
