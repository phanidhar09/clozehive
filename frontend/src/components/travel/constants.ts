/**
 * Shared constants, option lists, and helpers for the Travel Planner.
 * Extracted from pages/TravelPlanner.tsx.
 */

import type { TripActivity } from '@/types'

// ── Error extractor ────────────────────────────────────────────────────────

export function tripApiErr(err: unknown, fallback: string): string {
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

export const DESTINATIONS = [
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

export const PURPOSE_OPTIONS = [
  { value: 'leisure', label: '🌴 Leisure / Holiday' },
  { value: 'business', label: '💼 Business' },
  { value: 'beach', label: '🏖️ Beach / Resort' },
  { value: 'formal', label: '🎩 Formal Event' },
  { value: 'adventure', label: '🏔️ Adventure / Hiking' },
]

export const TRIP_STYLE_OPTS = [
  { value: 'casual', label: 'Casual', emoji: '😎' },
  { value: 'smart_casual', label: 'Smart Casual', emoji: '👔' },
  { value: 'chic', label: 'Chic', emoji: '✨' },
  { value: 'business', label: 'Business', emoji: '💼' },
  { value: 'sporty', label: 'Sporty', emoji: '🏃' },
  { value: 'beach', label: 'Beach Vibes', emoji: '🏖️' },
  { value: 'boho', label: 'Boho', emoji: '🌸' },
  { value: 'streetwear', label: 'Streetwear', emoji: '🎒' },
]

export const BAG_SIZE_OPTS = [
  { value: 'backpack', label: '🎒 Backpack only', desc: '1-2 outfits/day, strong rewear' },
  { value: 'carry_on', label: '🧳 Carry-on', desc: '4-5 tops, 2-3 bottoms, 1-2 shoes' },
  { value: 'medium_suitcase', label: '🧳 Medium Suitcase', desc: '6-8 tops, 3-4 bottoms, 2-3 shoes' },
  { value: 'large_suitcase', label: '🧳 Large Suitcase', desc: 'Full variety, minimal limits' },
  { value: 'none', label: '❓ Not sure yet', desc: 'AI will suggest what to pack' },
]

export const ACTIVITY_PRESETS: { id: string; name: string; emoji: string; formality: string; time_of_day: string }[] = [
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

export const TIME_OF_DAY_OPTS = [
  { value: 'morning', label: '🌅 Morning' },
  { value: 'afternoon', label: '☀️ Afternoon' },
  { value: 'evening', label: '🌆 Evening' },
  { value: 'night', label: '🌙 Night' },
  { value: 'full_day', label: '🕐 Full Day' },
]

export const FORMALITY_OPTS = [
  { value: 'casual', label: '😎 Casual' },
  { value: 'smart_casual', label: '👔 Smart Casual' },
  { value: 'formal', label: '🎩 Formal' },
  { value: 'active', label: '🏃 Active' },
  { value: 'beachwear', label: '🏖️ Beachwear' },
  { value: 'business', label: '💼 Business' },
]

export const CATEGORY_EMOJI: Record<string, string> = {
  tops: '👕', bottoms: '👖', shoes: '👟', outerwear: '🧥', accessories: '👜',
  dresses: '👗', innerwear: '🩲', sleepwear: '😴', toiletries: '🧴',
  travel_essentials: '✈️', essentials: '✅', general: '📦',
}

export const SOURCE_BADGE: Record<string, { label: string; variant: 'green' | 'amber' | 'gray' | 'blue' }> = {
  from_closet: { label: 'In Closet', variant: 'green' },
  missing_recommended: { label: 'Buy / Borrow', variant: 'amber' },
  optional: { label: 'Optional', variant: 'gray' },
  essential: { label: 'Essential', variant: 'blue' },
  custom: { label: 'Custom', variant: 'gray' },
}

export interface ActivityDraft extends TripActivity {
  _id: string  // local UUID
}
