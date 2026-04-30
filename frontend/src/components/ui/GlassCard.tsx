import { forwardRef } from 'react'
import { cn } from '@/lib/utils'

interface GlassCardProps extends React.HTMLAttributes<HTMLDivElement> {
  /** Enable lift + glow on hover */
  hover?: boolean
  /** Extra indigo glow ring on hover */
  glow?: boolean
  /** Padding preset */
  padding?: 'none' | 'sm' | 'md' | 'lg'
}

const PADDING = {
  none: '',
  sm:   'p-3',
  md:   'p-4',
  lg:   'p-6',
} as const

/**
 * Premium glass-morphism card.
 * Light mode: white/80 with cream border.
 * Dark mode:  white/4 backdrop-blur with subtle glow on hover.
 */
const GlassCard = forwardRef<HTMLDivElement, GlassCardProps>(
  ({ className, hover = false, glow = false, padding = 'md', children, ...props }, ref) => (
    <div
      ref={ref}
      className={cn(
        // Base glass surface
        'rounded-2xl border border-cream-200/70 dark:border-white/[0.08]',
        'bg-white/70 dark:bg-white/[0.04]',
        'backdrop-blur-xl',
        'shadow-glass-card',
        PADDING[padding],
        // Hover lift
        hover && [
          'transition-all duration-300 cursor-pointer',
          'hover:-translate-y-1',
          'hover:bg-white/90 dark:hover:bg-white/[0.07]',
          'hover:border-cream-300 dark:hover:border-white/[0.14]',
          'hover:shadow-card-hover dark:hover:shadow-glass-card-hover',
        ],
        // Extra indigo glow ring
        glow && 'dark:hover:border-glow',
        className,
      )}
      {...props}
    >
      {children}
    </div>
  ),
)

GlassCard.displayName = 'GlassCard'
export default GlassCard
