import { createContext, useContext, useState, useCallback, useEffect } from 'react'
import type { ClosetItem, ColorScheme, AuthUser } from '@/types'
import { tokenStorage, authApi, closetApi } from '@/lib/api'

// ─────────────────────────────────────────────────────────────────────────────
//  Types
// ─────────────────────────────────────────────────────────────────────────────

interface AppState {
  // ── Theme ──────────────────────────────────────────────────────────────────
  theme: ColorScheme
  toggleTheme: () => void

  // ── Auth ───────────────────────────────────────────────────────────────────
  currentUser: AuthUser | null
  isAuthenticated: boolean
  login: (user: AuthUser, accessToken: string, refreshToken: string) => void
  logout: () => void
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

// ─────────────────────────────────────────────────────────────────────────────
//  Context
// ─────────────────────────────────────────────────────────────────────────────

export const AppContext = createContext<AppState | null>(null)

export function useApp() {
  const ctx = useContext(AppContext)
  if (!ctx) throw new Error('useApp must be used inside AppProvider')
  return ctx
}

// ─────────────────────────────────────────────────────────────────────────────
//  Persistence helpers  (user profile only — tokens live in tokenStorage)
// ─────────────────────────────────────────────────────────────────────────────

const USER_KEY = 'ch_user'

function loadPersistedUser(): AuthUser | null {
  try {
    const raw = localStorage.getItem(USER_KEY)
    return raw ? (JSON.parse(raw) as AuthUser) : null
  } catch {
    return null
  }
}

function persistUser(user: AuthUser) {
  try { localStorage.setItem(USER_KEY, JSON.stringify(user)) } catch { /* ignore */ }
}

function clearPersistedUser() {
  try { localStorage.removeItem(USER_KEY) } catch { /* ignore */ }
}

// ─────────────────────────────────────────────────────────────────────────────
//  State factory (called inside a React component / Provider)
// ─────────────────────────────────────────────────────────────────────────────

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

  // ── Auth ───────────────────────────────────────────────────────────────────
  //  Restore user from localStorage; tokens come from tokenStorage (set by api.ts)

  const [currentUser, setCurrentUser] = useState<AuthUser | null>(() => {
    // Only trust persisted user if we still have a valid access token
    const hasToken = Boolean(tokenStorage.getAccess())
    return hasToken ? loadPersistedUser() : null
  })

  const login = useCallback((user: AuthUser, accessToken: string, refreshToken: string) => {
    tokenStorage.set(accessToken, refreshToken)
    setCurrentUser(user)
    persistUser(user)
  }, [])

  const logout = useCallback(async () => {
    try { await authApi.logout() } catch { /* best-effort */ }
    tokenStorage.clear()
    clearPersistedUser()
    setCurrentUser(null)
    setClosetItems([])
  }, [])

  const updateCurrentUser = useCallback((updates: Partial<AuthUser>) => {
    setCurrentUser(prev => {
      if (!prev) return prev
      const updated = { ...prev, ...updates }
      persistUser(updated)
      return updated
    })
  }, [])

  // Listen for the global unauthenticated event fired by the 401 interceptor
  useEffect(() => {
    const handler = () => {
      clearPersistedUser()
      setCurrentUser(null)
      setClosetItems([])
    }
    window.addEventListener('ch:unauthenticated', handler)
    return () => window.removeEventListener('ch:unauthenticated', handler)
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

  // ── Return ─────────────────────────────────────────────────────────────────

  return {
    theme,
    toggleTheme,
    currentUser,
    isAuthenticated: !!currentUser && !!tokenStorage.getAccess(),
    login,
    logout,
    updateCurrentUser,
    closetItems,
    setClosetItems,
    addClosetItem,
    removeClosetItem,
    fetchClosetItems,
    closetLoading,
    closetError,
    sidebarOpen,
    setSidebarOpen,
  }
}
