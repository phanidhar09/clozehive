import { useId, useState } from 'react'
import { cn } from '@/lib/utils'

type Side = 'top' | 'bottom' | 'left' | 'right'

interface TooltipProps {
  content: React.ReactNode
  side?: Side
  className?: string
  children: React.ReactElement
}

const SIDE: Record<Side, string> = {
  top: 'bottom-full left-1/2 -translate-x-1/2 mb-2',
  bottom: 'top-full left-1/2 -translate-x-1/2 mt-2',
  left: 'right-full top-1/2 -translate-y-1/2 mr-2',
  right: 'left-full top-1/2 -translate-y-1/2 ml-2',
}

/**
 * Lightweight, dependency-free tooltip. Shows on hover and keyboard focus,
 * hides on Escape, and links trigger + bubble with `aria-describedby` so it is
 * announced by screen readers. Wrap a single focusable child.
 */
export default function Tooltip({ content, side = 'top', className, children }: TooltipProps) {
  const [open, setOpen] = useState(false)
  const id = useId()

  return (
    <span
      className="relative inline-flex"
      onMouseEnter={() => setOpen(true)}
      onMouseLeave={() => setOpen(false)}
      onFocus={() => setOpen(true)}
      onBlur={() => setOpen(false)}
      onKeyDown={(e) => {
        if (e.key === 'Escape') setOpen(false)
      }}
    >
      <span aria-describedby={open ? id : undefined} className="inline-flex">
        {children}
      </span>
      {open && (
        <span
          role="tooltip"
          id={id}
          className={cn(
            'pointer-events-none absolute z-50 whitespace-nowrap rounded-lg px-2.5 py-1.5 text-xs font-medium shadow-lg',
            'bg-slate-900 text-white dark:bg-white dark:text-slate-900',
            'animate-fade-in',
            SIDE[side],
            className,
          )}
        >
          {content}
        </span>
      )}
    </span>
  )
}
