/**
 * SimilarityWarningBanner — shown in the Upload flow after AI analysis,
 * before the user saves a new item. Displays similar/duplicate items so the
 * user can make an informed decision.
 */

import { AlertTriangle, ChevronDown, ChevronUp, Loader2, ShieldCheck, Sparkles } from 'lucide-react'
import { useState } from 'react'
import { cn } from '@/lib/utils'
import type { SimilarClosetItem } from '@/lib/api'
import SimilarItemCard from './SimilarItemCard'

interface Props {
  loading: boolean
  error: boolean
  items: SimilarClosetItem[]
  itemName?: string
  className?: string
}

export default function SimilarityWarningBanner({ loading, error, items, itemName, className }: Props) {
  const [expanded, setExpanded] = useState(true)

  // Determine the severity
  const hasDuplicate = items.some(i => i.similarity_score >= 90)
  const hasVerySimilar = items.some(i => i.similarity_score >= 75)

  if (loading) {
    return (
      <div className={cn(
        'flex items-center gap-2.5 px-4 py-3 rounded-2xl',
        'bg-slate-50 dark:bg-white/[0.04]',
        'border border-slate-200 dark:border-white/[0.08]',
        'text-xs text-slate-500 dark:text-slate-400',
        className,
      )}>
        <Loader2 size={13} className="animate-spin flex-shrink-0 text-brand-500" />
        Checking your closet for similar items…
      </div>
    )
  }

  if (error) {
    return (
      <div className={cn(
        'flex items-center gap-2.5 px-4 py-3 rounded-2xl',
        'bg-slate-50 dark:bg-white/[0.04]',
        'border border-slate-200 dark:border-white/[0.08]',
        'text-xs text-slate-400 dark:text-slate-500',
        className,
      )}>
        <Sparkles size={13} className="flex-shrink-0 text-slate-400" />
        Couldn't compare similar items right now — you can still save this item.
      </div>
    )
  }

  if (items.length === 0) {
    return (
      <div className={cn(
        'flex items-center gap-2.5 px-4 py-3 rounded-2xl',
        'bg-emerald-50 dark:bg-emerald-900/10',
        'border border-emerald-200 dark:border-emerald-700/30',
        'text-xs text-emerald-700 dark:text-emerald-400',
        className,
      )}>
        <ShieldCheck size={13} className="flex-shrink-0" />
        This looks unique in your closet — no similar items found.
      </div>
    )
  }

  // There are similar items — show warning
  const bannerConfig = hasDuplicate
    ? {
        bg: 'bg-red-50 dark:bg-red-900/10',
        border: 'border-red-200 dark:border-red-700/30',
        iconBg: 'bg-red-100 dark:bg-red-900/30',
        iconColor: 'text-red-600 dark:text-red-400',
        titleColor: 'text-red-800 dark:text-red-300',
        subtitleColor: 'text-red-600 dark:text-red-400',
        title: 'Possible duplicate detected',
        subtitle: `You may already own something very similar${itemName ? ` to "${itemName}"` : ''}.`,
      }
    : hasVerySimilar
    ? {
        bg: 'bg-amber-50 dark:bg-amber-900/10',
        border: 'border-amber-200 dark:border-amber-700/30',
        iconBg: 'bg-amber-100 dark:bg-amber-900/30',
        iconColor: 'text-amber-600 dark:text-amber-400',
        titleColor: 'text-amber-800 dark:text-amber-300',
        subtitleColor: 'text-amber-600 dark:text-amber-400',
        title: 'Similar items already in closet',
        subtitle: 'This item is similar but may still add variety to your wardrobe.',
      }
    : {
        bg: 'bg-sky-50 dark:bg-sky-900/10',
        border: 'border-sky-200 dark:border-sky-700/30',
        iconBg: 'bg-sky-100 dark:bg-sky-900/30',
        iconColor: 'text-sky-600 dark:text-sky-400',
        titleColor: 'text-sky-800 dark:text-sky-300',
        subtitleColor: 'text-sky-600 dark:text-sky-400',
        title: 'Related items already in closet',
        subtitle: 'You have some related items — this one still adds something different.',
      }

  return (
    <div className={cn(
      'rounded-2xl border overflow-hidden',
      bannerConfig.bg,
      bannerConfig.border,
      className,
    )}>
      {/* Header row */}
      <button
        type="button"
        onClick={() => setExpanded(v => !v)}
        className="w-full flex items-center justify-between gap-3 px-4 py-3 text-left"
      >
        <div className="flex items-center gap-3">
          <div className={cn('w-8 h-8 rounded-xl flex items-center justify-center flex-shrink-0', bannerConfig.iconBg)}>
            <AlertTriangle size={14} className={bannerConfig.iconColor} />
          </div>
          <div>
            <p className={cn('text-sm font-semibold', bannerConfig.titleColor)}>
              {bannerConfig.title}
            </p>
            <p className={cn('text-xs mt-0.5', bannerConfig.subtitleColor)}>
              {bannerConfig.subtitle}
            </p>
          </div>
        </div>
        <div className="flex items-center gap-2 flex-shrink-0">
          <span className={cn(
            'text-[11px] font-bold px-2 py-0.5 rounded-full',
            bannerConfig.iconBg, bannerConfig.iconColor,
          )}>
            {items.length} found
          </span>
          {expanded
            ? <ChevronUp size={14} className={bannerConfig.iconColor} />
            : <ChevronDown size={14} className={bannerConfig.iconColor} />}
        </div>
      </button>

      {/* Expanded items */}
      {expanded && (
        <div className="px-4 pb-4 space-y-2 border-t border-current/10">
          <p className="text-[11px] text-slate-500 dark:text-slate-400 pt-3">
            You can still save this item — this is just a heads up.
          </p>
          <div className="space-y-2">
            {items.map(item => (
              <SimilarItemCard
                key={item.item_id || item.id}
                item={item}
                compact
              />
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
