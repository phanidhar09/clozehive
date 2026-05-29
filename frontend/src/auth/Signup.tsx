import { useState, FormEvent } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { Eye, EyeOff, ArrowRight, Loader2, AlertCircle, CheckCircle2 } from 'lucide-react'
import { useApp } from '@/store'
import { authApi, profileApi } from '@/lib/api'
import AuthShell from './AuthShell'
import GoogleButton from './GoogleButton'
import { parseAuthError } from './authError'

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
  const [consentGiven, setConsentGiven] = useState(false)
  const [showPw, setShowPw] = useState(false)
  const [showConfirm, setShowConfirm] = useState(false)
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
      const { user, access_token } = await authApi.signup({
        name: form.name.trim(),
        email: form.email.trim().toLowerCase(),
        username: form.username.trim().toLowerCase(),
        password: form.password,
        gdpr_consent: true,
      })
      login(user, access_token)
      try {
        const st = await profileApi.getOnboardingStatus()
        if (!st.onboarding_completed) {
          navigate('/onboarding/style-profile', { replace: true })
          return
        }
      } catch {
        /* continue */
      }
      navigate('/dashboard', { replace: true, state: { fromLogin: true } })
    } catch (err: unknown) {
      setError(parseAuthError(err, 'Signup failed'))
    } finally {
      setLoading(false)
    }
  }

  const mismatch = form.confirm.length > 0 && form.confirm !== form.password

  return (
    <AuthShell
      activeStep={1}
      brandHeading={<>Start your style<br /><span className="text-emerald-300">journey</span> today.</>}
      brandSub="Create your free account and let ClozéHive curate perfect outfits using clothes you already own."
    >
      {/* Heading + step hint (accurate to the real flow: account → style profile) */}
      <div className="mb-6">
        <span className="inline-flex items-center gap-1.5 text-[11px] font-semibold text-brand-600 dark:text-brand-400 bg-brand-50 dark:bg-brand-900/30 px-2.5 py-1 rounded-full mb-3">
          Step 1 of 2 · Account
        </span>
        <h2 className="font-display font-bold text-2xl text-slate-900 dark:text-white mb-1">
          Create your account
        </h2>
        <p className="text-slate-500 dark:text-slate-400 text-sm">
          Next, you&apos;ll set up your style profile — takes about 2 minutes.
        </p>
      </div>

      {/* Error */}
      {error && (
        <div className="flex items-start gap-2 p-3 mb-5 rounded-xl bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 text-red-600 dark:text-red-300 text-sm">
          <AlertCircle size={15} className="flex-shrink-0 mt-0.5" />
          <span>{error}</span>
        </div>
      )}

      <form onSubmit={handleSubmit} className="space-y-4">
        {/* Name */}
        <div className="space-y-1.5">
          <label className="label text-slate-700 dark:text-slate-300">Full name</label>
          <input
            type="text" className="input w-full" placeholder="Alex Johnson"
            value={form.name} onChange={set('name')} autoComplete="name" autoFocus required
          />
        </div>

        {/* Email */}
        <div className="space-y-1.5">
          <label className="label text-slate-700 dark:text-slate-300">Email</label>
          <input
            type="email" className="input w-full" placeholder="you@example.com"
            value={form.email} onChange={set('email')} autoComplete="email" required
          />
        </div>

        {/* Username */}
        <div className="space-y-1.5">
          <label className="label text-slate-700 dark:text-slate-300">Username</label>
          <div className="relative">
            <span className="absolute left-3.5 top-1/2 -translate-y-1/2 text-slate-400 text-sm font-medium">@</span>
            <input
              type="text" className="input w-full pl-7" placeholder="alex_johnson"
              value={form.username} onChange={set('username')} autoComplete="username"
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
              type={showPw ? 'text' : 'password'} className="input w-full pr-11"
              placeholder="At least 8 characters"
              value={form.password} onChange={set('password')} autoComplete="new-password" required
            />
            <button
              type="button" onClick={() => setShowPw(v => !v)}
              className="absolute right-3 top-1/2 -translate-y-1/2 text-slate-400 hover:text-slate-600 dark:hover:text-slate-300 transition-colors"
              aria-label={showPw ? 'Hide password' : 'Show password'}
            >
              {showPw ? <EyeOff size={18} /> : <Eye size={18} />}
            </button>
          </div>
          <PasswordStrength password={form.password} />
        </div>

        {/* Confirm password */}
        <div className="space-y-1.5">
          <label className="label text-slate-700 dark:text-slate-300">Confirm password</label>
          <div className="relative">
            <input
              type={showConfirm ? 'text' : 'password'}
              className={`input w-full pr-11 ${mismatch ? 'border-red-400 focus:ring-red-400' : ''}`}
              placeholder="Repeat your password"
              value={form.confirm} onChange={set('confirm')} autoComplete="new-password" required
            />
            <button
              type="button" onClick={() => setShowConfirm(v => !v)}
              className="absolute right-3 top-1/2 -translate-y-1/2 text-slate-400 hover:text-slate-600 dark:hover:text-slate-300 transition-colors"
              aria-label={showConfirm ? 'Hide password' : 'Show password'}
            >
              {showConfirm ? <EyeOff size={18} /> : <Eye size={18} />}
            </button>
          </div>
          {mismatch && <p className="text-xs text-red-500">Passwords don&apos;t match</p>}
        </div>

        {/* GDPR consent */}
        <label className="flex items-start gap-3 cursor-pointer select-none">
          <input
            type="checkbox" checked={consentGiven} onChange={e => setConsentGiven(e.target.checked)}
            className="mt-0.5 h-4 w-4 rounded border-slate-300 dark:border-slate-600 text-brand-600 focus:ring-brand-500 accent-brand-600 flex-shrink-0"
            required
          />
          <span className="text-xs text-slate-500 dark:text-slate-400 leading-relaxed">
            I have read and agree to the{' '}
            <a href="/terms" target="_blank" rel="noopener noreferrer" className="text-brand-600 dark:text-brand-400 hover:underline font-medium">Terms of Service</a>
            {' '}and{' '}
            <a href="/privacy" target="_blank" rel="noopener noreferrer" className="text-brand-600 dark:text-brand-400 hover:underline font-medium">Privacy Policy</a>,
            including the processing of my personal data.
          </span>
        </label>

        <button
          type="submit"
          disabled={loading || !form.name || !form.email || !form.username || !form.password || mismatch || !consentGiven}
          className="w-full h-11 rounded-xl bg-gradient-brand text-white font-semibold text-sm flex items-center justify-center gap-2 shadow-lg hover:opacity-90 active:scale-[0.98] transition-all disabled:opacity-50 disabled:cursor-not-allowed mt-1"
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

      <GoogleButton label="Sign up with Google" />

      <p className="text-center text-sm text-slate-500 dark:text-slate-400 mt-5">
        Already have an account?{' '}
        <Link to="/login" className="font-semibold text-brand-600 dark:text-brand-400 hover:underline">
          Sign in
        </Link>
      </p>
    </AuthShell>
  )
}
