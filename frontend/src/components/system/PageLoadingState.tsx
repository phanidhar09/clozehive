import { FaniLoader } from '@/components/system/FaniLoader'
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
        'flex min-h-[240px] flex-col items-center justify-center rounded-3xl border border-cream-200 bg-white/70 p-10 text-center dark:border-white/10 dark:bg-white/[0.04]',
        className,
      )}
    >
      <FaniLoader
        size="md"
        messages={title ? [title] : undefined}
        {...(description ? { subline: description } : {})}
      />
    </div>
  )
}
