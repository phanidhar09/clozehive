import { test, expect, type Page } from '@playwright/test'

/**
 * Closet view E2E smoke test.
 *
 * Stubs the closet list endpoint and verifies the authenticated user can reach
 * the closet, see their items, and that an empty wardrobe shows the empty state.
 */

const TEST_USER = {
  id: '00000000-0000-0000-0000-000000000001',
  email: 'test@example.com',
  username: 'testuser',
  name: 'Test User',
  role: 'user',
}

const ITEM = {
  id: '11111111-1111-1111-1111-111111111111',
  user_id: TEST_USER.id,
  name: 'Blue Oxford Shirt',
  category: 'tops',
  color: 'blue',
  season: ['spring', 'fall'],
  occasion: ['work'],
  tags: [],
  wear_count: 3,
  created_at: new Date().toISOString(),
}

/** Seed auth state so the app boots logged-in. */
async function seedAuth(page: Page) {
  await page.addInitScript(
    ([user, token]) => {
      sessionStorage.setItem('ch_access_token', token as string)
      localStorage.setItem('ch_user', JSON.stringify(user))
    },
    [TEST_USER, 'tok_e2e'],
  )
  await page.route('**/api/v1/auth/me', route => route.fulfill({ json: TEST_USER }))
}

test.describe('Closet view', () => {
  test('renders wardrobe items returned by the API', async ({ page }) => {
    await seedAuth(page)
    // Catch-all first (Playwright matches last-registered first), then specifics.
    await page.route('**/api/v1/**', route => route.fulfill({ json: {} }))
    await page.route('**/api/v1/closet/**', route =>
      route.fulfill({ json: { items: [ITEM], total: 1, page: 1, per_page: 500 } }),
    )

    await page.goto('/closet')

    await expect(
      page.getByRole('main').getByRole('heading', { name: 'My Closet' }),
    ).toBeVisible()
    await expect(page.getByText('Blue Oxford Shirt')).toBeVisible()
  })

  test('shows the empty state when the wardrobe has no items', async ({ page }) => {
    await seedAuth(page)
    await page.route('**/api/v1/**', route => route.fulfill({ json: {} }))
    await page.route('**/api/v1/closet/**', route =>
      route.fulfill({ json: { items: [], total: 0, page: 1, per_page: 500 } }),
    )

    await page.goto('/closet')

    await expect(page.getByText(/your wardrobe is empty/i)).toBeVisible()
  })
})
