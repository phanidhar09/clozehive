/**
 * NotificationBell — bell icon with live unread badge, connection dot,
 * and a dropdown list of recent real-time notifications.
 */

import { useEffect, useRef, useState } from 'react'
import { Bell, X, CheckCheck, Trash2 } from 'lucide-react'
import { useNotifications } from '@/store/notificationStore'
import { wsClient, type WsStatus } from '@/services/wsClient'
import { cn } from '@/lib/utils'

// ── Connection status dot ─────────────────────────────────────────────────────

const STATUS_DOT: Record<WsStatus, string> = {
  connected:    'bg-emerald-400',
  connecting:   'bg-amber-400 animate-pulse',
  disconnected: 'bg-slate-400',
  error:        'bg-red-400',
}

// ── Relative time ─────────────────────────────────────────────────────────────

function relTime(ts: Date): string {
  const diff = Math.floor((Date.now() - ts.getTime()) / 1000)
  if (diff < 60)  return 'just now'
  if (diff < 3600) return `${Math.floor(diff / 60)}m ago`
  if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`
  return ts.toLocaleDateString()
}

// ── Component ─────────────────────────────────────────────────────────────────

export default function NotificationBell() {
  const { notifications, unread, markAllRead, dismiss, clearAll } = useNotifications()
  const [open, setOpen] = useState(false)
  const [status, setStatus] = useState<WsStatus>(wsClient.status)
  const ref = useRef<HTMLDivElement>(null)

  // Track WS connection status
  useEffect(() => {
    const handler = (msg: { status?: WsStatus }) => {
      if (msg.status) setStatus(msg.status)
    }
    wsClient.on('status', handler as never)
    return () => wsClient.off('status', handler as never)
  }, [])

  // Close dropdown on outside click
  useEffect(() => {
    if (!open) return
    const handler = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false)
    }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [open])

  const handleOpen = () => {
    setOpen(o => !o)
    if (!open && unread > 0) markAllRead()
  }

  return (
    <div ref={ref} className="relative">
      {/* Bell button */}
      <button
        onClick={handleOpen}
        aria-label={`Notifications${unread > 0 ? ` (${unread} unread)` : ''}`}
        className="relative p-2 min-h-[44px] min-w-[44px] rounded-xl
                   text-slate-500 dark:text-white/50
                   hover:text-slate-800 dark:hover:text-white
                   hover:bg-slate-100 dark:hover:bg-white/[0.08]
                   transition-colors"
      >
        <Bell size={19} />

        {/* Unread badge */}
        {unread > 0 && (
          <span className="absolute top-1 right-1 min-w-[16px] h-4 px-0.5 rounded-full
                           bg-brand-500 text-white text-[9px] font-bold
                           flex items-center justify-center leading-none
                           ring-2 ring-white dark:ring-slate-950">
            {unread > 9 ? '9+' : unread}
          </span>
        )}

        {/* Connection dot (bottom-right, only when no unread badge) */}
        {unread === 0 && (
          <span className={cn(
            'absolute bottom-1.5 right-1.5 w-2 h-2 rounded-full ring-2 ring-white dark:ring-slate-950',
            STATUS_DOT[status],
          )} />
        )}
      </button>

      {/* Dropdown */}
      {open && (
        <div className="absolute right-0 top-full mt-2 w-80 max-w-[calc(100vw-16px)]
                        rounded-2xl bg-white dark:bg-slate-900
                        border border-cream-200 dark:border-slate-700
                        shadow-xl z-50 overflow-hidden">
          {/* Header */}
          <div className="flex items-center justify-between px-4 py-3
                          border-b border-cream-100 dark:border-slate-800">
            <div className="flex items-center gap-2">
              <span className="text-sm font-semibold text-slate-800 dark:text-white">
                Notifications
              </span>
              <span className={cn(
                'w-2 h-2 rounded-full flex-shrink-0',
                STATUS_DOT[status],
              )} title={status} />
              <span className="text-[10px] text-slate-400 capitalize">{status}</span>
            </div>
            {notifications.length > 0 && (
              <div className="flex gap-1">
                <button
                  onClick={markAllRead}
                  title="Mark all read"
                  className="p-1 rounded-lg text-slate-400 hover:text-brand-500 hover:bg-brand-50 dark:hover:bg-brand-900/20 transition-colors"
                >
                  <CheckCheck size={13} />
                </button>
                <button
                  onClick={clearAll}
                  title="Clear all"
                  className="p-1 rounded-lg text-slate-400 hover:text-red-500 hover:bg-red-50 dark:hover:bg-red-500/10 transition-colors"
                >
                  <Trash2 size={13} />
                </button>
              </div>
            )}
          </div>

          {/* List */}
          <div className="max-h-80 overflow-y-auto">
            {notifications.length === 0 ? (
              <div className="flex flex-col items-center gap-2 py-8 text-center">
                <Bell size={22} className="text-slate-300 dark:text-slate-600" />
                <p className="text-xs text-slate-400 dark:text-slate-500">
                  No notifications yet
                </p>
                <p className="text-[10px] text-slate-300 dark:text-slate-600">
                  Real-time updates will appear here
                </p>
              </div>
            ) : (
              <ul className="divide-y divide-cream-100 dark:divide-slate-800">
                {notifications.map(n => (
                  <li
                    key={n.id}
                    className={cn(
                      'flex gap-3 px-4 py-3 hover:bg-slate-50 dark:hover:bg-slate-800/50 transition-colors',
                      !n.read && 'bg-brand-50/50 dark:bg-brand-900/10',
                    )}
                  >
                    {/* Icon */}
                    <span className="flex-shrink-0 w-8 h-8 rounded-xl bg-slate-100 dark:bg-slate-800
                                     flex items-center justify-center text-base mt-0.5">
                      {n.icon ?? '🔔'}
                    </span>

                    {/* Content */}
                    <div className="flex-1 min-w-0">
                      <p className="text-xs font-semibold text-slate-800 dark:text-white leading-snug">
                        {n.title}
                      </p>
                      {n.body && (
                        <p className="text-[11px] text-slate-500 dark:text-slate-400 mt-0.5 leading-snug">
                          {n.body}
                        </p>
                      )}
                      <p className="text-[10px] text-slate-400 mt-1">
                        {relTime(n.timestamp)}
                      </p>
                    </div>

                    {/* Dismiss */}
                    <button
                      onClick={() => dismiss(n.id)}
                      className="flex-shrink-0 p-1 rounded-lg text-slate-300 hover:text-slate-500
                                 dark:text-slate-600 dark:hover:text-slate-400 transition-colors self-start mt-0.5"
                      aria-label="Dismiss"
                    >
                      <X size={12} />
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </div>
        </div>
      )}
    </div>
  )
}
