import type { ClosetItem, StyleTag } from '@/types'

const STYLE_KEYWORDS: Record<StyleTag, string[]> = {
  casual: ['cotton', 'tee', 't-shirt', 'denim', 'sneaker', 'hoodie', 'jogger', 'everyday'],
  formal: ['suit', 'blazer', 'dress shirt', 'oxford', 'heel', 'tailored'],
  streetwear: ['street', 'graphic', 'cargo', 'cap', 'bucket', 'oversized'],
  sporty: ['sport', 'athletic', 'gym', 'runner', 'track', 'performance'],
  minimal: ['minimal', 'plain', 'neutral', 'simple', 'monochrome'],
  business: ['business', 'work', 'office', 'slacks', 'loafer'],
  boho: ['boho', 'floral', 'fringe', 'lace', 'crochet'],
  vintage: ['vintage', 'retro', 'classic', 'heritage'],
  preppy: ['preppy', 'polo', 'plaid', 'boat'],
  elegant: ['elegant', 'silk', 'satin', 'evening'],
}

export interface ClosetInsight {
  totalItems: number
  confident: boolean
  dominantStyle: StyleTag | null
  scores: Partial<Record<StyleTag, number>>
  topColors: Array<{ color: string; count: number }>
  topCategories: Array<{ category: string; count: number }>
}

/**
 * Lightweight on-device closet stats for Profile tabs (no API call).
 */
export function analyzeCloset(items: ClosetItem[]): ClosetInsight {
  const totalItems = items.length
  if (totalItems === 0) {
    return {
      totalItems: 0,
      confident: false,
      dominantStyle: null,
      scores: {},
      topColors: [],
      topCategories: [],
    }
  }

  const colorCounts = new Map<string, number>()
  const categoryCounts = new Map<string, number>()
  const scores: Partial<Record<StyleTag, number>> = {}
  for (const tag of Object.keys(STYLE_KEYWORDS) as StyleTag[]) scores[tag] = 0

  const haystackFor = (item: ClosetItem): string => {
    const parts = [
      item.name,
      item.category,
      item.color,
      item.pattern,
      item.brand,
      item.notes,
      ...(item.tags ?? []),
      ...(item.occasion ?? []),
      Array.isArray(item.season) ? item.season.join(' ') : (item.season ?? ''),
    ]
    return parts.filter(Boolean).join(' ').toLowerCase()
  }

  for (const item of items) {
    const cat = (item.category || 'other').toLowerCase()
    categoryCounts.set(cat, (categoryCounts.get(cat) ?? 0) + 1)

    const col = (item.color || '').trim().toLowerCase()
    if (col) colorCounts.set(col, (colorCounts.get(col) ?? 0) + 1)

    const text = haystackFor(item)
    for (const [style, keywords] of Object.entries(STYLE_KEYWORDS) as [StyleTag, string[]][]) {
      let add = 0
      for (const kw of keywords) {
        if (text.includes(kw)) add += 1
      }
      scores[style] = (scores[style] ?? 0) + add + (cat.includes(style) ? 2 : 0)
    }
  }

  const topColors = [...colorCounts.entries()]
    .map(([color, count]) => ({ color, count }))
    .sort((a, b) => b.count - a.count)
    .slice(0, 8)

  const topCategories = [...categoryCounts.entries()]
    .map(([category, count]) => ({ category, count }))
    .sort((a, b) => b.count - a.count)

  const rankedStyles = (Object.entries(scores) as [StyleTag, number][])
    .filter(([, v]) => v > 0)
    .sort((a, b) => b[1] - a[1])

  const dominantStyle = rankedStyles.length > 0 ? rankedStyles[0][0] : null
  const confident = totalItems >= 10 && (rankedStyles[0]?.[1] ?? 0) >= 3

  return {
    totalItems,
    confident,
    dominantStyle,
    scores,
    topColors,
    topCategories,
  }
}
