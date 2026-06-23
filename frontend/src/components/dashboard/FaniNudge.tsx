import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import {
  Sparkles, X, Clock, CloudSun, Plane, PartyPopper, Shirt, ArrowRight,
} from 'lucide-react'
import { nudgeApi, type DailyNudge } from '@/lib/api'

/** Per-type icon + call-to-action. Falls back to a generic "Ask FANI" prompt. */
function nudgeMeta(type: string): { icon: React.ReactNode; cta: string; to: string } {
  switch (type) {
    case 'forgotten_gem':
      return { icon: <Clock size={18} />, cta: 'Bring it back', to: '/ai-stylist' }
    case 'unworn_pick':
      return { icon: <Shirt size={18} />, cta: 'Style it', to: '/ai-stylist' }
    case 'new_arrival':
      return { icon: <Sparkles size={18} />, cta: 'Build an outfit', to: '/ai-stylist' }
    case 'weather_outfit':
      return { icon: <CloudSun size={18} />, cta: "Today's look", to: '/ai-stylist' }
    case 'calendar_prep':
      return { icon: <Plane size={18} />, cta: 'Open planner', to: '/planner' }
    case 'festival':
      return { icon: <PartyPopper size={18} />, cta: 'Dress for it', to: '/ai-stylist' }
    default:
      return { icon: <Sparkles size={18} />, cta: 'Ask FANI', to: '/ai-stylist' }
  }
}

/**
 * Today's proactive FANI nudge — the app's daily return trigger. Renders nothing
 * until a nudge loads, and nothing at all when the user has no actionable nudge
 * or has dismissed today's. Generation happens server-side on first fetch.
 */
export default function FaniNudge() {
  const [nudge, setNudge] = useState<DailyNudge | null>(null)
  const [hidden, setHidden] = useState(false)

  useEffect(() => {
    let alive = true
    nudgeApi
      .getToday()
      .then(n => { if (alive) setNudge(n && !n.dismissed ? n : null) })
      .catch(() => { /* nudges are best-effort; never block the dashboard */ })
    return () => { alive = false }
  }, [])

  if (!nudge || hidden) return null

  const { icon, cta, to } = nudgeMeta(nudge.nudge_type)

  const dismiss = () => {
    setHidden(true)
    nudgeApi.dismiss(nudge.id).catch(() => { /* optimistic — already hidden */ })
  }

  return (
    <div className="relative flex items-center gap-4 rounded-2xl border border-brand-200/70 dark:border-brand-400/20
                    bg-gradient-to-r from-brand-50 to-amber-50/40 dark:from-brand-500/[0.08] dark:to-amber-500/[0.04]
                    px-4 py-3.5 sm:px-5">
      <div className="shrink-0 w-10 h-10 rounded-xl bg-white/70 dark:bg-white/10 text-brand-600 dark:text-brand-400
                      flex items-center justify-center ring-1 ring-brand-200/60 dark:ring-white/10">
        {icon}
      </div>
      <div className="min-w-0 flex-1">
        <p className="text-[10px] font-semibold uppercase tracking-wider text-brand-600 dark:text-brand-400 mb-0.5 flex items-center gap-1">
          <Sparkles size={10} /> FANI
        </p>
        <p className="text-sm text-slate-700 dark:text-white/80 leading-snug">{nudge.message}</p>
      </div>
      <Link
        to={to}
        className="hidden sm:inline-flex shrink-0 items-center gap-1 text-sm font-semibold text-brand-600 dark:text-brand-400
                   hover:text-brand-700 dark:hover:text-brand-300 transition-colors"
      >
        {cta} <ArrowRight size={14} />
      </Link>
      <button
        onClick={dismiss}
        aria-label="Dismiss"
        className="shrink-0 w-7 h-7 rounded-lg flex items-center justify-center text-slate-400 hover:text-slate-600
                   dark:text-white/40 dark:hover:text-white/70 hover:bg-black/5 dark:hover:bg-white/10 transition-colors"
      >
        <X size={15} />
      </button>
    </div>
  )
}
