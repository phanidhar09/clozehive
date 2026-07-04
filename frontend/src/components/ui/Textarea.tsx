import { forwardRef, useId } from 'react'
import { cn } from '@/lib/utils'

interface TextareaProps extends React.TextareaHTMLAttributes<HTMLTextAreaElement> {
  label?: string
  error?: string
  hint?: string
}

/**
 * Textarea matching the `.input` token system with proper label association
 * and `aria-invalid` / `aria-describedby` wiring for accessibility.
 */
const Textarea = forwardRef<HTMLTextAreaElement, TextareaProps>(
  ({ label, error, hint, className, id, rows = 4, ...rest }, ref) => {
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
        <textarea
          ref={ref}
          id={fieldId}
          rows={rows}
          aria-invalid={error ? true : undefined}
          aria-describedby={describedBy}
          className={cn('input resize-y', error && 'border-red-400 focus:ring-red-400', className)}
          {...rest}
        />
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

Textarea.displayName = 'Textarea'
export default Textarea
