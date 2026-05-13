import { RefreshCw } from 'lucide-react'
import { cn } from '@/lib/utils'

export function RetryButton({
  children = 'Try again',
  onClick,
  disabled,
  className,
}: {
  children?: React.ReactNode
  onClick: () => void
  disabled?: boolean
  className?: string
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      className={cn(
        'inline-flex items-center gap-2 rounded-2xl border border-slate-200 bg-white px-4 py-2 text-sm font-semibold text-slate-800 shadow-sm transition hover:bg-slate-50 disabled:opacity-50 dark:border-white/10 dark:bg-white/5 dark:text-white dark:hover:bg-white/10',
        className,
      )}
    >
      <RefreshCw size={14} aria-hidden />
      {children}
    </button>
  )
}
