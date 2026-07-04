import { cn } from '@/lib/utils'
import { forwardRef, useId } from 'react'

interface InputProps extends React.InputHTMLAttributes<HTMLInputElement> {
  label?: string
  error?: string
  hint?: string
  leftIcon?: React.ReactNode
}

const Input = forwardRef<HTMLInputElement, InputProps>(
  ({ label, error, hint, leftIcon, className, id, ...rest }, ref) => {
    const autoId = useId()
    const fieldId = id ?? autoId
    const describedBy = error ? `${fieldId}-error` : hint ? `${fieldId}-hint` : undefined
    return (
      <div className="w-full">
        {label && (
          <label htmlFor={fieldId} className="label">
            {label}
          </label>
        )}
        <div className="relative">
          {leftIcon && (
            <div className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400 pointer-events-none">
              {leftIcon}
            </div>
          )}
          <input
            ref={ref}
            id={fieldId}
            aria-invalid={error ? true : undefined}
            aria-describedby={describedBy}
            className={cn(
              'input',
              leftIcon && 'pl-10',
              error && 'border-red-400 focus:ring-red-400',
              className,
            )}
            {...rest}
          />
        </div>
        {error && (
          <p id={`${fieldId}-error`} className="mt-1.5 text-xs text-red-500">
            {error}
          </p>
        )}
        {hint && !error && (
          <p id={`${fieldId}-hint`} className="mt-1.5 text-xs text-slate-400">
            {hint}
          </p>
        )}
      </div>
    )
  },
)

Input.displayName = 'Input'
export default Input

interface SelectProps extends React.SelectHTMLAttributes<HTMLSelectElement> {
  label?: string
  options: { value: string; label: string }[]
}

export function Select({ label, options, className, id, ...rest }: SelectProps) {
  const autoId = useId()
  const fieldId = id ?? autoId
  return (
    <div className="w-full">
      {label && (
        <label htmlFor={fieldId} className="label">
          {label}
        </label>
      )}
      <select
        id={fieldId}
        className={cn('input appearance-none bg-white dark:bg-slate-800', className)}
        {...rest}
      >
        {options.map(o => (
          <option key={o.value} value={o.value}>{o.label}</option>
        ))}
      </select>
    </div>
  )
}
