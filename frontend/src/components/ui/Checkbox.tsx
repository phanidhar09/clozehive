import { forwardRef, useId } from 'react'
import { Check } from 'lucide-react'
import { cn } from '@/lib/utils'

interface CheckboxProps
  extends Omit<React.InputHTMLAttributes<HTMLInputElement>, 'type' | 'size'> {
  label?: React.ReactNode
}

/**
 * Styled checkbox that keeps a real, focusable native `<input type="checkbox">`
 * for full keyboard + assistive-tech support, with a custom visual on top.
 */
const Checkbox = forwardRef<HTMLInputElement, CheckboxProps>(
  ({ label, className, id, disabled, ...rest }, ref) => {
    const autoId = useId()
    const inputId = id ?? autoId
    return (
      <label
        htmlFor={inputId}
        className={cn(
          'group inline-flex cursor-pointer items-center gap-2.5 text-sm text-slate-700 dark:text-white/80',
          disabled && 'cursor-not-allowed opacity-50',
          className,
        )}
      >
        <span className="relative inline-flex h-5 w-5 items-center justify-center">
          <input
            ref={ref}
            id={inputId}
            type="checkbox"
            disabled={disabled}
            className="peer absolute inset-0 h-full w-full cursor-pointer appearance-none rounded-md border border-cream-300 bg-white transition-colors checked:border-brand-600 checked:bg-brand-600 focus:outline-none focus-visible:ring-2 focus-visible:ring-brand-500/60 focus-visible:ring-offset-1 disabled:cursor-not-allowed dark:border-white/[0.15] dark:bg-white/[0.05] dark:checked:border-brand-500 dark:checked:bg-brand-600"
            {...rest}
          />
          <Check
            size={13}
            strokeWidth={3}
            className="pointer-events-none text-white opacity-0 transition-opacity peer-checked:opacity-100"
            aria-hidden
          />
        </span>
        {label && <span>{label}</span>}
      </label>
    )
  },
)

Checkbox.displayName = 'Checkbox'
export default Checkbox
