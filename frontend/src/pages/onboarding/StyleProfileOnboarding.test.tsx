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
      submitOnboarding: vi.fn(() => Promise.reject(new Error('not used in this test'))),
      completeOnboarding: vi.fn(() => Promise.resolve()),
    },
  }
})

describe('StyleProfileOnboarding', () => {
  it('walks the multi-step flow and reaches the About You / gender step', async () => {
    const user = userEvent.setup()
    const router = createMemoryRouter([
      { path: '/onboarding/style-profile', element: <StyleProfileOnboarding /> },
    ], { initialEntries: ['/onboarding/style-profile'] })

    render(<RouterProvider router={router} />)

    // First step renders once the existing-profile pre-fetch resolves
    expect(await screen.findByRole('heading', { name: /Your Style Vibe/i })).toBeInTheDocument()

    // Advancing moves to the next step
    await user.click(screen.getByRole('button', { name: /Next/i }))
    expect(await screen.findByRole('heading', { name: /Your Lifestyle/i })).toBeInTheDocument()

    // Continue through fit → colours → goals → body (the final "About You" step)
    for (let i = 0; i < 4; i++) {
      await user.click(screen.getByRole('button', { name: /Next/i }))
    }

    expect(await screen.findByRole('heading', { name: /A Little About You/i })).toBeInTheDocument()
    // Gender selection lives on this step
    expect(screen.getByText(/I shop in the/i)).toBeInTheDocument()
    // Final step swaps the Next button for the submit CTA
    expect(screen.getByRole('button', { name: /Build My Profile/i })).toBeInTheDocument()
  })
})
