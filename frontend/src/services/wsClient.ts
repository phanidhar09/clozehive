/**
 * wsClient — singleton WebSocket client with automatic reconnection.
 *
 * Usage:
 *   wsClient.connect(token)          // call once after login
 *   wsClient.disconnect()            // call on logout
 *   wsClient.on('notification', cb)  // subscribe to a server message type
 *   wsClient.off('notification', cb) // unsubscribe
 *   wsClient.send({ type: 'ping' })  // send a message
 *
 * The client:
 *   - Converts http(s) → ws(s) automatically from VITE_API_URL
 *   - Reconnects with exponential back-off (1 s → 32 s max)
 *   - Sends a ping every 30 s so the server-side 5-min idle timeout never fires
 *   - Emits a 'status' event whenever the connection state changes
 */

import { apiOrigin } from '@/lib/apiOrigin'

// ── Types ─────────────────────────────────────────────────────────────────────

export type WsStatus = 'disconnected' | 'connecting' | 'connected' | 'error'

export interface WsMessage {
  type: string
  [key: string]: unknown
}

type MessageHandler = (msg: WsMessage) => void

// ── URL builder ───────────────────────────────────────────────────────────────

function buildWsUrl(token: string): string {
  const origin = apiOrigin()
  let base: string

  if (origin) {
    // Replace http(s) with ws(s) for an explicit API host
    base = origin.replace(/^https/, 'wss').replace(/^http/, 'ws')
  } else {
    // Same-origin SPA — derive from the current page host
    const proto = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
    base = `${proto}//${window.location.host}`
  }

  return `${base}/api/v1/ws?token=${encodeURIComponent(token)}`
}

// ── Client ────────────────────────────────────────────────────────────────────

class WsClient {
  private socket: WebSocket | null = null
  private token: string | null = null
  private listeners: Map<string, Set<MessageHandler>> = new Map()
  private _status: WsStatus = 'disconnected'
  private retryCount = 0
  private retryTimer: ReturnType<typeof setTimeout> | null = null
  private pingTimer: ReturnType<typeof setInterval> | null = null
  private intentionalClose = false

  // ── Status ──────────────────────────────────────────────────────────────────

  get status(): WsStatus {
    return this._status
  }

  private setStatus(s: WsStatus) {
    this._status = s
    this._emit('status', { type: 'status', status: s })
  }

  // ── Public API ──────────────────────────────────────────────────────────────

  connect(token: string): void {
    if (this.socket && (this.socket.readyState === WebSocket.OPEN || this.socket.readyState === WebSocket.CONNECTING)) {
      return
    }
    this.token = token
    this.intentionalClose = false
    this._open()
  }

  disconnect(): void {
    this.intentionalClose = true
    this._clearTimers()
    this.token = null
    this.retryCount = 0
    if (this.socket) {
      this.socket.close(1000, 'logout')
      this.socket = null
    }
    this.setStatus('disconnected')
  }

  send(msg: WsMessage): void {
    if (this.socket?.readyState === WebSocket.OPEN) {
      this.socket.send(JSON.stringify(msg))
    }
  }

  on(type: string, handler: MessageHandler): void {
    if (!this.listeners.has(type)) this.listeners.set(type, new Set())
    this.listeners.get(type)!.add(handler)
  }

  off(type: string, handler: MessageHandler): void {
    this.listeners.get(type)?.delete(handler)
  }

  // ── Internal ────────────────────────────────────────────────────────────────

  private _open(): void {
    if (!this.token) return
    this.setStatus('connecting')

    try {
      const url = buildWsUrl(this.token)
      this.socket = new WebSocket(url)
    } catch {
      this.setStatus('error')
      this._scheduleRetry()
      return
    }

    this.socket.onopen = () => {
      this.retryCount = 0
      this.setStatus('connected')
      this._startPing()
    }

    this.socket.onmessage = (event) => {
      try {
        const msg = JSON.parse(event.data) as WsMessage
        this._emit(msg.type, msg)
      } catch {
        // ignore malformed frames
      }
    }

    this.socket.onclose = (event) => {
      this._clearPing()
      if (this.intentionalClose) return
      // 4001 = unauthorized — don't retry, token is bad
      if (event.code === 4001) {
        this.setStatus('error')
        return
      }
      this.setStatus('disconnected')
      this._scheduleRetry()
    }

    this.socket.onerror = () => {
      this.setStatus('error')
      // onclose fires right after onerror, retry handled there
    }
  }

  private _scheduleRetry(): void {
    if (this.intentionalClose || !this.token) return
    const delay = Math.min(1000 * 2 ** this.retryCount, 32_000)
    this.retryCount++
    this.retryTimer = setTimeout(() => this._open(), delay)
  }

  private _startPing(): void {
    this._clearPing()
    this.pingTimer = setInterval(() => {
      this.send({ type: 'ping' })
    }, 30_000)
  }

  private _clearPing(): void {
    if (this.pingTimer !== null) {
      clearInterval(this.pingTimer)
      this.pingTimer = null
    }
  }

  private _clearTimers(): void {
    this._clearPing()
    if (this.retryTimer !== null) {
      clearTimeout(this.retryTimer)
      this.retryTimer = null
    }
  }

  private _emit(type: string, msg: WsMessage): void {
    this.listeners.get(type)?.forEach(h => h(msg))
    // also emit '*' wildcard listeners
    this.listeners.get('*')?.forEach(h => h(msg))
  }
}

export const wsClient = new WsClient()
