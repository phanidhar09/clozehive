import { AlertCircle } from 'lucide-react'
import { cn } from '@/lib/utils'

/** Inline validation / API error strip — never show raw stack traces to users. */
export function InlineError({
  message,
  className,
  children,
}: {
  message: string
  className?: string
  children?: React.ReactNode
}) {
  return (
    <div
      className={cn(
        'flex flex-wrap items-start gap-2 rounded-2xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-800 dark:border-red-500/30 dark:bg-red-500/10 dark:text-red-200',
        className,
      )}
      role="alert"
    >
      <AlertCircle className="mt-0.5 h-4 w-4 flex-shrink-0" aria-hidden />
      <div className="min-w-0 flex-1">
        <p>{message}</p>
        {children}
      </div>
    </div>
  )
}
