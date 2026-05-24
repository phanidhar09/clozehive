/**
 * JWT token storage for the SPA.
 *
 * Security model (post-hardening):
 * ─────────────────────────────────
 * • ACCESS TOKEN  — kept in-memory (module-level variable). Falls back to
 *   sessionStorage for page-refresh survival (short TTL, acceptable risk).
 *   NO longer stored in localStorage (which persists indefinitely).
 *
 * • REFRESH TOKEN — stored exclusively in the HttpOnly cookie set by the
 *   backend (/api/v1/auth endpoints). This module intentionally has NO
 *   getter/setter for the refresh token so JavaScript can never read it.
 *
 * Migration: legacy call-sites that pass both tokens to set(access, refresh)
 * still compile — the refresh argument is accepted but silently ignored.
 */

const ACCESS_KEY = 'ch_access_token'

// In-memory primary store (cleared on tab close; survives React re-renders).
let _memAccess: string | null = null

// One-time migration: clear any old localStorage keys if present.
try {
  if (localStorage.getItem('ch_refresh_token')) {
    localStorage.removeItem('ch_refresh_token')
  }
  // Migrate access token from localStorage → sessionStorage on first load.
  const legacy = localStorage.getItem(ACCESS_KEY)
  if (legacy) {
    sessionStorage.setItem(ACCESS_KEY, legacy)
    localStorage.removeItem(ACCESS_KEY)
  }
} catch { /* ignore — private browsing etc. */ }

export const tokenStorage = {
  getAccess(): string | null {
    if (_memAccess) return _memAccess
    // Fallback: sessionStorage survives page refresh but not tab close.
    try {
      const stored = sessionStorage.getItem(ACCESS_KEY)
      if (stored) _memAccess = stored
      return stored
    } catch {
      return null
    }
  },

  /** @deprecated Refresh token now lives in HttpOnly cookie only — always returns null. */
  getRefresh(): string | null {
    return null
  },

  /**
   * Store the access token in memory + sessionStorage.
   * @param access - The JWT access token to store.
   * @param _refresh - Ignored: refresh token is set as HttpOnly cookie by the server.
   */
  set(access: string, _refresh?: string): void {
    _memAccess = access
    try {
      sessionStorage.setItem(ACCESS_KEY, access)
    } catch { /* sessionStorage unavailable — in-memory only */ }
  },

  /**
   * Clear the stored access token. The HttpOnly refresh cookie is cleared
   * server-side by the /auth/logout endpoint.
   */
  clear(): void {
    _memAccess = null
    try {
      sessionStorage.removeItem(ACCESS_KEY)
    } catch { /* ignore */ }
    // Belt-and-suspenders: remove any old localStorage remnants.
    try {
      localStorage.removeItem(ACCESS_KEY)
      localStorage.removeItem('ch_refresh_token')
    } catch { /* ignore */ }
  },
}
