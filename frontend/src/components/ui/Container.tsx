import { forwardRef } from 'react'
import { cn } from '@/lib/utils'

type Size = 'sm' | 'md' | 'lg' | 'xl' | 'full'

const MAX_WIDTH: Record<Size, string> = {
  sm: 'max-w-2xl',
  md: 'max-w-4xl',
  lg: 'max-w-5xl',
  xl: 'max-w-6xl',
  full: 'max-w-none',
}

interface ContainerProps extends React.HTMLAttributes<HTMLDivElement> {
  /** Max content width preset. Defaults to `xl` (max-w-6xl). */
  size?: Size
}

/**
 * Single source of truth for page content width. Centers content and applies a
 * responsive max width so every page reads consistently across breakpoints
 * instead of each page hand-picking `max-w-2xl..6xl`.
 */
const Container = forwardRef<HTMLDivElement, ContainerProps>(
  ({ size = 'xl', className, children, ...props }, ref) => (
    <div ref={ref} className={cn('mx-auto w-full', MAX_WIDTH[size], className)} {...props}>
      {children}
    </div>
  ),
)

Container.displayName = 'Container'
export default Container
