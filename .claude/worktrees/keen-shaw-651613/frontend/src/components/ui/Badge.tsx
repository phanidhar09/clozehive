import { cn } from '@/lib/utils'

type Variant = 'purple' | 'green' | 'amber' | 'red' | 'blue' | 'pink' | 'gray' | 'teal'

const variants: Record<Variant, string> = {
  purple: 'bg-brand-50 text-brand-700 dark:bg-brand-900/30 dark:text-brand-300',
  green:  'bg-emerald-50 text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-300',
  amber:  'bg-amber-50 text-amber-700 dark:bg-amber-900/30 dark:text-amber-300',
  red:    'bg-red-50 text-red-700 dark:bg-red-900/30 dark:text-red-300',
  blue:   'bg-sky-50 text-sky-700 dark:bg-sky-900/30 dark:text-sky-300',
  pink:   'bg-pink-50 text-pink-700 dark:bg-pink-900/30 dark:text-pink-300',
  gray:   'bg-slate-100 text-slate-600 dark:bg-slate-700 dark:text-slate-300',
  teal:   'bg-teal-50 text-teal-700 dark:bg-teal-900/30 dark:text-teal-300',
}

interface Props {
  children: React.ReactNode
  variant?: Variant
  className?: string
}

export default function Badge({ children, variant = 'gray', className }: Props) {
  return (
    <span className={cn('badge', variants[variant], className)}>
      {children}
    </span>
  )
}
