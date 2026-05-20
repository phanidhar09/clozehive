import { useEffect, useState } from 'react'
import { Sparkles, Loader2 } from 'lucide-react'
import { closetSimilarityApi, type SimilarClosetItem } from '@/lib/api'
import { cn } from '@/lib/utils'

interface Props {
  itemId: string
  limit?: number
}

export default function SimilarItems({ itemId, limit = 6 }: Props) {
  const [items, setItems] = useState<SimilarClosetItem[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    closetSimilarityApi.getSimilarToItem(itemId, limit)
      .then(data => { if (!cancelled) setItems(data.results) })
      .catch(() => { if (!cancelled) setItems([]) })
      .finally(() => { if (!cancelled) setLoading(false) })
    return () => { cancelled = true }
  }, [itemId, limit])

  if (loading) {
    return (
      <div className="flex items-center gap-2 text-xs text-slate-400 dark:text-white/40 py-2">
        <Loader2 size={12} className="animate-spin" /> Finding similar items…
      </div>
    )
  }

  if (items.length === 0) return null

  return (
    <div className="space-y-2.5">
      <p className="text-xs font-semibold uppercase tracking-widest text-slate-400 dark:text-white/40 flex items-center gap-1.5">
        <Sparkles size={11} /> Similar in your closet
      </p>

      <div
        className="flex gap-2.5 overflow-x-auto pb-1"
        style={{ scrollbarWidth: 'none' }}
      >
        {items.map(item => (
          <div
            key={item.item_id}
            title={item.reason || item.name}
            className={cn(
              'flex-shrink-0 w-[72px] rounded-xl overflow-hidden',
              'bg-slate-50 dark:bg-white/[0.06]',
              'border border-cream-200 dark:border-white/[0.07]',
              'hover:border-indigo-300 dark:hover:border-indigo-500/40',
              'transition-all duration-200 group cursor-default',
            )}
          >
            {/* Portrait image */}
            <div className="relative aspect-[3/4] bg-slate-100 dark:bg-slate-800 overflow-hidden">
              {item.image_url ? (
                <img
                  src={item.image_url}
                  alt={item.name}
                  className="w-full h-full object-cover group-hover:scale-105 transition-transform duration-300"
                />
              ) : (
                <div className="w-full h-full flex items-center justify-center text-xl">👕</div>
              )}
              {/* Similarity badge */}
              <span className="absolute top-1 right-1 text-[9px] font-bold leading-none bg-black/55 text-white rounded-full px-1.5 py-0.5">
                {Math.round(item.similarity_score * 100)}%
              </span>
            </div>

            {/* Label */}
            <div className="px-1.5 py-1.5">
              <p className="text-[10px] font-semibold text-slate-700 dark:text-white truncate leading-tight">
                {item.name}
              </p>
              <p className="text-[9px] text-slate-400 dark:text-white/40 capitalize">
                {item.category}
              </p>
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}
