/**
 * TravelPlanner — activity-aware travel outfit planner powered by FANI AI Stylist.
 * Step 1: Trip basics → Step 2: Activities → Step 3: Day-by-day outfit result
 */

import { useState, useRef, useEffect, useCallback, useMemo } from 'react'
import BackButton from '@/components/ui/BackButton'
import { usePageState } from '@/hooks/usePageState'
import {
  Plane, Calendar, MapPin, Loader2, ArrowLeft, CheckCircle2,
  ShoppingCart, Shirt, Star, BookmarkCheck, BookmarkPlus, Bookmark,
  ChevronRight, AlertCircle, Plus, X, ChevronDown, ChevronUp,
  RefreshCw, Layers, Sparkles, Clock, Package, Tag, Luggage,
  Sun, CloudRain, Thermometer, AlertTriangle, Check,
} from 'lucide-react'
import Button from '@/components/ui/Button'
import Input, { Select } from '@/components/ui/Input'
import Badge from '@/components/ui/Badge'
import GlassCard from '@/components/ui/GlassCard'
import { useApp } from '@/store'
import { tripsApi } from '@/lib/api'
import { cn } from '@/lib/utils'
import type {
  Trip, PackingPlan, TripActivity, RichDayPlan,
  PackingChecklistItem, RewearStrategyItem,
  BagCapacitySummary,
} from '@/types'

// ── Error extractor ────────────────────────────────────────────────────────

function tripApiErr(err: unknown, fallback: string): string {
  type ApiErr = { response?: { data?: { message?: string; error?: string; detail?: string | Array<{ loc?: (string | number)[]; msg?: string }> } } }
  const d = (err as ApiErr)?.response?.data
  let msg: string | undefined
  if (typeof d?.detail === 'string') msg = d.detail
  else if (Array.isArray(d?.detail)) {
    msg = d.detail.map(e => {
      const field = Array.isArray(e.loc) ? e.loc.slice(1).join('.') : ''
      return field ? `${field}: ${e.msg ?? ''}` : (e.msg ?? '')
    }).filter(Boolean).join(' · ')
  }
  msg = msg ?? d?.message ?? d?.error ?? (err instanceof Error ? err.message : undefined)
  return msg?.trim() ? msg : fallback
}

// ── Destinations ──────────────────────────────────────────────────────────

const DESTINATIONS = [
  'Tokyo, Japan','Kyoto, Japan','Seoul, South Korea','Bangkok, Thailand','Bali, Indonesia',
  'Singapore','Kuala Lumpur, Malaysia','Ho Chi Minh City, Vietnam','Mumbai, India','Goa, India',
  'Dubai, UAE','Istanbul, Turkey','Tel Aviv, Israel','Paris, France','London, UK',
  'Rome, Italy','Milan, Italy','Barcelona, Spain','Lisbon, Portugal','Amsterdam, Netherlands',
  'Berlin, Germany','Vienna, Austria','Prague, Czech Republic','Athens, Greece','Santorini, Greece',
  'Stockholm, Sweden','Copenhagen, Denmark','Reykjavik, Iceland','New York, USA','Los Angeles, USA',
  'Miami, USA','Chicago, USA','San Francisco, USA','Las Vegas, USA','Orlando, USA','Nashville, USA',
  'Austin, USA','Toronto, Canada','Vancouver, Canada','Mexico City, Mexico','Cancun, Mexico',
  'Playa del Carmen, Mexico','Rio de Janeiro, Brazil','Buenos Aires, Argentina','Lima, Peru',
  'Bogotá, Colombia','Cartagena, Colombia','Cape Town, South Africa','Marrakech, Morocco',
  'Cairo, Egypt','Nairobi, Kenya','Sydney, Australia','Melbourne, Australia','Auckland, New Zealand',
  'Maldives','Bali, Indonesia','Phuket, Thailand','Santorini, Greece','Ibiza, Spain','Mykonos, Greece',
]

// ── Constants ──────────────────────────────────────────────────────────────

const PURPOSE_OPTIONS = [
  { value: 'leisure', label: '🌴 Leisure / Holiday' },
  { value: 'business', label: '💼 Business' },
  { value: 'beach', label: '🏖️ Beach / Resort' },
  { value: 'formal', label: '🎩 Formal Event' },
  { value: 'adventure', label: '🏔️ Adventure / Hiking' },
]

const TRIP_STYLE_OPTS = [
  { value: 'casual', label: 'Casual', emoji: '😎' },
  { value: 'smart_casual', label: 'Smart Casual', emoji: '👔' },
  { value: 'chic', label: 'Chic', emoji: '✨' },
  { value: 'business', label: 'Business', emoji: '💼' },
  { value: 'sporty', label: 'Sporty', emoji: '🏃' },
  { value: 'beach', label: 'Beach Vibes', emoji: '🏖️' },
  { value: 'boho', label: 'Boho', emoji: '🌸' },
  { value: 'streetwear', label: 'Streetwear', emoji: '🎒' },
]

const BAG_SIZE_OPTS = [
  { value: 'backpack', label: '🎒 Backpack only', desc: '1-2 outfits/day, strong rewear' },
  { value: 'carry_on', label: '🧳 Carry-on', desc: '4-5 tops, 2-3 bottoms, 1-2 shoes' },
  { value: 'medium_suitcase', label: '🧳 Medium Suitcase', desc: '6-8 tops, 3-4 bottoms, 2-3 shoes' },
  { value: 'large_suitcase', label: '🧳 Large Suitcase', desc: 'Full variety, minimal limits' },
  { value: 'none', label: '❓ Not sure yet', desc: 'AI will suggest what to pack' },
]

const ACTIVITY_PRESETS: { id: string; name: string; emoji: string; formality: string; time_of_day: string }[] = [
  { id: 'beach', name: 'Beach / Pool', emoji: '🏖️', formality: 'beachwear', time_of_day: 'afternoon' },
  { id: 'brunch', name: 'Brunch / Café', emoji: '☕', formality: 'casual', time_of_day: 'morning' },
  { id: 'dinner', name: 'Dinner / Date night', emoji: '🍽️', formality: 'smart_casual', time_of_day: 'evening' },
  { id: 'nightlife', name: 'Nightlife / Club', emoji: '🎉', formality: 'smart_casual', time_of_day: 'night' },
  { id: 'sightseeing', name: 'Sightseeing / Walking', emoji: '🚶', formality: 'casual', time_of_day: 'morning' },
  { id: 'business', name: 'Business Meeting', emoji: '💼', formality: 'business', time_of_day: 'morning' },
  { id: 'formal', name: 'Wedding / Formal', emoji: '💍', formality: 'formal', time_of_day: 'afternoon' },
  { id: 'hiking', name: 'Hiking / Outdoor', emoji: '🥾', formality: 'active', time_of_day: 'morning' },
  { id: 'gym', name: 'Gym / Fitness', emoji: '💪', formality: 'active', time_of_day: 'morning' },
  { id: 'shopping', name: 'Shopping', emoji: '🛍️', formality: 'casual', time_of_day: 'afternoon' },
  { id: 'boat', name: 'Boat / Cruise', emoji: '⛵', formality: 'casual', time_of_day: 'afternoon' },
  { id: 'photoshoot', name: 'Photoshoot', emoji: '📸', formality: 'smart_casual', time_of_day: 'afternoon' },
  { id: 'cultural', name: 'Cultural / Museum', emoji: '🏛️', formality: 'smart_casual', time_of_day: 'morning' },
  { id: 'theme_park', name: 'Theme Park', emoji: '🎢', formality: 'casual', time_of_day: 'full_day' },
  { id: 'airport', name: 'Airport Travel', emoji: '✈️', formality: 'casual', time_of_day: 'morning' },
  { id: 'spa', name: 'Spa / Pool Day', emoji: '♨️', formality: 'beachwear', time_of_day: 'afternoon' },
]

const TIME_OF_DAY_OPTS = [
  { value: 'morning', label: '🌅 Morning' },
  { value: 'afternoon', label: '☀️ Afternoon' },
  { value: 'evening', label: '🌆 Evening' },
  { value: 'night', label: '🌙 Night' },
  { value: 'full_day', label: '🕐 Full Day' },
]

const FORMALITY_OPTS = [
  { value: 'casual', label: '😎 Casual' },
  { value: 'smart_casual', label: '👔 Smart Casual' },
  { value: 'formal', label: '🎩 Formal' },
  { value: 'active', label: '🏃 Active' },
  { value: 'beachwear', label: '🏖️ Beachwear' },
  { value: 'business', label: '💼 Business' },
]

const CATEGORY_EMOJI: Record<string, string> = {
  tops: '👕', bottoms: '👖', shoes: '👟', outerwear: '🧥', accessories: '👜',
  dresses: '👗', innerwear: '🩲', sleepwear: '😴', toiletries: '🧴',
  travel_essentials: '✈️', essentials: '✅', general: '📦',
}

const SOURCE_BADGE: Record<string, { label: string; variant: 'green' | 'amber' | 'gray' | 'blue' }> = {
  from_closet: { label: 'In Closet', variant: 'green' },
  missing_recommended: { label: 'Buy / Borrow', variant: 'amber' },
  optional: { label: 'Optional', variant: 'gray' },
  essential: { label: 'Essential', variant: 'blue' },
  custom: { label: 'Custom', variant: 'gray' },
}

interface ActivityDraft extends TripActivity {
  _id: string  // local UUID
}

// ── Destination combobox ──────────────────────────────────────────────────

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
          placeholder="e.g. Miami, Paris, Bali…"
          onChange={e => { setQuery(e.target.value); onChange(e.target.value); setOpen(true) }}
          onFocus={() => setOpen(true)}
          className="w-full pl-9 pr-3 py-2.5 rounded-xl border border-slate-300 dark:border-white/10 bg-white dark:bg-slate-900 text-slate-900 dark:text-white text-sm focus:outline-none focus:ring-2 focus:ring-brand-500"
        />
      </div>
      {open && matches.length > 0 && (
        <ul className="absolute z-50 mt-1 w-full bg-white dark:bg-slate-800 border border-slate-200 dark:border-white/10 rounded-xl shadow-lg overflow-hidden max-h-56 overflow-y-auto">
          {matches.map(dest => (
            <li
              key={dest}
              onMouseDown={() => { setQuery(dest); onChange(dest); setOpen(false) }}
              className="flex items-center gap-2 px-3 py-2 text-sm cursor-pointer text-slate-800 dark:text-white hover:bg-brand-50 dark:hover:bg-brand-500/10"
            >
              <MapPin size={11} className="text-slate-400 flex-shrink-0" />
              {dest}
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}

// ── Step indicator ────────────────────────────────────────────────────────

function StepIndicator({ step }: { step: 1 | 2 | 3 }) {
  const steps = [
    { n: 1, label: 'Trip Details' },
    { n: 2, label: 'Activities' },
    { n: 3, label: 'Your Planner' },
  ]
  return (
    <div className="flex items-center gap-2">
      {steps.map((s, i) => (
        <div key={s.n} className="flex items-center gap-2">
          <div className={cn(
            'flex items-center gap-2 px-3 py-1.5 rounded-full text-xs font-semibold transition-all',
            step === s.n
              ? 'bg-brand-500 text-white shadow-sm shadow-brand-500/30'
              : step > s.n
                ? 'bg-emerald-100 dark:bg-emerald-900/30 text-emerald-700 dark:text-emerald-400'
                : 'bg-slate-100 dark:bg-white/5 text-slate-400 dark:text-white/30',
          )}>
            {step > s.n
              ? <Check size={11} />
              : <span className={cn('w-4 h-4 rounded-full text-center leading-4 text-[10px]',
                  step === s.n ? 'bg-white/30' : 'bg-current/20'
                )}>{s.n}</span>
            }
            <span className="hidden sm:inline">{s.label}</span>
          </div>
          {i < steps.length - 1 && (
            <div className={cn('w-6 h-px', step > s.n ? 'bg-emerald-300 dark:bg-emerald-700/50' : 'bg-slate-200 dark:bg-white/10')} />
          )}
        </div>
      ))}
    </div>
  )
}

// ── Activity chip card ────────────────────────────────────────────────────

function ActivityChip({
  preset, selected, onClick,
}: { preset: typeof ACTIVITY_PRESETS[0]; selected: boolean; onClick: () => void }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        'flex items-center gap-2 px-3 py-2 rounded-xl border text-sm font-medium transition-all',
        selected
          ? 'bg-brand-50 dark:bg-brand-900/30 border-brand-300 dark:border-brand-600 text-brand-700 dark:text-brand-300 shadow-sm'
          : 'bg-white dark:bg-white/5 border-slate-200 dark:border-white/10 text-slate-700 dark:text-slate-300 hover:border-brand-300 dark:hover:border-brand-700',
      )}
    >
      <span className="text-base">{preset.emoji}</span>
      <span className="truncate">{preset.name}</span>
      {selected && <Check size={12} className="flex-shrink-0 text-brand-500" />}
    </button>
  )
}

// ── Selected activity inline editor ──────────────────────────────────────

function SelectedActivityCard({
  activity, index, tripDays, onUpdate, onRemove,
}: {
  activity: ActivityDraft
  index: number
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

function DayPlanCard({ day, startDate }: { day: RichDayPlan; startDate: string }) {
  const [expanded, setExpanded] = useState(day.day_number <= 3)
  const dateStr = day.date
    ? new Date(day.date + 'T00:00:00').toLocaleDateString(undefined, { weekday: 'short', month: 'short', day: 'numeric' })
    : `Day ${day.day_number}`

  const slotColors: Record<string, string> = {
    morning: 'bg-amber-50 dark:bg-amber-900/10 border-amber-200/60 dark:border-amber-700/20 text-amber-700 dark:text-amber-400',
    afternoon: 'bg-sky-50 dark:bg-sky-900/10 border-sky-200/60 dark:border-sky-700/20 text-sky-700 dark:text-sky-400',
    evening: 'bg-violet-50 dark:bg-violet-900/10 border-violet-200/60 dark:border-violet-700/20 text-violet-700 dark:text-violet-400',
    night: 'bg-indigo-50 dark:bg-indigo-900/10 border-indigo-200/60 dark:border-indigo-700/20 text-indigo-700 dark:text-indigo-400',
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
                  <div className="flex items-start gap-2 text-xs text-slate-600 dark:text-white/50 bg-violet-50/50 dark:bg-violet-900/10 rounded-lg px-2.5 py-1.5">
                    <Sparkles size={11} className="text-violet-500 flex-shrink-0 mt-0.5" />
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

// ── Rewear strategy panel ─────────────────────────────────────────────────

function RewearStrategyPanel({ items }: { items: RewearStrategyItem[] }) {
  if (items.length === 0) return (
    <div className="text-center py-10 text-slate-400 dark:text-white/30 text-sm">
      No specific rewear strategy — each outfit uses distinct items.
    </div>
  )
  return (
    <div className="space-y-3">
      {items.map((item, i) => (
        <div key={i} className="flex items-start gap-3 p-3 rounded-xl bg-teal-50/60 dark:bg-teal-900/10 border border-teal-200/60 dark:border-teal-700/20">
          <div className="w-8 h-8 rounded-xl bg-teal-100 dark:bg-teal-900/30 flex items-center justify-center flex-shrink-0">
            <RefreshCw size={14} className="text-teal-600 dark:text-teal-400" />
          </div>
          <div className="flex-1 min-w-0">
            <p className="text-sm font-semibold text-slate-800 dark:text-white">{item.item_name}</p>
            {item.worn_on_days.length > 0 && (
              <p className="text-xs text-teal-700 dark:text-teal-400 mt-0.5">
                {item.worn_on_days.join(' · ')}
              </p>
            )}
            {item.worn_for && item.worn_for.length > 0 && (
              <p className="text-xs text-slate-400 mt-0.5">{item.worn_for.join(', ')}</p>
            )}
            {item.reason && (
              <p className="text-xs text-slate-500 dark:text-white/40 mt-1">{item.reason}</p>
            )}
          </div>
        </div>
      ))}
    </div>
  )
}

// ── Packing checklist panel ───────────────────────────────────────────────

const CHECKLIST_CATEGORY_ORDER = [
  'tops', 'bottoms', 'dresses', 'outerwear', 'shoes', 'accessories',
  'innerwear', 'sleepwear', 'toiletries', 'travel_essentials', 'essentials', 'general',
]

function PackingChecklistPanel({
  items, tripId, packedState, onToggle,
}: {
  items: PackingChecklistItem[]
  tripId: string
  packedState: Record<string, boolean>
  onToggle: (key: string, val: boolean) => void
}) {
  // Group by category
  const grouped = useMemo(() => {
    const map: Record<string, PackingChecklistItem[]> = {}
    for (const item of items) {
      const cat = item.category?.toLowerCase() || 'general'
      map[cat] = map[cat] ?? []
      map[cat].push(item)
    }
    return map
  }, [items])

  const orderedCategories = [
    ...CHECKLIST_CATEGORY_ORDER.filter(c => grouped[c]),
    ...Object.keys(grouped).filter(c => !CHECKLIST_CATEGORY_ORDER.includes(c)),
  ]

  const total = items.length
  const packed = items.filter(i => {
    const key = i.closet_item_id || i.item_name.toLowerCase()
    return packedState[key] ?? i.is_packed
  }).length

  if (items.length === 0) return (
    <div className="text-center py-10 text-slate-400 dark:text-white/30 text-sm">
      Save the planner to generate your packing checklist.
    </div>
  )

  return (
    <div className="space-y-4">
      {/* Progress */}
      <div className="flex items-center gap-3">
        <div className="flex-1 h-2 rounded-full bg-slate-100 dark:bg-white/10 overflow-hidden">
          <div
            className="h-full rounded-full bg-emerald-500 dark:bg-emerald-400 transition-all duration-500"
            style={{ width: `${total > 0 ? (packed / total) * 100 : 0}%` }}
          />
        </div>
        <span className="text-xs font-semibold text-slate-600 dark:text-slate-300 flex-shrink-0">
          {packed}/{total} packed
        </span>
      </div>

      {orderedCategories.map(cat => (
        <div key={cat}>
          <div className="flex items-center gap-2 mb-2">
            <span className="text-base">{CATEGORY_EMOJI[cat] ?? '📦'}</span>
            <h4 className="text-xs font-bold uppercase tracking-widest text-slate-500 dark:text-white/40 capitalize">
              {cat.replace('_', ' ')}
            </h4>
            <span className="text-[10px] text-slate-400 ml-auto">
              {grouped[cat].length} item{grouped[cat].length !== 1 ? 's' : ''}
            </span>
          </div>
          <div className="space-y-1.5">
            {grouped[cat].map((item, i) => {
              const key = item.closet_item_id || item.item_name.toLowerCase()
              const isPacked = packedState[key] ?? item.is_packed
              const badgeCfg = SOURCE_BADGE[item.source] ?? SOURCE_BADGE.optional

              return (
                <label
                  key={i}
                  className={cn(
                    'flex items-center gap-3 p-2.5 rounded-xl border cursor-pointer transition-all',
                    isPacked
                      ? 'bg-emerald-50/80 dark:bg-emerald-900/10 border-emerald-200/60 dark:border-emerald-700/20 opacity-70'
                      : 'bg-white dark:bg-white/[0.03] border-slate-200 dark:border-white/[0.07] hover:border-brand-200 dark:hover:border-brand-700/30',
                  )}
                >
                  <input
                    type="checkbox"
                    checked={isPacked}
                    onChange={e => onToggle(key, e.target.checked)}
                    className="rounded border-slate-300 accent-emerald-600 flex-shrink-0"
                  />
                  {/* Thumbnail */}
                  {item.image_url ? (
                    <img
                      src={item.image_url}
                      alt={item.item_name}
                      className="w-9 h-10 object-cover rounded-lg flex-shrink-0 bg-slate-100 dark:bg-slate-800"
                      onError={e => { (e.target as HTMLImageElement).style.display = 'none' }}
                    />
                  ) : (
                    <div className="w-9 h-10 rounded-lg bg-slate-100 dark:bg-slate-800 flex items-center justify-center text-lg flex-shrink-0">
                      {CATEGORY_EMOJI[cat] ?? '📦'}
                    </div>
                  )}
                  <div className="flex-1 min-w-0">
                    <p className={cn(
                      'text-sm font-medium truncate',
                      isPacked ? 'line-through text-slate-400 dark:text-white/30' : 'text-slate-800 dark:text-white',
                    )}>
                      {item.item_name}
                      {item.quantity > 1 && (
                        <span className="ml-1 text-xs text-slate-400">×{item.quantity}</span>
                      )}
                    </p>
                    <div className="flex flex-wrap gap-1 mt-0.5">
                      {item.planned_days.length > 0 && (
                        <span className="text-[10px] text-slate-400">{item.planned_days.slice(0, 3).join(', ')}</span>
                      )}
                      {item.rewear_count > 1 && (
                        <span className="text-[10px] text-teal-500 flex items-center gap-0.5">
                          <RefreshCw size={8} />×{item.rewear_count}
                        </span>
                      )}
                      {item.activities.length > 0 && (
                        <span className="text-[10px] text-slate-400 truncate max-w-[100px]">
                          {item.activities.slice(0, 2).join(', ')}
                        </span>
                      )}
                    </div>
                  </div>
                  <Badge variant={badgeCfg.variant} className="flex-shrink-0 text-[9px] hidden sm:flex">
                    {badgeCfg.label}
                  </Badge>
                </label>
              )
            })}
          </div>
        </div>
      ))}
    </div>
  )
}

// ── Missing items panel ───────────────────────────────────────────────────

type MissingItem = { name?: string; item_name?: string; category: string; needed_for?: string; priority?: string; reason?: string }

function MissingItemsPanel({ items }: { items: MissingItem[] }) {
  if (items.length === 0) return null
  return (
    <GlassCard padding="lg">
      <h3 className="font-semibold text-slate-800 dark:text-white flex items-center gap-2 mb-4">
        <ShoppingCart size={16} className="text-amber-500" />
        Items to buy / borrow
        <span className="ml-auto text-xs font-normal text-slate-400 dark:text-white/30">{items.length} item{items.length !== 1 ? 's' : ''}</span>
      </h3>
      <div className="space-y-2">
        {items.map((item, i) => {
          const displayName = item.item_name ?? item.name ?? ''
          const priority = item.priority ?? 'recommended'
          const priorityColor = priority === 'essential' ? 'bg-red-50 dark:bg-red-900/10 border-red-200/60 dark:border-red-700/20' :
            priority === 'recommended' ? 'bg-amber-50/60 dark:bg-amber-900/10 border-amber-200/60 dark:border-amber-700/20' :
            'bg-slate-50 dark:bg-white/[0.03] border-slate-200 dark:border-white/[0.07]'
          return (
            <div key={i} className={cn('flex items-start gap-3 p-3 rounded-xl border', priorityColor)}>
              <ShoppingCart size={14} className="flex-shrink-0 mt-0.5 text-amber-500" />
              <div className="flex-1 min-w-0">
                <p className="text-sm font-medium text-slate-800 dark:text-white">{displayName}</p>
                {item.needed_for && <p className="text-xs text-slate-500 dark:text-white/40 capitalize">{item.needed_for}</p>}
                {item.reason && <p className="text-xs text-slate-400 dark:text-white/30 mt-0.5">{item.reason}</p>}
              </div>
              <Badge variant={priority === 'essential' ? 'red' : priority === 'recommended' ? 'amber' : 'gray'} className="flex-shrink-0 text-[9px]">
                {priority}
              </Badge>
            </div>
          )
        })}
      </div>
    </GlassCard>
  )
}

// ── Trip summary banner ───────────────────────────────────────────────────

function TripSummaryBanner({ trip, plan }: { trip: Trip; plan: PackingPlan }) {
  const duration = Math.ceil((new Date(trip.end_date).getTime() - new Date(trip.start_date).getTime()) / 86_400_000)
  const bagLabel = BAG_SIZE_OPTS.find(b => b.value === trip.bag_size)?.label ?? ''
  const bagCap = plan.bag_capacity_summary as BagCapacitySummary | null | undefined
  const statusColor = bagCap?.packing_status === 'fits' ? 'text-emerald-600 dark:text-emerald-400' :
    bagCap?.packing_status === 'tight' ? 'text-amber-600 dark:text-amber-400' :
    'text-red-600 dark:text-red-400'

  return (
    <div className="rounded-2xl border border-brand-200/60 dark:border-brand-500/20 bg-gradient-to-br from-brand-500/[0.06] via-violet-500/[0.04] to-transparent p-4 space-y-3">
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

// ── Saved planners tab ────────────────────────────────────────────────────

function SavedPlannersTab({
  closetItems,
}: { closetItems: { id: string; name: string }[] }) {
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
      ;(p.checklist_state || {}) && Object.assign(state, p.checklist_state)
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
                ? (plan.day_plans_rich).map(d => <DayPlanCard key={d.day_number} day={d} startDate={selected.start_date} />)
                : <p className="text-sm text-slate-400 dark:text-white/30 py-4">No day plans found in this saved planner.</p>}
            </div>
          )}
          {planTab === 'rewear' && <RewearStrategyPanel items={plan.rewear_strategy ?? []} />}
          {planTab === 'checklist' && (
            <PackingChecklistPanel
              items={plan.packing_checklist ?? []}
              tripId={selected.id}
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

// ── Main TravelPlanner page ───────────────────────────────────────────────

export default function TravelPlanner() {
  const { closetItems } = useApp()

  // Step state
  const [step, setStep] = useState<1 | 2 | 3>(1)
  const [activeTab, setActiveTab] = useState<'new' | 'saved'>('new')

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
      setGenError(tripApiErr(err, 'Failed to create trip and generate plan. Please try again.'))
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
    } catch (err: unknown) {
      setSaveError(tripApiErr(err, 'Failed to save planner.'))
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
      <div className="flex items-start justify-between gap-4 flex-wrap">
        <div>
          <h2 className="font-display font-bold text-xl text-slate-800 dark:text-slate-100 flex items-center gap-2">
            <Plane size={20} className="text-brand-500" /> Travel Packing Planner
          </h2>
          <p className="text-sm text-slate-400 mt-0.5">
            AI-powered day-by-day outfit plans from your closet
          </p>
        </div>
        <div className="flex rounded-xl border border-slate-200 dark:border-white/10 overflow-hidden text-sm font-medium">
          <button onClick={() => setActiveTab('new')}
            className={`px-4 py-2 transition-colors ${activeTab === 'new' ? 'bg-brand-500 text-white' : 'bg-white dark:bg-slate-900 text-slate-600 dark:text-white/60 hover:bg-slate-50 dark:hover:bg-white/5'}`}>
            New Trip
          </button>
          <button onClick={() => setActiveTab('saved')}
            className={`px-4 py-2 transition-colors flex items-center gap-1.5 ${activeTab === 'saved' ? 'bg-brand-500 text-white' : 'bg-white dark:bg-slate-900 text-slate-600 dark:text-white/60 hover:bg-slate-50 dark:hover:bg-white/5'}`}>
            <Bookmark size={13} /> Saved
          </button>
        </div>
      </div>

      {/* ── SAVED TAB ────────────────────────────────────────────────────── */}
      {activeTab === 'saved' && <SavedPlannersTab closetItems={closetItems} />}

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
                  {activities.map((act, i) => (
                    <SelectedActivityCard
                      key={act._id}
                      activity={act}
                      index={i}
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
                <div className="card p-8 flex flex-col items-center gap-3 text-slate-500 dark:text-white/40">
                  <Loader2 size={28} className="animate-spin text-brand-500" />
                  <p className="text-sm font-medium">FANI is building your personalized travel wardrobe…</p>
                  <p className="text-xs text-slate-400">Analyzing your closet · Checking weather · Planning outfits by activity</p>
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
                  <div className="rounded-2xl border border-brand-200/60 dark:border-brand-500/20 bg-gradient-to-r from-brand-500/[0.07] to-violet-500/[0.07] p-4">
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
                            <DayPlanCard key={day.day_number} day={day} startDate={trip.start_date} />
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
                      tripId={trip.id}
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
