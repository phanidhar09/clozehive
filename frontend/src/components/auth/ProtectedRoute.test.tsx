import { render, screen, waitFor } from '@testing-library/react'
import {
  RouterProvider,
  createMemoryRouter,
} from 'react-router-dom'
import ProtectedRoute from '@/components/auth/ProtectedRoute'
import { MockAppProvider, mockAuthUser } from '@/test/utils'

describe('ProtectedRoute', () => {
  it('redirects unauthenticated visitors away from protected content', async () => {
    const router = createMemoryRouter(
      [
        {
          path: '/login',
          element: <div>Sign-in page</div>,
        },
        {
          path: '/secret',
          element: (
            <MockAppProvider value={{ isAuthenticated: false }}>
              <ProtectedRoute>
                <div>Secret area</div>
              </ProtectedRoute>
            </MockAppProvider>
          ),
        },
      ],
      { initialEntries: ['/secret'] },
    )

    render(<RouterProvider router={router} />)

    await waitFor(() => {
      expect(router.state.location.pathname).toBe('/login')
    })
    expect(screen.queryByText('Secret area')).not.toBeInTheDocument()
  })

  it('renders children when the user is authenticated', () => {
    const router = createMemoryRouter(
      [
        {
          path: '/dashboard',
          element: (
            <MockAppProvider
              value={{
                isAuthenticated: true,
                currentUser: mockAuthUser(),
              }}
            >
              <ProtectedRoute>
                <span>Authenticated content</span>
              </ProtectedRoute>
            </MockAppProvider>
          ),
        },
      ],
      { initialEntries: ['/dashboard'] },
    )

    render(<RouterProvider router={router} />)

    expect(screen.getByText('Authenticated content')).toBeInTheDocument()
  })
})
