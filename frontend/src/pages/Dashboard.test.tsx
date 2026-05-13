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

function renderDashboard(extra?: Partial<AppState> & { items?: ClosetItem[] }) {
  const { items = [], ...rest } = extra ?? {}
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
    { initialEntries: ['/dashboard'] },
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

  it('renders greeting, stats row, and quick actions when onboarding is complete', async () => {
    renderDashboard({ items: [wardrobeItem({ name: 'Jacket', category: 'outerwear' })] })

    await waitFor(() => {
      expect(screen.getByText(/Quick actions/i)).toBeInTheDocument()
    })

    expect(screen.getByRole('heading', { level: 2, name: /Test User/i })).toBeInTheDocument()
    expect(screen.getByText(/Total Items/i)).toBeInTheDocument()
    expect(screen.getByText('Smart Closet Scan')).toBeInTheDocument()
  })

  it('redirects to style profile onboarding when onboarding is incomplete', async () => {
    vi.mocked(Api.profileApi.getOnboardingStatus).mockResolvedValue({
      onboarding_completed: false,
      onboarding_skipped: false,
      has_profile_record: false,
    })

    const router = renderDashboard({ items: [] })

    await waitFor(() => {
      expect(router.state.location.pathname).toBe('/onboarding/style-profile')
    })
  })

  it('shows empty-closet messaging when wardrobe has no items', async () => {
    renderDashboard({ items: [] })

    await waitFor(() => {
      expect(screen.getByText(/Add your first item to see outfit suggestions/i)).toBeInTheDocument()
    })
  })
})
