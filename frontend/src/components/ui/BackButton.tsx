/**
 * BackButton — a mobile-friendly, accessible back-navigation button.
 *
 * Props:
 *   fallback  — route to use when there's no history (default '/')
 *   label     — text shown next to the chevron (default 'Back')
 *   className — additional Tailwind classes
 *   onClick   — optional override; if provided, called instead of goBack()
 */

import { ChevronLeft } from 'lucide-react'
import { useBackNavigation } from '@/hooks/useBackNavigation'
import { cn } from '@/lib/utils'

interface BackButtonProps {
  fallback?: string
  label?: string
  className?: string
  onClick?: () => void
}

export function BackButton({
  fallback = '/',
  label = 'Back',
  className,
  onClick,
}: BackButtonProps) {
  const goBack = useBackNavigation({ fallback })

  return (
    <button
      type="button"
      onClick={onClick ?? goBack}
      aria-label={label}
      className={cn(
        // Base — minimum 44 × 44 px touch target (WCAG 2.5.5)
        'inline-flex items-center gap-1 min-h-[44px] px-2 -ml-1',
        'text-sm font-medium',
        // Colours (light / dark)
        'text-slate-600 hover:text-slate-900 dark:text-slate-400 dark:hover:text-slate-100',
        // Focus ring
        'rounded-lg focus:outline-none focus-visible:ring-2 focus-visible:ring-brand-500',
        // Transition
        'transition-colors duration-150',
        className,
      )}
    >
      <ChevronLeft className="h-5 w-5 shrink-0" aria-hidden="true" />
      <span>{label}</span>
    </button>
  )
}

export default BackButton
