/**
 * SimilarItems — panel shown inside the item detail modal.
 * Fetches similar items from /closet/items/{id}/similar and renders them.
 */

import { useEffect, useState } from 'react'
import { Layers, Loader2, Sparkles } from 'lucide-react'
import { closetSimilarityApi, type SimilarClosetItem } from '@/lib/api'
import SimilarItemCard from './SimilarItemCard'

interface Props {
  itemId: string
  /** Called when user clicks "View Details" on a similar item */
  onViewItem?: (itemId: string) => void
  limit?: number
}

export default function SimilarItems({ itemId, onViewItem, limit = 6 }: Props) {
  const [items, setItems] = useState<SimilarClosetItem[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(false)

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    setError(false)
    closetSimilarityApi.getSimilarForItem(itemId, limit)
      .then(data => {
        if (!cancelled) setItems(data)
      })
      .catch(() => {
        if (!cancelled) { setItems([]); setError(true) }
      })
      .finally(() => { if (!cancelled) setLoading(false) })
    return () => { cancelled = true }
  }, [itemId, limit])

  return (
    <div className="space-y-3">
      {/* Header */}
      <div className="flex items-center gap-2">
        <div className="w-5 h-5 rounded-lg bg-gradient-to-br from-brand-500 to-brand-500 flex items-center justify-center flex-shrink-0">
          <Layers size={10} className="text-white" />
        </div>
        <p className="text-xs font-bold uppercase tracking-widest text-slate-500 dark:text-white/40">
          Similar in your closet
        </p>
      </div>

      {/* Loading */}
      {loading && (
        <div className="flex items-center gap-2 py-4 text-xs text-slate-400 dark:text-white/30">
          <Loader2 size={13} className="animate-spin flex-shrink-0" />
          Checking your closet for similar items…
        </div>
      )}

      {/* Error */}
      {!loading && error && (
        <p className="text-xs text-slate-400 dark:text-white/30 py-2">
          Couldn't check for similar items right now.
        </p>
      )}

      {/* Empty */}
      {!loading && !error && items.length === 0 && (
        <div className="flex items-start gap-2 rounded-xl bg-emerald-50 dark:bg-emerald-900/10 border border-emerald-200 dark:border-emerald-700/30 px-3 py-2.5">
          <Sparkles size={13} className="text-emerald-500 flex-shrink-0 mt-0.5" />
          <p className="text-xs text-emerald-700 dark:text-emerald-400 leading-relaxed">
            This item adds something unique to your closet — no close matches found.
          </p>
        </div>
      )}

      {/* Cards */}
      {!loading && items.length > 0 && (
        <div className="grid grid-cols-2 sm:grid-cols-3 gap-2.5">
          {items.map(item => (
            <SimilarItemCard
              key={item.item_id || item.id}
              item={item}
              onViewDetails={onViewItem}
            />
          ))}
        </div>
      )}
    </div>
  )
}
