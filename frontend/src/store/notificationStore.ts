/**
 * notificationStore — lightweight pub/sub store for real-time notifications.
 *
 * No Zustand / Redux — just a module-level array with React-compatible
 * subscription so any component can call useNotifications() and re-render
 * when the list changes.
 */

import { useSyncExternalStore } from 'react'
import { generateId } from '@/lib/utils'

// ── Types ─────────────────────────────────────────────────────────────────────

export type NotificationChannel = 'closet' | 'social' | 'ai' | 'notifications' | 'system'

export interface AppNotification {
  id: string
  channel: NotificationChannel
  title: string
  body: string
  timestamp: Date
  read: boolean
  /** Optional icon emoji shown in the bell dropdown */
  icon?: string
}

// ── Internal state ────────────────────────────────────────────────────────────

const MAX = 50  // keep at most 50 notifications in memory

let _notifications: AppNotification[] = []
const _listeners = new Set<() => void>()

function _notify() {
  _listeners.forEach(l => l())
}

// ── Store API ─────────────────────────────────────────────────────────────────

export const notificationStore = {
  push(n: Omit<AppNotification, 'id' | 'timestamp' | 'read'>): void {
    _notifications = [
      { ...n, id: generateId(), timestamp: new Date(), read: false },
      ..._notifications,
    ].slice(0, MAX)
    _notify()
  },

  markAllRead(): void {
    _notifications = _notifications.map(n => ({ ...n, read: true }))
    _notify()
  },

  dismiss(id: string): void {
    _notifications = _notifications.filter(n => n.id !== id)
    _notify()
  },

  clearAll(): void {
    _notifications = []
    _notify()
  },

  getSnapshot(): AppNotification[] {
    return _notifications
  },

  subscribe(listener: () => void): () => void {
    _listeners.add(listener)
    return () => _listeners.delete(listener)
  },
}

// ── React hook ────────────────────────────────────────────────────────────────

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
    dismiss: notificationStore.dismiss,
    clearAll: notificationStore.clearAll,
  }
}
