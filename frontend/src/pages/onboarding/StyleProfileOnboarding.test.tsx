import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import {
  RouterProvider,
  createMemoryRouter,
} from 'react-router-dom'
import { vi } from 'vitest'
import StyleProfileOnboarding from '@/pages/onboarding/StyleProfileOnboarding'

vi.mock('@/lib/api', async importOriginal => {
  const actual = await importOriginal<typeof import('@/lib/api')>()
  return {
    ...actual,
    profileApi: {
      ...actual.profileApi,
      getStyleProfile: vi.fn(() => Promise.resolve(null)),
      patchStyleProfile: vi.fn(() => Promise.reject(new Error('not used in this test'))),
      completeOnboarding: vi.fn(() => Promise.resolve()),
    },
  }
})

describe('StyleProfileOnboarding', () => {
  it('shows the custom gender field only when Custom identity is selected', async () => {
    const user = userEvent.setup()
    const router = createMemoryRouter([
      { path: '/onboarding/style-profile', element: <StyleProfileOnboarding /> },
    ], { initialEntries: ['/onboarding/style-profile'] })

    render(<RouterProvider router={router} />)

    await user.click(await screen.findByRole('button', { name: 'Start' }))

    expect(await screen.findByText(/Gender \/ style identity/i)).toBeInTheDocument()
    expect(screen.queryByPlaceholderText(/Describe your gender/i)).not.toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: 'Custom' }))

    expect(
      await screen.findByPlaceholderText(/Describe your gender \/ style identity/i),
    ).toBeInTheDocument()
  })
})
