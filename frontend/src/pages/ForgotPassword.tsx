/**
 * ForgotPassword — sends a password-reset link to the user's email.
 *
 * Security: The API returns the same success message regardless of whether
 * the email exists (no account enumeration).
 */

import { useState } from 'react'
import { Link } from 'react-router-dom'
import { Mail, ArrowLeft, Loader2, CheckCircle } from 'lucide-react'
import { authApi } from '@/lib/api'

export default function ForgotPassword() {
  const [email, setEmail]       = useState('')
  const [loading, setLoading]   = useState(false)
  const [sent, setSent]         = useState(false)
  const [error, setError]       = useState<string | null>(null)

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError(null)
    setLoading(true)
    try {
      await authApi.forgotPassword(email.trim().toLowerCase())
      setSent(true)
    } catch (err: unknown) {
      // Even on network errors show a generic message to avoid leaking info
      const msg =
        (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail
        ?? 'Something went wrong. Please try again.'
      setError(msg)
    } finally {
      setLoading(false)
    }
  }

  if (sent) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-cream-50 dark:bg-slate-950 px-4">
        <div className="w-full max-w-md text-center space-y-5">
          <div className="flex justify-center">
            <div className="w-14 h-14 rounded-2xl bg-emerald-100 dark:bg-emerald-900/30 flex items-center justify-center">
              <CheckCircle className="text-emerald-500" size={28} />
            </div>
          </div>
          <h1 className="font-display font-bold text-2xl text-slate-800 dark:text-white">
            Check your inbox
          </h1>
          <p className="text-slate-500 dark:text-slate-400">
            If <span className="font-medium text-slate-700 dark:text-slate-200">{email}</span> is
            registered, we've sent a password-reset link. It expires in 30 minutes.
          </p>
          <p className="text-sm text-slate-400">
            Didn't receive it? Check your spam folder or{' '}
            <button
              onClick={() => { setSent(false); setEmail('') }}
              className="text-brand-500 hover:text-brand-600 font-medium underline-offset-2 hover:underline"
            >
              try again
            </button>.
          </p>
          <Link
            to="/login"
            className="inline-flex items-center gap-1.5 text-sm text-brand-500 hover:text-brand-600 font-medium"
          >
            <ArrowLeft size={14} /> Back to login
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
              <Mail className="text-violet-500" size={28} />
            </div>
          </div>
          <h1 className="font-display font-bold text-2xl text-slate-800 dark:text-white">
            Forgot your password?
          </h1>
          <p className="text-sm text-slate-500 dark:text-slate-400">
            Enter your email and we'll send a secure reset link.
          </p>
        </div>

        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label htmlFor="fp-email" className="block text-sm font-medium text-slate-700 dark:text-slate-300 mb-1">
              Email address
            </label>
            <input
              id="fp-email"
              type="email"
              required
              autoComplete="email"
              value={email}
              onChange={e => setEmail(e.target.value)}
              placeholder="you@example.com"
              className="w-full rounded-xl border border-slate-200 dark:border-white/10 bg-white dark:bg-white/5
                         px-4 py-2.5 text-sm text-slate-800 dark:text-white placeholder:text-slate-400
                         focus:outline-none focus:ring-2 focus:ring-violet-500 transition"
            />
          </div>

          {error && (
            <p className="text-sm text-red-500 dark:text-red-400">{error}</p>
          )}

          <button
            type="submit"
            disabled={loading || !email}
            className="w-full rounded-xl bg-gradient-to-r from-brand-500 to-violet-500 text-white
                       py-2.5 text-sm font-semibold shadow-sm hover:opacity-90 disabled:opacity-50
                       transition flex items-center justify-center gap-2"
          >
            {loading ? <Loader2 size={16} className="animate-spin" /> : <Mail size={16} />}
            {loading ? 'Sending…' : 'Send reset link'}
          </button>
        </form>

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
