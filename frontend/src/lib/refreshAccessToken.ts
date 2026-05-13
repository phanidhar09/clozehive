/**
 * Refresh access + refresh tokens via POST /auth/refresh (no interceptors).
 * Single-flight: concurrent callers share one in-flight refresh.
 */

import axios from 'axios'

import { apiOrigin } from './apiOrigin'
import { tokenStorage } from './tokenStorage'

const refreshClient = axios.create({
  baseURL: `${apiOrigin()}/api/v1`,
  timeout: 30_000,
  headers: { 'Content-Type': 'application/json' },
})

let inFlight: Promise<string> | null = null

/** Test helper — reset single-flight state */
export function __resetRefreshFlightForTests(): void {
  inFlight = null
}

export async function refreshAccessToken(): Promise<string> {
  const rt = tokenStorage.getRefresh()
  if (!rt) throw new Error('no_refresh_token')

  if (!inFlight) {
    inFlight = refreshClient
      .post<{ access_token: string; refresh_token: string }>('/auth/refresh', {
        refresh_token: rt,
      })
      .then(res => {
        const a = String(res.data.access_token)
        const r = String(res.data.refresh_token)
        tokenStorage.set(a, r)
        return a
      })
      .finally(() => {
        inFlight = null
      })
  }

  return inFlight
}
