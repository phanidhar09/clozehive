import { cn } from '@/lib/utils'

/** Skeleton block for cards/lists — use with animate-pulse parent or standalone. */
export function LoadingSkeleton({ className }: { className?: string }) {
  return (
    <div
      className={cn(
        'animate-pulse rounded-2xl bg-slate-200/80 dark:bg-white/[0.08]',
        className,
      )}
      aria-hidden
    />
  )
}

export function LoadingSkeletonText({ lines = 3, className }: { lines?: number; className?: string }) {
  return (
    <div className={cn('space-y-2', className)} aria-hidden>
      {Array.from({ length: lines }).map((_, i) => (
        <LoadingSkeleton
          key={i}
          className={cn('h-3', i === lines - 1 ? 'w-2/3' : 'w-full')}
        />
      ))}
    </div>
  )
}
