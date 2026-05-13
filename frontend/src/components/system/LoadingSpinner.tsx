import { Loader2 } from 'lucide-react'
import { cn } from '@/lib/utils'

type Size = 'sm' | 'md' | 'lg'

const sizeMap: Record<Size, string> = {
  sm: 'h-5 w-5',
  md: 'h-8 w-8',
  lg: 'h-10 w-10',
}

export function LoadingSpinner({
  className,
  size = 'md',
  label,
}: {
  className?: string
  size?: Size
  /** Accessibility label */
  label?: string
}) {
  return (
    <Loader2
      className={cn('animate-spin text-brand-500', sizeMap[size], className)}
      aria-hidden={label ? undefined : true}
      aria-label={label ?? 'Loading'}
    />
  )
}
