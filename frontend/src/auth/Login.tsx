import { useState, FormEvent, useEffect } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'
import { Eye, EyeOff, ArrowRight, Loader2, AlertCircle } from 'lucide-react'
import { useApp } from '@/store'
import { authApi, profileApi } from '@/lib/api'
import AuthShell from './AuthShell'
import GoogleButton from './GoogleButton'
import { parseAuthError } from './authError'

const OAUTH_ERRORS: Record<string, string> = {
  oauth_cancelled: 'Google sign-in was cancelled.',
  oauth_failed: 'Google sign-in failed. Please try again.',
  oauth_invalid_state: 'Invalid sign-in session. Please try again.',
  oauth_redis_unavailable:
    'Sign-in is temporarily unavailable: the server could not store your session (check Redis is running and REDIS_URL matches the API).',
  oauth_redirect_mismatch:
    'Google OAuth redirect URL does not match. In Google Cloud Console, set the redirect URI to exactly: your API host + /api/v1/auth/google/callback (same as GOOGLE_REDIRECT_URI in .env).',
}

const OAUTH_REASON_HINTS: Record<string, string> = {
  redirect_uri_mismatch:
    'Fix: Google Cloud Console → Credentials → your OAuth client → Authorized redirect URIs must include the same URL as GOOGLE_REDIRECT_URI.',
  invalid_client: 'Fix: Check GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET in your API .env.',
  token_exchange:
    'Fix: Ensure GOOGLE_REDIRECT_URI in .env exactly matches a redirect URI authorized in Google Cloud (including http vs https and port).',
}

export default function Login() {
  const navigate = useNavigate()
  const [searchParams] = useSearchParams()
  const { login } = useApp()

  const [identifier, setIdentifier] = useState('')
  const [password, setPassword] = useState('')
  const [showPw, setShowPw] = useState(false)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    const err = searchParams.get('error')
    const reason = searchParams.get('reason')
    if (!err) return
    let msg = OAUTH_ERRORS[err] ?? 'Sign-in failed. Please try again.'
    if (err === 'oauth_failed' && reason && OAUTH_REASON_HINTS[reason]) {
      msg = `${msg} ${OAUTH_REASON_HINTS[reason]}`
    }
    setError(msg)
  }, [searchParams])

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault()
    if (!identifier.trim() || !password) return
    setLoading(true)
    setError(null)
    try {
      const { user, access_token } = await authApi.login({
        identifier: identifier.trim(),
        password,
      })
      login(user, access_token)
      try {
        const st = await profileApi.getOnboardingStatus()
        if (!st.onboarding_completed) {
          navigate('/onboarding/style-profile', { replace: true })
          return
        }
      } catch {
        /* if status fails, continue to dashboard */
      }
      navigate('/dashboard', { replace: true, state: { fromLogin: true } })
    } catch (err: unknown) {
      setError(parseAuthError(err, 'Login failed'))
    } finally {
      setLoading(false)
    }
  }

  return (
    <AuthShell
      activeStep={0}
      brandHeading={<>Your wardrobe,<br /><span className="text-emerald-300">reimagined</span> by AI.</>}
      brandSub="Welcome back. Sign in to pick up where you left off — your closet, outfits and FANI are waiting."
    >
      {/* Heading */}
      <div className="mb-7">
        <h2 className="font-display font-bold text-2xl text-slate-900 dark:text-white mb-1">
          Welcome back 👋
        </h2>
        <p className="text-slate-500 dark:text-slate-400 text-sm">
          Sign in to access your AI wardrobe
        </p>
      </div>

      {/* Error banner */}
      {error && (
        <div className="flex items-start gap-2 p-3 mb-5 rounded-xl bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 text-red-600 dark:text-red-300 text-sm">
          <AlertCircle size={15} className="flex-shrink-0 mt-0.5" />
          <span>{error}</span>
        </div>
      )}

      <form onSubmit={handleSubmit} className="space-y-4">
        {/* Identifier */}
        <div className="space-y-1.5">
          <label className="label text-slate-700 dark:text-slate-300">Email or username</label>
          <input
            type="text"
            className="input w-full"
            placeholder="you@example.com or @username"
            value={identifier}
            onChange={e => setIdentifier(e.target.value)}
            autoComplete="username email"
            autoFocus
            required
          />
        </div>

        {/* Password */}
        <div className="space-y-1.5">
          <div className="flex items-center justify-between">
            <label className="label text-slate-700 dark:text-slate-300 mb-0">Password</label>
            <Link
              to="/forgot-password"
              className="text-xs text-brand-500 hover:text-brand-600 font-medium transition-colors"
            >
              Forgot password?
            </Link>
          </div>
          <div className="relative">
            <input
              type={showPw ? 'text' : 'password'}
              className="input w-full pr-11"
              placeholder="Enter your password"
              value={password}
              onChange={e => setPassword(e.target.value)}
              autoComplete="current-password"
              required
            />
            <button
              type="button"
              onClick={() => setShowPw(v => !v)}
              className="absolute right-3 top-1/2 -translate-y-1/2 text-slate-400 hover:text-slate-600 dark:hover:text-slate-300 transition-colors"
              aria-label={showPw ? 'Hide password' : 'Show password'}
            >
              {showPw ? <EyeOff size={18} /> : <Eye size={18} />}
            </button>
          </div>
        </div>

        {/* Submit */}
        <button
          type="submit"
          disabled={loading || !identifier.trim() || !password}
          className="w-full h-11 rounded-xl bg-gradient-brand text-white font-semibold text-sm flex items-center justify-center gap-2 shadow-lg hover:opacity-90 active:scale-[0.98] transition-all disabled:opacity-50 disabled:cursor-not-allowed mt-1"
        >
          {loading
            ? <><Loader2 size={16} className="animate-spin" /> Signing in…</>
            : <><span>Sign in</span> <ArrowRight size={16} /></>
          }
        </button>
      </form>

      {/* Divider */}
      <div className="flex items-center gap-3 my-5">
        <div className="flex-1 h-px bg-slate-200 dark:bg-slate-700" />
        <span className="text-xs text-slate-400">OR</span>
        <div className="flex-1 h-px bg-slate-200 dark:bg-slate-700" />
      </div>

      <GoogleButton label="Continue with Google" />

      {/* Sign up link */}
      <p className="text-center text-sm text-slate-500 dark:text-slate-400 mt-6">
        Don&apos;t have an account?{' '}
        <Link to="/signup" className="font-semibold text-brand-600 dark:text-brand-400 hover:underline">
          Create one free
        </Link>
      </p>
    </AuthShell>
  )
}
