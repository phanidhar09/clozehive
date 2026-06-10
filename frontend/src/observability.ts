/**
 * Frontend observability — error tracking (Sentry) and, in Phase 6, Web Vitals.
 *
 * Everything is gated by env vars and loaded dynamically, so when nothing is
 * configured there is zero bundle/runtime cost and the app behaves as before.
 *
 *   VITE_SENTRY_DSN   — enables Sentry browser error + performance tracking
 *   VITE_APP_VERSION  — release tag for grouping (optional)
 *   VITE_ENVIRONMENT  — environment tag (default "production")
 */

export async function initObservability(): Promise<void> {
  await initSentry();
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
  } catch (err) {
    // Never let observability setup break app startup.
    console.warn('Sentry init skipped:', err);
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
