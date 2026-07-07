/**
 * useWebSocket — connects/disconnects the WS client when auth state changes,
 * and pipes incoming server messages into the notification store.
 *
 * Mount this ONCE in App.tsx (inside AppProvider so it can read the token).
 */

import { useEffect } from 'react'
import { tokenStorage } from '@/lib/api'
import { wsClient, type WsMessage } from '@/services/wsClient'
import { notificationStore, type NotificationChannel } from '@/store/notificationStore'
import { useApp } from '@/store'

// ── Channel → human-readable title map ───────────────────────────────────────

const CHANNEL_META: Record<string, { icon: string; title: (data: Record<string, unknown>) => string; body: (data: Record<string, unknown>) => string }> = {
  closet: {
    icon: '👕',
    title: () => 'Closet updated',
    body: (d) => (d.item_name as string) ? `"${d.item_name}" was added to your closet` : 'Your closet was updated',
  },
  ai: {
    icon: '✨',
    title: (d) => (d.event === 'analysis_complete') ? 'Outfit analysed' : 'AI update',
    body: (d) => {
      if (d.event === 'analysis_complete') return `Score: ${d.score ?? '—'}/100`
      return String(d.message ?? 'Your AI request is ready')
    },
  },
  social: {
    icon: '🐝',
    title: () => 'Hive activity',
    body: (d) => String(d.message ?? 'New activity in your Hive'),
  },
  notifications: {
    icon: '🔔',
    title: (d) => String(d.title ?? 'Notification'),
    body: (d) => String(d.body ?? d.message ?? ''),
  },
}

// ── Hook ──────────────────────────────────────────────────────────────────────

export function useWebSocket() {
  const { currentUser } = useApp()

  useEffect(() => {
    // The token itself never reaches the WS URL — wsClient exchanges it for a
    // single-use ticket via the authenticated API client on each connect.
    if (!currentUser || !tokenStorage.getAccess()) {
      wsClient.disconnect()
      return
    }

    wsClient.connect()

    // Handle incoming notification events from the server
    const onNotification = (msg: WsMessage) => {
      const channel = String(msg.channel ?? 'notifications') as NotificationChannel
      const data = (msg.data ?? {}) as Record<string, unknown>
      const meta = CHANNEL_META[channel] ?? CHANNEL_META.notifications

      notificationStore.push({
        channel,
        icon: meta.icon,
        title: meta.title(data),
        body: meta.body(data),
      })
    }

    wsClient.on('notification', onNotification)

    return () => {
      wsClient.off('notification', onNotification)
      // Don't disconnect on every re-render — only disconnect when user logs out (handled by token check above)
    }
  }, [currentUser])

  // Also disconnect cleanly when the window unloads
  useEffect(() => {
    const onUnload = () => wsClient.disconnect()
    window.addEventListener('beforeunload', onUnload)
    return () => window.removeEventListener('beforeunload', onUnload)
  }, [])
}
