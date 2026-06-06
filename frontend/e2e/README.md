# E2E tests (Playwright)

Real-browser smoke tests for the core user flows. They are **self-contained**:
every backend request is stubbed with `page.route()`, so no live API or database
is required.

## Setup (first time only)

```bash
npm install                                   # installs @playwright/test
npx playwright install --with-deps chromium   # downloads the browser binary
```

## Run

```bash
npm run test:e2e        # headless
npm run test:e2e:ui     # interactive UI mode
```

The Playwright config (`playwright.config.ts`) auto-starts the dev server
(`npm run dev` on port 3000) before the suite and reuses an already-running one
locally.

## What's covered

| Spec               | Flow                                                          |
|--------------------|--------------------------------------------------------------|
| `auth.spec.ts`     | Login success → dashboard, bad credentials, OAuth error, protected-route redirects |
| `closet.spec.ts`   | Authenticated closet renders items / shows empty state       |

## Notes

- Specs live here in `e2e/`, **outside** `src/`, so Vitest never picks them up.
- Vitest covers component + integration logic (`src/**/*.test.tsx`); Playwright
  covers real-browser flows. They are complementary.
- Auth state is seeded the way the app stores it: access token in
  `sessionStorage['ch_access_token']`, user profile in `localStorage['ch_user']`.
