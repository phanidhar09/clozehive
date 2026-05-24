/**
 * Refresh access token via POST /auth/refresh.
 *
 * Security: the refresh token lives in an HttpOnly cookie, so we do NOT read
 * or send it in the request body.  We only need ``withCredentials: true`` so
 * the browser automatically attaches the HttpOnly cookie.
 *
 * Single-flight: concurrent callers share one in-flight refresh promise so we
 * never issue parallel refresh requests (which would invalidate each other).
 */

import axios from 'axios'

import { apiOrigin } from './apiOrigin'
import { tokenStorage } from './tokenStorage'

const refreshClient = axios.create({
  baseURL: `${apiOrigin()}/api/v1`,
  timeout: 30_000,
  headers: { 'Content-Type': 'application/json' },
  // CRITICAL: must be true so the browser sends the HttpOnly refresh cookie.
  withCredentials: true,
})

let inFlight: Promise<string> | null = null

/** Test helper — reset single-flight state. */
export function __resetRefreshFlightForTests(): void {
  inFlight = null
}

export async function refreshAccessToken(): Promise<string> {
  // No local refresh token to check — it lives only in the HttpOnly cookie.
  // If the cookie is absent/expired the server will return 401 and we'll
  // propagate the error to trigger re-login.

  if (!inFlight) {
    inFlight = refreshClient
      .post<{ access_token: string }>('/auth/refresh')
      .then(res => {
        const access = String(res.data.access_token)
        // Store new access token; refresh token is rotated via cookie by server.
        tokenStorage.set(access)
        return access
      })
      .finally(() => {
        inFlight = null
      })
  }

  return inFlight
}
