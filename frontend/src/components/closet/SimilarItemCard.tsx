/**
 * SimilarItemCard — renders a single similar closet item with score, label, reason, and diff.
 * Used in both the SimilarItems panel (detail view) and the SimilarityWarningBanner (upload flow).
 */

import { Copy, Layers, Link2 } from 'lucide-react'
import { cn } from '@/lib/utils'
import type { SimilarClosetItem } from '@/lib/api'

interface Props {
  item: SimilarClosetItem
  /** Compact mode for upload-flow warning banner */
  compact?: boolean
  /** Called when "View Details" is clicked */
  onViewDetails?: (itemId: string) => void
  className?: string
}

function LabelBadge({ label }: { label: string }) {
  const cfg = LABEL_CONFIG[label] ?? LABEL_CONFIG['Related item']
  return (
    <span className={cn('inline-flex items-center gap-1 text-[10px] font-bold px-2 py-0.5 rounded-full', cfg.bg, cfg.text)}>
      <cfg.Icon size={9} />
      {label}
    </span>
  )
}

function ScoreRing({ score }: { score: number }) {
  const color =
    score >= 90 ? 'text-red-500 dark:text-red-400' :
    score >= 75 ? 'text-amber-500 dark:text-amber-400' :
    'text-sky-500 dark:text-sky-400'
  return (
    <span className={cn('text-xs font-bold tabular-nums', color)}>
      {score}%
    </span>
  )
}

const LABEL_CONFIG: Record<string, { bg: string; text: string; Icon: React.ElementType }> = {
  'Possible duplicate': {
    bg: 'bg-red-100 dark:bg-red-900/30',
    text: 'text-red-700 dark:text-red-400',
    Icon: Copy,
  },
  'Very similar': {
    bg: 'bg-amber-100 dark:bg-amber-900/30',
    text: 'text-amber-700 dark:text-amber-400',
    Icon: Layers,
  },
  'Related item': {
    bg: 'bg-sky-100 dark:bg-sky-900/30',
    text: 'text-sky-700 dark:text-sky-400',
    Icon: Link2,
  },
}

function ImagePlaceholder({ category }: { category: string }) {
  const emoji =
    category === 'shoes' ? '👟' :
    category === 'dresses' ? '👗' :
    category === 'accessories' ? '👜' :
    category === 'outerwear' ? '🧥' :
    category === 'bottoms' ? '👖' : '👕'
  return (
    <div className="w-full h-full flex items-center justify-center text-2xl bg-slate-100 dark:bg-slate-800">
      {emoji}
    </div>
  )
}

export default function SimilarItemCard({ item, compact = false, onViewDetails, className }: Props) {
  const label = item.similarity_label || 'Related item'

  if (compact) {
    return (
      <div className={cn(
        'flex items-center gap-3 p-3 rounded-2xl border transition-all duration-200',
        'bg-white/80 dark:bg-white/[0.05]',
        'border-cream-200 dark:border-white/[0.08]',
        'hover:border-slate-300 dark:hover:border-white/[0.15]',
        className,
      )}>
        {/* Thumbnail */}
        <div className="w-14 h-16 flex-shrink-0 rounded-xl overflow-hidden bg-slate-100 dark:bg-slate-800 border border-cream-200 dark:border-white/[0.07]">
          {item.image_url ? (
            <img
              src={item.image_url}
              alt={item.name}
              className="w-full h-full object-cover"
              onError={e => { (e.target as HTMLImageElement).style.display = 'none' }}
            />
          ) : (
            <ImagePlaceholder category={item.category} />
          )}
        </div>

        {/* Info */}
        <div className="flex-1 min-w-0">
          <div className="flex items-center justify-between gap-2 mb-0.5">
            <p className="text-sm font-semibold text-slate-800 dark:text-white truncate">{item.name}</p>
            <ScoreRing score={item.similarity_score} />
          </div>
          <LabelBadge label={label} />
          {item.similarity_reason && (
            <p className="text-[11px] text-slate-500 dark:text-slate-400 mt-1 line-clamp-2 leading-relaxed">
              {item.similarity_reason}
            </p>
          )}
        </div>

        {onViewDetails && (
          <button
            onClick={() => onViewDetails(item.id || item.item_id)}
            className="flex-shrink-0 text-[10px] font-semibold text-brand-600 dark:text-brand-400 hover:underline"
          >
            View
          </button>
        )}
      </div>
    )
  }

  // Full card (for detail modal)
  return (
    <div className={cn(
      'rounded-2xl overflow-hidden border transition-all duration-200',
      'bg-white dark:bg-white/[0.04]',
      'border-cream-200 dark:border-white/[0.08]',
      'hover:shadow-card-hover dark:hover:border-white/[0.14] hover:-translate-y-0.5',
      className,
    )}>
      {/* Image */}
      <div className="relative aspect-[3/4] bg-slate-100 dark:bg-slate-800 overflow-hidden">
        {item.image_url ? (
          <img
            src={item.image_url}
            alt={item.name}
            className="w-full h-full object-cover"
            onError={e => { (e.target as HTMLImageElement).style.display = 'none' }}
          />
        ) : (
          <ImagePlaceholder category={item.category} />
        )}
        {/* Score overlay */}
        <div className="absolute top-2 right-2 bg-black/60 backdrop-blur-sm rounded-full px-1.5 py-0.5">
          <ScoreRing score={item.similarity_score} />
        </div>
      </div>

      {/* Content */}
      <div className="p-3 space-y-2">
        <div>
          <p className="text-sm font-semibold text-slate-800 dark:text-white truncate">{item.name}</p>
          <p className="text-[11px] text-slate-400 dark:text-slate-500 capitalize">{item.category}</p>
        </div>

        <LabelBadge label={label} />

        {item.similarity_reason && (
          <p className="text-[11px] text-slate-500 dark:text-slate-400 leading-relaxed line-clamp-2">
            {item.similarity_reason}
          </p>
        )}

        {item.difference_summary && item.difference_summary !== item.similarity_reason && (
          <p className="text-[11px] text-slate-400 dark:text-slate-500 leading-relaxed line-clamp-2 italic">
            {item.difference_summary}
          </p>
        )}

        {onViewDetails && (
          <button
            onClick={() => onViewDetails(item.id || item.item_id)}
            className="w-full text-[11px] font-semibold text-brand-600 dark:text-brand-400 hover:text-brand-700 dark:hover:text-brand-300 py-1.5 rounded-xl border border-brand-200 dark:border-brand-800 hover:bg-brand-50 dark:hover:bg-brand-900/20 transition-colors"
          >
            View Details
          </button>
        )}
      </div>
    </div>
  )
}
