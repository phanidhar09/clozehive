import { render, screen, waitFor } from '@testing-library/react'
import { RouterProvider, createMemoryRouter } from 'react-router-dom'
import userEvent from '@testing-library/user-event'
import { vi } from 'vitest'
import Closet from '@/pages/Closet'
import { MockAppProvider, mockAuthUser } from '@/test/utils'
import type { AppState } from '@/store'
import type { ClosetItem } from '@/types'

vi.mock('@/lib/api', async importOriginal => {
  const actual = await importOriginal<typeof import('@/lib/api')>()
  return {
    ...actual,
    closetApi: {
      ...actual.closetApi,
      delete: vi.fn(),
    },
  }
})

const dress = (overrides: Partial<ClosetItem>): ClosetItem => ({
  id: overrides.id ?? 'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa',
  user_id: 'bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb',
  name: overrides.name ?? 'Dress',
  category: overrides.category ?? 'dresses',
  tags: [],
  wear_count: 0,
  occasion: [],
  created_at: new Date().toISOString(),
  ...overrides,
})

/** Render Closet inside a memory router so react-router <Link>s resolve. */
function renderCloset(value?: Partial<AppState>) {
  const router = createMemoryRouter(
    [
      {
        path: '/',
        element: (
          <MockAppProvider value={value}>
            <Closet />
          </MockAppProvider>
        ),
      },
      { path: '/upload', element: <div>Upload page</div> },
      { path: '/closet-match', element: <div>Fit match page</div> },
    ],
    { initialEntries: ['/'] },
  )
  render(<RouterProvider router={router} />)
  return router
}

describe('Closet', () => {
  it('shows a loading state while wardrobe is fetching', () => {
    renderCloset({ closetLoading: true, closetItems: [] })
    expect(screen.getByRole('status')).toBeInTheDocument()
    expect(screen.getByText(/Loading your wardrobe/i)).toBeInTheDocument()
  })

  it('shows an empty wardrobe message when closet has no items', () => {
    renderCloset({
      isAuthenticated: true,
      currentUser: mockAuthUser(),
      closetItems: [],
      closetLoading: false,
    })
    expect(screen.getByText(/Your wardrobe is empty/i)).toBeInTheDocument()
    expect(
      screen.getByRole('link', { name: /Add items with AI/i }),
    ).toHaveAttribute('href', '/upload')
  })

  it('shows a friendly banner and retry when load failed', async () => {
    const user = userEvent.setup()
    const fetchClosetItems = vi.fn()
    renderCloset({
      closetError: 'Network error',
      fetchClosetItems,
      closetItems: [],
      closetLoading: false,
    })
    expect(screen.getByRole('alert')).toHaveTextContent(/Network error/i)
    await user.click(screen.getByRole('button', { name: /Try again/i }))
    expect(fetchClosetItems).toHaveBeenCalledTimes(1)
  })

  it('lists items once data is loaded', async () => {
    const items = [dress({ id: '1', name: 'Red top', category: 'tops', created_at: '2026-05-07T12:00:00Z' })]
    renderCloset({ closetItems: items, closetLoading: false })
    await waitFor(() => {
      expect(screen.getAllByText('Red top').length).toBeGreaterThanOrEqual(1)
    })
    expect(screen.getByRole('heading', { name: /My Closet/i })).toBeInTheDocument()
  })
})
