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
  { value: 'eco',    label: 'Eco score' },
  { value: 'name',   label: 'Name A–Z' },
]

export const CLOSET_SEASONS = ['spring', 'summer', 'fall', 'winter'] as const
export const CLOSET_OCCASIONS = ['casual', 'formal', 'work', 'sport', 'evening', 'travel'] as const
