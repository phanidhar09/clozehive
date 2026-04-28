import { useEffect } from 'react'
import { X } from 'lucide-react'
import { cn } from '@/lib/utils'

interface Props {
  open: boolean
  onClose: () => void
  title?: string
  children: React.ReactNode
  size?: 'sm' | 'md' | 'lg' | 'xl'
}

const sizes = { sm: 'max-w-sm', md: 'max-w-md', lg: 'max-w-2xl', xl: 'max-w-4xl' }

export default function Modal({ open, onClose, title, children, size = 'md' }: Props) {
  useEffect(() => {
    if (open) document.body.style.overflow = 'hidden'
    else document.body.style.overflow = ''
    return () => { document.body.style.overflow = '' }
  }, [open])

  useEffect(() => {
    const handler = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose() }
    document.addEventListener('keydown', handler)
    return () => document.removeEventListener('keydown', handler)
  }, [onClose])

  if (!open) return null

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      {/* Backdrop */}
      <div className="absolute inset-0 bg-black/50 backdrop-blur-sm animate-fade-in" onClick={onClose} />

      {/* Panel */}
      <div className={cn(
        'relative w-full bg-white dark:bg-slate-900 rounded-2xl shadow-2xl border border-cream-300 dark:border-slate-700 animate-slide-up overflow-hidden',
        sizes[size],
      )}>
        {title && (
          <div className="flex items-center justify-between px-6 py-4 border-b border-cream-300 dark:border-slate-700">
            <h2 className="font-display font-semibold text-lg">{title}</h2>
            <button onClick={onClose} className="p-1.5 rounded-xl hover:bg-cream-100 dark:hover:bg-slate-800 transition-colors">
              <X size={18} className="text-slate-500" />
            </button>
          </div>
        )}
        <div className="p-6">{children}</div>
      </div>
    </div>
  )
}
