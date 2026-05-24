/**
 * notificationStore — lightweight pub/sub store for real-time notifications.
 *
 * Two separate queues:
 *   _notifications  — persisted bell-dropdown history (max 50)
 *   _toasts         — short-lived pop-ups that auto-dismiss (max 5 visible at once)
 *
 * No Zustand / Redux — plain module-level state with useSyncExternalStore.
 */

import { useSyncExternalStore } from 'react'
import { generateId } from '@/lib/utils'

// ── Types ─────────────────────────────────────────────────────────────────────

export type NotificationChannel = 'closet' | 'social' | 'ai' | 'notifications' | 'system'

export type ToastVariant = 'default' | 'success' | 'error' | 'warning'

export interface AppNotification {
  id: string
  channel: NotificationChannel
  title: string
  body: string
  timestamp: Date
  read: boolean
  icon?: string
}

export interface AppToast {
  id: string
  title: string
  body?: string
  icon?: string
  variant: ToastVariant
  /** ms before auto-dismiss — default 4000 */
  duration: number
}

// ── Internal state ────────────────────────────────────────────────────────────

const MAX_NOTIFICATIONS = 50
const MAX_TOASTS = 5

let _notifications: AppNotification[] = []
let _toasts: AppToast[] = []

const _notifListeners = new Set<() => void>()
const _toastListeners = new Set<() => void>()

function _notifyNotif() { _notifListeners.forEach(l => l()) }
function _notifyToast()  { _toastListeners.forEach(l => l()) }

// ── Notification store ────────────────────────────────────────────────────────

export const notificationStore = {
  /** Add a notification to the bell history AND queue a toast pop-up. */
  push(n: Omit<AppNotification, 'id' | 'timestamp' | 'read'>): void {
    const id = generateId()
    _notifications = [
      { ...n, id, timestamp: new Date(), read: false },
      ..._notifications,
    ].slice(0, MAX_NOTIFICATIONS)
    _notifyNotif()

    // Also show as a toast
    toastStore.add({
      title: n.title,
      body: n.body,
      icon: n.icon,
      variant: 'default',
    })
  },

  markAllRead(): void {
    _notifications = _notifications.map(n => ({ ...n, read: true }))
    _notifyNotif()
  },

  dismiss(id: string): void {
    _notifications = _notifications.filter(n => n.id !== id)
    _notifyNotif()
  },

  clearAll(): void {
    _notifications = []
    _notifyNotif()
  },

  getSnapshot(): AppNotification[] { return _notifications },

  subscribe(listener: () => void): () => void {
    _notifListeners.add(listener)
    return () => _notifListeners.delete(listener)
  },
}

// ── Toast store ───────────────────────────────────────────────────────────────

export const toastStore = {
  add(t: Omit<AppToast, 'id' | 'duration'> & { duration?: number }): void {
    const toast: AppToast = { ...t, id: generateId(), duration: t.duration ?? 4000 }
    _toasts = [toast, ..._toasts].slice(0, MAX_TOASTS)
    _notifyToast()
  },

  dismiss(id: string): void {
    _toasts = _toasts.filter(t => t.id !== id)
    _notifyToast()
  },

  getSnapshot(): AppToast[] { return _toasts },

  subscribe(listener: () => void): () => void {
    _toastListeners.add(listener)
    return () => _toastListeners.delete(listener)
  },
}

// ── React hooks ───────────────────────────────────────────────────────────────

export function useNotifications() {
  const notifications = useSyncExternalStore(
    notificationStore.subscribe,
    notificationStore.getSnapshot,
    notificationStore.getSnapshot,
  )
  const unread = notifications.filter(n => !n.read).length
  return {
    notifications,
    unread,
    markAllRead: notificationStore.markAllRead,
    dismiss:     notificationStore.dismiss,
    clearAll:    notificationStore.clearAll,
  }
}

export function useToasts() {
  return useSyncExternalStore(
    toastStore.subscribe,
    toastStore.getSnapshot,
    toastStore.getSnapshot,
  )
}
