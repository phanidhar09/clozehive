import type { Category } from '@/types'

/** Tabs use canonical API categories; "other" also catches legacy `uncategorised` / unknown labels. */
export const CANONICAL_TAB_CATEGORIES = new Set([
  'tops', 'bottoms', 'shoes', 'outerwear', 'dresses', 'accessories',
])

export const CLOSET_CATEGORY_TABS: { value: Category; label: string; emoji: string }[] = [
  { value: 'all',        label: 'All',         emoji: '✨' },
  { value: 'tops',       label: 'Tops',        emoji: '👕' },
  { value: 'bottoms',    label: 'Bottoms',     emoji: '👖' },
  { value: 'shoes',      label: 'Shoes',       emoji: '👟' },
  { value: 'outerwear',  label: 'Outerwear',   emoji: '🧥' },
  { value: 'dresses',    label: 'Dresses',     emoji: '👗' },
  { value: 'accessories',label: 'Accessories', emoji: '👜' },
  { value: 'other',      label: 'Other',       emoji: '📦' },
]

export const CLOSET_SORT_OPTIONS = [
  { value: 'recent', label: 'Recently added' },
  { value: 'worn',   label: 'Most worn' },
  { value: 'name',   label: 'Name A–Z' },
]

export const CLOSET_SEASONS = ['spring', 'summer', 'fall', 'winter'] as const

/** Standard everyday occasions shown as the primary chip row */
export const CLOSET_OCCASIONS = [
  'casual', 'formal', 'work', 'sport', 'evening', 'travel',
  'party', 'date night', 'beach', 'gym', 'wedding',
] as const

/** Cultural, religious, and festival occasions — shown in a second chip row */
export const CLOSET_CULTURAL_OCCASIONS = [
  'diwali', 'navratri', 'holi', 'durga puja', 'eid', 'ramadan',
  'christmas', 'hanukkah', 'thanksgiving', 'onam', 'pongal',
  'baisakhi', 'chinese new year', 'raksha bandhan', 'new year',
] as const
