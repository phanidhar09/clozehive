import { Check } from 'lucide-react'
import { cn } from '@/lib/utils'
import { ACTIVITY_PRESETS } from './constants'

// ── Activity chip card ────────────────────────────────────────────────────

export function ActivityChip({
  preset, selected, onClick,
}: { preset: typeof ACTIVITY_PRESETS[0]; selected: boolean; onClick: () => void }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        'flex items-center gap-2 px-3 py-2 rounded-xl border text-sm font-medium transition-all',
        selected
          ? 'bg-brand-50 dark:bg-brand-900/30 border-brand-300 dark:border-brand-600 text-brand-700 dark:text-brand-300 shadow-sm'
          : 'bg-white dark:bg-white/5 border-slate-200 dark:border-white/10 text-slate-700 dark:text-slate-300 hover:border-brand-300 dark:hover:border-brand-700',
      )}
    >
      <span className="text-base">{preset.emoji}</span>
      <span className="truncate">{preset.name}</span>
      {selected && <Check size={12} className="flex-shrink-0 text-brand-500" />}
    </button>
  )
}
