export function apiOrigin(): string {
  const raw = import.meta.env.VITE_API_URL as string | undefined
  const trimmed = raw?.trim().replace(/\/$/, '') ?? ''
  // Return empty string → relative URLs (/api/v1/...) so every call goes
  // through whatever is serving the page (Vite dev proxy or nginx).
  // Set VITE_API_URL only when the API lives on a different host than the frontend.
  return trimmed
}

/**
 * Hostnames only reachable inside Docker/K8s. Browsers must load `/uploads/...`
 * via the SPA origin (Vite proxy or frontend nginx), not these hosts.
 */
export function isNonPublicApiHostname(hostname: string): boolean {
  const h = hostname.toLowerCase()
  if (h === 'api-gateway' || h === 'backend' || h === 'gateway') return true
  if (h.endsWith('.svc.cluster.local')) return true
  if (h.endsWith('.docker.internal')) return true
  return false
}

/** Loopback hosts often used for the API in dev; see resolveUploadUrl rewrite when ``apiOrigin()`` is empty. */
export function isLoopbackHostname(hostname: string): boolean {
  const h = hostname.toLowerCase()
  return h === 'localhost' || h === '127.0.0.1' || h === '::1'
}

/**
 * Origin to prefix on `/uploads/...` when resolving image URLs in the browser.
 * Empty string keeps root-relative `/uploads/...` (same document origin).
 */
export function uploadsOrigin(): string {
  if (typeof window === 'undefined') {
    return apiOrigin()
  }
  const o = apiOrigin()
  if (!o) return ''
  try {
    const { hostname } = new URL(o)
    if (isNonPublicApiHostname(hostname)) {
      return window.location.origin
    }
  } catch {
    return o
  }
  return o
}
