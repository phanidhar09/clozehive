/**
 * Frontend observability — error tracking (Sentry), product analytics
 * (PostHog), and Web Vitals.
 *
 * Everything is gated by env vars and loaded dynamically, so when nothing is
 * configured there is zero bundle/runtime cost and the app behaves as before.
 *
 *   VITE_SENTRY_DSN   — enables Sentry browser error + performance tracking
 *   VITE_POSTHOG_KEY  — enables PostHog product analytics
 *   VITE_POSTHOG_HOST — PostHog ingestion host (default https://us.i.posthog.com)
 *   VITE_APP_VERSION  — release tag for grouping (optional)
 *   VITE_ENVIRONMENT  — environment tag (default "production")
 */

type ClozehiveSentryBridge = {
  captureException: (
    error: unknown,
    context?: import('@sentry/react').CaptureContext,
  ) => string;
  captureTestError: () => string;
};

export async function initObservability(): Promise<void> {
  await Promise.all([initSentry(), initPostHog()]);
  void initWebVitals();
}

async function initSentry(): Promise<void> {
  const dsn = import.meta.env.VITE_SENTRY_DSN as string | undefined;
  if (!dsn) return;

  try {
    const Sentry = await import('@sentry/react');
    Sentry.init({
      dsn,
      environment: (import.meta.env.VITE_ENVIRONMENT as string) || 'production',
      release: (import.meta.env.VITE_APP_VERSION as string) || undefined,
      integrations: [Sentry.browserTracingIntegration()],
      // Sample performance traces; lower in high-traffic production.
      tracesSampleRate: Number(import.meta.env.VITE_SENTRY_TRACES_SAMPLE_RATE ?? 0.1),
      // Propagate trace headers to our API so frontend spans link to backend traces.
      tracePropagationTargets: [/^\/api\//, /^\/uploads\//],
    });

    // Expose for ErrorBoundary + manual verification in DevTools.
    // Note: `throw new Error(...)` in the console is NOT captured by Sentry
    // (runs outside the app context). Use __clozehiveSentry.captureTestError().
    (window as unknown as { __clozehiveSentry?: ClozehiveSentryBridge }).__clozehiveSentry = {
      captureException: (error: unknown, context?: Parameters<typeof Sentry.captureException>[1]) =>
        Sentry.captureException(error, context),
      captureTestError: () => Sentry.captureException(new Error('Sentry frontend test')),
    };
  } catch (err) {
    // Never let observability setup break app startup.
    console.warn('Sentry init skipped:', err);
  }
}

// ── PostHog product analytics ────────────────────────────────────────────────
// Loaded lazily and cached so identify/reset/capture can reach the same client
// without re-importing. Null until init succeeds (or when no key is configured).
type PostHog = typeof import('posthog-js')['default'];
let posthogClient: PostHog | null = null;
// An identify() can fire before the async init resolves (e.g. a user restored
// from localStorage on page load). Buffer the latest call and flush it once the
// client is ready so we never drop the logged-in identity to the init race.
let pendingIdentify: { userId: string; properties?: Record<string, unknown> } | null = null;

async function initPostHog(): Promise<void> {
  const key = import.meta.env.VITE_POSTHOG_KEY as string | undefined;
  if (!key) return;

  try {
    const { default: posthog } = await import('posthog-js');
    posthog.init(key, {
      api_host: (import.meta.env.VITE_POSTHOG_HOST as string) || 'https://us.i.posthog.com',
      // SPA: capture route changes ourselves via SDK history listener.
      capture_pageview: true,
      capture_pageleave: true,
      // Don't fingerprint anonymous visitors before they log in / consent.
      person_profiles: 'identified_only',
      // Mask all text/inputs in session recordings if they're ever enabled.
      mask_all_text: true,
      mask_all_element_attributes: true,
      autocapture: true,
    });
    posthog.register({
      environment: (import.meta.env.VITE_ENVIRONMENT as string) || 'production',
      app_version: (import.meta.env.VITE_APP_VERSION as string) || undefined,
    });
    posthogClient = posthog;
    if (pendingIdentify) {
      posthog.identify(pendingIdentify.userId, pendingIdentify.properties);
      pendingIdentify = null;
    }
  } catch (err) {
    // Never let analytics setup break app startup.
    console.warn('PostHog init skipped:', err);
  }
}

/** Associate subsequent events with a logged-in user. Buffered until PostHog inits. */
export function analyticsIdentify(
  userId: string,
  properties?: Record<string, unknown>,
): void {
  try {
    if (posthogClient) {
      posthogClient.identify(userId, properties);
    } else {
      // Init may still be in flight (or unconfigured); replay once it's ready.
      pendingIdentify = { userId, properties };
    }
  } catch {
    /* best-effort */
  }
}

/** Track a product event. No-op when PostHog isn't configured. */
export function analyticsCapture(event: string, properties?: Record<string, unknown>): void {
  try {
    posthogClient?.capture(event, properties);
  } catch {
    /* best-effort */
  }
}

/** Clear the identified user (call on logout) so the next session starts anonymous. */
export function analyticsReset(): void {
  pendingIdentify = null;
  try {
    posthogClient?.reset();
  } catch {
    /* best-effort */
  }
}

/**
 * Report Core Web Vitals (LCP/INP/CLS/FCP/TTFB) to the backend RUM endpoint,
 * which records them as Prometheus metrics (clozehive_web_vital). Uses
 * sendBeacon so reports survive page unload. Always on — these are anonymous,
 * low-volume, and the endpoint validates/bounds everything it receives.
 */
async function initWebVitals(): Promise<void> {
  try {
    const { onLCP, onINP, onCLS, onFCP, onTTFB } = await import('web-vitals');
    const base = (import.meta.env.VITE_API_URL as string) || '';
    const url = `${base}/api/v1/rum/vitals`;

    const report = (metric: { name: string; value: number; rating: string }) => {
      const body = JSON.stringify({
        metric: metric.name,
        value: metric.value,
        rating: metric.rating,
      });
      try {
        // text/plain is CORS-safelisted: no preflight, which sendBeacon cannot
        // perform. An application/json Blob silently fails on any cross-origin
        // API base. The RUM endpoint parses the raw body regardless of type.
        if (navigator.sendBeacon) {
          navigator.sendBeacon(url, new Blob([body], { type: 'text/plain' }));
        } else {
          void fetch(url, { method: 'POST', body, headers: { 'Content-Type': 'text/plain' }, keepalive: true });
        }
      } catch {
        /* best-effort — never disrupt the page */
      }
    };

    onLCP(report);
    onINP(report);
    onCLS(report);
    onFCP(report);
    onTTFB(report);
  } catch (err) {
    console.warn('Web Vitals reporting skipped:', err);
  }
}
