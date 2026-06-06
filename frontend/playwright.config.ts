import { defineConfig, devices } from '@playwright/test'

/**
 * Playwright E2E configuration.
 *
 * Specs live in ./e2e (outside src/, so Vitest never picks them up).
 * Tests stub the backend with page.route() interception, so they run fully
 * self-contained against a production-style preview build — no live API needed.
 *
 * Run:  npm run test:e2e        (headless)
 *       npm run test:e2e:ui     (interactive UI mode)
 *
 * First-time setup also requires the browser binaries:
 *       npx playwright install --with-deps chromium
 */
export default defineConfig({
  testDir: './e2e',
  // Each spec is independent; allow parallelism.
  fullyParallel: true,
  // Fail the CI build if a test.only is committed by accident.
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 2 : 0,
  workers: process.env.CI ? 1 : undefined,
  reporter: process.env.CI ? 'github' : 'list',
  timeout: 30_000,

  use: {
    baseURL: 'http://localhost:3000',
    trace: 'on-first-retry',
    screenshot: 'only-on-failure',
  },

  projects: [
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'] },
    },
  ],

  // Start the app automatically before the suite. Uses the dev server so no
  // build step is needed; reuse an already-running server locally.
  webServer: {
    command: 'npm run dev',
    url: 'http://localhost:3000',
    reuseExistingServer: !process.env.CI,
    timeout: 120_000,
  },
})
