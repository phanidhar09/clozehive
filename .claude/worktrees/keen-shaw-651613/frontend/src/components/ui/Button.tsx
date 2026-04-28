import { cn } from '@/lib/utils'
import { Loader2 } from 'lucide-react'

type Variant = 'primary' | 'secondary' | 'ghost' | 'danger'
type Size = 'sm' | 'md' | 'lg'

const variants: Record<Variant, string> = {
  primary: 'btn-primary',
  secondary: 'btn-secondary',
  ghost: 'btn-ghost',
  danger: 'inline-flex items-center justify-center gap-2 px-5 py-2.5 rounded-xl font-semibold text-sm bg-red-600 text-white hover:bg-red-700 active:scale-[.98] transition-all',
}

const sizes: Record<Size, string> = {
  sm: 'text-xs px-3 py-1.5 rounded-lg',
  md: '',
  lg: 'text-base px-6 py-3 rounded-2xl',
}

interface Props extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant
  size?: Size
  loading?: boolean
  icon?: React.ReactNode
}

export default function Button({ variant = 'primary', size = 'md', loading, icon, children, className, disabled, ...rest }: Props) {
  return (
    <button
      className={cn(variants[variant], sizes[size], className)}
      disabled={disabled || loading}
      {...rest}
    >
      {loading ? <Loader2 size={16} className="animate-spin" /> : icon}
      {children}
    </button>
  )
}
