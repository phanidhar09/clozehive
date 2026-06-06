import { test, expect, type Page } from '@playwright/test'

/**
 * Auth flow E2E smoke tests.
 *
 * Fully self-contained: every backend call is stubbed with page.route(), so
 * these run against the dev server without a live API or database.
 *
 * Storage model (see src/lib/tokenStorage.ts + src/store/index.ts):
 *   - access token  → sessionStorage['ch_access_token']
 *   - user profile  → localStorage['ch_user']
 */

const TEST_USER = {
  id: '00000000-0000-0000-0000-000000000001',
  email: 'test@example.com',
  username: 'testuser',
  name: 'Test User',
  role: 'user',
}

/**
 * Stub the endpoints the dashboard hits on first load so it renders cleanly.
 *
 * NOTE: Playwright matches routes in REVERSE registration order (last wins), so
 * the broad catch-all is registered FIRST; the specific routes registered after
 * it take priority. Tests that add their own specific routes after calling this
 * helper will likewise win over the catch-all.
 */
async function stubAuthedBootstrap(page: Page) {
  // Catch-all first — swallow anything not specifically handled so nothing hangs.
  await page.route('**/api/v1/**', route => route.fulfill({ json: {} }))
  await page.route('**/api/v1/closet/**', route =>
    route.fulfill({ json: { items: [], total: 0, page: 1, per_page: 500 } }),
  )
  await page.route('**/api/v1/auth/me', route => route.fulfill({ json: TEST_USER }))
}

test.describe('Login flow', () => {
  test('successful login lands on the dashboard', async ({ page }) => {
    // Catch-all + bootstrap first, then specific routes so they take priority.
    await stubAuthedBootstrap(page)
    await page.route('**/api/v1/auth/login', route =>
      route.fulfill({ json: { user: TEST_USER, access_token: 'tok_e2e' } }),
    )
    await page.route('**/api/v1/profile/onboarding-status', route =>
      route.fulfill({ json: { onboarding_completed: true } }),
    )

    await page.goto('/login')

    await page.getByPlaceholder(/you@example.com/i).fill('test@example.com')
    await page.getByPlaceholder(/enter your password/i).fill('hunter2!')
    await page.getByRole('button', { name: /sign in/i }).click()

    await expect(page).toHaveURL(/\/dashboard/)
    // Access token persisted for subsequent requests.
    const token = await page.evaluate(() => sessionStorage.getItem('ch_access_token'))
    expect(token).toBe('tok_e2e')
  })

  test('invalid credentials show an inline error and stay on /login', async ({ page }) => {
    await page.route('**/api/v1/auth/login', route =>
      route.fulfill({ status: 401, json: { detail: 'Invalid credentials' } }),
    )

    await page.goto('/login')

    await page.getByPlaceholder(/you@example.com/i).fill('bad@example.com')
    await page.getByPlaceholder(/enter your password/i).fill('wrongpass')
    await page.getByRole('button', { name: /sign in/i }).click()

    await expect(page.getByText(/invalid credentials|login failed/i)).toBeVisible()
    await expect(page).toHaveURL(/\/login/)
  })

  test('a cancelled Google OAuth redirect surfaces an error banner', async ({ page }) => {
    await page.goto('/login?error=oauth_cancelled')
    await expect(page.getByText(/google sign-in was cancelled/i)).toBeVisible()
  })
})

test.describe('Protected routes', () => {
  test('unauthenticated visit to a protected page redirects to /login', async ({ page }) => {
    await page.goto('/dashboard')
    await expect(page).toHaveURL(/\/login/)
  })

  test('an already-authenticated user is bounced from /login to /dashboard', async ({ page }) => {
    await stubAuthedBootstrap(page)
    // Seed auth state the way the app does on login.
    await page.addInitScript(
      ([user, token]) => {
        sessionStorage.setItem('ch_access_token', token as string)
        localStorage.setItem('ch_user', JSON.stringify(user))
      },
      [TEST_USER, 'tok_e2e'],
    )

    await page.goto('/login')
    await expect(page).toHaveURL(/\/dashboard/)
  })
})
