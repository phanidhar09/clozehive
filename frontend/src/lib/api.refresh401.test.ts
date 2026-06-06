/**
 * Regression: axios response interceptor refreshes JWT on 401 and retries once.
 * Uses a custom axios adapter — no real API or cloud.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest'
import type { AxiosError, InternalAxiosRequestConfig } from 'axios'

const { refreshSpy, tokenStore } = vi.hoisted(() => {
  const refreshSpy = vi.fn(async () => 'new-access-token')
  const tokenStore = {
    access: 'stale-access',
    refresh: 'refresh-token',
  }
  return { refreshSpy, tokenStore }
})

let requestAttempt = 0

vi.mock('@/lib/apiOrigin', () => ({ apiOrigin: () => 'http://127.0.0.1:9' }))

vi.mock('@/lib/authUrlGuards', () => ({
  skipRefreshOn401: () => false,
}))

vi.mock('@/lib/refreshAccessToken', () => ({
  refreshAccessToken: () => refreshSpy(),
  __resetRefreshFlightForTests: vi.fn(),
}))

vi.mock('@/lib/tokenStorage', () => ({
  tokenStorage: {
    getAccess: () => tokenStore.access,
    getRefresh: () => tokenStore.refresh,
    set: (a: string, r: string) => {
      tokenStore.access = a
      tokenStore.refresh = r
    },
    clear: () => {
      tokenStore.access = ''
      tokenStore.refresh = ''
    },
  },
}))

vi.mock('axios', async importActual => {
  const ax = await importActual<typeof import('axios')>()
  return {
    ...ax,
    default: {
      ...ax.default,
      create: (defaults?: object) =>
        ax.default.create({
          ...defaults,
          adapter: async config => {
            requestAttempt += 1
            if (requestAttempt === 1) {
              const err = new Error('Unauthorized') as AxiosError
              err.isAxiosError = true
              err.config = config as InternalAxiosRequestConfig
              err.response = {
                status: 401,
                data: {},
                statusText: 'Unauthorized',
                headers: {},
                config: config as InternalAxiosRequestConfig,
              }
              throw err
            }
            return {
              data: { items: [] },
              status: 200,
              statusText: 'OK',
              headers: {},
              config,
              request: {},
            }
          },
        }),
    },
  }
})

describe('api client 401 handling', () => {
  beforeEach(async () => {
    vi.resetModules()
    requestAttempt = 0
    tokenStore.access = 'stale-access'
    tokenStore.refresh = 'refresh-token'
    refreshSpy.mockClear()
  })

  it('calls refresh once and retries the original request', async () => {
    const { closetApi } = await import('@/lib/api')
    const { items } = await closetApi.list()

    expect(refreshSpy).toHaveBeenCalledTimes(1)
    expect(items).toEqual([])
  })
})
