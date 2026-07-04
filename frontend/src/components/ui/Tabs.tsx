import { useRef } from 'react'
import { cn } from '@/lib/utils'

export interface TabItem {
  value: string
  label: React.ReactNode
  icon?: React.ReactNode
  /** Optional badge/count shown after the label. */
  badge?: React.ReactNode
}

interface TabsProps {
  items: TabItem[]
  value: string
  onChange: (value: string) => void
  /** Accessible name for the tablist. */
  label?: string
  /** id prefix for aria-controls wiring to your panels. */
  idPrefix?: string
  className?: string
  /** Visual style. `pill` (default) or `underline`. */
  variant?: 'pill' | 'underline'
}

/**
 * Accessible tab bar implementing the WAI-ARIA tab pattern: `role="tablist"`,
 * roving focus, Arrow/Home/End keyboard navigation and `aria-selected`.
 * Render your panels with `role="tabpanel"` and
 * `id={`${idPrefix}-panel-${value}`}` + `aria-labelledby={`${idPrefix}-tab-${value}`}`.
 */
export default function Tabs({
  items,
  value,
  onChange,
  label,
  idPrefix = 'tabs',
  className,
  variant = 'pill',
}: TabsProps) {
  const refs = useRef<(HTMLButtonElement | null)[]>([])

  const focusTab = (index: number) => {
    const clamped = (index + items.length) % items.length
    const el = refs.current[clamped]
    el?.focus()
    onChange(items[clamped].value)
  }

  const onKeyDown = (e: React.KeyboardEvent, index: number) => {
    switch (e.key) {
      case 'ArrowRight':
      case 'ArrowDown':
        e.preventDefault()
        focusTab(index + 1)
        break
      case 'ArrowLeft':
      case 'ArrowUp':
        e.preventDefault()
        focusTab(index - 1)
        break
      case 'Home':
        e.preventDefault()
        focusTab(0)
        break
      case 'End':
        e.preventDefault()
        focusTab(items.length - 1)
        break
    }
  }

  return (
    <div
      role="tablist"
      aria-label={label}
      aria-orientation="horizontal"
      className={cn(
        'flex items-center gap-1 overflow-x-auto scrollbar-hide',
        variant === 'pill' &&
          'rounded-2xl border border-cream-200 bg-white/60 p-1 dark:border-white/[0.08] dark:bg-white/[0.04]',
        variant === 'underline' && 'border-b border-cream-200 dark:border-white/[0.08]',
        className,
      )}
    >
      {items.map((item, i) => {
        const selected = item.value === value
        return (
          <button
            key={item.value}
            ref={(el) => {
              refs.current[i] = el
            }}
            role="tab"
            id={`${idPrefix}-tab-${item.value}`}
            aria-selected={selected}
            aria-controls={`${idPrefix}-panel-${item.value}`}
            tabIndex={selected ? 0 : -1}
            onClick={() => onChange(item.value)}
            onKeyDown={(e) => onKeyDown(e, i)}
            className={cn(
              'inline-flex shrink-0 items-center gap-2 whitespace-nowrap text-sm font-medium transition-all duration-200',
              'focus:outline-none focus-visible:ring-2 focus-visible:ring-brand-500/60',
              variant === 'pill' && [
                'rounded-xl px-3.5 py-2 focus-visible:ring-offset-1',
                selected
                  ? 'bg-white text-slate-900 shadow-card dark:bg-white/[0.10] dark:text-white'
                  : 'text-slate-500 hover:text-slate-800 dark:text-white/50 dark:hover:text-white',
              ],
              variant === 'underline' && [
                '-mb-px border-b-2 px-3.5 py-2.5',
                selected
                  ? 'border-brand-500 text-slate-900 dark:text-white'
                  : 'border-transparent text-slate-500 hover:text-slate-800 dark:text-white/50 dark:hover:text-white',
              ],
            )}
          >
            {item.icon}
            {item.label}
            {item.badge}
          </button>
        )
      })}
    </div>
  )
}
