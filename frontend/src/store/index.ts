import { createContext, useContext, useState, useCallback, useEffect } from 'react'
import type { ClosetItem, ColorScheme, AuthUser } from '@/types'
import { tokenStorage, authApi, closetApi } from '@/lib/api'

// ─────────────────────────────────────────────────────────────────────────────
//  Types
// ─────────────────────────────────────────────────────────────────────────────

interface AppState {
  // ── Theme ──────────────────────────────────────────────────────────────────
  colorScheme: ColorScheme
  toggleColorScheme: () => void
  initColorScheme: () => void
  // Backwards-compatible aliases used by older components.
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
const COLOR_SCHEME_KEY = 'closetiq-color-scheme'

function getSystemColorScheme(): ColorScheme {
  if (typeof window === 'undefined') return 'light'
  return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light'
}

function readStoredColorScheme(): ColorScheme | null {
  try {
    const value = localStorage.getItem(COLOR_SCHEME_KEY)
    return value === 'dark' || value === 'light' ? value : null
  } catch {
    return null
  }
}

function applyColorScheme(colorScheme: ColorScheme) {
  if (typeof document === 'undefined') return
  document.documentElement.classList.toggle('dark', colorScheme === 'dark')
}

export function initColorSchemeBeforeRender(): ColorScheme {
  const colorScheme = readStoredColorScheme() ?? getSystemColorScheme()
  applyColorScheme(colorScheme)
  return colorScheme
}

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

  const [colorScheme, setColorScheme] = useState<ColorScheme>(() => initColorSchemeBeforeRender())

  const initColorScheme = useCallback(() => {
    const next = initColorSchemeBeforeRender()
    setColorScheme(next)
  }, [])

  const toggleColorScheme = useCallback(() => {
    setColorScheme(current => {
      const next = current === 'light' ? 'dark' : 'light'
      applyColorScheme(next)
      try { localStorage.setItem(COLOR_SCHEME_KEY, next) } catch { /* ignore */ }
      return next
    })
  }, [])

  useEffect(() => {
    applyColorScheme(colorScheme)
  }, [colorScheme])

  useEffect(() => {
    const media = window.matchMedia('(prefers-color-scheme: dark)')
    const handler = (event: MediaQueryListEvent) => {
      if (readStoredColorScheme()) return
      setColorScheme(event.matches ? 'dark' : 'light')
    }
    media.addEventListener('change', handler)
    return () => media.removeEventListener('change', handler)
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
    if (window.location.pathname !== '/login') window.location.assign('/login')
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
      if (window.location.pathname !== '/login') window.location.assign('/login')
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
    colorScheme,
    toggleColorScheme,
    initColorScheme,
    theme: colorScheme,
    toggleTheme: toggleColorScheme,
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
