import { useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import {
  Sparkles, TrendingUp, DollarSign, Clock, Shirt, ArrowRight,
} from 'lucide-react'
import { useApp } from '@/store'
import { analyticsApi, type WeeklyDigest as WeeklyDigestData, type DigestItem } from '@/lib/api'

/** A highlighted item with thumbnail, label, and the digest's detail line. */
function Highlight({
  icon, label, item, image, accent,
}: {
  icon: React.ReactNode
  label: string
  item: DigestItem
  image?: string
  accent: string
}) {
  return (
    <div className="flex items-center gap-3 rounded-xl bg-white/60 dark:bg-white/[0.04] px-3 py-2.5
                    ring-1 ring-black/[0.04] dark:ring-white/[0.06]">
      {image
        ? <img src={image} alt={item.name} className="w-10 h-10 rounded-lg object-cover shrink-0 ring-1 ring-black/5 dark:ring-white/10" />
        : (
          <div className="w-10 h-10 rounded-lg bg-slate-100 dark:bg-white/10 flex items-center justify-center shrink-0">
            <Shirt size={16} className="text-slate-300 dark:text-white/30" />
          </div>
        )}
      <div className="min-w-0 flex-1">
        <p className={`text-[10px] font-semibold uppercase tracking-wider mb-0.5 flex items-center gap-1 ${accent}`}>
          {icon} {label}
        </p>
        <p className="text-sm font-medium text-slate-800 dark:text-white truncate leading-tight">{item.name}</p>
        <p className="text-[11px] text-slate-400 dark:text-white/40">{item.detail}</p>
      </div>
    </div>
  )
}

/**
 * "Your Week in Style" — the trailing-7-day recap, the app's scheduled return
 * trigger. Self-hides for brand-new users who have no week to recap yet.
 */
export default function WeeklyDigest() {
  const { closetItems } = useApp()
  const [digest, setDigest] = useState<WeeklyDigestData | null>(null)

  const imageById = useMemo(() => {
    const m = new Map<string, string | undefined>()
    for (const it of closetItems) m.set(it.id, it.image_url ?? undefined)
    return m
  }, [closetItems])

  useEffect(() => {
    let alive = true
    analyticsApi
      .getWeeklyDigest()
      .then(d => { if (alive) setDigest(d) })
      .catch(() => { /* best-effort; never block the dashboard */ })
    return () => { alive = false }
  }, [])

  // Nothing to recap yet — don't show an empty card to new users.
  const hasSignal = digest && (digest.wears_logged > 0 || digest.new_items > 0 || digest.forgotten_gem)
  if (!digest || !hasSignal) return null

  return (
    <section className="rounded-2xl border border-cream-200 dark:border-white/[0.07]
                        bg-white dark:bg-white/[0.03] p-5 sm:p-6">
      <div className="flex items-center justify-between gap-3 mb-1">
        <h3 className="font-display text-lg font-bold text-slate-800 dark:text-white flex items-center gap-2">
          <Sparkles size={16} className="text-brand-500" /> Your Week in Style
        </h3>
        <Link
          to="/analytics"
          className="hidden sm:inline-flex items-center gap-1 text-xs font-semibold text-brand-600 dark:text-brand-400 hover:text-brand-700"
        >
          Full insights <ArrowRight size={13} />
        </Link>
      </div>
      <p className="text-sm text-slate-600 dark:text-white/70 leading-snug mb-4">{digest.headline}</p>

      {/* Stat row */}
      <div className="grid grid-cols-3 gap-3 mb-4">
        {[
          { value: digest.wears_logged, label: digest.wears_logged === 1 ? 'Wear logged' : 'Wears logged' },
          { value: digest.items_worn, label: digest.items_worn === 1 ? 'Piece worn' : 'Pieces worn' },
          { value: `${digest.utilization_rate}%`, label: 'Closet used' },
        ].map(({ value, label }) => (
          <div key={label} className="rounded-xl bg-cream-50 dark:bg-white/[0.04] px-3 py-2.5 text-center">
            <p className="text-xl font-bold text-slate-800 dark:text-white leading-none">{value}</p>
            <p className="text-[10px] font-medium text-slate-400 dark:text-white/40 mt-1">{label}</p>
          </div>
        ))}
      </div>

      {/* Highlights */}
      <div className="grid sm:grid-cols-3 gap-2.5">
        {digest.most_worn && (
          <Highlight
            icon={<TrendingUp size={10} />} label="Most worn" item={digest.most_worn}
            image={imageById.get(digest.most_worn.item_id)} accent="text-emerald-600 dark:text-emerald-400"
          />
        )}
        {digest.best_value && (
          <Highlight
            icon={<DollarSign size={10} />} label="Best value" item={digest.best_value}
            image={imageById.get(digest.best_value.item_id)} accent="text-sky-600 dark:text-sky-400"
          />
        )}
        {digest.forgotten_gem && (
          <Highlight
            icon={<Clock size={10} />} label="Revive this" item={digest.forgotten_gem}
            image={imageById.get(digest.forgotten_gem.item_id)} accent="text-amber-600 dark:text-amber-400"
          />
        )}
      </div>
    </section>
  )
}
