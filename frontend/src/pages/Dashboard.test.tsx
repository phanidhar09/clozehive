import { render, screen, waitFor } from '@testing-library/react'
import {
  RouterProvider,
  createMemoryRouter,
} from 'react-router-dom'
import { vi } from 'vitest'
import Dashboard from '@/pages/Dashboard'
import { MockAppProvider, mockAuthUser } from '@/test/utils'
import type { AppState } from '@/store'
import type { ClosetItem } from '@/types'
import * as Api from '@/lib/api'

const wardrobeItem = (partial: Partial<ClosetItem> = {}): ClosetItem => ({
  id: partial.id ?? '11111111-1111-1111-1111-111111111111',
  user_id: '00000000-0000-0000-0000-000000000001',
  name: partial.name ?? 'Blue tee',
  category: partial.category ?? 'tops',
  tags: [],
  wear_count: 0,
  occasion: [],
  created_at: new Date().toISOString(),
  ...partial,
})

vi.mock('@/lib/api', async importOriginal => {
  const actual = await importOriginal<typeof import('@/lib/api')>()
  return {
    ...actual,
    profileApi: {
      ...actual.profileApi,
      getOnboardingStatus: vi.fn(),
    },
    outfitsApi: {
      ...actual.outfitsApi,
      getOutfitOfDay: vi.fn(),
    },
  }
})

function renderDashboard(
  extra?: Partial<AppState> & { items?: ClosetItem[]; locationState?: Record<string, unknown> },
) {
  const { items = [], locationState, ...rest } = extra ?? {}
  const router = createMemoryRouter(
    [
      {
        path: '/dashboard',
        element: (
          <MockAppProvider
            value={{
              isAuthenticated: true,
              currentUser: mockAuthUser(),
              closetItems: items,
              closetLoading: false,
              ...rest,
            }}
          >
            <Dashboard />
          </MockAppProvider>
        ),
      },
      {
        path: '/onboarding/style-profile',
        element: <div>Style profile onboarding</div>,
      },
    ],
    { initialEntries: [{ pathname: '/dashboard', state: locationState }] },
  )
  render(<RouterProvider router={router} />)
  return router
}

describe('Dashboard', () => {
  beforeEach(() => {
    vi.mocked(Api.profileApi.getOnboardingStatus).mockResolvedValue({
      onboarding_completed: true,
      onboarding_skipped: false,
      has_profile_record: true,
    })
    vi.mocked(Api.outfitsApi.getOutfitOfDay).mockRejectedValue(new Error('no mock outfit'))
  })

  it('renders greeting, stats, and key sections when onboarding is complete', async () => {
    renderDashboard({ items: [wardrobeItem({ name: 'Jacket', category: 'outerwear' })] })

    // Greeting heading includes the user's display name
    expect(screen.getByRole('heading', { level: 2, name: /Test User/i })).toBeInTheDocument()

    // Hero stats row (the "Active" stat is always present) + primary sections
    expect(screen.getByText('Active')).toBeInTheDocument()
    expect(screen.getByText("Today's Look")).toBeInTheDocument()
    expect(screen.getByText('Recent Pieces')).toBeInTheDocument()

    // The wardrobe item surfaces (Recent Pieces strip + Wardrobe Pulse "Most Worn")
    expect(screen.getAllByText('Jacket').length).toBeGreaterThanOrEqual(1)
  })

  it('stays on the dashboard when onboarding is incomplete (the login-time redirect lives in the auth flow)', async () => {
    vi.mocked(Api.profileApi.getOnboardingStatus).mockResolvedValue({
      onboarding_completed: false,
      onboarding_skipped: false,
      has_profile_record: false,
    })

    const router = renderDashboard({ items: [], locationState: { fromLogin: true } })

    // The onboarding redirect now happens in Login/Signup/OAuthCallback before
    // the dashboard renders — the dashboard itself must not redirect.
    await waitFor(() => {
      expect(screen.getByRole('heading', { name: /Welcome to Cloz/i })).toBeInTheDocument()
    })
    expect(router.state.location.pathname).toBe('/dashboard')
  })

  it('surfaces the onboarding checklist (account-setup step) when onboarding is incomplete', async () => {
    vi.mocked(Api.profileApi.getOnboardingStatus).mockResolvedValue({
      onboarding_completed: false,
      onboarding_skipped: false,
      has_profile_record: false,
    })

    const router = renderDashboard({ items: [wardrobeItem()] })

    // The style-profile reminder now lives in the OnboardingChecklist.
    expect(await screen.findByText(/Account setup/i)).toBeInTheDocument()
    // Stays on the dashboard — no redirect from here.
    expect(router.state.location.pathname).toBe('/dashboard')
  })

  it('shows the guided empty state when wardrobe has no items', async () => {
    renderDashboard({ items: [] })

    expect(await screen.findByText(/Welcome to Cloz/i)).toBeInTheDocument()
    expect(screen.getByText(/Start guided setup/i)).toBeInTheDocument()
  })
})
