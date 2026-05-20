import { useCallback, useEffect, useState, type CSSProperties } from 'react'
import { Link, useNavigate, useLocation } from 'react-router-dom'
import {
  Shirt, ArrowRight,
  Percent, TrendingUp, Sun,
  Sparkles, RefreshCw, Loader2, Check, CloudSun,
  Bookmark, AlertCircle, Star, Zap,
} from 'lucide-react'
import { useApp } from '@/store'
import { outfitsApi, profileApi, type OutfitOfDayResponse } from '@/lib/api'
import GlassCard from '@/components/ui/GlassCard'
import EmptyState from '@/components/ui/EmptyState'
import { useCursorGlow } from '@/hooks/useCursorGlow'
import { DASHBOARD_QUICK_ACTIONS } from '@/features/dashboard/quickActions'
import OnboardingChecklist from '@/components/dashboard/OnboardingChecklist'
import type { ClosetItem, OutfitSuggestion } from '@/types'

// ── Outfit rating ─────────────────────────────────────────────────────────────

type RatingLabel = 'Needs Improvement' | 'Average' | 'Good' | 'Excellent' | 'Best Fit'
type OutfitRating = {
  label: RatingLabel
  gradient: string
  textColor: string
  stars: number        // filled stars out of 5
  stylistNote: string  // one-line AI stylist tip shown under the badge
}

function getOutfitRating(
  styleScore: number | undefined,
  itemCount: number,
  hasWeather: boolean,
  tipCount: number,
): OutfitRating {
  const score = styleScore ?? 0
  // Each signal adds one point; score carries up to 2 points
  const signals =
    (score >= 0.85 ? 2 : score >= 0.65 ? 1 : 0) +
    (itemCount >= 4 ? 1 : 0) +
    (hasWeather ? 1 : 0) +
    (tipCount >= 2 ? 1 : 0)

  if (signals >= 4)
    return {
      label: 'Best Fit',
      gradient: 'from-amber-400 to-orange-400',
      textColor: 'text-amber-700 dark:text-amber-300',
      stars: 5,
      stylistNote: 'A stylist-approved, complete look — wear it with confidence.',
    }
  if (signals === 3)
    return {
      label: 'Excellent',
      gradient: 'from-violet-500 to-fuchsia-500',
      textColor: 'text-violet-700 dark:text-violet-300',
      stars: 4,
      stylistNote: 'Well-coordinated outfit — a small accessory would perfect it.',
    }
  if (signals === 2)
    return {
      label: 'Good',
      gradient: 'from-emerald-500 to-teal-400',
      textColor: 'text-emerald-700 dark:text-emerald-300',
      stars: 3,
      stylistNote: 'Solid everyday look — try adding a layer or colour accent.',
    }
  if (signals === 1)
    return {
      label: 'Average',
      gradient: 'from-slate-400 to-slate-500',
      textColor: 'text-slate-600 dark:text-slate-300',
      stars: 2,
      stylistNote: 'Decent base — mix in a statement piece to elevate the outfit.',
    }
  return {
    label: 'Needs Improvement',
    gradient: 'from-rose-500 to-pink-500',
    textColor: 'text-rose-700 dark:text-rose-300',
    stars: 1,
    stylistNote: 'Consider pairing with complementary colours or adding more items.',
  }
}

// ── FANI daily tips ───────────────────────────────────────────────────────────

const FANI_TIPS = [
  { tip: 'Build every outfit around 3 neutrals — every piece stays effortlessly versatile.', tag: 'Colour Theory' },
  { tip: 'One statement item per look. Let it breathe and keep everything else minimal.', tag: 'Styling Rule' },
  { tip: 'Quality over quantity — 10 great pieces outperform 50 average ones every time.', tag: 'Wardrobe Edit' },
  { tip: 'Match your shoe tone to your belt for an instant, no-effort polish boost.', tag: 'Classic Rule' },
  { tip: 'Layer textures, not just colours. It adds depth and dimension without visual noise.', tag: 'Layering' },
  { tip: 'Your most-worn item reveals your true style signature — lean into it unapologetically.', tag: 'Self Awareness' },
  { tip: 'A well-tailored fit at any price point looks more elevated than a loose designer piece.', tag: 'Fit First' },
]

function FaniTipCard() {
  const dayIndex = new Date().getDay() // 0–6
  const { tip, tag } = FANI_TIPS[dayIndex]
  return (
    <div className="flex items-start gap-4 rounded-2xl
                    bg-gradient-to-r from-violet-50 to-fuchsia-50
                    dark:from-violet-950/30 dark:to-fuchsia-950/20
                    border border-violet-200/60 dark:border-violet-500/20
                    px-5 py-4">
      <div className="w-9 h-9 rounded-xl bg-gradient-to-br from-violet-500 to-fuchsia-500
                      flex items-center justify-center flex-shrink-0 shadow-sm">
        <Zap size={15} className="text-white" />
      </div>
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2 mb-1">
          <span className="text-[10px] font-bold uppercase tracking-widest text-violet-500 dark:text-violet-400">
            FANI Tip · {tag}
          </span>
        </div>
        <p className="text-sm text-slate-700 dark:text-white/80 leading-relaxed">{tip}</p>
      </div>
    </div>
  )
}

// ── Style at a glance ─────────────────────────────────────────────────────────

function StyleGlance({ closetItems }: { closetItems: ClosetItem[] }) {
  if (closetItems.length === 0) return null

  const mostWorn = [...closetItems].sort((a, b) => (b.wear_count ?? 0) - (a.wear_count ?? 0))[0]
  const unworn   = closetItems.filter(i => (i.wear_count ?? 0) === 0).length
  const categories = new Set(closetItems.map(i => i.category?.toLowerCase()))
  const essentials = ['tops', 'bottoms', 'shoes', 'outerwear']
  const missing = essentials.filter(e => !categories.has(e))

  const glances = [
    {
      label: 'Most Worn',
      value: mostWorn?.name ? mostWorn.name.split(' ').slice(0, 3).join(' ') : '—',
      sub: mostWorn?.wear_count ? `${mostWorn.wear_count} wear${mostWorn.wear_count === 1 ? '' : 's'}` : 'Track your wears',
      color: 'text-violet-600 dark:text-violet-400',
      dot: 'bg-violet-500',
    },
    {
      label: 'Never Worn',
      value: String(unworn),
      sub: unworn === 0 ? 'Great — fully active closet' : `item${unworn === 1 ? '' : 's'} waiting for a moment`,
      color: unworn > 0 ? 'text-amber-600 dark:text-amber-400' : 'text-emerald-600 dark:text-emerald-400',
      dot: unworn > 0 ? 'bg-amber-500' : 'bg-emerald-500',
    },
    {
      label: 'Closet Gaps',
      value: missing.length === 0 ? 'None' : missing.map(m => m.charAt(0).toUpperCase() + m.slice(1)).join(', '),
      sub: missing.length === 0 ? 'All essentials covered' : 'Missing wardrobe essentials',
      color: missing.length > 0 ? 'text-rose-600 dark:text-rose-400' : 'text-emerald-600 dark:text-emerald-400',
      dot: missing.length > 0 ? 'bg-rose-500' : 'bg-emerald-500',
    },
  ]

  return (
    <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
      {glances.map(({ label, value, sub, color, dot }) => (
        <div key={label}
             className="rounded-2xl border border-cream-200 dark:border-white/[0.07]
                        bg-white/80 dark:bg-white/[0.04] px-4 py-3.5 backdrop-blur-sm">
          <div className="flex items-center gap-1.5 mb-1.5">
            <span className={`w-1.5 h-1.5 rounded-full ${dot} flex-shrink-0`} />
            <span className="text-[10px] font-bold uppercase tracking-widest text-slate-400 dark:text-white/30">
              {label}
            </span>
          </div>
          <p className={`text-sm font-bold truncate ${color}`}>{value}</p>
          <p className="text-[11px] text-slate-400 dark:text-white/35 mt-0.5 leading-tight">{sub}</p>
        </div>
      ))}
    </div>
  )
}

// ── Outfit-of-the-Day card ────────────────────────────────────────────────────

function OutfitOfDayCard({ closetItems }: { closetItems: ClosetItem[] }) {
  const [data, setData] = useState<OutfitOfDayResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [saved, setSaved] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    setSaved(false)
    try {
      const result = await outfitsApi.getOutfitOfDay()
      setData(result)
    } catch {
      setError('Could not generate today\'s outfit. Please try again.')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { load() }, [load])

  // Cross-reference outfit items with closet to get image_url
  const resolvedItems = (data?.outfit?.items ?? []).map(oi => {
    const full = closetItems.find(ci => ci.id === oi.id)
    return full ?? oi as Partial<ClosetItem>
  })

  const saveOutfit = async (outfit: OutfitSuggestion) => {
    const itemIds = (outfit.item_ids ?? resolvedItems.map(i => i.id).filter(Boolean)) as string[]
    if (!itemIds.length) return
    setSaving(true)
    try {
      await outfitsApi.create({
        name: outfit.name || `Outfit of the Day — ${new Date().toLocaleDateString()}`,
        item_ids: itemIds,
        occasion: data?.occasion ?? 'casual',
        notes: outfit.style_notes ?? undefined,
      })
      setSaved(true)
    } catch {
      /* ignore */
    } finally {
      setSaving(false)
    }
  }

  const weatherChip = data?.weather && (
    <div className="flex items-center gap-1.5 rounded-full border border-sky-200/60 bg-sky-50/80 px-3 py-1 text-xs font-medium text-sky-700 dark:border-sky-500/30 dark:bg-sky-500/10 dark:text-sky-300">
      <CloudSun size={12} className="flex-shrink-0" />
      {data.weather.condition}
      {data.weather.temp_c != null ? ` · ${Math.round(data.weather.temp_c)}°C` : ''}
      {data.weather.location_label ? ` · ${data.weather.location_label}` : ''}
    </div>
  )

  return (
    <div className="relative overflow-hidden rounded-3xl border border-violet-200/60 bg-gradient-to-br from-violet-50 via-fuchsia-50 to-rose-50 shadow-card dark:border-violet-500/20 dark:from-violet-950/40 dark:via-fuchsia-950/30 dark:to-rose-950/30">
      {/* Decorative background blob */}
      <div className="pointer-events-none absolute -right-16 -top-16 h-56 w-56 rounded-full bg-violet-300/20 blur-3xl dark:bg-violet-500/10" />

      <div className="relative p-5 lg:p-6">
        {/* Header row */}
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="flex items-center gap-2">
            <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-gradient-to-br from-violet-500 to-fuchsia-500 shadow">
              <Sparkles size={16} className="text-white" />
            </div>
            <div>
              <h3 className="font-display text-base font-bold text-slate-800 dark:text-white">
                Outfit of the Day
              </h3>
              <p className="text-xs text-slate-500 dark:text-slate-400">
                FANI-picked from your closet
                {data?.occasion ? ` · ${data.occasion}` : ''}
              </p>
            </div>
          </div>

          <div className="flex items-center gap-2">
            {weatherChip}
            <button
              onClick={load}
              disabled={loading}
              className="flex h-8 w-8 items-center justify-center rounded-lg border border-slate-200 bg-white text-slate-500 hover:bg-slate-50 hover:text-violet-600 disabled:opacity-40 dark:border-white/10 dark:bg-white/5 dark:hover:bg-white/10"
              title="Regenerate"
            >
              <RefreshCw size={13} className={loading ? 'animate-spin' : ''} />
            </button>
          </div>
        </div>

        {/* Body */}
        <div className="mt-5">
          {loading && (
            <div className="flex flex-col items-center gap-3 py-10">
              <Loader2 size={28} className="animate-spin text-violet-500" />
              <p className="text-sm text-slate-500 dark:text-slate-400">Curating your look…</p>
            </div>
          )}

          {!loading && error && (
            <div className="flex items-center gap-2 rounded-2xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700 dark:border-red-500/30 dark:bg-red-500/10 dark:text-red-300">
              <AlertCircle size={14} className="flex-shrink-0" />
              {error}
            </div>
          )}

          {!loading && !error && data?.outfit && (
            <>
              {/* Outfit name + style notes */}
              <div className="mb-4">
                <div className="flex flex-wrap items-start justify-between gap-2">
                  <p className="font-display text-lg font-semibold text-slate-800 dark:text-white">
                    {data.outfit.name}
                  </p>
                  {/* Outfit rating badge */}
                  {(() => {
                    const rating = getOutfitRating(
                      data.outfit!.style_score,
                      resolvedItems.length,
                      Boolean(data.weather),
                      (data.style_tips ?? []).length,
                    )
                    return (
                      <div className="flex flex-col items-end gap-1">
                        <div className={`flex items-center gap-1 rounded-full bg-gradient-to-r ${rating.gradient} px-3 py-1 shadow-sm`}>
                          {Array.from({ length: 5 }).map((_, i) => (
                            <Star
                              key={i}
                              size={9}
                              className={i < rating.stars ? 'fill-white text-white' : 'fill-white/30 text-white/30'}
                            />
                          ))}
                          <span className="ml-1 text-[11px] font-bold text-white">{rating.label}</span>
                        </div>
                        <p className={`text-[10px] font-medium ${rating.textColor} max-w-[180px] text-right leading-tight`}>
                          {rating.stylistNote}
                        </p>
                      </div>
                    )
                  })()}
                </div>
                {data.outfit.style_notes && (
                  <p className="mt-1 text-sm text-slate-500 dark:text-slate-400">{data.outfit.style_notes}</p>
                )}
                {data.outfit.weather_suitability && (
                  <p className="mt-0.5 text-xs text-violet-600 dark:text-violet-400">
                    {data.outfit.weather_suitability}
                  </p>
                )}
              </div>

              {/* Item grid */}
              <div className="grid grid-cols-3 gap-3 sm:grid-cols-4 lg:grid-cols-5">
                {resolvedItems.slice(0, 5).map((item, i) => (
                  <div
                    key={item.id ?? i}
                    className="group flex flex-col overflow-hidden rounded-2xl border border-white/80 bg-white shadow-card dark:border-white/10 dark:bg-slate-900"
                  >
                    <div className="aspect-square overflow-hidden bg-slate-100 dark:bg-slate-800">
                      {item.image_url ? (
                        <img
                          src={item.image_url}
                          alt={item.name ?? ''}
                          className="h-full w-full object-cover transition-transform duration-300 group-hover:scale-105"
                        />
                      ) : (
                        <div className="flex h-full w-full items-center justify-center text-2xl">👕</div>
                      )}
                    </div>
                    <div className="px-2 py-1.5">
                      <p className="truncate text-xs font-semibold text-slate-700 dark:text-white">{item.name}</p>
                      <p className="truncate text-[10px] capitalize text-slate-400 dark:text-slate-500">{item.category}</p>
                    </div>
                  </div>
                ))}

                {resolvedItems.length === 0 && (
                  <p className="col-span-full text-sm text-slate-400">No items matched your closet.</p>
                )}
              </div>

              {/* Style tips */}
              {(data.style_tips ?? []).length > 0 && (
                <div className="mt-4 flex flex-wrap gap-2">
                  {data.style_tips.slice(0, 3).map((tip, i) => (
                    <span
                      key={i}
                      className="rounded-full border border-violet-200 bg-white/70 px-3 py-1 text-xs text-violet-700 dark:border-violet-500/30 dark:bg-violet-500/10 dark:text-violet-300"
                    >
                      ✦ {tip}
                    </span>
                  ))}
                </div>
              )}

              {/* Save button */}
              <div className="mt-4 flex items-center gap-3">
                <button
                  onClick={() => saveOutfit(data.outfit!)}
                  disabled={saving || saved || resolvedItems.length === 0}
                  className={`flex items-center gap-2 rounded-2xl px-4 py-2 text-sm font-semibold transition disabled:cursor-not-allowed disabled:opacity-50 ${
                    saved
                      ? 'border border-emerald-200 bg-emerald-50 text-emerald-700 dark:border-emerald-500/30 dark:bg-emerald-500/10 dark:text-emerald-300'
                      : 'bg-gradient-to-r from-violet-600 to-fuchsia-500 text-white shadow hover:opacity-90'
                  }`}
                >
                  {saving ? (
                    <><Loader2 size={13} className="animate-spin" /> Saving…</>
                  ) : saved ? (
                    <><Check size={13} /> Saved to outfits</>
                  ) : (
                    <><Bookmark size={13} /> Save this look</>
                  )}
                </button>
                <Link
                  to="/outfit-builder"
                  className="text-xs font-medium text-violet-600 hover:underline dark:text-violet-400"
                >
                  Customize in Builder →
                </Link>
              </div>
            </>
          )}

          {!loading && !error && !data?.outfit && closetItems.length === 0 && (
            <div className="py-6 text-center">
              <p className="text-sm text-slate-500 dark:text-slate-400">
                Add items to your closet to get a personalised outfit suggestion each day.
              </p>
              <Link to="/upload" className="mt-3 inline-block text-sm font-semibold text-violet-600 hover:underline dark:text-violet-400">
                Add your first item →
              </Link>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

// ── Dashboard ─────────────────────────────────────────────────────────────────

export default function Dashboard() {
  const navigate = useNavigate()
  const location = useLocation()
  const { closetItems, closetLoading, currentUser } = useApp()
  const { containerRef, glowRef } = useCursorGlow({ lerpFactor: 0.08, orbitRadius: 320 })
  const [hour] = useState(new Date().getHours())
  const [showStyleReminder, setShowStyleReminder] = useState(false)

  const locationState = location.state as Record<string, unknown> | null

  useEffect(() => {
    // Hard redirect happens only once at login time (Login.tsx / Signup.tsx / OAuthCallback.tsx).
    // On any subsequent visit — including page reloads — we never force the user back to
    // onboarding. We only show a soft reminder banner so they can reach the dashboard freely.
    let cancelled = false
    profileApi
      .getOnboardingStatus()
      .then(st => {
        if (cancelled) return
        // Show the reminder banner if the profile is incomplete or was skipped.
        // Redirect ONLY when navigating here fresh from login (state flag set by login handlers).
        const fromLogin = Boolean(locationState?.fromLogin)
        if (!st.onboarding_completed && fromLogin) {
          navigate('/onboarding/style-profile', { replace: true })
          return
        }
        if (!st.onboarding_completed || st.onboarding_skipped) {
          setShowStyleReminder(true)
        }
      })
      .catch(() => {})
    return () => { cancelled = true }
  }, [navigate, locationState?.fromLogin])

  const greeting = hour < 12 ? 'Good morning' : hour < 17 ? 'Good afternoon' : 'Good evening'

  const totalItems = closetItems.length
  const categories = new Set(closetItems.map(i => i.category)).size
  const wornItems = closetItems.filter(i => (i.wear_count ?? 0) > 0).length
  const closetUsedPct = totalItems > 0 ? Math.round((wornItems / totalItems) * 100) : 0

  const stats = [
    { label: 'Total Items', value: totalItems, icon: Shirt, color: 'from-rose-500 to-pink-500', suffix: '' },
    { label: 'Categories', value: categories, icon: TrendingUp, color: 'from-violet-500 to-purple-500', suffix: '' },
    { label: 'Closet Used', value: closetUsedPct, icon: Percent, color: 'from-sky-500 to-blue-500', suffix: '%' },
  ]

  return (
    <div className="space-y-6 max-w-6xl">

      {/* Onboarding checklist — shown to new users until all steps complete or dismissed */}
      <OnboardingChecklist />

      {showStyleReminder && (
        <div className="flex flex-wrap items-center justify-between gap-3 rounded-2xl border border-amber-200 bg-amber-50/90 px-4 py-3 text-sm text-amber-900 dark:border-amber-500/30 dark:bg-amber-500/10 dark:text-amber-100">
          <span>Complete your Style Profile for better outfit recommendations.</span>
          <Link
            to="/onboarding/style-profile"
            className="font-semibold text-amber-800 underline hover:no-underline dark:text-amber-200"
          >
            Continue setup
          </Link>
        </div>
      )}

      {/* ── Hero ──────────────────────────────────────────────────────────── */}
      <div
        ref={containerRef}
        className="relative overflow-hidden rounded-3xl p-6 lg:p-10
                   bg-gradient-to-br from-indigo-600 via-violet-600 to-fuchsia-500
                   text-white shadow-glow-md"
      >
        {/* Cursor-follow glow */}
        <div
          ref={glowRef}
          className="pointer-events-none absolute top-0 left-0 w-[640px] h-[640px] rounded-full
                     bg-[radial-gradient(circle,rgba(255,255,255,0.22),transparent_55%)]
                     opacity-0 transition-opacity duration-300 will-change-transform"
        />

        {/* Decorative blobs */}
        <div className="pointer-events-none absolute -top-20 -right-20 w-72 h-72 rounded-full bg-white/10 blur-3xl animate-float-1" />
        <div className="pointer-events-none absolute -bottom-24 left-12 w-80 h-80 rounded-full bg-violet-400/30 blur-3xl animate-float-2" />

        {/* Subtle dot grid */}
        <div
          className="pointer-events-none absolute inset-0 opacity-[0.06]"
          style={{
            backgroundImage: 'radial-gradient(rgba(255,255,255,0.6) 1px, transparent 1px)',
            backgroundSize: '24px 24px',
          }}
        />

        <div className="relative">
          <div className="flex items-center gap-2 mb-2">
            <Sun size={14} className="text-amber-200" />
            <span className="text-xs font-medium text-white/70 tracking-wide">
              {new Date().toLocaleDateString('en-US', { weekday: 'long', month: 'long', day: 'numeric' })}
            </span>
          </div>

          <h2 className="font-display text-3xl lg:text-4xl font-bold mb-2 leading-tight">
            {greeting},{' '}
            <span className="bg-gradient-to-r from-white via-amber-100 to-rose-100 bg-clip-text text-transparent">
              {currentUser?.display_name || currentUser?.username || 'there'}
            </span>{' '}
            <span className="inline-block animate-float-3">👋</span>
          </h2>

          <p className="text-white/70 text-sm lg:text-base mb-7 max-w-xl">
            {closetLoading
              ? 'Loading your wardrobe…'
              : totalItems > 0
                ? `You have ${totalItems} curated piece${totalItems === 1 ? '' : 's'}. FANI has picked today's look below.`
                : 'Start by scanning your closet to build your digital wardrobe.'}
          </p>

          <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
            {stats.map(({ label, value, icon: Icon, color, suffix }) => (
              <div key={label} className="bg-white/10 backdrop-blur-md rounded-xl p-3 border border-white/15">
                <div className="flex items-center gap-3">
                  <div className={`w-10 h-10 rounded-lg bg-gradient-to-br ${color} flex items-center justify-center flex-shrink-0`}>
                    <Icon size={16} className="text-white" />
                  </div>
                  <div>
                    <p className="text-[10px] font-bold text-white/60 uppercase tracking-wider">{label}</p>
                    <p className="text-xl font-bold text-white">{value}{suffix}</p>
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* ── FANI Tip of the Day ───────────────────────────────────────────── */}
      <FaniTipCard />

      {/* ── Outfit of the Day ─────────────────────────────────────────────── */}
      {!closetLoading && (
        <OutfitOfDayCard closetItems={closetItems} />
      )}

      {/* ── Style at a Glance ─────────────────────────────────────────────── */}
      {!closetLoading && totalItems > 0 && (
        <div>
          <h3 className="font-display font-semibold text-sm uppercase tracking-widest
                         text-slate-500 dark:text-white/40 mb-3">
            Style at a glance
          </h3>
          <StyleGlance closetItems={closetItems} />
        </div>
      )}

      {/* ── Quick actions ─────────────────────────────────────────────────── */}
      <div>
        <h3 className="font-display font-semibold text-sm uppercase tracking-widest
                       text-slate-500 dark:text-white/40 mb-3">
          Quick actions
        </h3>
        <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3 stagger">
          {DASHBOARD_QUICK_ACTIONS.map(({ label, desc, icon: Icon, to, gradient }, idx) => (
            <Link key={to} to={to} style={{ '--i': idx } as CSSProperties}>
              <GlassCard hover glow padding="md" className="group h-full">
                <div className={`w-11 h-11 rounded-xl bg-gradient-to-br ${gradient}
                                 flex items-center justify-center mb-3 shadow-glow-sm
                                 group-hover:scale-110 group-hover:shadow-glow-md
                                 transition-all duration-300`}>
                  <Icon size={18} className="text-white" />
                </div>
                <p className="font-semibold text-sm text-slate-800 dark:text-white">{label}</p>
                <p className="text-xs text-slate-500 dark:text-white/40 mt-0.5">{desc}</p>
              </GlassCard>
            </Link>
          ))}
        </div>
      </div>

      {/* ── Recent items ─────────────────────────────────────────────────── */}
      {totalItems > 0 && (
        <div>
          <div className="flex items-center justify-between mb-3">
            <h3 className="font-display font-semibold text-sm uppercase tracking-widest
                           text-slate-500 dark:text-white/40">
              Recently added
            </h3>
            <Link to="/closet" className="text-xs text-brand-600 dark:text-brand-400 hover:underline flex items-center gap-1">
              View all <ArrowRight size={12} />
            </Link>
          </div>
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
            {closetItems.slice(0, 4).map(item => (
              <GlassCard key={item.id} padding="none" className="overflow-hidden group">
                <div className="relative w-full aspect-square bg-slate-100 dark:bg-slate-800 overflow-hidden">
                  {item.image_url ? (
                    <img src={item.image_url} alt={item.name} className="w-full h-full object-cover group-hover:scale-105 transition-transform duration-300" />
                  ) : (
                    <div className="w-full h-full flex items-center justify-center text-3xl">👕</div>
                  )}
                </div>
                <div className="p-3">
                  <p className="font-semibold text-sm text-slate-800 dark:text-white line-clamp-1">{item.name}</p>
                  <p className="text-xs text-slate-500 dark:text-white/40 mt-0.5 capitalize">{item.category}</p>
                </div>
              </GlassCard>
            ))}
          </div>
        </div>
      )}

      {/* ── Empty state ───────────────────────────────────────────────────── */}
      {totalItems === 0 && !closetLoading && (
        <EmptyState
          icon={<Shirt />}
          title="Add your first item to see outfit suggestions"
          description="Upload a clothing photo and CLOZEHIVE will start building personalized outfit ideas from your wardrobe."
          primaryAction={{ label: 'Add First Item', href: '/upload' }}
          secondaryAction={{ label: 'View Closet', href: '/closet' }}
          variant="card"
        />
      )}
    </div>
  )
}
