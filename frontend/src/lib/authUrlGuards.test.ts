import { describe, expect, it } from 'vitest'

import { skipRefreshOn401 } from './authUrlGuards'

describe('skipRefreshOn401', () => {
  it('skips refresh for auth endpoints', () => {
    expect(skipRefreshOn401(undefined)).toBe(true)
    expect(skipRefreshOn401('/auth/refresh')).toBe(true)
    expect(skipRefreshOn401('/auth/login')).toBe(true)
    expect(skipRefreshOn401('/auth/signup')).toBe(true)
    expect(skipRefreshOn401('/auth/register')).toBe(true)
    expect(skipRefreshOn401('http://localhost:8000/api/v1/auth/refresh')).toBe(true)
    expect(skipRefreshOn401('/auth/google/callback?x=1')).toBe(true)
  })

  it('allows refresh for API paths', () => {
    expect(skipRefreshOn401('/auth/me')).toBe(false)
    expect(skipRefreshOn401('/closet/')).toBe(false)
    expect(skipRefreshOn401('/trips/')).toBe(false)
  })
})
