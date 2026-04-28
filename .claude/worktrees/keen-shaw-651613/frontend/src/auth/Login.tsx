/**
 * Login page
 *
 * - Email/username + password form with loading & error states
 * - Google Identity Services (One Tap + button) — gated on VITE_GOOGLE_CLIENT_ID
 * - Account lockout UX: distinguishes 429 "locked" from generic 401
 * - Forgot password link (placeholder — backend endpoint not yet implemented)
 */
import { useState, useEffect, useRef, FormEvent } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { Eye, EyeOff, Sparkles, ArrowRight, Loader2, AlertCircle, Clock } from 'lucide-react'
import { useApp } from '@/store'
import { authApi } from '@/lib/api'

// ── Google Identity Services type stubs ──────────────────────────────────────
// The real types come from @types/google.accounts; we use a minimal inline
// declaration to avoid adding a heavy dev-dep.
declare global {
  interface Window {
    google?: {
      accounts: {
        id: {
          initialize: (config: {
            client_id: string
            callback: (response: { credential: string }) => void
            auto_select?: boolean
            cancel_on_tap_outside?: boolean
          }) => void
          renderButton: (
            parent: HTMLElement,
            options: {
              type?: string
              theme?: string
              size?: string
              width?: number
              text?: string
            },
          ) => void
          prompt: () => void
          disableAutoSelect: () => void
        }
      }
    }
  }
}

const GOOGLE_CLIENT_ID = import.meta.env.VITE_GOOGLE_CLIENT_ID as string | undefined

const BRAND_ITEMS = [
  { emoji: '👗', label: 'Smart wardrobe AI' },
  { emoji: '✨', label: 'Personalised outfit picks' },
  { emoji: '🌍', label: 'Eco-conscious styling' },
  { emoji: '✈️', label: 'Travel packing assistant' },
]

// ── Helpers ───────────────────────────────────────────────────────────────────

/** Parse a lockout remaining-minutes value from a 429 detail string. */
function parseLockoutMinutes(detail: string): number | null {
  const m = detail.match(/(\d+)\s*minute/)
  return m ? Number(m[1]) : null
}

/** Extract an API error message from an axios error. */
function extractErrorMessage(err: unknown): { message: string; isLocked: boolean; lockMinutes: number | null } {
  const res = (err as { response?: { status?: number; data?: { detail?: string; error?: string } } })?.response
  const status = res?.status
  const detail = res?.data?.detail ?? res?.data?.error ?? (err instanceof Error ? err.message : 'Login failed')

  if (status === 429) {
    const mins = parseLockoutMinutes(detail)
    return { message: detail, isLocked: true, lockMinutes: mins }
  }
  return { message: detail, isLocked: false, lockMinutes: null }
}

// ── Component ─────────────────────────────────────────────────────────────────

export default function Login() {
  const navigate = useNavigate()
  const { login } = useApp()

  const [identifier, setIdentifier]   = useState('')
  const [password,   setPassword]     = useState('')
  const [showPw,     setShowPw]       = useState(false)
  const [loading,    setLoading]      = useState(false)
  const [gLoading,   setGLoading]     = useState(false)
  const [error,      setError]        = useState<string | null>(null)
  const [isLocked,   setIsLocked]     = useState(false)
  const [lockMinutes, setLockMinutes] = useState<number | null>(null)
  const [gReady,     setGReady]       = useState(false)

  const googleBtnRef = useRef<HTMLDivElement>(null)

  // ── Google Identity Services init ─────────────────────────────────────────
  useEffect(() => {
    if (!GOOGLE_CLIENT_ID) return

    function initGSI() {
      if (!window.google) return
      window.google.accounts.id.initialize({
        client_id: GOOGLE_CLIENT_ID!,
        callback: handleGoogleCredential,
        auto_select: false,
        cancel_on_tap_outside: true,
      })

      if (googleBtnRef.current) {
        window.google.accounts.id.renderButton(googleBtnRef.current, {
          type:  'standard',
          theme: 'outline',
          size:  'large',
          width: googleBtnRef.current.offsetWidth || 400,
          text:  'signin_with',
        })
      }

      setGReady(true)
    }

    // If the GSI script is already loaded (e.g. on hot reload), init immediately.
    if (window.google) {
      initGSI()
      return
    }

    // Otherwise inject the script and wait for it to load.
    const existingScript = document.getElementById('google-gsi-script')
    if (existingScript) {
      existingScript.addEventListener('load', initGSI)
      return () => existingScript.removeEventListener('load', initGSI)
    }

    const script = document.createElement('script')
    script.id  = 'google-gsi-script'
    script.src = 'https://accounts.google.com/gsi/client'
    script.async = true
    script.defer = true
    script.onload = initGSI
    document.head.appendChild(script)

    return () => {
      // Cleanup: disable auto-select when navigating away
      window.google?.accounts.id.disableAutoSelect()
    }
  }, []) // eslint-disable-line react-hooks/exhaustive-deps

  // ── Auth handlers ─────────────────────────────────────────────────────────

  async function handleGoogleCredential(response: { credential: string }) {
    setGLoading(true)
    setError(null)
    setIsLocked(false)
    try {
      const result = await authApi.google(response.credential)
      login(result.user, result.tokens)
      navigate('/dashboard', { replace: true })
    } catch (err) {
      const { message } = extractErrorMessage(err)
      setError(message)
    } finally {
      setGLoading(false)
    }
  }

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault()
    if (!identifier.trim() || !password) return

    setLoading(true)
    setError(null)
    setIsLocked(false)
    setLockMinutes(null)

    try {
      const result = await authApi.login({ identifier: identifier.trim(), password })
      login(result.user, result.tokens)
      navigate('/dashboard', { replace: true })
    } catch (err: unknown) {
      const { message, isLocked: locked, lockMinutes: mins } = extractErrorMessage(err)
      setError(message)
      setIsLocked(locked)
      setLockMinutes(mins)
    } finally {
      setLoading(false)
    }
  }

  // ── Render ────────────────────────────────────────────────────────────────

  return (
    <div className="min-h-screen flex">
      {/* ── Left branding panel ────────────────────────────────────────────── */}
      <div
        className="hidden lg:flex lg:w-[45%] relative overflow-hidden flex-col justify-between p-12"
        style={{ background: 'linear-gradient(135deg, #18143A 0%, #3B35A0 50%, #7670F1 100%)' }}
      >
        {/* Decorative circles */}
        <div className="absolute -top-24 -right-24 w-72 h-72 rounded-full bg-white/5 blur-2xl" />
        <div className="absolute -bottom-32 -left-16 w-96 h-96 rounded-full bg-brand-500/20 blur-3xl" />
        <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-64 h-64 rounded-full bg-violet-400/10 blur-2xl" />

        {/* Logo */}
        <div className="relative flex items-center gap-3">
          <div className="w-11 h-11 rounded-2xl bg-white/15 backdrop-blur flex items-center justify-center shadow-lg border border-white/20">
            <Sparkles size={22} className="text-white" />
          </div>
          <div>
            <div className="font-display font-bold text-xl text-white">ClozéHive</div>
            <div className="text-xs text-white/50 font-medium tracking-wide">AI Wardrobe</div>
          </div>
        </div>

        {/* Hero text */}
        <div className="relative space-y-6">
          <div>
            <h1 className="font-display font-bold text-4xl text-white leading-tight mb-3">
              Your wardrobe,<br />
              <span className="text-brand-300">reimagined</span> by AI.
            </h1>
            <p className="text-white/60 text-base leading-relaxed">
              Join thousands of style-conscious people who let ClozéHive curate perfect outfits every day.
            </p>
          </div>

          <div className="space-y-3">
            {BRAND_ITEMS.map(({ emoji, label }) => (
              <div key={label} className="flex items-center gap-3">
                <div className="w-9 h-9 rounded-xl bg-white/10 flex items-center justify-center text-lg flex-shrink-0">
                  {emoji}
                </div>
                <span className="text-white/80 text-sm font-medium">{label}</span>
              </div>
            ))}
          </div>
        </div>

        <div className="relative">
          <blockquote className="text-white/50 text-sm italic border-l-2 border-white/20 pl-4">
            "Getting dressed has never been this effortless."
          </blockquote>
        </div>
      </div>

      {/* ── Right form panel ───────────────────────────────────────────────── */}
      <div className="flex-1 flex items-center justify-center p-6 sm:p-12 bg-white dark:bg-slate-900">
        <div className="w-full max-w-md animate-slide-up">

          {/* Mobile logo */}
          <div className="lg:hidden flex items-center gap-2 mb-8">
            <div className="w-9 h-9 rounded-xl bg-gradient-brand flex items-center justify-center">
              <Sparkles size={18} className="text-white" />
            </div>
            <span className="font-display font-bold text-lg text-slate-800 dark:text-slate-100">ClozéHive</span>
          </div>

          {/* Heading */}
          <div className="mb-8">
            <h2 className="font-display font-bold text-2xl text-slate-900 dark:text-white mb-1">
              Welcome back 👋
            </h2>
            <p className="text-slate-500 dark:text-slate-400 text-sm">
              Sign in to access your AI wardrobe
            </p>
          </div>

          {/* Error / lockout banner */}
          {error && (
            <div className={`flex items-start gap-2 p-3 mb-5 rounded-xl border text-sm ${
              isLocked
                ? 'bg-amber-50 dark:bg-amber-900/20 border-amber-200 dark:border-amber-700 text-amber-700 dark:text-amber-300'
                : 'bg-red-50 dark:bg-red-900/20 border-red-200 dark:border-red-800 text-red-600 dark:text-red-300'
            }`}>
              {isLocked
                ? <Clock size={15} className="flex-shrink-0 mt-0.5" />
                : <AlertCircle size={15} className="flex-shrink-0 mt-0.5" />
              }
              <div>
                {isLocked
                  ? <>
                      <p className="font-semibold mb-0.5">Account temporarily locked</p>
                      <p className="text-xs opacity-90">
                        {lockMinutes != null
                          ? `Too many failed attempts. Try again in ${lockMinutes} minute${lockMinutes === 1 ? '' : 's'}.`
                          : error}
                      </p>
                    </>
                  : error
                }
              </div>
            </div>
          )}

          <form onSubmit={handleSubmit} className="space-y-4">
            {/* Identifier */}
            <div className="space-y-1.5">
              <label className="label text-slate-700 dark:text-slate-300">
                Email or username
              </label>
              <input
                type="text"
                className="input w-full"
                placeholder="you@example.com or @username"
                value={identifier}
                onChange={e => setIdentifier(e.target.value)}
                autoComplete="username email"
                autoFocus
                required
                disabled={loading}
              />
            </div>

            {/* Password */}
            <div className="space-y-1.5">
              <div className="flex items-center justify-between">
                <label className="label text-slate-700 dark:text-slate-300">Password</label>
                {/* Forgot password — link to a future /forgot-password page */}
                <Link
                  to="/forgot-password"
                  className="text-xs text-brand-600 dark:text-brand-400 hover:underline font-medium"
                  tabIndex={-1}
                >
                  Forgot password?
                </Link>
              </div>
              <div className="relative">
                <input
                  type={showPw ? 'text' : 'password'}
                  className="input w-full pr-11"
                  placeholder="••••••••"
                  value={password}
                  onChange={e => setPassword(e.target.value)}
                  autoComplete="current-password"
                  required
                  disabled={loading}
                />
                <button
                  type="button"
                  onClick={() => setShowPw(v => !v)}
                  className="absolute right-3 top-1/2 -translate-y-1/2 text-slate-400 hover:text-slate-600 dark:hover:text-slate-300 transition-colors"
                  tabIndex={-1}
                >
                  {showPw ? <EyeOff size={18} /> : <Eye size={18} />}
                </button>
              </div>
            </div>

            {/* Submit */}
            <button
              type="submit"
              disabled={loading || gLoading || !identifier.trim() || !password}
              className="w-full h-11 rounded-xl bg-gradient-brand text-white font-semibold text-sm flex items-center justify-center gap-2 shadow-lg hover:opacity-90 active:scale-[0.98] transition-all disabled:opacity-50 disabled:cursor-not-allowed mt-2"
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

          {/* Google button ─────────────────────────────────────────────────── */}
          {GOOGLE_CLIENT_ID ? (
            // Real GSI-rendered button (appears once the script loads)
            <div className="relative">
              {/* GSI injects its own button into this div */}
              <div ref={googleBtnRef} className="w-full flex justify-center" />

              {/* Loading overlay while GSI script is initialising */}
              {!gReady && (
                <div className="w-full h-11 rounded-xl border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 flex items-center justify-center gap-3 text-sm text-slate-500">
                  <Loader2 size={16} className="animate-spin" />
                  Loading Google…
                </div>
              )}

              {/* Global loading overlay during Google auth */}
              {gLoading && (
                <div className="absolute inset-0 flex items-center justify-center rounded-xl bg-white/80 dark:bg-slate-900/80">
                  <Loader2 size={20} className="animate-spin text-brand-600" />
                </div>
              )}
            </div>
          ) : (
            // Fallback when VITE_GOOGLE_CLIENT_ID is not configured
            <button
              type="button"
              disabled
              title="Configure VITE_GOOGLE_CLIENT_ID in your .env to enable Google login"
              className="w-full h-11 rounded-xl border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-800/50 text-slate-400 dark:text-slate-500 text-sm font-medium flex items-center justify-center gap-3 cursor-not-allowed"
            >
              <GoogleSvg />
              Continue with Google
              <span className="ml-auto text-[10px] bg-slate-200 dark:bg-slate-700 text-slate-500 dark:text-slate-400 px-1.5 py-0.5 rounded font-mono">
                ENV
              </span>
            </button>
          )}

          {/* New user hint */}
          <div className="mt-5 p-3 rounded-xl bg-brand-50 dark:bg-brand-900/20 border border-brand-200 dark:border-brand-800">
            <p className="text-xs text-brand-700 dark:text-brand-300 font-medium mb-1">✨ New here?</p>
            <p className="text-xs text-brand-600 dark:text-brand-400">
              Create a free account to unlock AI outfit suggestions, travel packing, and your personal wardrobe.
            </p>
          </div>

          {/* Sign up link */}
          <p className="text-center text-sm text-slate-500 dark:text-slate-400 mt-6">
            Don't have an account?{' '}
            <Link to="/signup" className="font-semibold text-brand-600 dark:text-brand-400 hover:underline">
              Create one free
            </Link>
          </p>
        </div>
      </div>
    </div>
  )
}

// ── Google logo SVG ───────────────────────────────────────────────────────────

function GoogleSvg() {
  return (
    <svg width="18" height="18" viewBox="0 0 48 48" fill="none" aria-hidden="true">
      <path d="M43.611 20.083H42V20H24v8h11.303c-1.649 4.657-6.08 8-11.303 8-6.627 0-12-5.373-12-12s5.373-12 12-12c3.059 0 5.842 1.154 7.961 3.039l5.657-5.657C34.046 6.053 29.268 4 24 4 12.955 4 4 12.955 4 24s8.955 20 20 20 20-8.955 20-20c0-1.341-.138-2.65-.389-3.917z" fill="#FFC107"/>
      <path d="M6.306 14.691l6.571 4.819C14.655 15.108 19.001 12 24 12c3.059 0 5.842 1.154 7.961 3.039l5.657-5.657C34.046 6.053 29.268 4 24 4 16.318 4 9.656 8.337 6.306 14.691z" fill="#FF3D00"/>
      <path d="M24 44c5.166 0 9.86-1.977 13.409-5.192l-6.19-5.238A11.91 11.91 0 0 1 24 36c-5.202 0-9.619-3.317-11.283-7.946l-6.522 5.025C9.505 39.556 16.227 44 24 44z" fill="#4CAF50"/>
      <path d="M43.611 20.083H42V20H24v8h11.303a12.04 12.04 0 0 1-4.087 5.571l.003-.002 6.19 5.238C36.971 39.205 44 34 44 24c0-1.341-.138-2.65-.389-3.917z" fill="#1976D2"/>
    </svg>
  )
}
