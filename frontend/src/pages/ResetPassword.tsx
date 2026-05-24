/**
 * ResetPassword — consumes a password-reset token from the URL and sets a
 * new password.
 *
 * URL format: /reset-password?token=<raw_token>
 */

import { useState, useEffect } from 'react'
import { useNavigate, useSearchParams, Link } from 'react-router-dom'
import { KeyRound, Loader2, CheckCircle, AlertCircle, ArrowLeft, Eye, EyeOff } from 'lucide-react'
import { authApi } from '@/lib/api'

function PasswordInput({
  id, label, value, onChange, placeholder,
}: {
  id: string; label: string; value: string
  onChange: (v: string) => void; placeholder?: string
}) {
  const [show, setShow] = useState(false)
  return (
    <div>
      <label htmlFor={id} className="block text-sm font-medium text-slate-700 dark:text-slate-300 mb-1">
        {label}
      </label>
      <div className="relative">
        <input
          id={id}
          type={show ? 'text' : 'password'}
          required
          autoComplete={id === 'rp-password' ? 'new-password' : 'new-password'}
          value={value}
          onChange={e => onChange(e.target.value)}
          placeholder={placeholder}
          className="w-full rounded-xl border border-slate-200 dark:border-white/10 bg-white dark:bg-white/5
                     px-4 py-2.5 pr-10 text-sm text-slate-800 dark:text-white placeholder:text-slate-400
                     focus:outline-none focus:ring-2 focus:ring-violet-500 transition"
        />
        <button
          type="button"
          onClick={() => setShow(s => !s)}
          className="absolute right-3 top-1/2 -translate-y-1/2 text-slate-400 hover:text-slate-600 transition"
          aria-label={show ? 'Hide password' : 'Show password'}
        >
          {show ? <EyeOff size={16} /> : <Eye size={16} />}
        </button>
      </div>
    </div>
  )
}

export default function ResetPassword() {
  const [searchParams]        = useSearchParams()
  const navigate              = useNavigate()
  const token                 = searchParams.get('token') ?? ''
  const [password, setPassword]     = useState('')
  const [confirm, setConfirm]       = useState('')
  const [loading, setLoading]       = useState(false)
  const [success, setSuccess]       = useState(false)
  const [error, setError]           = useState<string | null>(null)

  useEffect(() => {
    if (!token) {
      setError('Reset link is missing or invalid. Please request a new one.')
    }
  }, [token])

  const validate = (): string | null => {
    if (password.length < 8) return 'Password must be at least 8 characters.'
    if (!/[A-Za-z]/.test(password) || !/\d/.test(password)) {
      return 'Password must contain at least one letter and one number.'
    }
    if (password !== confirm) return 'Passwords do not match.'
    return null
  }

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    const validationError = validate()
    if (validationError) { setError(validationError); return }
    setError(null)
    setLoading(true)
    try {
      await authApi.resetPassword(token, password)
      setSuccess(true)
      setTimeout(() => navigate('/login', { replace: true }), 3000)
    } catch (err: unknown) {
      const msg =
        (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail
        ?? 'Failed to reset password. The link may have expired.'
      setError(msg)
    } finally {
      setLoading(false)
    }
  }

  if (success) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-cream-50 dark:bg-slate-950 px-4">
        <div className="w-full max-w-md text-center space-y-5">
          <div className="flex justify-center">
            <div className="w-14 h-14 rounded-2xl bg-emerald-100 dark:bg-emerald-900/30 flex items-center justify-center">
              <CheckCircle className="text-emerald-500" size={28} />
            </div>
          </div>
          <h1 className="font-display font-bold text-2xl text-slate-800 dark:text-white">
            Password updated!
          </h1>
          <p className="text-slate-500 dark:text-slate-400">
            Your password has been changed. Redirecting you to login…
          </p>
          <Link
            to="/login"
            className="inline-flex items-center gap-1.5 text-sm text-brand-500 hover:text-brand-600 font-medium"
          >
            Go to login now
          </Link>
        </div>
      </div>
    )
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-cream-50 dark:bg-slate-950 px-4">
      <div className="w-full max-w-md space-y-6">

        <div className="text-center space-y-2">
          <div className="flex justify-center">
            <div className="w-14 h-14 rounded-2xl bg-violet-100 dark:bg-violet-900/30 flex items-center justify-center">
              <KeyRound className="text-violet-500" size={28} />
            </div>
          </div>
          <h1 className="font-display font-bold text-2xl text-slate-800 dark:text-white">
            Set new password
          </h1>
          <p className="text-sm text-slate-500 dark:text-slate-400">
            Choose a strong password with at least 8 characters, one letter, and one number.
          </p>
        </div>

        {!token ? (
          <div className="rounded-xl bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-500/30 p-4 flex gap-3">
            <AlertCircle className="text-red-500 shrink-0 mt-0.5" size={16} />
            <div className="text-sm text-red-700 dark:text-red-300">
              <p className="font-semibold mb-1">Invalid reset link</p>
              <p>This reset link is missing or malformed.{' '}
                <Link to="/forgot-password" className="underline hover:no-underline">Request a new one.</Link>
              </p>
            </div>
          </div>
        ) : (
          <form onSubmit={handleSubmit} className="space-y-4">
            <PasswordInput
              id="rp-password"
              label="New password"
              value={password}
              onChange={setPassword}
              placeholder="At least 8 characters"
            />
            <PasswordInput
              id="rp-confirm"
              label="Confirm new password"
              value={confirm}
              onChange={setConfirm}
              placeholder="Repeat your password"
            />

            {error && (
              <div className="rounded-xl bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-500/30 p-3 flex gap-2">
                <AlertCircle className="text-red-500 shrink-0 mt-0.5" size={15} />
                <p className="text-sm text-red-700 dark:text-red-300">{error}</p>
              </div>
            )}

            <button
              type="submit"
              disabled={loading || !password || !confirm}
              className="w-full rounded-xl bg-gradient-to-r from-brand-500 to-violet-500 text-white
                         py-2.5 text-sm font-semibold shadow-sm hover:opacity-90 disabled:opacity-50
                         transition flex items-center justify-center gap-2"
            >
              {loading ? <Loader2 size={16} className="animate-spin" /> : <KeyRound size={16} />}
              {loading ? 'Updating…' : 'Set new password'}
            </button>
          </form>
        )}

        <Link
          to="/login"
          className="flex items-center justify-center gap-1.5 text-sm text-slate-500 hover:text-slate-700
                     dark:text-slate-400 dark:hover:text-slate-200 transition"
        >
          <ArrowLeft size={14} /> Back to login
        </Link>
      </div>
    </div>
  )
}
