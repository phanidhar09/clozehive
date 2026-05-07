import { Link } from 'react-router-dom'
import { cn } from '@/lib/utils'

interface ActionConfig {
  label: string
  /** Internal route — renders a <Link>. Provide either href OR onClick, not both. */
  href?: string
  onClick?: () => void
  /** Accessible label override (defaults to label) */
  ariaLabel?: string
}

interface EmptyStateProps {
  /** Lucide icon element or any ReactNode. Rendered at 32×32 inside the icon bubble. */
  icon: React.ReactNode
  title: string
  description: string
  primaryAction?: ActionConfig
  secondaryAction?: ActionConfig
  /**
   * page   — full-section centered layout with generous padding (default)
   * card   — wrapped in a glass card; smaller vertical padding
   * inline — compact horizontal-friendly strip; minimal padding
   */
  variant?: 'page' | 'card' | 'inline'
  className?: string
}

function ActionButton({
  action,
  variant,
}: {
  action: ActionConfig
  variant: 'primary' | 'secondary'
}) {
  const base =
    'inline-flex items-center justify-center gap-2 rounded-xl px-5 py-2.5 text-sm font-semibold transition-all duration-200 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-500 focus-visible:ring-offset-2'

  const styles = {
    primary:
      'bg-gradient-to-r from-brand-500 to-violet-600 text-white shadow-md shadow-brand-500/25 hover:shadow-brand-500/40 hover:-translate-y-0.5 active:translate-y-0',
    secondary:
      'border border-slate-200 dark:border-white/10 bg-white/70 dark:bg-white/5 text-slate-700 dark:text-white/80 hover:bg-white dark:hover:bg-white/10 hover:-translate-y-0.5 active:translate-y-0 backdrop-blur-sm',
  }

  const cls = cn(base, styles[variant])
  const label = action.ariaLabel ?? action.label

  if (action.href) {
    return (
      <Link to={action.href} className={cls} aria-label={label}>
        {action.label}
      </Link>
    )
  }

  return (
    <button type="button" onClick={action.onClick} className={cls} aria-label={label}>
      {action.label}
    </button>
  )
}

export default function EmptyState({
  icon,
  title,
  description,
  primaryAction,
  secondaryAction,
  variant = 'page',
  className,
}: EmptyStateProps) {
  const isInline = variant === 'inline'

  const wrapper = cn(
    'relative overflow-hidden',
    variant === 'page' && 'rounded-3xl border border-dashed border-slate-200 dark:border-white/8 py-16 px-6',
    variant === 'card' && 'rounded-3xl border border-cream-200 dark:border-white/10 bg-white/60 dark:bg-white/[0.03] shadow-card py-12 px-6',
    variant === 'inline' && 'rounded-2xl border border-slate-200 dark:border-white/10 bg-white/50 dark:bg-white/[0.03] py-10 px-6',
    className,
  )

  const iconSize = isInline ? 24 : 32

  return (
    <div className={wrapper} role="status" aria-label={title}>
      {/* Ambient glow */}
      <div
        aria-hidden="true"
        className="pointer-events-none absolute left-1/2 top-1/2 h-64 w-64 -translate-x-1/2 -translate-y-1/2 rounded-full bg-brand-500/[0.06] dark:bg-brand-400/[0.04] blur-3xl"
      />

      <div className="relative flex flex-col items-center text-center">
        {/* Icon bubble */}
        <div
          aria-hidden="true"
          className={cn(
            'mb-5 flex items-center justify-center rounded-2xl',
            'bg-gradient-to-br from-brand-500/10 to-violet-500/10 dark:from-brand-400/10 dark:to-violet-400/10',
            'ring-1 ring-brand-200/60 dark:ring-brand-500/20',
            isInline ? 'h-14 w-14 rounded-xl' : 'h-20 w-20',
          )}
        >
          <span className="text-brand-500 dark:text-brand-400">
            {/* Clone with explicit size so callers don't need to pass size prop */}
            {typeof icon === 'object' && icon !== null
              ? (() => {
                  const el = icon as React.ReactElement
                  try {
                    return { ...el, props: { ...el.props, size: iconSize } }
                  } catch {
                    return icon
                  }
                })()
              : icon}
          </span>
        </div>

        {/* Text */}
        <h3
          className={cn(
            'font-display font-bold text-slate-800 dark:text-white mb-2',
            isInline ? 'text-base' : 'text-xl',
          )}
        >
          {title}
        </h3>
        <p
          className={cn(
            'text-slate-500 dark:text-white/50 leading-relaxed max-w-sm',
            isInline ? 'text-xs' : 'text-sm',
          )}
        >
          {description}
        </p>

        {/* CTAs */}
        {(primaryAction || secondaryAction) && (
          <div className={cn('flex flex-wrap items-center justify-center gap-3', isInline ? 'mt-5' : 'mt-7')}>
            {primaryAction && <ActionButton action={primaryAction} variant="primary" />}
            {secondaryAction && <ActionButton action={secondaryAction} variant="secondary" />}
          </div>
        )}
      </div>
    </div>
  )
}
