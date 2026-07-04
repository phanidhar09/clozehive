import { cn } from '@/lib/utils'

interface SwitchProps {
  checked: boolean
  onChange: (checked: boolean) => void
  /** Accessible label. Provide either this or `labelledBy`. */
  label?: string
  labelledBy?: string
  disabled?: boolean
  className?: string
}

/**
 * Accessible toggle built on a native button with `role="switch"` and
 * `aria-checked`. Keyboard operable (Space/Enter) via the underlying button.
 */
export default function Switch({
  checked,
  onChange,
  label,
  labelledBy,
  disabled,
  className,
}: SwitchProps) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      aria-label={label}
      aria-labelledby={labelledBy}
      disabled={disabled}
      onClick={() => onChange(!checked)}
      className={cn(
        'relative inline-flex h-6 w-11 shrink-0 items-center rounded-full transition-colors duration-200',
        'focus:outline-none focus-visible:ring-2 focus-visible:ring-brand-500/60 focus-visible:ring-offset-2',
        'focus-visible:ring-offset-cream-100 dark:focus-visible:ring-offset-slate-950',
        checked ? 'bg-brand-600' : 'bg-slate-300 dark:bg-white/[0.15]',
        disabled && 'cursor-not-allowed opacity-50',
        className,
      )}
    >
      <span
        aria-hidden
        className={cn(
          'inline-block h-5 w-5 transform rounded-full bg-white shadow transition-transform duration-200',
          checked ? 'translate-x-[22px]' : 'translate-x-0.5',
        )}
      />
    </button>
  )
}
