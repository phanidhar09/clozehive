import { forwardRef } from 'react'
import { cn } from '@/lib/utils'

type Variant = 'solid' | 'glass'
type Padding = 'none' | 'sm' | 'md' | 'lg'

const PADDING: Record<Padding, string> = {
  none: '',
  sm: 'p-3',
  md: 'p-4 sm:p-5',
  lg: 'p-5 sm:p-6',
}

interface CardProps extends React.HTMLAttributes<HTMLDivElement> {
  /** `solid` uses the light-white/dark-glass `.card` look; `glass` is glass in both themes. */
  variant?: Variant
  /** Lift + shadow on hover (adds cursor-pointer). */
  hover?: boolean
  /** Padding preset applied to the card root. Use `none` when composing Card.Header/Body/Footer. */
  padding?: Padding
}

/**
 * Composable surface primitive. Wraps the existing `.card` / glass token system
 * so pages stop re-declaring `rounded-2xl border ... shadow` shells inline.
 */
const CardRoot = forwardRef<HTMLDivElement, CardProps>(
  ({ variant = 'solid', hover = false, padding = 'md', className, children, ...props }, ref) => (
    <div
      ref={ref}
      className={cn(
        variant === 'glass' ? 'glass-card' : 'card',
        hover && (variant === 'glass' ? 'glass-card-hover' : 'card-hover'),
        PADDING[padding],
        className,
      )}
      {...props}
    >
      {children}
    </div>
  ),
)
CardRoot.displayName = 'Card'

function CardHeader({ className, ...props }: React.HTMLAttributes<HTMLDivElement>) {
  return <div className={cn('mb-4 flex items-center justify-between gap-3', className)} {...props} />
}
CardHeader.displayName = 'Card.Header'

function CardTitle({ className, ...props }: React.HTMLAttributes<HTMLHeadingElement>) {
  return (
    <h3
      className={cn('font-display text-base font-semibold text-slate-900 dark:text-white', className)}
      {...props}
    />
  )
}
CardTitle.displayName = 'Card.Title'

function CardBody({ className, ...props }: React.HTMLAttributes<HTMLDivElement>) {
  return <div className={cn('space-y-3', className)} {...props} />
}
CardBody.displayName = 'Card.Body'

function CardFooter({ className, ...props }: React.HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      className={cn('mt-4 flex items-center justify-end gap-2 border-t pt-4', className)}
      {...props}
    />
  )
}
CardFooter.displayName = 'Card.Footer'

type CardComponent = typeof CardRoot & {
  Header: typeof CardHeader
  Title: typeof CardTitle
  Body: typeof CardBody
  Footer: typeof CardFooter
}

const Card = CardRoot as CardComponent
Card.Header = CardHeader
Card.Title = CardTitle
Card.Body = CardBody
Card.Footer = CardFooter

export default Card
