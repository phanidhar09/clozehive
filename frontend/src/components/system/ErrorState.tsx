import { AlertTriangle } from 'lucide-react'
import GlassCard from '@/components/ui/GlassCard'
import { RetryButton } from '@/components/system/RetryButton'
import { cn } from '@/lib/utils'

export function ErrorState({
  title = 'Something went wrong',
  message,
  onRetry,
  retryLabel = 'Try again',
  className,
}: {
  title?: string
  message: string
  onRetry?: () => void
  retryLabel?: string
  className?: string
}) {
  return (
    <div className={cn('flex justify-center p-4', className)}>
      <GlassCard padding="lg" className="max-w-md w-full text-center">
        <div className="mx-auto mb-3 flex h-12 w-12 items-center justify-center rounded-2xl bg-red-50 dark:bg-red-900/20">
          <AlertTriangle className="h-6 w-6 text-red-500" aria-hidden />
        </div>
        <h2 className="font-display text-lg font-bold text-slate-800 dark:text-white">{title}</h2>
        <p className="mt-1 text-sm text-slate-600 dark:text-slate-400">{message}</p>
        {onRetry && (
          <div className="mt-4">
            <RetryButton onClick={onRetry}>{retryLabel}</RetryButton>
          </div>
        )}
      </GlassCard>
    </div>
  )
}
