import { useEffect, useRef } from 'react'
import { useNavigate } from 'react-router-dom'
import { Sparkles, Loader2 } from 'lucide-react'
import { tokenStorage, authApi } from '@/lib/api'
import { useApp } from '@/store'

export default function OAuthCallback() {
  const navigate = useNavigate()
  const { login } = useApp()
  const ran = useRef(false)

  useEffect(() => {
    // Guard against React 18 strict-mode double-invoke
    if (ran.current) return
    ran.current = true

    const params = new URLSearchParams(window.location.search)
    const accessToken = params.get('access_token')
    const refreshToken = params.get('refresh_token')

    if (!accessToken || !refreshToken) {
      navigate('/login?error=oauth_failed', { replace: true })
      return
    }

    // Remove tokens from browser history immediately
    window.history.replaceState({}, '', '/oauth/callback')

    tokenStorage.set(accessToken, refreshToken)

    authApi
      .getMe()
      .then(user => {
        login(user, accessToken, refreshToken)
        navigate('/profile?onboarding=1', { replace: true })
      })
      .catch(() => {
        tokenStorage.clear()
        navigate('/login?error=oauth_failed', { replace: true })
      })
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
