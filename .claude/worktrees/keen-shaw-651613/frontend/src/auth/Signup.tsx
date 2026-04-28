/**
 * Signup page
 *
 * - Full name / email / username / password form
 * - Password strength meter aligned with backend rules (min 8 chars)
 * - Password confirmation check
 * - Google Identity Services (One Tap + button) — gated on VITE_GOOGLE_CLIENT_ID
 * - API conflict errors (409 duplicate email/username) surfaced clearly
 */
import { useState, useEffect, useRef, FormEvent } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { Eye, EyeOff, Sparkles, ArrowRight, Loader2, AlertCircle, CheckCircle2 } from 'lucide-react'
import { useApp } from '@/store'
import { authApi } from '@/lib/api'

const GOOGLE_CLIENT_ID = import.meta.env.VITE_GOOGLE_CLIENT_ID as string | undefined

// ── Google Identity Services type stubs (same as Login.tsx) ──────────────────
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
            options: { type?: string; theme?: string; size?: string; width?: number; text?: string },
          ) => void
          prompt: () => void
          disableAutoSelect: () => void
        }
      }
    }
  }
}

// ── Password strength component ───────────────────────────────────────────────
// Backend requires: min 8 chars, at least one uppercase, at least one digit.

const PW_CHECKS = [
  { label: '8+ characters',   test: (p: string) => p.length >= 8 },
  { label: 'Uppercase letter', test: (p: string) => /[A-Z]/.test(p) },
  { label: 'Number',           test: (p: string) => /\d/.test(p) },
]

function PasswordStrength({ password }: { password: string }) {
  if (!password) return null
  const score = PW_CHECKS.filter(c => c.test(password)).length
  const barColor =
    score === 0 ? 'bg-slate-200 dark:bg-slate-700'
    : score === 1 ? 'bg-red-400'
    : score === 2 ? 'bg-amber-400'
    : 'bg-emerald-500'

  return (
    <div className="space-y-2 pt-1">
      <div className="flex gap-1">
        {[0, 1, 2].map(i => (
          <div
            key={i}
            className={`h-1 flex-1 rounded-full transition-all duration-300 ${i < score ? barColor : 'bg-slate-200 dark:bg-slate-700'}`}
          />
        ))}
      </div>
      <div className="flex gap-3 flex-wrap">
        {PW_CHECKS.map(c => {
          const pass = c.test(password)
          return (
            <span
              key={c.label}
              className={`text-[11px] flex items-center gap-1 ${pass ? 'text-emerald-600 dark:text-emerald-400' : 'text-slate-400'}`}
            >
              <CheckCircle2 size={11} className={pass ? 'text-emerald-500' : 'text-slate-300'} />
              {c.label}
            </span>
          )
        })}
      </div>
    </div>
  )
}

// ── Helpers ───────────────────────────────────────────────────────────────────

function extractError(err: unknown): string {
  const res = (err as { response?: { data?: { detail?: string; error?: string } } })?.response
  return res?.data?.detail ?? res?.data?.error ?? (err instanceof Error ? err.message : 'Signup failed')
}

// ── Component ─────────────────────────────────────────────────────────────────

export default function Signup() {
  const navigate = useNavigate()
  const { login }  = useApp()

  const [form, setForm]     = useState({ name: '', email: '', username: '', password: '', confirm: '' })
  const [showPw,  setShowPw]  = useState(false)
  const [loading, setLoading] = useState(false)
  const [gLoading, setGLoading] = useState(false)
  const [error,   setError]   = useState<string | null>(null)
  const [gReady,  setGReady]  = useState(false)

  const googleBtnRef = useRef<HTMLDivElement>(null)

  const set = (k: keyof typeof form) => (e: React.ChangeEvent<HTMLInputElement>) =>
    setForm(f => ({ ...f, [k]: e.target.value }))

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
          type: 'standard', theme: 'outline', size: 'large',
          width: googleBtnRef.current.offsetWidth || 400,
          text: 'signup_with',
        })
      }
      setGReady(true)
    }

    if (window.google) { initGSI(); return }

    const existing = document.getElementById('google-gsi-script')
    if (existing) { existing.addEventListener('load', initGSI); return () => existing.removeEventListener('load', initGSI) }

    const script = document.createElement('script')
    script.id = 'google-gsi-script'
    script.src = 'https://accounts.google.com/gsi/client'
    script.async = true; script.defer = true
    script.onload = initGSI
    document.head.appendChild(script)

    return () => { window.google?.accounts.id.disableAutoSelect() }
  }, []) // eslint-disable-line react-hooks/exhaustive-deps

  // ── Auth handlers ─────────────────────────────────────────────────────────

  async function handleGoogleCredential(response: { credential: string }) {
    setGLoading(true); setError(null)
    try {
      const result = await authApi.google(response.credential)
      login(result.user, result.tokens)
      navigate('/dashboard', { replace: true })
    } catch (err) {
      setError(extractError(err))
    } finally {
      setGLoading(false)
    }
  }

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault()
    if (!form.name || !form.email || !form.username || !form.password) return

    if (form.password !== form.confirm) { setError('Passwords do not match'); return }
    if (form.password.length < 8)       { setError('Password must be at least 8 characters'); return }
    if (!PW_CHECKS[1].test(form.password)) { setError('Password must contain at least one uppercase letter'); return }
    if (!PW_CHECKS[2].test(form.password)) { setError('Password must contain at least one number'); return }

    setLoading(true); setError(null)
    try {
      const result = await authApi.signup({
        name:     form.name.trim(),
        email:    form.email.trim().toLowerCase(),
        username: form.username.trim().toLowerCase(),
        password: form.password,
      })
      login(result.user, result.tokens)
      navigate('/dashboard', { replace: true })
    } catch (err: unknown) {
      setError(extractError(err))
    } finally {
      setLoading(false)
    }
  }

  const pwValid = form.password.length >= 8 && PW_CHECKS.every(c => c.test(form.password))
  const canSubmit = !loading && !gLoading
    && form.name.trim() && form.email && form.username
    && pwValid && form.password === form.confirm

  // ── Render ────────────────────────────────────────────────────────────────

  return (
    <div className="min-h-screen flex">
      {/* ── Left branding panel ────────────────────────────────────────────── */}
      <div
        className="hidden lg:flex lg:w-[45%] relative overflow-hidden flex-col justify-center items-center p-12"
        style={{ background: 'linear-gradient(135deg, #18143A 0%, #3B35A0 50%, #7670F1 100%)' }}
      >
        <div className="absolute -top-24 -right-24 w-72 h-72 rounded-full bg-white/5 blur-2xl" />
        <div className="absolute -bottom-32 -left-16 w-96 h-96 rounded-full bg-brand-500/20 blur-3xl" />

        <div className="relative text-center space-y-6">
          <div className="w-20 h-20 rounded-3xl bg-white/15 backdrop-blur mx-auto flex items-center justify-center shadow-2xl border border-white/20">
            <Sparkles size={36} className="text-white" />
          </div>
          <div>
            <h1 className="font-display font-bold text-3xl text-white mb-2">Join ClozéHive</h1>
            <p className="text-white/60 text-sm leading-relaxed max-w-xs mx-auto">
              Create your free account and start styling your wardrobe with the power of AI.
            </p>
          </div>

          <div className="flex gap-6 justify-center pt-4">
            {[
              { value: '10K+', label: 'Users' },
              { value: '500K+', label: 'Outfits' },
              { value: '4.9★', label: 'Rating' },
            ].map(s => (
              <div key={s.label} className="text-center">
                <div className="font-display font-bold text-2xl text-white">{s.value}</div>
                <div className="text-xs text-white/50">{s.label}</div>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* ── Right form panel ───────────────────────────────────────────────── */}
      <div className="flex-1 flex items-center justify-center p-6 sm:p-12 bg-white dark:bg-slate-900 overflow-y-auto">
        <div className="w-full max-w-md py-8 animate-slide-up">

          {/* Mobile logo */}
          <div className="lg:hidden flex items-center gap-2 mb-8">
            <div className="w-9 h-9 rounded-xl bg-gradient-brand flex items-center justify-center">
              <Sparkles size={18} className="text-white" />
            </div>
            <span className="font-display font-bold text-lg text-slate-800 dark:text-slate-100">ClozéHive</span>
          </div>

          <div className="mb-7">
            <h2 className="font-display font-bold text-2xl text-slate-900 dark:text-white mb-1">
              Create your account
            </h2>
            <p className="text-slate-500 dark:text-slate-400 text-sm">Free forever · No credit card required</p>
          </div>

          {/* Error */}
          {error && (
            <div className="flex items-center gap-2 p-3 mb-5 rounded-xl bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 text-red-600 dark:text-red-300 text-sm">
              <AlertCircle size={15} className="flex-shrink-0" />
              {error}
            </div>
          )}

          <form onSubmit={handleSubmit} className="space-y-4">
            {/* Full name */}
            <div className="space-y-1.5">
              <label className="label text-slate-700 dark:text-slate-300">Full name</label>
              <input
                type="text"
                className="input w-full"
                placeholder="Alex Carter"
                value={form.name}
                onChange={set('name')}
                autoComplete="name"
                autoFocus
                required
                disabled={loading || gLoading}
              />
            </div>

            {/* Email */}
            <div className="space-y-1.5">
              <label className="label text-slate-700 dark:text-slate-300">Email</label>
              <input
                type="email"
                className="input w-full"
                placeholder="you@example.com"
                value={form.email}
                onChange={set('email')}
                autoComplete="email"
                required
                disabled={loading || gLoading}
              />
            </div>

            {/* Username */}
            <div className="space-y-1.5">
              <label className="label text-slate-700 dark:text-slate-300">Username</label>
              <div className="relative">
                <span className="absolute left-3.5 top-1/2 -translate-y-1/2 text-slate-400 text-sm font-medium">@</span>
                <input
                  type="text"
                  className="input w-full pl-7"
                  placeholder="alexcarter"
                  value={form.username}
                  onChange={set('username')}
                  autoComplete="username"
                  pattern="[a-zA-Z0-9_]{3,30}"
                  title="3–30 characters: letters, numbers, and underscores only"
                  required
                  disabled={loading || gLoading}
                />
              </div>
              <p className="text-[11px] text-slate-400">3–30 chars · letters, numbers, underscores only</p>
            </div>

            {/* Password */}
            <div className="space-y-1.5">
              <label className="label text-slate-700 dark:text-slate-300">Password</label>
              <div className="relative">
                <input
                  type={showPw ? 'text' : 'password'}
                  className="input w-full pr-11"
                  placeholder="••••••••"
                  value={form.password}
                  onChange={set('password')}
                  autoComplete="new-password"
                  minLength={8}
                  required
                  disabled={loading || gLoading}
                />
                <button
                  type="button"
                  onClick={() => setShowPw(v => !v)}
                  tabIndex={-1}
                  className="absolute right-3 top-1/2 -translate-y-1/2 text-slate-400 hover:text-slate-600 dark:hover:text-slate-300 transition-colors"
                >
                  {showPw ? <EyeOff size={18} /> : <Eye size={18} />}
                </button>
              </div>
              <PasswordStrength password={form.password} />
            </div>

            {/* Confirm password */}
            <div className="space-y-1.5">
              <label className="label text-slate-700 dark:text-slate-300">Confirm password</label>
              <input
                type={showPw ? 'text' : 'password'}
                className={`input w-full ${form.confirm && form.confirm !== form.password ? 'border-red-400 focus:ring-red-400' : ''}`}
                placeholder="••••••••"
                value={form.confirm}
                onChange={set('confirm')}
                autoComplete="new-password"
                required
                disabled={loading || gLoading}
              />
              {form.confirm && form.confirm !== form.password && (
                <p className="text-xs text-red-500">Passwords don't match</p>
              )}
            </div>

            <button
              type="submit"
              disabled={!canSubmit}
              className="w-full h-11 rounded-xl bg-gradient-brand text-white font-semibold text-sm flex items-center justify-center gap-2 shadow-lg hover:opacity-90 active:scale-[0.98] transition-all disabled:opacity-50 disabled:cursor-not-allowed mt-2"
            >
              {loading
                ? <><Loader2 size={16} className="animate-spin" /> Creating account…</>
                : <><span>Create account</span> <ArrowRight size={16} /></>
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
            <div className="relative">
              <div ref={googleBtnRef} className="w-full flex justify-center" />
              {!gReady && (
                <div className="w-full h-11 rounded-xl border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 flex items-center justify-center gap-3 text-sm text-slate-500">
                  <Loader2 size={16} className="animate-spin" /> Loading Google…
                </div>
              )}
              {gLoading && (
                <div className="absolute inset-0 flex items-center justify-center rounded-xl bg-white/80 dark:bg-slate-900/80">
                  <Loader2 size={20} className="animate-spin text-brand-600" />
                </div>
              )}
            </div>
          ) : (
            <button
              type="button"
              disabled
              title="Configure VITE_GOOGLE_CLIENT_ID in your .env to enable Google sign-up"
              className="w-full h-11 rounded-xl border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-800/50 text-slate-400 dark:text-slate-500 text-sm font-medium flex items-center justify-center gap-3 cursor-not-allowed"
            >
              <GoogleSvg />
              Sign up with Google
              <span className="ml-auto text-[10px] bg-slate-200 dark:bg-slate-700 text-slate-500 dark:text-slate-400 px-1.5 py-0.5 rounded font-mono">
                ENV
              </span>
            </button>
          )}

          <p className="text-xs text-center text-slate-400 mt-4">
            By creating an account, you agree to our{' '}
            <span className="text-brand-600 dark:text-brand-400 cursor-pointer hover:underline">Terms of Service</span>
            {' '}and{' '}
            <span className="text-brand-600 dark:text-brand-400 cursor-pointer hover:underline">Privacy Policy</span>.
          </p>

          <p className="text-center text-sm text-slate-500 dark:text-slate-400 mt-5">
            Already have an account?{' '}
            <Link to="/login" className="font-semibold text-brand-600 dark:text-brand-400 hover:underline">
              Sign in
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
