/**
 * SimilarityWarningBanner — shown in the Upload flow after AI analysis,
 * before the user saves a new item. Displays similar/duplicate items so the
 * user can make an informed decision.
 *
 * Uses RAG (pgvector cosine similarity) on the backend to surface near-matches.
 */

import { AlertTriangle, ChevronDown, ChevronUp, Loader2, ShieldCheck, Zap } from 'lucide-react'
import { useState } from 'react'
import { cn } from '@/lib/utils'
import type { SimilarClosetItem } from '@/lib/api'
import SimilarItemCard from './SimilarItemCard'

interface Props {
  loading: boolean
  error: boolean
  items: SimilarClosetItem[]
  itemName?: string
  /** Pass the new item's preview URL for a side-by-side comparison view */
  newItemImageUrl?: string
  className?: string
}

// ── Internal helpers ──────────────────────────────────────────────────────────

function RAGBadge() {
  return (
    <span className="inline-flex items-center gap-1 text-[9px] font-bold px-2 py-0.5 rounded-full bg-brand-100 dark:bg-brand-900/30 text-brand-700 dark:text-brand-400 border border-brand-200 dark:border-brand-700/40">
      <Zap size={8} className="fill-brand-600 dark:fill-brand-400" />
      AI Vector Search
    </span>
  )
}

function ItemPlaceholder({ category }: { category: string }) {
  const emoji =
    category === 'shoes' ? '👟' :
    category === 'dresses' ? '👗' :
    category === 'accessories' ? '👜' :
    category === 'outerwear' ? '🧥' :
    category === 'bottoms' ? '👖' : '👕'
  return (
    <div className="w-full h-full flex items-center justify-center text-3xl bg-slate-50 dark:bg-slate-800">
      {emoji}
    </div>
  )
}

// ── Side-by-side comparison (only for high-confidence duplicates) ──────────────

function DuplicateComparison({
  existingItem,
  newItemImageUrl,
  itemName,
}: {
  existingItem: SimilarClosetItem
  newItemImageUrl?: string
  itemName?: string
}) {
  return (
    <div className="px-4 pb-4">
      <p className="text-[11px] font-semibold text-red-600 dark:text-red-400 mb-3 uppercase tracking-wide">
        Visual comparison
      </p>
      <div className="flex items-stretch gap-3">
        {/* New item */}
        <div className="flex-1 rounded-2xl overflow-hidden border-2 border-red-200 dark:border-red-700/50">
          <div className="h-28 bg-slate-50 dark:bg-slate-800">
            {newItemImageUrl ? (
              <img
                src={newItemImageUrl}
                alt="New item"
                className="w-full h-full object-contain"
              />
            ) : (
              <div className="w-full h-full flex items-center justify-center text-3xl">🆕</div>
            )}
          </div>
          <div className="px-2 py-1.5 bg-red-50 dark:bg-red-900/20 text-center">
            <p className="text-[10px] font-bold text-red-700 dark:text-red-400">Adding now</p>
            {itemName && <p className="text-[9px] text-red-500 dark:text-red-500 truncate">{itemName}</p>}
          </div>
        </div>

        {/* VS divider */}
        <div className="flex items-center">
          <div className="flex flex-col items-center gap-1">
            <div className="w-px h-6 bg-red-200 dark:bg-red-800" />
            <span className="text-[10px] font-extrabold text-red-400 bg-red-50 dark:bg-red-900/30 px-1.5 py-0.5 rounded-full">
              vs
            </span>
            <div className="w-px h-6 bg-red-200 dark:bg-red-800" />
          </div>
        </div>

        {/* Existing item */}
        <div className="flex-1 rounded-2xl overflow-hidden border-2 border-red-200 dark:border-red-700/50">
          <div className="h-28 bg-slate-50 dark:bg-slate-800">
            {existingItem.image_url ? (
              <img
                src={existingItem.image_url}
                alt={existingItem.name}
                className="w-full h-full object-contain"
              />
            ) : (
              <ItemPlaceholder category={existingItem.category} />
            )}
          </div>
          <div className="px-2 py-1.5 bg-red-50 dark:bg-red-900/20 text-center">
            <p className="text-[10px] font-bold text-red-700 dark:text-red-400">
              Already in closet — {existingItem.similarity_score}% match
            </p>
            <p className="text-[9px] text-red-500 dark:text-red-500 truncate">{existingItem.name}</p>
          </div>
        </div>
      </div>

      {/* Why they match */}
      {existingItem.similarity_reason && (
        <p className="mt-3 text-[11px] text-slate-600 dark:text-slate-400 bg-white/80 dark:bg-slate-800/60 rounded-xl px-3 py-2 border border-slate-100 dark:border-slate-700 leading-relaxed">
          <span className="font-semibold text-slate-700 dark:text-slate-300">Why they match: </span>
          {existingItem.similarity_reason}
        </p>
      )}
      {existingItem.difference_summary && existingItem.difference_summary !== existingItem.similarity_reason && (
        <p className="mt-1.5 text-[11px] text-slate-500 dark:text-slate-500 italic px-3 leading-relaxed">
          <span className="font-semibold not-italic">Differences: </span>
          {existingItem.difference_summary}
        </p>
      )}
    </div>
  )
}

// ── Main component ────────────────────────────────────────────────────────────

export default function SimilarityWarningBanner({ loading, error, items, itemName, newItemImageUrl, className }: Props) {
  // Collapsed by default — the header still surfaces the warning + match count,
  // so the review screen stays compact. Users expand to see the details.
  const [expanded, setExpanded] = useState(false)

  const hasDuplicate = items.some(i => i.similarity_score >= 90)
  const hasVerySimilar = items.some(i => i.similarity_score >= 75)
  const topItem = items[0]

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
        <span>FANI is scanning your closet for similar items…</span>
        <RAGBadge />
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
        <Zap size={13} className="flex-shrink-0 text-slate-400" />
        Couldn't compare similar items right now — you can still save this item.
      </div>
    )
  }

  if (items.length === 0) {
    return (
      <div className={cn(
        'flex items-center justify-between gap-2.5 px-4 py-3 rounded-2xl',
        'bg-emerald-50 dark:bg-emerald-900/10',
        'border border-emerald-200 dark:border-emerald-700/30',
        'text-xs text-emerald-700 dark:text-emerald-400',
        className,
      )}>
        <div className="flex items-center gap-2">
          <ShieldCheck size={13} className="flex-shrink-0" />
          This item looks unique in your closet — no near-matches found.
        </div>
        <RAGBadge />
      </div>
    )
  }

  const bannerConfig = hasDuplicate
    ? {
        bg: 'bg-red-50 dark:bg-red-900/10',
        border: 'border-red-300 dark:border-red-700/40',
        iconBg: 'bg-red-100 dark:bg-red-900/30',
        iconColor: 'text-red-600 dark:text-red-400',
        titleColor: 'text-red-800 dark:text-red-300',
        subtitleColor: 'text-red-600 dark:text-red-500',
        title: 'FANI found a near-identical item already in your closet',
        subtitle: `You may not need another${itemName ? ` "${itemName}"` : ''} — check the comparison below.`,
      }
    : hasVerySimilar
    ? {
        bg: 'bg-amber-50 dark:bg-amber-900/10',
        border: 'border-amber-200 dark:border-amber-700/30',
        iconBg: 'bg-amber-100 dark:bg-amber-900/30',
        iconColor: 'text-amber-600 dark:text-amber-400',
        titleColor: 'text-amber-800 dark:text-amber-300',
        subtitleColor: 'text-amber-600 dark:text-amber-500',
        title: 'You already own something very similar',
        subtitle: 'This item is close but may still add variety to your wardrobe.',
      }
    : {
        bg: 'bg-sky-50 dark:bg-sky-900/10',
        border: 'border-sky-200 dark:border-sky-700/30',
        iconBg: 'bg-sky-100 dark:bg-sky-900/30',
        iconColor: 'text-sky-600 dark:text-sky-400',
        titleColor: 'text-sky-800 dark:text-sky-300',
        subtitleColor: 'text-sky-600 dark:text-sky-500',
        title: 'Related items already in your closet',
        subtitle: 'You have some related pieces — this still adds something different.',
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
        className="w-full flex items-start justify-between gap-3 px-4 py-3 text-left"
      >
        <div className="flex items-start gap-3">
          <div className={cn('w-8 h-8 rounded-xl flex items-center justify-center flex-shrink-0 mt-0.5', bannerConfig.iconBg)}>
            <AlertTriangle size={14} className={bannerConfig.iconColor} />
          </div>
          <div className="space-y-1">
            <p className={cn('text-sm font-semibold', bannerConfig.titleColor)}>
              {bannerConfig.title}
            </p>
            <p className={cn('text-xs', bannerConfig.subtitleColor)}>
              {bannerConfig.subtitle}
            </p>
            <RAGBadge />
          </div>
        </div>
        <div className="flex items-center gap-2 flex-shrink-0 mt-0.5">
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

      {/* Expanded content */}
      {expanded && (
        <div className="border-t border-current/10">
          {/* Side-by-side comparison for near-duplicates */}
          {hasDuplicate && topItem && (
            <DuplicateComparison
              existingItem={topItem}
              newItemImageUrl={newItemImageUrl}
              itemName={itemName}
            />
          )}

          {/* List of all similar items */}
          <div className={cn('px-4 pb-4 space-y-2', hasDuplicate && 'border-t border-current/10 pt-3')}>
            {!hasDuplicate && (
              <p className="text-[11px] text-slate-500 dark:text-slate-400 pt-3">
                You can still save this item — this is just a heads-up.
              </p>
            )}
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
