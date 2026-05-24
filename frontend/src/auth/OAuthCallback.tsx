import { useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { Sparkles, Loader2 } from 'lucide-react'
import { tokenStorage, authApi, profileApi } from '@/lib/api'
import { useApp } from '@/store'

const INFLIGHT_KEY = 'ch_oauth_inflight'

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
        console.error('[OAuth] token exchange failed', err)
        tokenStorage.clear()
        navigate('/login?error=oauth_failed', { replace: true })
      })
      .finally(finish)
  }, [login, navigate])

  return (
    <div className="min-h-screen flex flex-col items-center justify-center gap-6 bg-white dark:bg-slate-900">
      <div className="w-14 h-14 rounded-2xl bg-gradient-to-br from-brand-500 to-violet-600 flex items-center justify-center shadow-lg">
        <Sparkles size={26} className="text-white" />
      </div>

      <div className="flex flex-col items-center gap-3 text-center">
        <Loader2 size={24} className="animate-spin text-brand-500" />
        <p className="text-slate-700 dark:text-slate-300 font-medium">Completing sign-in…</p>
        <p className="text-xs text-slate-400 dark:text-slate-500">Setting up your wardrobe</p>
      </div>
    </div>
  )
}
