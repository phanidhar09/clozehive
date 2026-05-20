import { useState } from 'react'
import { Bookmark, ThumbsUp, ThumbsDown, RefreshCw, Star, ChevronDown, ChevronUp, Sparkles } from 'lucide-react'
import { cn } from '@/lib/utils'
import { resolveUploadUrl } from '@/lib/api'
import { saveRecommendedOutfit, submitOutfitFeedback } from '@/services/aiChatApi'
import type { RecommendedOutfit, AIChatItemRef } from '@/types'

interface Props {
  outfit: RecommendedOutfit
  rank?: number
  sessionId?: string
  onRegenerate?: () => void
}

function ScoreBadge({ score }: { score: number }) {
  const colour =
    score >= 85 ? 'bg-emerald-500' :
    score >= 70 ? 'bg-brand-500' :
    score >= 55 ? 'bg-amber-500' : 'bg-slate-400'
  return (
    <span className={cn('inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-white text-xs font-semibold', colour)}>
      <Star size={10} className="fill-white" />
      {score}
    </span>
  )
}

function ItemThumb({ item }: { item: AIChatItemRef }) {
  const src = resolveUploadUrl(item.image_url ?? undefined)
  return (
    <div className="flex flex-col items-center gap-1 w-14 flex-shrink-0">
      <div className="w-14 h-14 rounded-xl overflow-hidden bg-slate-100 dark:bg-slate-800 border border-cream-200 dark:border-slate-700 shadow-sm flex items-center justify-center">
        {src ? (
          <img src={src} alt={item.name} className="w-full h-full object-cover" />
        ) : (
          <div className="w-full h-full flex items-center justify-center text-slate-400 text-[10px] text-center px-1 leading-tight">
            {item.category}
          </div>
        )}
      </div>
      <span className="text-[9px] text-slate-500 dark:text-slate-400 text-center leading-tight max-w-[56px] truncate">
        {item.name}
      </span>
    </div>
  )
}

function ScoreBar({ label, value, max }: { label: string; value: number; max: number }) {
  const pct = Math.round((value / max) * 100)
  return (
    <div className="flex items-center gap-2 text-xs">
      <span className="w-20 text-slate-500 dark:text-slate-400 capitalize">{label}</span>
      <div className="flex-1 h-1.5 bg-slate-100 dark:bg-slate-700 rounded-full overflow-hidden">
        <div
          className="h-full rounded-full bg-gradient-to-r from-brand-400 to-violet-500"
          style={{ width: `${pct}%` }}
        />
      </div>
      <span className="w-8 text-right text-slate-600 dark:text-slate-300 font-medium">{value}/{max}</span>
    </div>
  )
}

export default function OutfitRecommendationCard({ outfit, rank = 0, sessionId, onRegenerate }: Props) {
  const [expanded, setExpanded] = useState(rank === 0)
  const [saving, setSaving] = useState(false)
  const [saved, setSaved] = useState(false)
  const [feedbackSent, setFeedbackSent] = useState<'up' | 'down' | null>(null)
  const [saveError, setSaveError] = useState<string | null>(null)

  const handleSave = async () => {
    if (saving || saved) return
    setSaving(true)
    setSaveError(null)
    try {
      await saveRecommendedOutfit({
        name: outfit.title,
        item_ids: outfit.items.map(i => i.id),
        occasion: 'casual',
        explanation: outfit.reasoning,
        style_score: outfit.matching_score,
        session_id: sessionId ?? null,
      })
      setSaved(true)
    } catch {
      setSaveError('Could not save — try again')
    } finally {
      setSaving(false)
    }
  }

  const handleFeedback = async (type: 'up' | 'down') => {
    if (feedbackSent) return
    setFeedbackSent(type)
    try {
      await submitOutfitFeedback({
        closet_item_ids: outfit.items.map(i => i.id),
        rating: type === 'up' ? 5 : 2,
        feedback_text: type === 'up' ? 'Loved this outfit' : 'Not for me',
      })
    } catch {
      // fire-and-forget feedback
    }
  }

  const scoreBreakdown = outfit.score_breakdown
  const scoreEntries: Array<[string, number, number]> = scoreBreakdown
    ? [
        ['Color', scoreBreakdown.color, 25],
        ['Occasion', scoreBreakdown.occasion, 25],
        ['Fit', scoreBreakdown.fit, 20],
        ['Style', scoreBreakdown.style, 15],
        ['Weather', scoreBreakdown.weather, 10],
        ['Preference', scoreBreakdown.preference, 5],
      ]
    : []

  return (
    <div className={cn(
      'card rounded-2xl overflow-hidden transition-shadow',
      expanded ? 'shadow-card-hover' : 'shadow-card',
    )}>
      {/* Header */}
      <button
        onClick={() => setExpanded(v => !v)}
        className="w-full flex items-center justify-between px-4 py-3 hover:bg-slate-50 dark:hover:bg-slate-800/50 transition-colors"
      >
        <div className="flex items-center gap-2">
          <div className="w-6 h-6 rounded-lg bg-gradient-brand flex items-center justify-center flex-shrink-0">
            <Sparkles size={12} className="text-white" />
          </div>
          <span className="font-semibold text-sm text-slate-800 dark:text-slate-100 truncate max-w-[180px]">
            {outfit.title}
          </span>
          <ScoreBadge score={outfit.matching_score} />
        </div>
        {expanded ? (
          <ChevronUp size={15} className="text-slate-400 flex-shrink-0" />
        ) : (
          <ChevronDown size={15} className="text-slate-400 flex-shrink-0" />
        )}
      </button>

      {expanded && (
        <div className="px-4 pb-4 space-y-4 border-t border-cream-200 dark:border-slate-700 pt-3">

          {/* Item thumbnails */}
          <div className="flex gap-2 overflow-x-auto pb-1">
            {outfit.items.map((item, i) => (
              <ItemThumb key={item.id + i} item={item} />
            ))}
            {outfit.items.length === 0 && (
              <p className="text-xs text-slate-400 italic">No closet items matched</p>
            )}
          </div>

          {/* Occasion match badge */}
          {outfit.occasion_match && (
            <div className="flex items-center gap-2">
              <span className="text-xs text-slate-500 dark:text-slate-400">Occasion match:</span>
              <span className={cn(
                'text-xs font-medium px-2 py-0.5 rounded-full',
                outfit.occasion_match === 'High'
                  ? 'bg-emerald-100 dark:bg-emerald-900/30 text-emerald-700 dark:text-emerald-400'
                  : outfit.occasion_match === 'Medium'
                  ? 'bg-amber-100 dark:bg-amber-900/30 text-amber-700 dark:text-amber-400'
                  : 'bg-red-100 dark:bg-red-900/30 text-red-700 dark:text-red-400',
              )}>
                {outfit.occasion_match}
              </span>
            </div>
          )}

          {/* Score breakdown */}
          {scoreEntries.length > 0 && (
            <div className="space-y-1.5">
              {scoreEntries.map(([label, val, max]) => (
                <ScoreBar key={label} label={label} value={val} max={max} />
              ))}
            </div>
          )}

          {/* Reasoning */}
          <p className="text-xs text-slate-600 dark:text-slate-300 leading-relaxed">
            {outfit.reasoning}
          </p>

          {/* Fashion rules used */}
          {outfit.fashion_rules_used?.length > 0 && (
            <div className="flex flex-wrap gap-1">
              {outfit.fashion_rules_used.map(rule => (
                <span
                  key={rule}
                  className="text-[10px] px-2 py-0.5 rounded-full bg-brand-50 dark:bg-brand-900/30 text-brand-700 dark:text-brand-300 border border-brand-200 dark:border-brand-800"
                >
                  {rule}
                </span>
              ))}
            </div>
          )}

          {/* Improvement tips */}
          {outfit.improvement_tips?.length > 0 && (
            <div className="space-y-1">
              <p className="text-[10px] font-semibold text-slate-500 dark:text-slate-400 uppercase tracking-wide">
                Tips
              </p>
              {outfit.improvement_tips.map((tip, i) => (
                <p key={i} className="text-xs text-slate-600 dark:text-slate-300 flex gap-2">
                  <span className="text-brand-400 flex-shrink-0">→</span>
                  {tip}
                </p>
              ))}
            </div>
          )}

          {/* Actions */}
          <div className="flex items-center justify-between pt-1 border-t border-cream-100 dark:border-slate-700">
            <div className="flex gap-2">
              <button
                onClick={() => handleFeedback('up')}
                className={cn(
                  'p-1.5 rounded-lg transition-colors',
                  feedbackSent === 'up'
                    ? 'bg-emerald-100 dark:bg-emerald-900/40 text-emerald-600'
                    : 'hover:bg-slate-100 dark:hover:bg-slate-700 text-slate-400',
                )}
                title="Love this outfit"
              >
                <ThumbsUp size={14} />
              </button>
              <button
                onClick={() => handleFeedback('down')}
                className={cn(
                  'p-1.5 rounded-lg transition-colors',
                  feedbackSent === 'down'
                    ? 'bg-red-100 dark:bg-red-900/40 text-red-500'
                    : 'hover:bg-slate-100 dark:hover:bg-slate-700 text-slate-400',
                )}
                title="Not for me"
              >
                <ThumbsDown size={14} />
              </button>
              {onRegenerate && (
                <button
                  onClick={onRegenerate}
                  className="p-1.5 rounded-lg hover:bg-slate-100 dark:hover:bg-slate-700 text-slate-400 transition-colors"
                  title="Regenerate"
                >
                  <RefreshCw size={14} />
                </button>
              )}
            </div>

            <div className="flex flex-col items-end gap-0.5">
              <button
                onClick={handleSave}
                disabled={saving || saved || outfit.items.length === 0}
                className={cn(
                  'flex items-center gap-1.5 px-3 py-1.5 rounded-xl text-xs font-medium transition-all',
                  saved
                    ? 'bg-emerald-100 dark:bg-emerald-900/30 text-emerald-700 dark:text-emerald-400'
                    : 'bg-gradient-brand text-white hover:opacity-90 disabled:opacity-40',
                )}
              >
                <Bookmark size={12} className={saved ? 'fill-emerald-600' : ''} />
                {saved ? 'Saved!' : saving ? 'Saving…' : 'Save Outfit'}
              </button>
              {saveError && (
                <span className="text-[10px] text-red-500">{saveError}</span>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
