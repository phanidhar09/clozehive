import { useState, FormEvent } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { Eye, EyeOff, Sparkles, ArrowRight, Loader2, AlertCircle, CheckCircle2 } from 'lucide-react'
import { useApp } from '@/store'
import { authApi } from '@/lib/api'

function PasswordStrength({ password }: { password: string }) {
  const checks = [
    { label: '8+ characters', pass: password.length >= 8 },
    { label: 'Uppercase letter', pass: /[A-Z]/.test(password) },
    { label: 'Number', pass: /\d/.test(password) },
  ]
  const score = checks.filter(c => c.pass).length

  const barColor =
    score === 0 ? 'bg-slate-200 dark:bg-slate-700'
    : score === 1 ? 'bg-red-400'
    : score === 2 ? 'bg-amber-400'
    : 'bg-emerald-500'

  if (!password) return null
  return (
    <div className="space-y-2 pt-1">
      <div className="flex gap-1">
        {[0, 1, 2].map(i => (
          <div key={i} className={`h-1 flex-1 rounded-full transition-all duration-300 ${i < score ? barColor : 'bg-slate-200 dark:bg-slate-700'}`} />
        ))}
      </div>
      <div className="flex gap-3 flex-wrap">
        {checks.map(c => (
          <span key={c.label} className={`text-[11px] flex items-center gap-1 ${c.pass ? 'text-emerald-600 dark:text-emerald-400' : 'text-slate-400'}`}>
            <CheckCircle2 size={11} className={c.pass ? 'text-emerald-500' : 'text-slate-300'} />
            {c.label}
          </span>
        ))}
      </div>
    </div>
  )
}

export default function Signup() {
  const navigate = useNavigate()
  const { login } = useApp()

  const [form, setForm] = useState({ name: '', email: '', username: '', password: '', confirm: '' })
  const [showPw, setShowPw] = useState(false)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const set = (k: keyof typeof form) => (e: React.ChangeEvent<HTMLInputElement>) =>
    setForm(f => ({ ...f, [k]: e.target.value }))

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault()
    if (!form.name || !form.email || !form.username || !form.password) return
    if (form.password !== form.confirm) {
      setError('Passwords do not match')
      return
    }
    if (form.password.length < 8) {
      setError('Password must be at least 8 characters')
      return
    }
    if (!/[A-Z]/.test(form.password)) {
      setError('Password must contain at least one uppercase letter')
      return
    }
    if (!/\d/.test(form.password)) {
      setError('Password must contain at least one digit')
      return
    }

    setLoading(true)
    setError(null)
    try {
      const { user, access_token, refresh_token } = await authApi.signup({
        name: form.name.trim(),
        email: form.email.trim().toLowerCase(),
        username: form.username.trim().toLowerCase(),
        password: form.password,
      })
      login(user, access_token, refresh_token)
      navigate('/dashboard', { replace: true })
    } catch (err: unknown) {
      type ApiErr = {
        response?: {
          data?: {
            message?: string
            error?: string
            detail?: string | Array<{ loc?: (string | number)[]; msg?: string }>
          }
        }
      }
      const d = (err as ApiErr)?.response?.data
      let msg: string | undefined
      if (typeof d?.detail === 'string') msg = d.detail
      else if (Array.isArray(d?.detail)) {
        msg = d.detail
          .map(e => {
            const field = Array.isArray(e.loc) ? e.loc.slice(1).join('.') : ''
            return field ? `${field}: ${e.msg ?? ''}` : (e.msg ?? '')
          })
          .filter(Boolean)
          .join(' · ')
      }
      msg = msg ?? d?.message ?? d?.error ?? (err instanceof Error ? err.message : 'Signup failed')
      setError(msg)
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="min-h-screen flex">
      {/* ── Left branding panel ──────────────────────────────── */}
      <div className="hidden lg:flex lg:w-[45%] relative overflow-hidden flex-col justify-center items-center p-12"
        style={{ background: 'linear-gradient(135deg, #18143A 0%, #3B35A0 50%, #7670F1 100%)' }}>

        <div className="absolute -top-24 -right-24 w-72 h-72 rounded-full bg-white/5 blur-2xl" />
        <div className="absolute -bottom-32 -left-16 w-96 h-96 rounded-full bg-brand-500/20 blur-3xl" />

        {/* Logo */}
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

          {/* Stats */}
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

      {/* ── Right form panel ─────────────────────────────────── */}
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
            {/* Name */}
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
                  required
                />
                <button
                  type="button"
                  onClick={() => setShowPw(v => !v)}
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
              />
              {form.confirm && form.confirm !== form.password && (
                <p className="text-xs text-red-500">Passwords don't match</p>
              )}
            </div>

            <button
              type="submit"
              disabled={loading || !form.name || !form.email || !form.username || !form.password || form.password !== form.confirm}
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

          {/* Google button */}
          <button
            type="button"
            className="w-full h-11 rounded-xl border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 text-slate-700 dark:text-slate-200 text-sm font-medium flex items-center justify-center gap-3 hover:bg-slate-50 dark:hover:bg-slate-700/60 transition-colors"
            onClick={() => alert('Google OAuth coming soon! Configure GOOGLE_CLIENT_ID in your .env to enable.')}
          >
            <svg width="18" height="18" viewBox="0 0 48 48" fill="none">
              <path d="M43.611 20.083H42V20H24v8h11.303c-1.649 4.657-6.08 8-11.303 8-6.627 0-12-5.373-12-12s5.373-12 12-12c3.059 0 5.842 1.154 7.961 3.039l5.657-5.657C34.046 6.053 29.268 4 24 4 12.955 4 4 12.955 4 24s8.955 20 20 20 20-8.955 20-20c0-1.341-.138-2.65-.389-3.917z" fill="#FFC107"/>
              <path d="M6.306 14.691l6.571 4.819C14.655 15.108 19.001 12 24 12c3.059 0 5.842 1.154 7.961 3.039l5.657-5.657C34.046 6.053 29.268 4 24 4 16.318 4 9.656 8.337 6.306 14.691z" fill="#FF3D00"/>
              <path d="M24 44c5.166 0 9.86-1.977 13.409-5.192l-6.19-5.238A11.91 11.91 0 0 1 24 36c-5.202 0-9.619-3.317-11.283-7.946l-6.522 5.025C9.505 39.556 16.227 44 24 44z" fill="#4CAF50"/>
              <path d="M43.611 20.083H42V20H24v8h11.303a12.04 12.04 0 0 1-4.087 5.571l.003-.002 6.19 5.238C36.971 39.205 44 34 44 24c0-1.341-.138-2.65-.389-3.917z" fill="#1976D2"/>
            </svg>
            Continue with Google
          </button>

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
