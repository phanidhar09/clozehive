import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { RouterProvider, createMemoryRouter } from 'react-router-dom'
import { vi, beforeEach, describe, it, expect } from 'vitest'
import Login from '@/auth/Login'
import { MockAppProvider, mockAuthUser } from '@/test/utils'
import * as Api from '@/lib/api'

// Mock the API module so the login flow never hits a real backend.
vi.mock('@/lib/api', async importOriginal => {
  const actual = await importOriginal<typeof import('@/lib/api')>()
  return {
    ...actual,
    authApi: { ...actual.authApi, login: vi.fn() },
    profileApi: { ...actual.profileApi, getOnboardingStatus: vi.fn() },
  }
})

const loginMock = Api.authApi.login as unknown as ReturnType<typeof vi.fn>
const onboardingMock = Api.profileApi.getOnboardingStatus as unknown as ReturnType<typeof vi.fn>

/** Render Login inside a memory router with a stub dashboard + onboarding route. */
function renderLogin(loginFn = vi.fn()) {
  const router = createMemoryRouter(
    [
      {
        path: '/login',
        element: (
          <MockAppProvider value={{ isAuthenticated: false, login: loginFn }}>
            <Login />
          </MockAppProvider>
        ),
      },
      { path: '/dashboard', element: <div>Dashboard page</div> },
      { path: '/onboarding/style-profile', element: <div>Onboarding page</div> },
    ],
    { initialEntries: ['/login'] },
  )
  render(<RouterProvider router={router} />)
  return { router, loginFn }
}

describe('Login flow (integration)', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('logs in and navigates to the dashboard for an onboarded user', async () => {
    const user = userEvent.setup()
    loginMock.mockResolvedValue({ user: mockAuthUser(), access_token: 'tok_abc' })
    onboardingMock.mockResolvedValue({ onboarding_completed: true })

    const { router, loginFn } = renderLogin()

    await user.type(screen.getByPlaceholderText(/you@example.com/i), 'test@example.com')
    await user.type(screen.getByPlaceholderText(/enter your password/i), 'hunter2!')
    await user.click(screen.getByRole('button', { name: /sign in/i }))

    await waitFor(() => {
      expect(router.state.location.pathname).toBe('/dashboard')
    })
    expect(loginMock).toHaveBeenCalledWith({ identifier: 'test@example.com', password: 'hunter2!' })
    expect(loginFn).toHaveBeenCalledWith(mockAuthUser(), 'tok_abc')
  })

  it('redirects a not-yet-onboarded user to onboarding', async () => {
    const user = userEvent.setup()
    loginMock.mockResolvedValue({ user: mockAuthUser(), access_token: 'tok_abc' })
    onboardingMock.mockResolvedValue({ onboarding_completed: false })

    const { router } = renderLogin()

    await user.type(screen.getByPlaceholderText(/you@example.com/i), 'new@example.com')
    await user.type(screen.getByPlaceholderText(/enter your password/i), 'hunter2!')
    await user.click(screen.getByRole('button', { name: /sign in/i }))

    await waitFor(() => {
      expect(router.state.location.pathname).toBe('/onboarding/style-profile')
    })
  })

  it('shows an error message and stays on the page when login fails', async () => {
    const user = userEvent.setup()
    loginMock.mockRejectedValue(new Error('Invalid credentials'))

    const { router } = renderLogin()

    await user.type(screen.getByPlaceholderText(/you@example.com/i), 'bad@example.com')
    await user.type(screen.getByPlaceholderText(/enter your password/i), 'wrong')
    await user.click(screen.getByRole('button', { name: /sign in/i }))

    expect(await screen.findByText(/invalid credentials|login failed/i)).toBeInTheDocument()
    expect(router.state.location.pathname).toBe('/login')
  })

  it('still reaches the dashboard if the onboarding-status check fails', async () => {
    const user = userEvent.setup()
    loginMock.mockResolvedValue({ user: mockAuthUser(), access_token: 'tok_abc' })
    onboardingMock.mockRejectedValue(new Error('status unavailable'))

    const { router } = renderLogin()

    await user.type(screen.getByPlaceholderText(/you@example.com/i), 'test@example.com')
    await user.type(screen.getByPlaceholderText(/enter your password/i), 'hunter2!')
    await user.click(screen.getByRole('button', { name: /sign in/i }))

    await waitFor(() => {
      expect(router.state.location.pathname).toBe('/dashboard')
    })
  })

  it('surfaces an OAuth error passed via the URL query string', async () => {
    const router = createMemoryRouter(
      [
        {
          path: '/login',
          element: (
            <MockAppProvider value={{ isAuthenticated: false }}>
              <Login />
            </MockAppProvider>
          ),
        },
      ],
      { initialEntries: ['/login?error=oauth_cancelled'] },
    )
    render(<RouterProvider router={router} />)

    expect(await screen.findByText(/google sign-in was cancelled/i)).toBeInTheDocument()
  })
})
