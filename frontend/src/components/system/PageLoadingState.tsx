import { LoadingSpinner } from '@/components/system/LoadingSpinner'
import { cn } from '@/lib/utils'

export function PageLoadingState({
  title = 'Loading…',
  description,
  className,
}: {
  title?: string
  description?: string
  className?: string
}) {
  return (
    <div
      className={cn(
        'flex min-h-[240px] flex-col items-center justify-center gap-3 rounded-3xl border border-cream-200 bg-white/70 p-10 text-center dark:border-white/10 dark:bg-white/[0.04]',
        className,
      )}
      role="status"
      aria-live="polite"
      aria-busy="true"
    >
      <LoadingSpinner size="lg" label={title} />
      <p className="font-medium text-slate-700 dark:text-slate-200">{title}</p>
      {description && (
        <p className="max-w-sm text-sm text-slate-500 dark:text-slate-400">{description}</p>
      )}
    </div>
  )
}
