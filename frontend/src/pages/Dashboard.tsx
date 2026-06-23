import { useCallback, useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import {
  Shirt, ArrowRight, Sparkles, RefreshCw, Loader2, Check,
  CloudSun, Bookmark, AlertCircle, Star, Zap, TrendingUp,
  ChevronRight, Calendar, ArrowUpRight, Image, Wand2, MessageSquare,
} from 'lucide-react'
import { useApp } from '@/store'
import { outfitsApi, type OutfitOfDayResponse } from '@/lib/api'
import SectionHeader from '@/components/ui/SectionHeader'
import OnboardingChecklist from '@/components/dashboard/OnboardingChecklist'
import FaniNudge from '@/components/dashboard/FaniNudge'
import WeeklyDigest from '@/components/dashboard/WeeklyDigest'
import WeeklyPlanner from '@/components/dashboard/WeeklyPlanner'
import { FaniLoader } from '@/components/system/FaniLoader'
import type { ClosetItem, OutfitSuggestion } from '@/types'

// ── Outfit rating ─────────────────────────────────────────────────────────────

type RatingLabel = 'Needs Work' | 'Average' | 'Good' | 'Excellent' | 'Best Fit'
type OutfitRating = {
  label: RatingLabel
  gradient: string
  stars: number
  note: string
}

function getOutfitRating(
  styleScore: number | undefined,
  itemCount: number,
  hasWeather: boolean,
  tipCount: number,
): OutfitRating {
  const score = styleScore ?? 0
  const signals =
    (score >= 0.85 ? 2 : score >= 0.65 ? 1 : 0) +
    (itemCount >= 4 ? 1 : 0) +
    (hasWeather ? 1 : 0) +
    (tipCount >= 2 ? 1 : 0)

  if (signals >= 4) return { label: 'Best Fit',  gradient: 'from-amber-400 to-orange-400',   stars: 5, note: 'Stylist-approved — wear it with confidence.' }
  if (signals === 3) return { label: 'Excellent', gradient: 'from-brand-500 to-brand-500', stars: 4, note: 'Well-coordinated — a small accessory perfects it.' }
  if (signals === 2) return { label: 'Good',      gradient: 'from-emerald-500 to-teal-400',   stars: 3, note: 'Solid look — try adding a colour accent.' }
  if (signals === 1) return { label: 'Average',   gradient: 'from-slate-400 to-slate-500',    stars: 2, note: 'Decent base — mix in a statement piece.' }
  return               { label: 'Needs Work', gradient: 'from-rose-500 to-pink-500',       stars: 1, note: 'Try pairing with complementary colours.' }
}

// ── Daily FANI tips ───────────────────────────────────────────────────────────

const FANI_TIPS = [
  { tip: 'Build every outfit around 3 neutrals — every piece stays effortlessly versatile.', tag: 'Colour Theory' },
  { tip: 'One statement piece per look. Let it breathe and keep everything else minimal.', tag: 'Styling Rule' },
  { tip: 'Quality over quantity — 10 great pieces outperform 50 average ones every time.', tag: 'Wardrobe Edit' },
  { tip: 'Match your shoe tone to your belt for instant, no-effort polish.', tag: 'Classic Rule' },
  { tip: 'Layer textures, not just colours — it adds depth without visual noise.', tag: 'Layering' },
  { tip: 'Your most-worn item reveals your true style signature — lean into it.', tag: 'Self Awareness' },
  { tip: 'A well-tailored fit at any price point looks more elevated than a loose designer piece.', tag: 'Fit First' },
]

// ── Wardrobe Pulse (side-panel stats) ────────────────────────────────────────

function WardrobePulse({ closetItems }: { closetItems: ClosetItem[] }) {
  if (closetItems.length === 0) return null

  const mostWorn  = [...closetItems].sort((a, b) => (b.wear_count ?? 0) - (a.wear_count ?? 0))[0]
  const unworn    = closetItems.filter(i => (i.wear_count ?? 0) === 0).length
  const cats      = new Set(closetItems.map(i => i.category?.toLowerCase()))
  const essential = ['tops', 'bottoms', 'shoes', 'outerwear']
  const gaps      = essential.filter(e => !cats.has(e))

  const rows = [
    {
      label: 'Most Worn',
      value: mostWorn?.name ? mostWorn.name.split(' ').slice(0, 3).join(' ') : '—',
      sub:   mostWorn?.wear_count ? `${mostWorn.wear_count} wear${mostWorn.wear_count === 1 ? '' : 's'}` : 'Start tracking',
      accent: 'bg-brand-500',
    },
    {
      label: 'Never Worn',
      value: String(unworn),
      sub:   unworn === 0 ? 'Fully active closet' : `piece${unworn === 1 ? '' : 's'} waiting for a moment`,
      accent: unworn > 0 ? 'bg-amber-500' : 'bg-emerald-500',
    },
    {
      label: 'Missing Essentials',
      value: gaps.length === 0 ? 'None' : gaps.map(g => g.charAt(0).toUpperCase() + g.slice(1)).join(', '),
      sub:   gaps.length === 0 ? 'All essentials covered' : 'Wardrobe gaps detected',
      accent: gaps.length > 0 ? 'bg-rose-500' : 'bg-emerald-500',
    },
  ]

  return (
    <div className="rounded-2xl border border-cream-200 dark:border-white/[0.07] bg-white dark:bg-white/[0.03] overflow-hidden">
      <div className="px-4 py-3 border-b border-cream-200 dark:border-white/[0.06]">
        <div className="flex items-center gap-2">
          <TrendingUp size={14} className="text-brand-500" />
          <span className="text-sm font-semibold text-slate-800 dark:text-white">Wardrobe Pulse</span>
        </div>
      </div>
      <div className="divide-y divide-cream-100 dark:divide-white/[0.05]">
        {rows.map(({ label, value, sub, accent }) => (
          <div key={label} className="flex items-start gap-3 px-4 py-3">
            <span className={`mt-1.5 w-2 h-2 rounded-full flex-shrink-0 ${accent}`} />
            <div className="min-w-0 flex-1">
              <p className="text-[10px] font-bold uppercase tracking-widest text-slate-400 dark:text-white/30 mb-0.5">{label}</p>
              <p className="text-sm font-semibold text-slate-800 dark:text-white truncate">{value}</p>
              <p className="text-[11px] text-slate-400 dark:text-white/35 leading-tight">{sub}</p>
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}

// ── FANI Style Tip ────────────────────────────────────────────────────────────

function StyleTipCard() {
  const { tip, tag } = FANI_TIPS[new Date().getDay()]
  return (
    <div className="rounded-2xl border border-brand-200/60 dark:border-brand-500/20
                    bg-gradient-to-br from-brand-50 to-brand-50
                    dark:from-brand-900/30 dark:to-brand-900/20 p-4">
      <div className="flex items-center gap-2 mb-2">
        <div className="w-7 h-7 rounded-lg bg-gradient-to-br from-brand-500 to-brand-500
                        flex items-center justify-center flex-shrink-0">
          <Zap size={13} className="text-white" />
        </div>
        <div>
          <p className="text-[10px] font-bold uppercase tracking-widest text-brand-500 dark:text-brand-400">
            FANI Tip
          </p>
          <p className="text-[10px] text-brand-400 dark:text-brand-500">{tag}</p>
        </div>
      </div>
      <p className="text-sm text-slate-700 dark:text-white/80 leading-relaxed">{tip}</p>
    </div>
  )
}

// ── Today's Look (Outfit of the Day) ─────────────────────────────────────────

function TodaysLookCard({ closetItems }: { closetItems: ClosetItem[] }) {
  const [data, setData]     = useState<OutfitOfDayResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [saving, setSaving]   = useState(false)
  const [saved, setSaved]     = useState(false)
  const [error, setError]     = useState<string | null>(null)

  // No point asking FANI for a look when there's nothing in the closet —
  // the API returns a generic outfit with zero matched items, which renders
  // as a nonsense "Excellent" card. Show the add-items state instead.
  const hasItems = closetItems.length > 0

  const load = useCallback(async () => {
    if (!hasItems) { setData(null); setLoading(false); return }
    setLoading(true); setError(null); setSaved(false)
    try   { setData(await outfitsApi.getOutfitOfDay()) }
    catch { setError("Couldn't generate today's look. Try again.") }
    finally { setLoading(false) }
  }, [hasItems])

  useEffect(() => { load() }, [load])

  const resolvedItems = (data?.outfit?.items ?? []).map(oi => {
    const full = closetItems.find(ci => ci.id === oi.id)
    return full ?? oi as Partial<ClosetItem>
  })

  const saveOutfit = async (outfit: OutfitSuggestion) => {
    const ids = (outfit.item_ids ?? resolvedItems.map(i => i.id).filter(Boolean)) as string[]
    if (!ids.length) return
    setSaving(true)
    try {
      await outfitsApi.create({
        name: outfit.name || `Today's Look — ${new Date().toLocaleDateString()}`,
        item_ids: ids,
        occasion: data?.occasion ?? 'casual',
        notes: outfit.style_notes ?? undefined,
      })
      setSaved(true)
    } catch { /* ignore */ }
    finally { setSaving(false) }
  }

  return (
    <div className="rounded-2xl border border-cream-200 dark:border-white/[0.07]
                    bg-white dark:bg-white/[0.03] overflow-hidden">
      {/* Card header */}
      <div className="flex items-center justify-between px-5 py-4
                      border-b border-cream-200 dark:border-white/[0.06]">
        <div className="flex items-center gap-2.5">
          <div className="w-8 h-8 rounded-xl bg-gradient-to-br from-brand-500 to-brand-500
                          flex items-center justify-center flex-shrink-0 shadow-sm">
            <Sparkles size={14} className="text-white" />
          </div>
          <div>
            <h3 className="text-sm font-semibold text-slate-800 dark:text-white leading-tight">
              Today's Look
            </h3>
            <p className="text-[11px] text-slate-400 dark:text-white/35">
              Curated by FANI from your wardrobe
              {data?.occasion ? ` · ${data.occasion}` : ''}
            </p>
          </div>
        </div>

        <div className="flex items-center gap-2">
          {data?.weather && (
            <div className="hidden sm:flex items-center gap-1.5 rounded-full border border-sky-200/60
                            bg-sky-50 px-2.5 py-1 text-[11px] font-medium text-sky-700
                            dark:border-sky-500/30 dark:bg-sky-500/10 dark:text-sky-300">
              <CloudSun size={11} className="flex-shrink-0" />
              {data.weather.condition}
              {data.weather.temp_c != null ? ` · ${Math.round(data.weather.temp_c)}°C` : ''}
            </div>
          )}
          <button
            onClick={load}
            disabled={loading}
            title="Regenerate outfit"
            className="w-8 h-8 flex items-center justify-center rounded-xl
                       border border-cream-200 dark:border-white/[0.09]
                       text-slate-400 hover:text-brand-600 dark:hover:text-brand-400
                       hover:bg-slate-50 dark:hover:bg-white/[0.06]
                       disabled:opacity-40 transition-colors"
          >
            <RefreshCw size={13} className={loading ? 'animate-spin' : ''} />
          </button>
        </div>
      </div>

      {/* Card body */}
      <div className="p-5">
        {loading && (
          <div className="py-12">
            <FaniLoader size="md" messages={['Curating your look…']} />
          </div>
        )}

        {!loading && error && (
          <div className="flex items-center gap-2 rounded-xl border border-red-200
                          bg-red-50 px-4 py-3 text-sm text-red-700
                          dark:border-red-500/30 dark:bg-red-500/10 dark:text-red-300">
            <AlertCircle size={14} className="flex-shrink-0" />
            {error}
          </div>
        )}

        {!loading && !error && hasItems && data?.outfit && (() => {
          const rating = getOutfitRating(
            data.outfit!.style_score,
            resolvedItems.length,
            Boolean(data.weather),
            (data.style_tips ?? []).length,
          )
          return (
            <>
              {/* Outfit name + rating */}
              <div className="flex items-start justify-between gap-3 mb-4">
                <div className="min-w-0">
                  <h4 className="font-display text-xl font-bold text-slate-800 dark:text-white leading-tight truncate">
                    {data.outfit.name}
                  </h4>
                  {data.outfit.style_notes && (
                    <p className="mt-1 text-sm text-slate-500 dark:text-slate-400 line-clamp-2">
                      {data.outfit.style_notes}
                    </p>
                  )}
                </div>
                <div className={`flex-shrink-0 flex items-center gap-1 rounded-full
                                 bg-gradient-to-r ${rating.gradient} px-3 py-1.5 shadow-sm`}>
                  {Array.from({ length: 5 }).map((_, i) => (
                    <Star key={i} size={9}
                      className={i < rating.stars ? 'fill-white text-white' : 'fill-white/30 text-white/30'} />
                  ))}
                  <span className="ml-1 text-[11px] font-bold text-white whitespace-nowrap">
                    {rating.label}
                  </span>
                </div>
              </div>

              {/* Item strip */}
              <div className="flex gap-3 overflow-x-auto pb-1 -mx-1 px-1">
                {resolvedItems.slice(0, 5).map((item, i) => (
                  <div key={item.id ?? i}
                       className="flex-shrink-0 w-[90px] rounded-xl overflow-hidden
                                  border border-cream-200 dark:border-white/[0.08]
                                  bg-slate-50 dark:bg-slate-900 group">
                    <div className="w-full aspect-square overflow-hidden bg-slate-100 dark:bg-slate-800">
                      {item.image_url ? (
                        <img src={item.image_url} alt={item.name ?? ''}
                             className="w-full h-full object-cover transition-transform duration-300 group-hover:scale-105" />
                      ) : (
                        <div className="flex h-full w-full items-center justify-center text-2xl">👕</div>
                      )}
                    </div>
                    <div className="px-2 py-1.5">
                      <p className="truncate text-[11px] font-semibold text-slate-700 dark:text-white">
                        {item.name}
                      </p>
                      <p className="truncate text-[10px] capitalize text-slate-400 dark:text-slate-500">
                        {item.category}
                      </p>
                    </div>
                  </div>
                ))}
                {resolvedItems.length === 0 && (
                  <p className="text-sm text-slate-400 py-4">No wardrobe items matched.</p>
                )}
              </div>

              {/* Style tips */}
              {(data.style_tips ?? []).length > 0 && (
                <div className="flex flex-wrap gap-1.5 mt-4">
                  {data.style_tips.slice(0, 3).map((tip, i) => (
                    <span key={i}
                          className="rounded-full border border-brand-200 bg-brand-50/80
                                     px-3 py-1 text-xs text-brand-700
                                     dark:border-brand-500/30 dark:bg-brand-500/10 dark:text-brand-300">
                      ✦ {tip}
                    </span>
                  ))}
                </div>
              )}

              {/* Actions */}
              <div className="flex items-center gap-3 mt-5 pt-4
                              border-t border-cream-100 dark:border-white/[0.06]">
                <button
                  onClick={() => saveOutfit(data.outfit!)}
                  disabled={saving || saved || resolvedItems.length === 0}
                  className={`flex items-center gap-2 rounded-xl px-4 py-2 text-sm font-semibold
                              transition disabled:opacity-50 disabled:cursor-not-allowed ${
                    saved
                      ? 'border border-emerald-200 bg-emerald-50 text-emerald-700 dark:border-emerald-500/30 dark:bg-emerald-500/10 dark:text-emerald-300'
                      : 'bg-gradient-to-r from-brand-600 to-brand-500 text-white shadow-sm hover:opacity-90 active:scale-[0.98]'
                  }`}
                >
                  {saving ? <><Loader2 size={13} className="animate-spin" /> Saving…</>
                    : saved ? <><Check size={13} /> Saved</>
                    : <><Bookmark size={13} /> Save Look</>}
                </button>
                <Link to="/outfit-builder"
                      className="flex items-center gap-1 text-sm font-medium text-brand-600
                                 hover:text-brand-700 dark:text-brand-400 dark:hover:text-brand-300
                                 transition-colors">
                  Customise <ChevronRight size={14} />
                </Link>
              </div>
            </>
          )
        })()}

        {!loading && !error && !hasItems && (
          <div className="py-10 text-center space-y-3">
            <div className="w-12 h-12 rounded-2xl bg-brand-50 dark:bg-brand-500/10
                            flex items-center justify-center mx-auto">
              <Shirt size={20} className="text-brand-400" />
            </div>
            <p className="text-sm text-slate-500 dark:text-slate-400 max-w-xs mx-auto">
              Add items to your wardrobe and FANI will pick a personalised look each morning.
            </p>
            <Link to="/upload"
                  className="inline-flex items-center gap-1 text-sm font-semibold
                             text-brand-600 hover:text-brand-700 dark:text-brand-400
                             transition-colors">
              Add your first piece <ChevronRight size={14} />
            </Link>
          </div>
        )}
      </div>
    </div>
  )
}

// ── Guided empty state ────────────────────────────────────────────────────────

const HOW_IT_WORKS = [
  {
    step: '01',
    icon: Image,
    title: 'Upload your clothes',
    desc: 'Drop a photo — FANI\'s AI scans it and auto-tags category, colour, pattern, and season. Bulk-upload up to 20 photos at once.',
    color: 'from-brand-500 to-brand-600',
    href: '/upload',
  },
  {
    step: '02',
    icon: Wand2,
    title: 'Build outfits',
    desc: 'Mix and match your wardrobe in the outfit builder. Save looks for any occasion — work, casual, travel, or a night out.',
    color: 'from-brand-500 to-brand-600',
    href: '/outfit-builder',
  },
  {
    step: '03',
    icon: Sparkles,
    title: 'Get daily suggestions',
    desc: 'Every morning FANI picks Today\'s Look from your closet — weather-aware, occasion-matched, and rated for style.',
    color: 'from-brand-500 to-brand-600',
    href: '/dashboard',
  },
  {
    step: '04',
    icon: MessageSquare,
    title: 'Chat with your AI stylist',
    desc: 'Ask FANI anything — "What goes with my navy blazer?" — and get advice grounded in items you actually own.',
    color: 'from-brand-500 to-brand-600',
    href: '/ai-stylist',
  },
]

function GuidedEmptyState() {
  return (
    <div className="space-y-6">
      {/* Hero banner */}
      <div className="relative overflow-hidden rounded-3xl border border-brand-200/60 dark:border-brand-500/20 bg-gradient-to-br from-brand-50 to-white dark:from-brand-900/30 dark:to-slate-900/40 px-6 py-8 text-center">
        <div className="pointer-events-none absolute -top-16 -right-16 w-48 h-48 rounded-full bg-brand-200/30 dark:bg-brand-500/10 blur-3xl" />
        <div className="pointer-events-none absolute -bottom-12 -left-10 w-40 h-40 rounded-full bg-amber-200/30 dark:bg-amber-500/10 blur-3xl" />
        <div className="relative">
          <div className="w-14 h-14 rounded-2xl bg-gradient-to-br from-brand-500 to-brand-600 flex items-center justify-center mx-auto mb-4 shadow-lg shadow-brand-500/25">
            <Sparkles size={24} className="text-white" />
          </div>
          <h2 className="font-display text-2xl font-bold text-slate-800 dark:text-white mb-2">
            Welcome to ClozéHive
          </h2>
          <p className="text-slate-500 dark:text-slate-400 text-sm max-w-sm mx-auto leading-relaxed">
            Your AI-powered wardrobe is ready to set up. Add your first clothing items and FANI will start building personalised outfits for you.
          </p>
          <div className="flex items-center justify-center gap-3 mt-5">
            <Link
              to="/onboarding/style-profile"
              className="inline-flex items-center gap-2 rounded-xl bg-gradient-to-r from-brand-500 to-brand-600 px-5 py-2.5 text-sm font-semibold text-white shadow-md shadow-brand-500/25 hover:opacity-90 transition-opacity"
            >
              <Sparkles size={14} /> Start guided setup
            </Link>
          </div>
          <p className="mt-2 text-xs text-slate-400 dark:text-slate-500">
            One path: profile → upload → outfit → AI chat
          </p>
        </div>
      </div>

      {/* How it works */}
      <div>
        <p className="text-xs font-bold uppercase tracking-widest text-slate-400 dark:text-white/30 mb-3">
          How it works
        </p>
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3">
          {HOW_IT_WORKS.map(({ step, icon: Icon, title, desc, color, href }) => (
            <Link
              key={step}
              to={href}
              className="group relative rounded-2xl border border-cream-200 dark:border-white/[0.07] bg-white dark:bg-white/[0.03] p-4 hover:border-slate-200 dark:hover:border-white/[0.14] hover:-translate-y-0.5 hover:shadow-md transition-all duration-200"
            >
              <div className={`w-9 h-9 rounded-xl bg-gradient-to-br ${color} flex items-center justify-center mb-3 shadow-sm group-hover:scale-110 transition-transform duration-200`}>
                <Icon size={16} className="text-white" />
              </div>
              <span className="text-[10px] font-bold text-slate-300 dark:text-white/20 tracking-widest">
                STEP {step}
              </span>
              <p className="font-semibold text-sm text-slate-800 dark:text-white mt-0.5 leading-tight">
                {title}
              </p>
              <p className="text-[11px] text-slate-400 dark:text-white/40 mt-1.5 leading-snug">
                {desc}
              </p>
              <ArrowUpRight
                size={12}
                className="absolute top-3 right-3 text-slate-300 dark:text-white/20 opacity-0 group-hover:opacity-100 transition-opacity"
              />
            </Link>
          ))}
        </div>
      </div>
    </div>
  )
}

// ── Dashboard ─────────────────────────────────────────────────────────────────

export default function Dashboard() {
  const { closetItems, closetLoading, currentUser } = useApp()
  const [hour]      = useState(new Date().getHours())

  const greeting  = hour < 12 ? 'Good morning' : hour < 17 ? 'Good afternoon' : 'Good evening'
  const totalItems = closetItems.length
  const categories = new Set(closetItems.map(i => i.category)).size
  const wornItems  = closetItems.filter(i => (i.wear_count ?? 0) > 0).length
  const activePct  = totalItems > 0 ? Math.round((wornItems / totalItems) * 100) : 0
  const dateLabel  = new Date().toLocaleDateString('en-US', { weekday: 'long', month: 'long', day: 'numeric' })

  return (
    <div className="space-y-7 max-w-6xl">

      <OnboardingChecklist />

      <FaniNudge />

      {/* ── Hero ──────────────────────────────────────────────────────────── */}
      <div className="relative overflow-hidden rounded-3xl
                      bg-gradient-to-br from-brand-700 via-brand-600 to-brand-500
                      text-white shadow-xl">
        {/* Subtle dot grid */}
        <div className="pointer-events-none absolute inset-0 opacity-[0.07]"
             style={{ backgroundImage: 'radial-gradient(rgba(255,255,255,0.7) 1px, transparent 1px)', backgroundSize: '22px 22px' }} />
        {/* Decorative orbs */}
        <div className="pointer-events-none absolute -top-24 -right-24 w-80 h-80 rounded-full bg-white/10 blur-3xl" />
        <div className="pointer-events-none absolute -bottom-28 -left-10 w-72 h-72 rounded-full bg-brand-400/20 blur-3xl" />

        <div className="relative px-6 py-8 lg:px-10 lg:py-10">
          {/* Date */}
          <div className="flex items-center gap-1.5 mb-3">
            <Calendar size={12} className="text-white/50" />
            <span className="text-xs font-medium text-white/60 tracking-wide">{dateLabel}</span>
          </div>

          {/* Greeting */}
          <h2 className="font-display text-3xl lg:text-4xl font-bold leading-tight mb-1">
            {greeting},{' '}
            <span className="bg-gradient-to-r from-white via-amber-100 to-rose-100 bg-clip-text text-transparent">
              {currentUser?.display_name || currentUser?.username || 'there'}
            </span>
          </h2>
          <p className="text-white/60 text-sm lg:text-base mb-8">
            {closetLoading
              ? 'Loading your wardrobe…'
              : totalItems > 0
                ? `Your wardrobe has ${totalItems} piece${totalItems === 1 ? '' : 's'} — FANI has your look for today.`
                : 'Start building your digital wardrobe below.'}
          </p>

          {/* Stats row */}
          <div className="flex flex-wrap gap-3">
            {[
              { value: totalItems,  label: totalItems === 1 ? 'Piece' : 'Pieces' },
              { value: categories,  label: categories === 1 ? 'Category' : 'Categories' },
              { value: `${activePct}%`, label: 'Active' },
            ].map(({ value, label }) => (
              <div key={label}
                   className="flex items-baseline gap-2 rounded-2xl bg-white/[0.12]
                              backdrop-blur-sm border border-white/[0.16]
                              px-5 py-3 min-w-[90px]">
                <span className="text-2xl font-bold text-white">{value}</span>
                <span className="text-xs font-medium text-white/60">{label}</span>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* ── Weekly recap (self-hides when there's nothing to recap) ───────── */}
      {!closetLoading && totalItems > 0 && <WeeklyDigest />}

      {/* ── Main two-column area ──────────────────────────────────────────── */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-5">

        {/* Left — Today's Look (2 cols) */}
        <div className="lg:col-span-2">
          {!closetLoading && <TodaysLookCard closetItems={closetItems} />}
          {closetLoading && (
            <div className="rounded-2xl border border-cream-200 dark:border-white/[0.07]
                            bg-white dark:bg-white/[0.03] flex items-center justify-center py-20">
              <FaniLoader size="md" />
            </div>
          )}
        </div>

        {/* Right — Wardrobe Pulse + Style Tip */}
        <div className="flex flex-col gap-4">
          {!closetLoading && totalItems > 0 && <WardrobePulse closetItems={closetItems} />}
          <StyleTipCard />
        </div>
      </div>

      {/* ── Weekly outfit calendar ────────────────────────────────────────── */}
      {!closetLoading && <WeeklyPlanner />}

      {/* ── Recent Pieces ─────────────────────────────────────────────────── */}
      {totalItems > 0 && (
        <div>
          <SectionHeader
            icon={<Shirt size={16} />}
            title="Recent Pieces"
            actions={
              <Link to="/closet"
                    className="flex items-center gap-1 text-sm font-medium text-brand-600
                               hover:text-brand-700 dark:text-brand-400 dark:hover:text-brand-300
                               transition-colors">
                View all <ArrowRight size={14} />
              </Link>
            }
          />
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
            {closetItems.slice(0, 4).map(item => (
              <Link key={item.id} to="/closet"
                    className="group rounded-2xl border border-cream-200 dark:border-white/[0.07]
                               bg-white dark:bg-white/[0.03] overflow-hidden
                               hover:border-slate-300 dark:hover:border-white/[0.14]
                               hover:shadow-md transition-all duration-200">
                <div className="relative w-full aspect-square bg-slate-100 dark:bg-slate-800 overflow-hidden">
                  {item.image_url ? (
                    <img src={item.image_url} alt={item.name}
                         className="w-full h-full object-cover group-hover:scale-105 transition-transform duration-300" />
                  ) : (
                    <div className="w-full h-full flex items-center justify-center text-3xl">👕</div>
                  )}
                </div>
                <div className="p-3">
                  <p className="font-semibold text-sm text-slate-800 dark:text-white line-clamp-1">
                    {item.name}
                  </p>
                  <p className="text-xs text-slate-400 dark:text-white/40 mt-0.5 capitalize">
                    {item.category}
                  </p>
                </div>
              </Link>
            ))}
          </div>
        </div>
      )}

      {/* ── Guided empty state ────────────────────────────────────────────── */}
      {totalItems === 0 && !closetLoading && (
        <GuidedEmptyState />
      )}
    </div>
  )
}
