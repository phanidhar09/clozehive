import type { ReactNode } from 'react'
import { vi } from 'vitest'
import { AppContext, type AppState } from '@/store'
import type { AuthUser } from '@/types'

export function mockAuthUser(overrides: Partial<AuthUser> = {}): AuthUser {
  return {
    id: '00000000-0000-0000-0000-000000000001',
    email: 'test@example.com',
    username: 'testuser',
    display_name: 'Test User',
    role: 'user',
    avatar_url: null,
    bio: null,
    ...overrides,
  }
}

function baseMocks(): AppState {
  return {
    colorScheme: 'light',
    toggleColorScheme: vi.fn(),
    initColorScheme: vi.fn(),
    theme: 'light',
    toggleTheme: vi.fn(),
    currentUser: null,
    isAuthenticated: false,
    login: vi.fn(),
    logout: vi.fn(),
    updateCurrentUser: vi.fn(),
    closetItems: [],
    setClosetItems: vi.fn(),
    addClosetItem: vi.fn(),
    removeClosetItem: vi.fn(),
    fetchClosetItems: vi.fn(),
    loadMoreClosetItems: vi.fn(),
    closetLoading: false,
    closetError: null,
    closetTotal: 0,
    closetHasMore: false,
    sidebarOpen: false,
    setSidebarOpen: vi.fn(),
  }
}

/** Minimal full {@link AppState} for RTL — override only what each test needs. */
export function createMockAppState(overrides: Partial<AppState> = {}): AppState {
  return { ...baseMocks(), ...overrides }
}

export function MockAppProvider({
  children,
  value,
}: {
  children: ReactNode
  value?: Partial<AppState>
}) {
  return (
    <AppContext.Provider value={createMockAppState(value)}>
      {children}
    </AppContext.Provider>
  )
}
