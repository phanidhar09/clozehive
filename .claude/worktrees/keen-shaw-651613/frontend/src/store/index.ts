/**
 * Application state — React context + useState
 *
 * Auth state is bootstrapped from tokenStorage (localStorage) on mount so the
 * user stays logged in across refreshes.  The api.ts response interceptor
 * dispatches a `ch:unauthenticated` window event when a refresh attempt fails;
 * this store listens for it and clears local state automatically.
 *
 * Token storage is intentionally delegated to tokenStorage in api.ts so that
 * the axios interceptor and the store always read the same source of truth.
 */
import { createContext, useContext, useState, useCallback, useEffect } from 'react'
import type { ClosetItem, ColorScheme, AuthUser } from '@/types'
import { tokenStorage, closetApi, authApi } from '@/lib/api'

// ── Re-export TokenPair so callers don't need a second import ──────────────
export type { AuthResponse, TokenPair } from '@/lib/api'

// ── State shape ───────────────────────────────────────────────────────────────

interface AppState {
  // ── Theme ──────────────────────────────────────────────────────────────────
  theme: ColorScheme
  toggleTheme: () => void

  // ── Auth ───────────────────────────────────────────────────────────────────
  currentUser: AuthUser | null
  /** True when a valid user object + access token are present in storage. */
  isAuthenticated: boolean

  /**
   * Call after a successful login/signup/google response.
   * `tokens` must be the `{ access_token, refresh_token }` pair from the API.
   * tokenStorage.set() is also called here as a safety net (api.ts already
   * calls it inside _handleAuthResponse, so this is idempotent).
   */
  login: (user: AuthUser, tokens: { access_token: string; refresh_token: string }) => void

  /**
   * Revoke the current session's refresh token, clear local state.
   * Async so the caller can await the network call (best-effort — local state
   * is cleared even if the server call fails).
   */
  logout: () => Promise<void>

  /**
   * Revoke every active session for this account, clear local state.
   */
  logoutAll: () => Promise<void>

  updateCurrentUser: (updates: Partial<AuthUser>) => void

  // ── Closet ─────────────────────────────────────────────────────────────────
  closetItems: ClosetItem[]
  setClosetItems: (items: ClosetItem[]) => void
  addClosetItem: (item: ClosetItem) => void
  removeClosetItem: (id: string) => void
  fetchClosetItems: () => Promise<void>
  closetLoading: boolean
  closetError: string | null

  // ── UI ─────────────────────────────────────────────────────────────────────
  sidebarOpen: boolean
  setSidebarOpen: (v: boolean) => void
}

// ── Context ───────────────────────────────────────────────────────────────────

export const AppContext = createContext<AppState | null>(null)

export function useApp() {
  const ctx = useContext(AppContext)
  if (!ctx) throw new Error('useApp must be inside AppProvider')
  return ctx
}

// ── Factory ───────────────────────────────────────────────────────────────────

export function createAppState(): AppState {
  // ── Theme ──────────────────────────────────────────────────────────────────
  const [theme, setTheme] = useState<ColorScheme>('light')

  const toggleTheme = useCallback(() => {
    setTheme(t => {
      const next = t === 'light' ? 'dark' : 'light'
      document.documentElement.classList.toggle('dark', next === 'dark')
      return next
    })
  }, [])

  // ── Auth — bootstrap from localStorage on first render ────────────────────
  //
  // tokenStorage.getUser() reads from the same key that api.ts writes after
  // every successful auth response, so we're always in sync.
  const [currentUser, setCurrentUser] = useState<AuthUser | null>(() => tokenStorage.getUser())

  // Derived: authenticated when we have both a user object and an access token.
  // We compute this on every render rather than caching it so it always
  // reflects the current tokenStorage state without extra state variables.
  const isAuthenticated = !!currentUser && !!tokenStorage.getAccess()

  // ── Listen for forced-logout event from the api.ts refresh interceptor ────
  // When the silent refresh fails (refresh token expired / revoked) the
  // interceptor dispatches this event so we can clear local state.
  useEffect(() => {
    function handleUnauthenticated() {
      setCurrentUser(null)
      setClosetItems([])
    }
    window.addEventListener('ch:unauthenticated', handleUnauthenticated)
    return () => window.removeEventListener('ch:unauthenticated', handleUnauthenticated)
  }, [])

  // ── Set initial Authorization header if a token was restored ──────────────
  useEffect(() => {
    const token = tokenStorage.getAccess()
    if (token) {
      import('@/lib/api').then(mod => {
        mod.default.defaults.headers.common['Authorization'] = `Bearer ${token}`
      })
    }
  }, [])

  // ── Auth actions ──────────────────────────────────────────────────────────

  const login = useCallback(
    (user: AuthUser, tokens: { access_token: string; refresh_token: string }) => {
      // tokenStorage.set is already called by api.ts _handleAuthResponse, but
      // we call it again here as an idempotent safety net (e.g. when the store's
      // login() is called outside of authApi flows).
      tokenStorage.set(tokens.access_token, tokens.refresh_token)
      tokenStorage.setUser(user)
      setCurrentUser(user)
      // Keep axios default header in sync
      import('@/lib/api').then(mod => {
        mod.default.defaults.headers.common['Authorization'] = `Bearer ${tokens.access_token}`
      })
    },
    [],
  )

  const _clearLocalAuth = useCallback(() => {
    tokenStorage.clear()
    setCurrentUser(null)
    setClosetItems([])
    import('@/lib/api').then(mod => {
      delete mod.default.defaults.headers.common['Authorization']
    })
  }, [])

  const logout = useCallback(async () => {
    // Best-effort server call — local state is cleared regardless
    await authApi.logout(tokenStorage.getRefresh() ?? undefined)
    _clearLocalAuth()
  }, [_clearLocalAuth])

  const logoutAll = useCallback(async () => {
    await authApi.logoutAll()
    _clearLocalAuth()
  }, [_clearLocalAuth])

  const updateCurrentUser = useCallback((updates: Partial<AuthUser>) => {
    setCurrentUser(prev => {
      if (!prev) return prev
      const updated = { ...prev, ...updates }
      tokenStorage.setUser(updated)
      return updated
    })
  }, [])

  // ── Closet ─────────────────────────────────────────────────────────────────
  const [closetItems, setClosetItems] = useState<ClosetItem[]>([])
  const [closetLoading, setClosetLoading] = useState(false)
  const [closetError, setClosetError] = useState<string | null>(null)

  const fetchClosetItems = useCallback(async () => {
    if (!currentUser) return
    setClosetLoading(true)
    setClosetError(null)
    try {
      const items = await closetApi.list()
      setClosetItems(items)
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Failed to load wardrobe'
      setClosetError(msg)
      console.error('Failed to fetch closet items:', err)
    } finally {
      setClosetLoading(false)
    }
  }, [currentUser])

  const addClosetItem = useCallback((item: ClosetItem) => {
    setClosetItems(prev => [item, ...prev])
  }, [])

  const removeClosetItem = useCallback((id: string) => {
    setClosetItems(prev => prev.filter(i => i.id !== id))
  }, [])

  // ── UI ─────────────────────────────────────────────────────────────────────
  const [sidebarOpen, setSidebarOpen] = useState(false)

  return {
    theme, toggleTheme,
    currentUser, isAuthenticated,
    login, logout, logoutAll, updateCurrentUser,
    closetItems, setClosetItems, addClosetItem, removeClosetItem,
    fetchClosetItems, closetLoading, closetError,
    sidebarOpen, setSidebarOpen,
  }
}
