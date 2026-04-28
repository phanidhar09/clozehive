import { Heart, Leaf } from 'lucide-react'
import type { ClosetItem } from '@/types'
import { cn, ecoScoreBg, timeAgo } from '@/lib/utils'

interface Props {
  item: ClosetItem
  onClick: () => void
}

export default function ClosetItemCard({ item, onClick }: Props) {
  return (
    <div
      onClick={onClick}
      className="group card-hover overflow-hidden cursor-pointer"
    >
      {/* Image */}
      <div className="relative aspect-[3/4] overflow-hidden bg-cream-100 dark:bg-slate-700">
        {item.image_url ? (
          <img
            src={item.image_url}
            alt={item.name}
            className="w-full h-full object-cover transition-transform duration-500 group-hover:scale-105"
            loading="lazy"
          />
        ) : (
          <div className="w-full h-full flex flex-col items-center justify-center text-slate-300 dark:text-slate-600">
            <span className="text-4xl mb-2">
              {item.category === 'shoes' ? '👟' : item.category === 'bottoms' ? '👖' : item.category === 'dresses' ? '👗' : '👕'}
            </span>
            <span className="text-xs">{item.category}</span>
          </div>
        )}

        {/* Overlay badges */}
        <div className="absolute top-2 left-2 right-2 flex items-start justify-between gap-1">
          {item.is_favorite && (
            <span className="p-1.5 rounded-full bg-white/90 dark:bg-slate-900/90 shadow-sm">
              <Heart size={12} className="text-pink-500 fill-pink-500" />
            </span>
          )}
          {item.eco_score && (
            <span className={cn('badge text-[10px] ml-auto', ecoScoreBg(item.eco_score))}>
              <Leaf size={9} />
              {item.eco_score}/10
            </span>
          )}
        </div>

        {/* Hover reveal */}
        <div className="absolute inset-x-0 bottom-0 bg-gradient-to-t from-black/60 to-transparent p-3 translate-y-full group-hover:translate-y-0 transition-transform duration-300">
          <div className="flex gap-1.5 flex-wrap">
            {item.occasion.slice(0, 2).map(o => (
              <span key={o} className="text-[10px] font-medium px-2 py-0.5 rounded-full bg-white/20 text-white backdrop-blur-sm">{o}</span>
            ))}
          </div>
        </div>
      </div>

      {/* Info */}
      <div className="p-3">
        <p className="font-semibold text-sm text-slate-800 dark:text-slate-100 truncate">{item.name}</p>
        <div className="flex items-center justify-between mt-1">
          <span className="text-xs text-slate-400">{item.brand || item.fabric || item.category}</span>
          {item.last_worn && (
            <span className="text-[10px] text-slate-400">{timeAgo(item.last_worn)}</span>
          )}
        </div>
        {/* Color dot + wear count */}
        <div className="flex items-center gap-2 mt-2">
          {item.color_hex && (
            <span
              className="w-3.5 h-3.5 rounded-full border border-cream-300 dark:border-slate-600 flex-shrink-0"
              style={{ backgroundColor: item.color_hex }}
            />
          )}
          <span className="text-[11px] text-slate-500 dark:text-slate-400">{item.color}</span>
          <span className="ml-auto text-[11px] text-slate-400">{item.wear_count}× worn</span>
        </div>
      </div>
    </div>
  )
}
