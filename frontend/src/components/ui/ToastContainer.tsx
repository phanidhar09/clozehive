/**
 * ToastContainer — renders the live stack of real-time toast notifications.
 *
 * Mount ONCE near the root of the app (inside AppProvider).
 * Toasts slide in from the bottom-left and auto-dismiss after `duration` ms.
 * Up to 5 are shown at once; oldest are pushed off the top.
 *
 * The component is driven entirely by toastStore — nothing is passed via props.
 */

import { useEffect, useRef } from 'react'
import { AnimatePresence, motion } from 'framer-motion'
import { X } from 'lucide-react'
import { useToasts, toastStore, type AppToast, type ToastVariant } from '@/store/notificationStore'
import { cn } from '@/lib/utils'

// ── Variant styles ────────────────────────────────────────────────────────────

const VARIANT: Record<ToastVariant, { bar: string; bg: string; text: string }> = {
  default: {
    bar:  'bg-brand-500',
    bg:   'bg-white dark:bg-slate-800 border-cream-200 dark:border-slate-700',
    text: 'text-slate-800 dark:text-white',
  },
  success: {
    bar:  'bg-emerald-500',
    bg:   'bg-emerald-50 dark:bg-emerald-900/20 border-emerald-200 dark:border-emerald-700/40',
    text: 'text-emerald-900 dark:text-emerald-100',
  },
  error: {
    bar:  'bg-red-500',
    bg:   'bg-red-50 dark:bg-red-900/20 border-red-200 dark:border-red-700/40',
    text: 'text-red-900 dark:text-red-100',
  },
  warning: {
    bar:  'bg-amber-400',
    bg:   'bg-amber-50 dark:bg-amber-900/20 border-amber-200 dark:border-amber-700/40',
    text: 'text-amber-900 dark:text-amber-100',
  },
}

// ── Single toast item ─────────────────────────────────────────────────────────

function Toast({ toast }: { toast: AppToast }) {
  const v = VARIANT[toast.variant]
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const progressRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    // Start progress bar shrink
    if (progressRef.current) {
      progressRef.current.style.transition = `width ${toast.duration}ms linear`
      // Tiny delay so the transition starts after mount paint
      requestAnimationFrame(() => {
        if (progressRef.current) progressRef.current.style.width = '0%'
      })
    }
    // Auto-dismiss
    timerRef.current = setTimeout(() => toastStore.dismiss(toast.id), toast.duration)
    return () => {
      if (timerRef.current) clearTimeout(timerRef.current)
    }
  }, [toast.id, toast.duration])

  // Pause timer + progress on hover
  const pause = () => {
    if (timerRef.current) clearTimeout(timerRef.current)
    if (progressRef.current) progressRef.current.style.transition = 'none'
  }
  const resume = () => {
    const remaining = progressRef.current
      ? (parseFloat(progressRef.current.style.width) / 100) * toast.duration
      : toast.duration
    if (progressRef.current) {
      progressRef.current.style.transition = `width ${remaining}ms linear`
      progressRef.current.style.width = '0%'
    }
    timerRef.current = setTimeout(() => toastStore.dismiss(toast.id), remaining)
  }

  return (
    <motion.div
      layout
      initial={{ opacity: 0, x: -24, scale: 0.95 }}
      animate={{ opacity: 1, x: 0,   scale: 1    }}
      exit={{    opacity: 0, x: -24, scale: 0.95  }}
      transition={{ type: 'spring', stiffness: 420, damping: 30 }}
      onMouseEnter={pause}
      onMouseLeave={resume}
      className={cn(
        'relative w-80 max-w-[calc(100vw-24px)] rounded-2xl border shadow-lg overflow-hidden',
        'flex items-start gap-3 px-4 py-3',
        v.bg,
      )}
    >
      {/* Colour bar (left edge) */}
      <div className={cn('absolute left-0 inset-y-0 w-1 rounded-l-2xl', v.bar)} />

      {/* Icon */}
      {toast.icon && (
        <span className="flex-shrink-0 text-xl leading-none mt-0.5">{toast.icon}</span>
      )}

      {/* Text */}
      <div className="flex-1 min-w-0 pl-1">
        <p className={cn('text-sm font-semibold leading-snug', v.text)}>
          {toast.title}
        </p>
        {toast.body && (
          <p className="text-xs text-slate-500 dark:text-slate-400 mt-0.5 leading-snug">
            {toast.body}
          </p>
        )}
      </div>

      {/* Dismiss */}
      <button
        onClick={() => toastStore.dismiss(toast.id)}
        className="flex-shrink-0 p-0.5 rounded-lg text-slate-400 hover:text-slate-600 dark:hover:text-slate-300 transition-colors mt-0.5"
        aria-label="Dismiss"
      >
        <X size={13} />
      </button>

      {/* Progress bar */}
      <div className="absolute bottom-0 left-0 right-0 h-0.5 bg-black/5 dark:bg-white/5">
        <div
          ref={progressRef}
          style={{ width: '100%' }}
          className={cn('h-full rounded-full opacity-60', v.bar)}
        />
      </div>
    </motion.div>
  )
}

// ── Container ─────────────────────────────────────────────────────────────────

export default function ToastContainer() {
  const toasts = useToasts()

  return (
    // Bottom-left — lifted above the mobile bottom nav on small screens
    <div
      className="fixed bottom-24 lg:bottom-6 left-4 z-[9999] flex flex-col-reverse gap-2 pointer-events-none"
      aria-live="polite"
      aria-label="Notifications"
    >
      <AnimatePresence mode="popLayout">
        {toasts.map(t => (
          <div key={t.id} className="pointer-events-auto">
            <Toast toast={t} />
          </div>
        ))}
      </AnimatePresence>
    </div>
  )
}
