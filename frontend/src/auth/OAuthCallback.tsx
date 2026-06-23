import { useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { tokenStorage, authApi, profileApi } from '@/lib/api'
import { FaniLoader } from '@/components/system/FaniLoader'
import { useApp } from '@/store'

const INFLIGHT_KEY = 'ch_oauth_inflight'

function oauthFailureQuery(err: unknown): string {
  const params = new URLSearchParams({ error: 'oauth_failed' })
  const maybe = err as {
    response?: { status?: number; data?: unknown }
    message?: string
  }
  const status = maybe.response?.status
  const data = maybe.response?.data
  const detail =
    typeof data === 'object' && data && 'detail' in data && typeof data.detail === 'string'
      ? data.detail
      : ''

  if (status === 400) {
    params.set('reason', 'oauth_code_invalid')
  } else if (status === 401) {
    params.set('reason', 'oauth_exchange_unauthorized')
  } else if (status && status >= 500) {
    params.set('reason', 'oauth_exchange_server')
  } else if (typeof maybe.message === 'string' && maybe.message.toLowerCase().includes('network')) {
    params.set('reason', 'oauth_exchange_network')
  } else {
    params.set('reason', 'token_exchange')
  }

  if (detail) {
    params.set('detail', detail.slice(0, 200))
  }
  return params.toString()
}

/**
 * Completes Google OAuth via a secure two-step exchange:
 *
 * 1. The backend redirects here with a short-lived one-time `?code=` parameter
 *    (never the raw JWT tokens).
 * 2. We POST the code to /auth/oauth/exchange which returns the real tokens and
 *    immediately deletes the server-side entry so it cannot be replayed.
 *
 * React 18 Strict Mode runs effects twice in development. The `INFLIGHT_KEY`
 * flag prevents the second run from issuing a duplicate exchange request after
 * the first has already consumed the one-time code.
 */
export default function OAuthCallback() {
  const navigate = useNavigate()
  const { login } = useApp()

  useEffect(() => {
    const params = new URLSearchParams(window.location.search)
    const code = params.get('code')

    if (!code) {
      navigate('/login?error=oauth_failed', { replace: true })
      return
    }

    if (sessionStorage.getItem(INFLIGHT_KEY) === '1') {
      return
    }
    sessionStorage.setItem(INFLIGHT_KEY, '1')

    // Strip the one-time code from the URL immediately so it is not retained in
    // browser history even if the exchange call below fails.
    window.history.replaceState({}, '', '/oauth/callback')

    const finish = () => {
      sessionStorage.removeItem(INFLIGHT_KEY)
    }

    authApi
      .oauthExchange(code)
      .then(async ({ access_token }) => {
        // Refresh token is delivered as HttpOnly cookie by the server — do not store it here.
        tokenStorage.set(access_token)
        const user = await authApi.getMe()
        login(user, access_token)
        try {
          const st = await profileApi.getOnboardingStatus()
          if (!st.onboarding_completed) {
            navigate('/onboarding/style-profile', { replace: true })
            return
          }
        } catch {
          /* continue to dashboard */
        }
        navigate('/dashboard', { replace: true, state: { fromLogin: true } })
      })
      .catch(err => {
        // Log only the message — the raw axios error carries the full response
        // body and request config, which can include tokens.
        console.error('[OAuth] token exchange failed:', err instanceof Error ? err.message : String(err))
        tokenStorage.clear()
        navigate(`/login?${oauthFailureQuery(err)}`, { replace: true })
      })
      .finally(finish)
  }, [login, navigate])

  return (
    <div className="min-h-screen flex flex-col items-center justify-center bg-white dark:bg-slate-900">
      <FaniLoader messages={['Completing sign-in…']} subline="Setting up your wardrobe" />
    </div>
  )
}
