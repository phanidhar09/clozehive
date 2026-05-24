/**
 * StyleProfileResult — shown right after the v2 onboarding wizard completes.
 *
 * Reads `onboarding_result` from sessionStorage (written by the wizard on submit)
 * and displays the derived style profile with celebration animation.
 *
 * CTAs:
 *   • "Start Building My Closet" → /closet
 *   • "Add First Item"           → /upload
 */

import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { motion } from 'framer-motion'
import { ArrowRight, Shirt, Sparkles, Upload } from 'lucide-react'
import BackButton from '@/components/ui/BackButton'
import { profileApi } from '@/lib/api'
import type { UserStyleProfile } from '@/types'

// ── Archetype meta ────────────────────────────────────────────────────────────

const ARCHETYPE_META: Record<string, { emoji: string; color: string; tagline: string }> = {
  'Classic Minimalist':    { emoji: '🤍', color: 'from-slate-400 to-slate-600',    tagline: 'Clean, timeless, never overdressed.' },
  'Streetwear Edge':       { emoji: '🧢', color: 'from-zinc-600 to-zinc-900',      tagline: 'Urban energy, graphic intensity.' },
  'Bohemian Free Spirit':  { emoji: '🌸', color: 'from-amber-400 to-orange-500',   tagline: 'Earthy layers, flowing freedom.' },
  'Corporate Power':       { emoji: '💼', color: 'from-indigo-500 to-indigo-700',  tagline: 'Sharp silhouettes, boardroom authority.' },
  'Casual Comfort':        { emoji: '👕', color: 'from-sky-400 to-sky-600',        tagline: 'Effortless ease, everyday confidence.' },
  'Romantic Feminine':     { emoji: '🌹', color: 'from-rose-400 to-pink-600',      tagline: 'Soft details, elegant femininity.' },
  'Athleisure Athlete':    { emoji: '⚡', color: 'from-emerald-400 to-teal-600',   tagline: 'Performance meets street style.' },
  'Vintage Revivalist':    { emoji: '🎞️', color: 'from-amber-600 to-yellow-700',  tagline: 'Timeless classics, retro soul.' },
  'Eclectic Creative':     { emoji: '🎨', color: 'from-purple-400 to-violet-600',  tagline: 'Bold mixes, no rules, all you.' },
  'Outdoorsy Explorer':    { emoji: '🏕️', color: 'from-green-500 to-emerald-700', tagline: 'Durable, functional, adventure-proof.' },
}

const DEFAULT_META = { emoji: '✨', color: 'from-brand-400 to-violet-600', tagline: 'A style uniquely yours.' }

// ── Helpers ───────────────────────────────────────────────────────────────────

const OCCASION_LABELS: Record<string, string> = {
  work: 'Office', casual: 'Everyday', social: 'Nights Out', formal: 'Formal',
  gym: 'Sport', travel: 'Travel', date: 'Dates', homewear: 'Homewear',
}
const STYLE_LABELS: Record<string, string> = {
  minimal: 'Minimalist', streetwear: 'Streetwear', boho: 'Boho', corporate: 'Corporate',
  casual: 'Casual', romantic: 'Romantic', sporty: 'Athleisure', vintage: 'Vintage',
  eclectic: 'Eclectic', outdoor: 'Outdoorsy',
}
const GOAL_LABELS: Record<string, string> = {
  capsule: 'Build a capsule wardrobe', refresh: 'Refresh my style', polished: 'Look polished daily',
  express: 'Express my personality', conscious: 'Shop consciously', occasion: 'Dress for key occasions',
}

function label(map: Record<string, string>, key: string) {
  return map[key] ?? key.charAt(0).toUpperCase() + key.slice(1)
}

// ── Component ─────────────────────────────────────────────────────────────────

interface ResultData {
  style_archetype?: string
  style_preferences?: string[]
  occasion_preferences?: string[]
  styling_goals?: string[]
}

export default function StyleProfileResult() {
  const navigate = useNavigate()
  const [profile, setProfile] = useState<UserStyleProfile | null>(null)
  const [result, setResult] = useState<ResultData>({})
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    // Read wizard result from sessionStorage
    try {
      const raw = sessionStorage.getItem('onboarding_result')
      if (raw) setResult(JSON.parse(raw) as ResultData)
    } catch { /* ignore */ }

    // Fetch the final profile (may have AI-derived fields by now)
    ;(async () => {
      try {
        const p = await profileApi.getStyleProfile()
        if (p) setProfile(p)
      } catch { /* ignore */ }
      setLoading(false)
    })()
  }, [])

  const archetype =
    (profile as unknown as { style_archetype?: string })?.style_archetype ??
    result.style_archetype ??
    'Your Style'

  const meta = ARCHETYPE_META[archetype] ?? DEFAULT_META

  const summary =
    (profile as unknown as { style_summary?: string })?.style_summary ??
    null

  const stylePrefs  = profile?.style_preferences  ?? result.style_preferences  ?? []
  const occasions   = profile?.occasion_preferences ?? result.occasion_preferences ?? []
  const goals       = (result.styling_goals ?? []) as string[]

  return (
    <div className="min-h-screen flex flex-col items-center justify-start bg-cream-50 dark:bg-slate-950 px-4 py-12">

      {/* Back button */}
      <div className="w-full max-w-2xl mb-2">
        <BackButton fallback="/onboarding" label="Back to Onboarding" />
      </div>

      {/* Glow orb behind card */}
      <div className="pointer-events-none fixed inset-0 overflow-hidden -z-10">
        <div className={`absolute top-0 left-1/2 -translate-x-1/2 w-[640px] h-[400px] rounded-full bg-gradient-to-br ${meta.color} opacity-10 blur-[120px]`} />
      </div>

      {/* Sparkle entrance */}
      <motion.div
        initial={{ scale: 0.6, opacity: 0 }}
        animate={{ scale: 1,   opacity: 1 }}
        transition={{ type: 'spring', stiffness: 260, damping: 22, delay: 0.1 }}
        className="mb-8 flex flex-col items-center gap-2 text-center"
      >
        <div className={`flex h-20 w-20 items-center justify-center rounded-full bg-gradient-to-br ${meta.color} shadow-xl shadow-brand-500/20 text-4xl`}>
          {meta.emoji}
        </div>
        <div className="flex items-center gap-2 text-brand-500">
          <Sparkles size={14} />
          <span className="text-xs font-semibold uppercase tracking-widest">Your Style Archetype</span>
          <Sparkles size={14} />
        </div>
        <h1 className="text-3xl font-bold text-slate-900 dark:text-white">{archetype}</h1>
        <p className="text-slate-500 dark:text-slate-400 text-sm max-w-xs">{meta.tagline}</p>
      </motion.div>

      {/* Main card */}
      <motion.div
        initial={{ y: 24, opacity: 0 }}
        animate={{ y: 0,  opacity: 1 }}
        transition={{ delay: 0.25, duration: 0.4 }}
        className="w-full max-w-xl space-y-5"
      >
        {/* AI Summary */}
        {(summary || loading) && (
          <div className="rounded-2xl border border-cream-200 dark:border-white/[0.08] bg-white dark:bg-slate-900 p-5 shadow-sm">
            <p className="text-xs font-semibold uppercase tracking-widest text-slate-400 mb-2">AI Stylist's Take</p>
            {loading ? (
              <div className="space-y-2 animate-pulse">
                <div className="h-3 bg-cream-200 dark:bg-slate-700 rounded w-full" />
                <div className="h-3 bg-cream-200 dark:bg-slate-700 rounded w-5/6" />
                <div className="h-3 bg-cream-200 dark:bg-slate-700 rounded w-3/4" />
              </div>
            ) : (
              <p className="text-sm text-slate-700 dark:text-slate-300 leading-relaxed">{summary}</p>
            )}
          </div>
        )}

        {/* Style profile grid */}
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
          {/* Vibes */}
          {stylePrefs.length > 0 && (
            <div className="rounded-2xl border border-cream-200 dark:border-white/[0.08] bg-white dark:bg-slate-900 p-4 shadow-sm">
              <p className="text-[10px] font-semibold uppercase tracking-widest text-slate-400 mb-2">Your Vibes</p>
              <div className="flex flex-wrap gap-1.5">
                {stylePrefs.slice(0, 5).map(s => (
                  <span key={s} className="rounded-full bg-brand-50 dark:bg-brand-500/15 border border-brand-200 dark:border-brand-500/30 text-brand-700 dark:text-brand-300 px-2.5 py-0.5 text-xs font-medium">
                    {label(STYLE_LABELS, s)}
                  </span>
                ))}
              </div>
            </div>
          )}

          {/* Occasions */}
          {occasions.length > 0 && (
            <div className="rounded-2xl border border-cream-200 dark:border-white/[0.08] bg-white dark:bg-slate-900 p-4 shadow-sm">
              <p className="text-[10px] font-semibold uppercase tracking-widest text-slate-400 mb-2">Where You Wear</p>
              <div className="flex flex-wrap gap-1.5">
                {occasions.slice(0, 5).map(o => (
                  <span key={o} className="rounded-full bg-violet-50 dark:bg-violet-500/15 border border-violet-200 dark:border-violet-500/30 text-violet-700 dark:text-violet-300 px-2.5 py-0.5 text-xs font-medium">
                    {label(OCCASION_LABELS, o)}
                  </span>
                ))}
              </div>
            </div>
          )}

          {/* Goals */}
          {goals.length > 0 && (
            <div className="rounded-2xl border border-cream-200 dark:border-white/[0.08] bg-white dark:bg-slate-900 p-4 shadow-sm">
              <p className="text-[10px] font-semibold uppercase tracking-widest text-slate-400 mb-2">Your Goals</p>
              <div className="flex flex-wrap gap-1.5">
                {goals.slice(0, 3).map(g => (
                  <span key={g} className="rounded-full bg-emerald-50 dark:bg-emerald-500/15 border border-emerald-200 dark:border-emerald-500/30 text-emerald-700 dark:text-emerald-300 px-2.5 py-0.5 text-xs font-medium">
                    {label(GOAL_LABELS, g)}
                  </span>
                ))}
              </div>
            </div>
          )}
        </div>

        {/* CTAs */}
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 pt-2">
          <button
            type="button"
            onClick={() => navigate('/closet')}
            className="flex items-center justify-center gap-2 rounded-2xl bg-brand-500 hover:bg-brand-600 active:bg-brand-700 text-white px-6 py-4 text-sm font-semibold shadow-lg shadow-brand-500/25 transition"
          >
            <Shirt size={17} />
            Start Building My Closet
            <ArrowRight size={15} />
          </button>
          <button
            type="button"
            onClick={() => navigate('/upload')}
            className="flex items-center justify-center gap-2 rounded-2xl border border-brand-300 dark:border-brand-500/40 bg-white dark:bg-slate-900 text-brand-600 dark:text-brand-400 hover:bg-brand-50 dark:hover:bg-brand-500/10 px-6 py-4 text-sm font-semibold transition"
          >
            <Upload size={17} />
            Add First Item
          </button>
        </div>

        <p className="text-center text-xs text-slate-400 dark:text-slate-500 pt-1">
          Your profile is saved — FANI, your AI stylist, will use it for all recommendations.
        </p>
      </motion.div>
    </div>
  )
}
