import { useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { Sparkles, Loader2 } from 'lucide-react'
import { tokenStorage, authApi } from '@/lib/api'
import { useApp } from '@/store'

const INFLIGHT_KEY = 'ch_oauth_inflight'

/**
 * Completes Google OAuth: tokens arrive as query params on /oauth/callback.
 *
 * React 18 Strict Mode runs effects twice in development. We must not call
 * `history.replaceState` (which strips the query) before both runs have had
 * a chance to read `access_token` / `refresh_token`, or the second run sees an
 * empty URL and sends the user to "Google sign-in failed".
 */
export default function OAuthCallback() {
  const navigate = useNavigate()
  const { login } = useApp()

  useEffect(() => {
    const params = new URLSearchParams(window.location.search)
    const accessToken = params.get('access_token')
    const refreshToken = params.get('refresh_token')

    if (!accessToken || !refreshToken) {
      navigate('/login?error=oauth_failed', { replace: true })
      return
    }

    if (sessionStorage.getItem(INFLIGHT_KEY) === '1') {
      return
    }
    sessionStorage.setItem(INFLIGHT_KEY, '1')

    tokenStorage.set(accessToken, refreshToken)

    const finish = () => {
      sessionStorage.removeItem(INFLIGHT_KEY)
      window.history.replaceState({}, '', '/oauth/callback')
    }

    authApi
      .getMe()
      .then(user => {
        login(user, accessToken, refreshToken)
        navigate('/profile?onboarding=1', { replace: true })
      })
      .catch(err => {
        console.error('[OAuth] getMe failed after Google redirect', err)
        tokenStorage.clear()
        navigate('/login?error=oauth_failed', { replace: true })
      })
      .finally(finish)
  }, [])

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
