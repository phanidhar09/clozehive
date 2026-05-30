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

/**
 * Responsive dialog.
 *  - Mobile: a bottom sheet that slides up, spans full width, and scrolls
 *    internally (height-capped) so long content is always reachable.
 *  - Desktop (sm+): a centered modal.
 * Always renders a close control so it can be dismissed on touch.
 */
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
    <div className="fixed inset-0 z-50 flex items-end justify-center sm:items-center sm:p-4">
      {/* Backdrop */}
      <div className="absolute inset-0 bg-black/50 backdrop-blur-sm animate-fade-in" onClick={onClose} />

      {/* Panel */}
      <div className={cn(
        'relative w-full flex flex-col bg-white dark:bg-slate-900',
        'shadow-2xl border border-cream-300 dark:border-slate-700 animate-slide-up overflow-hidden',
        // Bottom sheet on mobile, centered card on desktop
        'rounded-t-3xl sm:rounded-2xl',
        'max-h-[92dvh] sm:max-h-[88vh]',
        sizes[size],
      )}>
        {/* Mobile drag handle */}
        <div className="sm:hidden flex justify-center pt-2.5 pb-1 flex-shrink-0">
          <span className="h-1.5 w-10 rounded-full bg-slate-300 dark:bg-white/15" />
        </div>

        {title ? (
          <div className="flex items-center justify-between px-6 py-4 border-b border-cream-300 dark:border-slate-700 flex-shrink-0">
            <h2 className="font-display font-semibold text-lg">{title}</h2>
            <button onClick={onClose} className="p-1.5 rounded-xl hover:bg-cream-100 dark:hover:bg-slate-800 transition-colors">
              <X size={18} className="text-slate-500" />
            </button>
          </div>
        ) : (
          // Floating close for title-less modals (e.g. item detail)
          <button
            onClick={onClose}
            aria-label="Close"
            className="absolute top-3 right-3 z-10 p-2 rounded-full
                       bg-white/80 dark:bg-black/40 backdrop-blur-sm shadow-sm
                       text-slate-600 dark:text-white/70
                       hover:bg-white dark:hover:bg-black/60 transition-colors"
          >
            <X size={18} />
          </button>
        )}

        {/* Scrollable content */}
        <div className="p-4 sm:p-6 overflow-y-auto overscroll-contain flex-1">
          {children}
        </div>
      </div>
    </div>
  )
}
