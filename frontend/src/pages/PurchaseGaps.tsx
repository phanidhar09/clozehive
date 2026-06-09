import { useEffect, useState } from 'react'
import { ShoppingBag, CheckCircle, AlertCircle, Loader2, RefreshCw, Trash2 } from 'lucide-react'
import BackButton from '@/components/ui/BackButton'
import GlassCard from '@/components/ui/GlassCard'
import PageHeader from '@/components/ui/PageHeader'
import Badge from '@/components/ui/Badge'
import { purchaseGapsApi, type PurchaseGap } from '@/lib/api'
import { cn } from '@/lib/utils'

const PRIORITY_COLORS: Record<string, string> = {
  high:   'bg-red-100    text-red-700    dark:bg-red-900/30  dark:text-red-400',
  medium: 'bg-amber-100  text-amber-700  dark:bg-amber-900/30 dark:text-amber-400',
  low:    'bg-slate-100  text-slate-600  dark:bg-white/10    dark:text-white/50',
}

function priorityLabel(score: number | null): 'high' | 'medium' | 'low' {
  if (score == null) return 'low'
  if (score >= 7) return 'high'
  if (score >= 4) return 'medium'
  return 'low'
}

function GapCard({ gap, onResolve, onDelete }: { gap: PurchaseGap; onResolve: (id: string) => void; onDelete: (id: string) => void }) {
  const [resolving, setResolving] = useState(false)
  const [deleting, setDeleting] = useState(false)
  const [confirmingDelete, setConfirmingDelete] = useState(false)
  const level = priorityLabel(gap.priority_score)

  const handleResolve = async () => {
    setResolving(true)
    try {
      await purchaseGapsApi.resolve(gap.id)
      onResolve(gap.id)
    } catch {
      setResolving(false)
    }
  }

  const handleDelete = async () => {
    if (!confirmingDelete) {
      setConfirmingDelete(true)
      setTimeout(() => setConfirmingDelete(false), 3000)
      return
    }
    setConfirmingDelete(false)
    setDeleting(true)
    try {
      await purchaseGapsApi.delete(gap.id)
      onDelete(gap.id)
    } catch {
      setDeleting(false)
    }
  }

  return (
    <GlassCard className="p-4 flex flex-col gap-3">
      <div className="flex items-start justify-between gap-2">
        <div className="flex items-center gap-2 flex-wrap">
          <span className={cn('text-xs font-semibold px-2 py-0.5 rounded-full capitalize', PRIORITY_COLORS[level])}>
            {level} priority
          </span>
          {gap.gap_type && (
            <Badge variant="gray" className="text-xs capitalize">
              {gap.gap_type.replace(/_/g, ' ')}
            </Badge>
          )}
        </div>
        {gap.priority_score != null && (
          <span className="text-xs text-slate-400 dark:text-white/40 shrink-0">
            Score {gap.priority_score.toFixed(1)}
          </span>
        )}
      </div>

      <div>
        <p className="font-semibold text-slate-800 dark:text-white capitalize">
          {gap.missing_category || 'Unknown category'}
          {gap.missing_color && ` · ${gap.missing_color}`}
          {gap.missing_season && ` · ${gap.missing_season}`}
        </p>
        {gap.missing_occasion && (
          <p className="text-xs text-slate-500 dark:text-white/50 mt-0.5 capitalize">
            Occasion: {gap.missing_occasion}
          </p>
        )}
      </div>

      {gap.reason && (
        <p className="text-sm text-slate-600 dark:text-white/60">{gap.reason}</p>
      )}

      {gap.suggested_attributes && Object.keys(gap.suggested_attributes).length > 0 && (
        <div className="flex flex-wrap gap-1.5">
          {Object.entries(gap.suggested_attributes).map(([k, v]) => (
            <span key={k} className="text-[11px] px-2 py-0.5 rounded-full bg-brand-50 dark:bg-brand-900/30 text-brand-600 dark:text-brand-400 capitalize">
              {k}: {String(v)}
            </span>
          ))}
        </div>
      )}

      <div className="flex items-center justify-end gap-2">
        <button
          onClick={handleDelete}
          disabled={deleting}
          aria-label={confirmingDelete ? 'Confirm delete gap' : 'Delete gap'}
          className={cn(
            'flex items-center gap-1.5 text-xs font-medium px-3 py-1.5 rounded-lg transition-colors disabled:opacity-50',
            confirmingDelete
              ? 'bg-red-500 text-white'
              : 'bg-slate-100 dark:bg-white/[0.06] text-slate-500 dark:text-white/50 hover:bg-red-50 dark:hover:bg-red-900/20 hover:text-red-500',
          )}
        >
          {deleting ? <Loader2 size={12} className="animate-spin" /> : <Trash2 size={12} />}
          {deleting ? 'Deleting…' : confirmingDelete ? 'Delete?' : 'Delete'}
        </button>
        <button
          onClick={handleResolve}
          disabled={resolving}
          className="flex items-center gap-1.5 text-xs font-medium px-3 py-1.5 rounded-lg
                     bg-emerald-50 dark:bg-emerald-900/20 text-emerald-700 dark:text-emerald-400
                     hover:bg-emerald-100 dark:hover:bg-emerald-900/40 transition-colors disabled:opacity-50"
        >
          {resolving ? <Loader2 size={12} className="animate-spin" /> : <CheckCircle size={12} />}
          {resolving ? 'Resolving…' : 'Mark resolved'}
        </button>
      </div>
    </GlassCard>
  )
}

export default function PurchaseGaps() {
  const [gaps, setGaps] = useState<PurchaseGap[]>([])
  const [showResolved, setShowResolved] = useState(false)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const load = async (resolved: boolean) => {
    setLoading(true)
    setError(null)
    try {
      const data = await purchaseGapsApi.list(resolved)
      setGaps(data.gaps)
    } catch {
      setError('Failed to load wardrobe gaps.')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    load(showResolved)
  }, [showResolved])

  const handleResolve = (id: string) => {
    setGaps(prev => prev.filter(g => g.id !== id))
  }

  const handleDelete = (id: string) => {
    setGaps(prev => prev.filter(g => g.id !== id))
  }

  return (
    <div className="max-w-3xl space-y-6">
      <BackButton fallback="/dashboard" label="Back to Dashboard" />
      {/* Header */}
      <PageHeader
        icon={<ShoppingBag size={18} />}
        chipClassName="bg-gradient-to-br from-amber-500 to-orange-600 shadow-glow-sm"
        iconColor="text-white"
        title="Wardrobe Gaps"
        subtitle="Items your wardrobe is missing based on your outfits and trips"
        actions={
          <>
            <button
              onClick={() => load(showResolved)}
              className="p-2 rounded-lg text-slate-400 hover:text-slate-700 dark:hover:text-white hover:bg-slate-100 dark:hover:bg-white/10 transition-colors"
              title="Refresh"
            >
              <RefreshCw size={16} />
            </button>
            <label className="flex items-center gap-2 text-sm text-slate-600 dark:text-white/60 cursor-pointer">
              <input
                type="checkbox"
                checked={showResolved}
                onChange={e => setShowResolved(e.target.checked)}
                className="rounded"
              />
              Show resolved
            </label>
          </>
        }
      />

      {/* Content */}
      {loading ? (
        <div className="flex items-center justify-center py-20 text-slate-400 dark:text-white/40">
          <Loader2 size={28} className="animate-spin" />
        </div>
      ) : error ? (
        <GlassCard className="p-6 flex items-center gap-3 text-red-600 dark:text-red-400">
          <AlertCircle size={20} />
          <p className="text-sm">{error}</p>
        </GlassCard>
      ) : gaps.length === 0 ? (
        <GlassCard className="p-10 text-center space-y-3">
          <CheckCircle size={36} className="mx-auto text-emerald-500" />
          <p className="font-semibold text-slate-700 dark:text-white">
            {showResolved ? 'No resolved gaps found.' : 'Your wardrobe looks complete!'}
          </p>
          <p className="text-sm text-slate-500 dark:text-white/50">
            {showResolved
              ? 'Gaps you mark as resolved will appear here.'
              : 'As you build outfits and pack for trips, any missing items will appear here.'}
          </p>
        </GlassCard>
      ) : (
        <div className="grid gap-4 sm:grid-cols-2">
          {gaps.map(gap => (
            <GapCard key={gap.id} gap={gap} onResolve={handleResolve} onDelete={handleDelete} />
          ))}
        </div>
      )}
    </div>
  )
}
