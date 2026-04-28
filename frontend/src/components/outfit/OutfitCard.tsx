import { Star, Sparkles } from 'lucide-react'
import type { OutfitSuggestion } from '@/types'
import Badge from '@/components/ui/Badge'
import { cn } from '@/lib/utils'

interface Props {
  outfit: OutfitSuggestion
  rank?: number
  compact?: boolean
}

const RANK_COLORS = ['from-amber-400 to-orange-400', 'from-slate-400 to-slate-500', 'from-amber-600 to-amber-700']

export default function OutfitCard({ outfit, rank, compact }: Props) {
  return (
    <div className={cn('card p-4 space-y-3 hover:shadow-card-hover transition-all duration-200', compact && 'p-3')}>
      {/* Header */}
      <div className="flex items-start justify-between gap-2">
        <div className="flex items-center gap-2">
          {rank !== undefined && rank < 3 && (
            <div className={cn('w-6 h-6 rounded-full bg-gradient-to-br flex items-center justify-center text-white text-[10px] font-bold flex-shrink-0', RANK_COLORS[rank])}>
              {rank + 1}
            </div>
          )}
          <div>
            <h3 className="font-semibold text-sm text-slate-800 dark:text-slate-100">{outfit.name}</h3>
            {outfit.occasion_fit && !compact && (
              <p className="text-xs text-slate-400 mt-0.5">{outfit.occasion_fit}</p>
            )}
          </div>
        </div>
        <div className="flex items-center gap-1 flex-shrink-0">
          <Star size={12} className="text-amber-400 fill-amber-400" />
          <span className="text-xs font-semibold text-slate-700 dark:text-slate-300">{outfit.style_score?.toFixed(1)}</span>
        </div>
      </div>

      {/* Item thumbnails */}
      {outfit.items && outfit.items.length > 0 && (
        <div className="flex gap-2">
          {outfit.items.slice(0, 4).map((item, i) => (
            <div
              key={item.id ?? i}
              className="w-14 h-14 rounded-xl overflow-hidden bg-cream-100 dark:bg-slate-700 flex-shrink-0 border border-cream-300 dark:border-slate-600"
            >
              {item.image_url ? (
                <img src={item.image_url} alt={item.name} className="w-full h-full object-cover" />
              ) : (
                <div className="w-full h-full flex items-center justify-center text-xl">
                  {item.category === 'shoes' ? '👟' : item.category === 'bottoms' ? '👖' : '👕'}
                </div>
              )}
            </div>
          ))}
          {(outfit.items.length > 4) && (
            <div className="w-14 h-14 rounded-xl bg-cream-100 dark:bg-slate-700 border border-cream-300 dark:border-slate-600 flex items-center justify-center text-xs font-medium text-slate-500">
              +{outfit.items.length - 4}
            </div>
          )}
        </div>
      )}

      {/* Explanation */}
      {!compact && (
        <div className="flex items-start gap-2 bg-brand-50 dark:bg-brand-900/20 rounded-xl p-3">
          <Sparkles size={14} className="text-brand-500 mt-0.5 flex-shrink-0" />
          <p className="text-xs text-slate-600 dark:text-slate-300 leading-relaxed">{outfit.explanation}</p>
        </div>
      )}

      {/* Tags */}
      <div className="flex gap-1.5 flex-wrap">
        {outfit.weather_fit && <Badge variant="blue">{outfit.weather_fit}</Badge>}
      </div>
    </div>
  )
}
