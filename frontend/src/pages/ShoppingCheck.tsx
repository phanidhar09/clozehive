import { useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  Camera, Upload, ShoppingCart, CheckCircle, XCircle, AlertCircle,
  Loader2, RotateCcw, Star, TrendingUp, Package, Sparkles, Trash2,
  PlusCircle, Shirt, Link2, ExternalLink, Copy, BarChart3,
} from 'lucide-react'
import BackButton from '@/components/ui/BackButton'
import GlassCard from '@/components/ui/GlassCard'
import PageHeader from '@/components/ui/PageHeader'
import Container from '@/components/ui/Container'
import LazyImage from '@/components/ui/LazyImage'
import { FaniLoader } from '@/components/system/FaniLoader'
import Badge from '@/components/ui/Badge'
import { useCachedQuery, invalidateQuery } from '@/hooks/useCachedQuery'
import { shoppingCheckApi, type ShoppingCheckResult, type ShoppingHistoryEntry,
  type BuiltOutfit, type GapSuggestion } from '@/lib/api'
import { resolveUploadUrl } from '@/lib/api'
import { cn } from '@/lib/utils'

const HISTORY_KEY = 'shopping:history'

// ── Rating colours ────────────────────────────────────────────────────────────

// The verdict is a 0–10 rating + a colour band — never a buy/skip word.
type RatingColor = 'green' | 'amber' | 'red'

const RATING_HEX: Record<RatingColor, string> = {
  green: '#10b981',
  amber: '#f59e0b',
  red: '#ef4444',
}

// Map a backend colour (preferred) or fall back to the 0–10 rating.
function ratingColorOf(color: RatingColor | undefined, rating: number): RatingColor {
  if (color) return color
  return rating >= 7 ? 'green' : rating >= 4.5 ? 'amber' : 'red'
}

// ── Score ring ────────────────────────────────────────────────────────────────

function ScoreRing({ rating, color }: { rating: number; color: RatingColor }) {
  const r = 42
  const circ = 2 * Math.PI * r
  const fill = (rating / 10) * circ
  const hex = RATING_HEX[color]

  return (
    <svg width={110} height={110} className="rotate-[-90deg]">
      <circle cx={55} cy={55} r={r} fill="none" stroke="currentColor"
        strokeWidth={9} className="text-slate-200 dark:text-white/10" />
      <circle cx={55} cy={55} r={r} fill="none" stroke={hex}
        strokeWidth={9} strokeLinecap="round"
        strokeDasharray={`${fill} ${circ}`}
        style={{ transition: 'stroke-dasharray 0.8s ease' }} />
      <text x={55} y={60} textAnchor="middle" dominantBaseline="middle"
        className="rotate-90 origin-center"
        style={{
          transform: 'rotate(90deg)',
          transformOrigin: '55px 55px',
          fontSize: 22,
          fontWeight: 700,
          fill: hex,
        }}>
        {rating.toFixed(1)}
      </text>
    </svg>
  )
}

// ── Rating badge ──────────────────────────────────────────────────────────────

// Keyed by colour band, not a buy/skip word. Labels describe the *fit*, never an
// instruction to purchase or pass.
const RATING_CONFIG: Record<RatingColor, {
  label: string
  icon: typeof CheckCircle
  classes: string
  border: string
}> = {
  green: {
    label: 'Strong match',
    icon: CheckCircle,
    classes: 'bg-emerald-100 text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-400',
    border: 'border-emerald-200 dark:border-emerald-700/40',
  },
  amber: {
    label: 'Fair match',
    icon: AlertCircle,
    classes: 'bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-400',
    border: 'border-amber-200 dark:border-amber-700/40',
  },
  red: {
    label: 'Weak match',
    icon: XCircle,
    classes: 'bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400',
    border: 'border-red-200 dark:border-red-700/40',
  },
}

// ── Purchase decision prompt ──────────────────────────────────────────────────

function PurchasePrompt({
  checkId,
  onDecision,
}: {
  checkId: string
  onDecision: (bought: boolean) => void
}) {
  const [loading, setLoading] = useState<boolean | null>(null)
  const [done, setDone] = useState(false)

  const decide = async (bought: boolean) => {
    setLoading(bought)
    try {
      await shoppingCheckApi.recordDecision(checkId, bought)
      setDone(true)
      onDecision(bought)
    } finally {
      setLoading(null)
    }
  }

  if (done) {
    return (
      <p className="text-sm text-center text-slate-500 dark:text-white/50 py-2">
        Decision recorded — thanks!
      </p>
    )
  }

  return (
    <div className="space-y-2">
      <p className="text-sm font-medium text-slate-700 dark:text-white/80 text-center">
        Did you end up buying it?
      </p>
      <div className="flex gap-2">
        <button
          onClick={() => decide(true)}
          disabled={loading !== null}
          className="flex-1 flex items-center justify-center gap-1.5 py-2 rounded-xl text-sm font-semibold
                     bg-emerald-50 dark:bg-emerald-900/20 text-emerald-700 dark:text-emerald-400
                     hover:bg-emerald-100 dark:hover:bg-emerald-900/40 border border-emerald-200 dark:border-emerald-700/40
                     transition-colors disabled:opacity-50"
        >
          {loading === true ? <Loader2 size={14} className="animate-spin" /> : <CheckCircle size={14} />}
          Yes, bought it!
        </button>
        <button
          onClick={() => decide(false)}
          disabled={loading !== null}
          className="flex-1 flex items-center justify-center gap-1.5 py-2 rounded-xl text-sm font-semibold
                     bg-slate-100 dark:bg-white/[0.06] text-slate-600 dark:text-white/60
                     hover:bg-slate-200 dark:hover:bg-white/10 border border-slate-200 dark:border-white/10
                     transition-colors disabled:opacity-50"
        >
          {loading === false ? <Loader2 size={14} className="animate-spin" /> : <XCircle size={14} />}
          Nope, left it
        </button>
      </div>
    </div>
  )
}

// ── Score breakdown ("Why this score") ─────────────────────────────────────────

// Factor labels/order for the breakdown. The per-factor max comes from the
// backend (`score_weights`) so the bars never drift if weights change; the
// `fallbackMax` here only applies if an older API response omits score_weights.
// Order = importance (highest weight first).
const FACTOR_META: { key: string; label: string; fallbackMax: number; hint: string }[] = [
  { key: 'compatibility', label: 'Pairs with your closet', fallbackMax: 35, hint: 'Genuinely matches things you own' },
  { key: 'uniqueness', label: 'Not a duplicate', fallbackMax: 30, hint: "You don't already own one like it" },
  { key: 'gap_fill', label: 'Fills a gap', fallbackMax: 15, hint: 'Covers a category you’re missing' },
  { key: 'occasion_new', label: 'New occasions', fallbackMax: 12, hint: 'Adds events you can dress for' },
  { key: 'season_new', label: 'New seasons', fallbackMax: 8, hint: 'Extends your seasonal range' },
]

function ScoreBreakdown({
  breakdown,
  weights,
}: {
  breakdown: Record<string, number>
  weights?: Record<string, number>
}) {
  const [mounted, setMounted] = useState(false)
  useEffect(() => {
    const t = requestAnimationFrame(() => setMounted(true))
    return () => cancelAnimationFrame(t)
  }, [])

  const rows = FACTOR_META.filter(f => f.key in breakdown)
  if (rows.length === 0) return null

  return (
    <GlassCard className="p-4 space-y-3">
      <div className="flex items-center gap-2">
        <BarChart3 size={15} className="text-brand-500" />
        <h3 className="text-sm font-semibold text-slate-800 dark:text-white">Why this score</h3>
      </div>
      <div className="space-y-2.5">
        {rows.map(({ key, label, fallbackMax, hint }) => {
          const max = weights?.[key] ?? fallbackMax
          const earned = Math.max(0, Math.round((breakdown[key] ?? 0) * 10) / 10)
          const pct = max > 0 ? Math.min(100, (earned / max) * 100) : 0
          const won = earned > 0
          const barColor = pct >= 66 ? 'bg-emerald-500' : pct >= 33 ? 'bg-amber-500' : won ? 'bg-amber-400' : 'bg-slate-300 dark:bg-white/10'
          return (
            <div key={key} className="space-y-1">
              <div className="flex items-baseline justify-between gap-2">
                <span className={cn(
                  'text-xs font-medium',
                  won ? 'text-slate-700 dark:text-white/80' : 'text-slate-400 dark:text-white/35',
                )}>
                  {label}
                </span>
                <span className={cn(
                  'text-[11px] font-semibold tabular-nums',
                  won ? 'text-slate-600 dark:text-white/60' : 'text-slate-300 dark:text-white/25',
                )}>
                  +{earned}<span className="text-slate-300 dark:text-white/25"> / {max}</span>
                </span>
              </div>
              <div className="h-1.5 rounded-full bg-slate-100 dark:bg-white/[0.06] overflow-hidden">
                <div
                  className={cn('h-full rounded-full transition-[width] duration-700 ease-out', barColor)}
                  style={{ width: mounted ? `${pct}%` : '0%' }}
                />
              </div>
              {!won && (
                <p className="text-[10px] text-slate-400 dark:text-white/30 leading-tight">{hint}</p>
              )}
            </div>
          )
        })}
      </div>
      <p className="text-[10px] text-slate-400 dark:text-white/35 pt-0.5 border-t border-slate-100 dark:border-white/[0.06]">
        Scores are computed from your actual closet — no guesswork.
      </p>
    </GlassCard>
  )
}

// ── Result card ───────────────────────────────────────────────────────────────

function AddToClosetButton({ checkId }: { checkId: string }) {
  const navigate = useNavigate()
  const [status, setStatus] = useState<'idle' | 'loading' | 'done' | 'error'>('idle')

  const handleAdd = async () => {
    setStatus('loading')
    try {
      await shoppingCheckApi.addToCloset(checkId)
      setStatus('done')
    } catch {
      setStatus('error')
    }
  }

  if (status === 'done') {
    return (
      <button
        onClick={() => navigate('/closet')}
        className="w-full flex items-center justify-center gap-2 py-2.5 rounded-xl text-sm font-semibold
                   bg-emerald-50 dark:bg-emerald-900/20 text-emerald-700 dark:text-emerald-400
                   border border-emerald-200 dark:border-emerald-700/40 transition-colors"
      >
        <Shirt size={14} /> View in My Closet
      </button>
    )
  }

  return (
    <button
      onClick={handleAdd}
      disabled={status === 'loading'}
      className="w-full flex items-center justify-center gap-2 py-2.5 rounded-xl text-sm font-semibold
                 bg-brand-50 dark:bg-brand-900/20 text-brand-700 dark:text-brand-400
                 hover:bg-brand-100 dark:hover:bg-brand-900/40
                 border border-brand-200 dark:border-brand-700/40
                 transition-colors disabled:opacity-50"
    >
      {status === 'loading'
        ? <Loader2 size={14} className="animate-spin" />
        : <PlusCircle size={14} />}
      {status === 'error' ? 'Failed — try again' : 'Add to My Closet'}
    </button>
  )
}

// ── Outfit builder (Ask 2) ────────────────────────────────────────────────────

const TIER_STYLE: Record<BuiltOutfit['tier'], string> = {
  Perfect: 'bg-emerald-100 text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-400',
  Great: 'bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400',
  Solid: 'bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-400',
  Wearable: 'bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-400',
  Risky: 'bg-slate-100 text-slate-600 dark:bg-white/[0.06] dark:text-white/50',
}

function OutfitCardMini({ outfit, anchorImg }: { outfit: BuiltOutfit; anchorImg: string | null }) {
  const forgotten = new Set(outfit.forgotten_item_ids)
  return (
    <div className="rounded-2xl border border-slate-200 dark:border-white/10 p-3 space-y-2">
      <div className="flex items-center justify-between">
        <span className={cn('text-xs font-bold px-2.5 py-1 rounded-full', TIER_STYLE[outfit.tier])}>
          {outfit.tier}
        </span>
        <span className="text-[11px] text-slate-400 dark:text-white/30">
          {Math.round(outfit.score * 100)}% cohesion
        </span>
      </div>
      <div className="flex gap-2 overflow-x-auto pb-1">
        {/* Anchor (the new item) leads the look */}
        <div className="flex-shrink-0 w-16 text-center space-y-1">
          <LazyImage
            src={anchorImg}
            alt="New item"
            aspect="aspect-square"
            rounded="rounded-xl"
            wrapperClassName="w-16 ring-2 ring-brand-400"
            fallback={<ShoppingCart size={18} className="text-brand-400" />}
          />
          <p className="text-[9px] text-brand-500 font-semibold">NEW</p>
        </div>
        {outfit.items.map(it => (
          <div key={it.id} className="flex-shrink-0 w-16 text-center space-y-1">
            <LazyImage
              src={it.image_url ? resolveUploadUrl(it.image_url) : null}
              alt={it.name}
              aspect="aspect-square"
              rounded="rounded-xl"
              wrapperClassName={cn('w-16', forgotten.has(it.id) && 'ring-2 ring-amber-300')}
              fallback={<Package size={18} className="text-slate-300 dark:text-white/20" />}
            />
            <p className="text-[9px] text-slate-500 dark:text-white/50 truncate leading-tight">{it.name}</p>
          </div>
        ))}
      </div>
      <p className="text-xs text-slate-600 dark:text-white/65 leading-snug">{outfit.note}</p>
    </div>
  )
}

function GapSuggestionCard({ gaps }: { gaps: GapSuggestion[] }) {
  if (gaps.length === 0) return null
  return (
    <div className="rounded-2xl border border-amber-200 dark:border-amber-700/40 bg-amber-50/60 dark:bg-amber-900/15 p-3 space-y-2">
      <div className="flex items-center gap-2">
        <TrendingUp size={14} className="text-amber-600 dark:text-amber-400" />
        <h4 className="text-sm font-semibold text-amber-800 dark:text-amber-300">Complete your closet</h4>
      </div>
      {gaps.map(g => (
        <div key={g.role} className="text-xs text-amber-800/90 dark:text-amber-200/80 leading-snug">
          <span className="font-semibold capitalize">Add {g.shop_for}</span>
          {' '}— {g.formality}, in {g.suggested_colors.slice(0, 2).join(' or ')}.
          {g.completes_outfits > 0 && (
            <span className="font-bold text-amber-900 dark:text-amber-200">
              {' '}Completes {g.completes_outfits} outfit{g.completes_outfits === 1 ? '' : 's'} you own.
            </span>
          )}
        </div>
      ))}
    </div>
  )
}

function OutfitBuilderSection({ checkId, anchorImg }: { checkId: string; anchorImg: string | null }) {
  const [status, setStatus] = useState<'idle' | 'loading' | 'done' | 'error'>('idle')
  const [outfits, setOutfits] = useState<BuiltOutfit[]>([])
  const [missing, setMissing] = useState<string[]>([])
  const [gaps, setGaps] = useState<GapSuggestion[]>([])
  const [completesN, setCompletesN] = useState(0)

  const load = async () => {
    setStatus('loading')
    try {
      const res = await shoppingCheckApi.buildOutfits(checkId)
      setOutfits(res.outfits)
      setMissing(res.missing_roles)
      setGaps(res.gap_suggestions)
      setCompletesN(res.completes_outfits)
      setStatus('done')
    } catch {
      setStatus('error')
    }
  }

  if (status === 'idle') {
    return (
      <button
        onClick={load}
        className="w-full flex items-center justify-center gap-2 py-2.5 rounded-xl text-sm font-semibold
                   bg-brand-50 dark:bg-brand-900/20 text-brand-700 dark:text-brand-400
                   border border-brand-200 dark:border-brand-700/40 hover:bg-brand-100 dark:hover:bg-brand-900/40 transition-colors"
      >
        <Sparkles size={15} /> Build outfits from my closet
      </button>
    )
  }

  return (
    <GlassCard className="p-4 space-y-3">
      <div className="flex items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          <Sparkles size={15} className="text-brand-500" />
          <h3 className="text-sm font-semibold text-slate-800 dark:text-white">Best looks you could build</h3>
        </div>
        {status === 'done' && completesN > 0 && (
          <span className="text-[11px] font-bold px-2 py-1 rounded-full bg-emerald-100 text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-400">
            Completes {completesN} outfit{completesN === 1 ? '' : 's'}
          </span>
        )}
      </div>
      {status === 'loading' && (
        <div className="py-4">
          <FaniLoader size="md" messages={['Searching your closet for the best combinations…']} />
        </div>
      )}
      {status === 'error' && (
        <button onClick={load} className="text-sm text-brand-600 dark:text-brand-400 hover:underline">
          Couldn’t build outfits — try again
        </button>
      )}
      {status === 'done' && outfits.length === 0 && (
        <p className="text-sm text-slate-500 dark:text-white/50">
          Not enough in your closet to complete a look around this yet
          {missing.length > 0 && <> — you’re missing a {missing.join(' and ')}.</>}
        </p>
      )}
      {status === 'done' && outfits.map((o, i) => (
        <OutfitCardMini key={i} outfit={o} anchorImg={anchorImg} />
      ))}
      {/* Ask 3 — gap completers with the buy-signal */}
      {status === 'done' && <GapSuggestionCard gaps={gaps} />}
      {status === 'done' && outfits.length > 0 && gaps.length === 0 && missing.length > 0 && (
        <p className="text-[11px] text-amber-600 dark:text-amber-400">
          Add a {missing.join(' and ')} to unlock more complete outfits.
        </p>
      )}
    </GlassCard>
  )
}

function ResultCard({
  result,
  previewUrl,
  onReset,
}: {
  result: ShoppingCheckResult
  previewUrl: string | null
  onReset: () => void
}) {
  const [bought, setBought] = useState<boolean | null>(null)
  const ratingColor = ratingColorOf(result.rating_color, result.rating)
  const rec = RATING_CONFIG[ratingColor]
  const RecIcon = rec.icon

  // Instrument: the user actually saw a verdict (funnel step after check_created).
  useEffect(() => {
    shoppingCheckApi.logEvent(result.check_id, 'verdict_viewed', {
      recommendation: result.buy_recommendation,
      input_type: result.input_type,
    })
  }, [result.check_id, result.buy_recommendation, result.input_type])

  const analysis = result.item_analysis as Record<string, unknown>
  const dupes = result.matched_items.filter(m => m.is_duplicate)
  const pairings = result.matched_items.filter(m => !m.is_duplicate)

  return (
    <div className="space-y-5">
      {/* Header strip */}
      <GlassCard className="p-4 sm:p-5">
        <div className="flex gap-4 sm:gap-5 items-start">
          {/* Item photo */}
          <LazyImage
            src={previewUrl}
            alt="Item you're checking"
            aspect="aspect-square"
            rounded="rounded-2xl"
            wrapperClassName="w-24 h-24 sm:w-28 sm:h-28 flex-shrink-0 shadow-md"
            fallback={<ShoppingCart size={28} className="text-slate-300 dark:text-white/20" />}
          />

          {/* Score + recommendation */}
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-3 flex-wrap">
              <ScoreRing rating={result.rating} color={ratingColor} />
              <div>
                <div className={cn(
                  'inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full text-sm font-bold border',
                  rec.classes, rec.border,
                )}>
                  <RecIcon size={15} />
                  {rec.label}
                </div>
                <p className="mt-2 text-[11px] text-slate-500 dark:text-white/40 uppercase tracking-wider font-semibold">
                  {result.rating.toFixed(1)} / 10 Rating
                </p>
              </div>
            </div>

            {/* Item quick-facts */}
            <div className="mt-3 flex flex-wrap gap-1.5">
              {Boolean(analysis.category) && (
                <Badge variant="gray" className="text-xs capitalize">{String(analysis.category)}</Badge>
              )}
              {Boolean(analysis.primary_color ?? analysis.color) && (
                <Badge variant="gray" className="text-xs capitalize">
                  {String(analysis.primary_color ?? analysis.color)}
                </Badge>
              )}
              {Boolean(analysis.material) && (
                <Badge variant="gray" className="text-xs capitalize">{String(analysis.material)}</Badge>
              )}
            </div>
          </div>
        </div>

        {/* Closet boost */}
        {result.closet_boost_pct > 0 && (
          <div className="mt-4 flex items-center gap-2 px-3 py-2 rounded-xl
                          bg-brand-50 dark:bg-brand-900/20 border border-brand-100 dark:border-brand-800/30">
            <TrendingUp size={15} className="text-brand-500 flex-shrink-0" />
            <p className="text-sm text-brand-700 dark:text-brand-400">
              Buying this would boost your wardrobe completeness by{' '}
              <span className="font-bold">+{result.closet_boost_pct}%</span>
            </p>
          </div>
        )}
      </GlassCard>

      {/* Why this score — transparent, closet-grounded breakdown */}
      {result.score_breakdown && Object.keys(result.score_breakdown).length > 0 && (
        <ScoreBreakdown breakdown={result.score_breakdown} weights={result.score_weights} />
      )}

      {/* Source attribution — only for URL / screenshot checks */}
      {result.source_url && (
        <a
          href={result.source_url}
          target="_blank"
          rel="noopener noreferrer"
          className="flex items-center gap-2 px-3 py-2 rounded-xl text-xs
                     bg-slate-50 dark:bg-white/[0.04] border border-slate-200 dark:border-white/10
                     text-slate-600 dark:text-white/60 hover:bg-slate-100 dark:hover:bg-white/[0.08] transition-colors"
        >
          <Link2 size={13} className="flex-shrink-0 text-brand-500" />
          <span className="truncate flex-1">
            {result.source_brand ? <span className="font-semibold">{result.source_brand} · </span> : null}
            {result.source_title || result.source_site || result.source_url}
            {result.source_price ? <span className="text-slate-400 dark:text-white/40"> · {result.source_price}</span> : null}
          </span>
          {result.input_type === 'screenshot' && (
            <span className="text-[10px] text-slate-400 dark:text-white/30 flex-shrink-0">via screenshot</span>
          )}
          <ExternalLink size={12} className="flex-shrink-0 text-slate-400" />
        </a>
      )}

      {/* Reasoning */}
      <GlassCard className="p-4 space-y-2">
        <div className="flex items-center gap-2">
          <Sparkles size={15} className="text-brand-500" />
          <h3 className="text-sm font-semibold text-slate-800 dark:text-white">FANI's Take</h3>
          {result.fani_take?.grounded && (
            <span className="ml-auto inline-flex items-center gap-1 text-[10px] font-semibold px-2 py-0.5 rounded-full
                             bg-brand-50 dark:bg-brand-900/20 text-brand-600 dark:text-brand-400">
              <Sparkles size={9} /> Grounded
            </span>
          )}
        </div>
        <p className="text-sm text-slate-600 dark:text-white/70 leading-relaxed">
          {result.fani_take?.take || result.reasoning}
        </p>

        {/* When an AI take is shown, keep the deterministic factors as a sub-line */}
        {result.fani_take?.take && (
          <p className="text-xs text-slate-400 dark:text-white/40 leading-relaxed">{result.reasoning}</p>
        )}

        {/* Cited fashion-knowledge sources — makes the take auditable */}
        {result.fani_take?.cited_titles && result.fani_take.cited_titles.length > 0 && (
          <p className="text-[10px] text-slate-400 dark:text-white/35 leading-tight">
            Grounded in: {result.fani_take.cited_titles.join(' · ')}
          </p>
        )}

        {/* Honest one-liners: dupe-check + completes-N-outfits */}
        <div className="flex flex-wrap gap-2 pt-1">
          {(result.dupe_count ?? 0) > 0 && (
            <span className="inline-flex items-center gap-1 text-xs font-medium px-2 py-1 rounded-full
                             bg-red-50 dark:bg-red-900/20 text-red-600 dark:text-red-400">
              <Copy size={12} />
              You own {result.dupe_count} like this
            </span>
          )}
          {(result.completes_outfits ?? 0) > 0 && (
            <span className="inline-flex items-center gap-1 text-xs font-medium px-2 py-1 rounded-full
                             bg-emerald-50 dark:bg-emerald-900/20 text-emerald-600 dark:text-emerald-400">
              <Shirt size={12} />
              Completes {result.completes_outfits} outfit{result.completes_outfits === 1 ? '' : 's'}
            </span>
          )}
        </div>
      </GlassCard>

      {/* Dupe-check — the honest "you already own this" warning */}
      {dupes.length > 0 && (
        <GlassCard className="p-4 space-y-3">
          <div className="flex items-center gap-2">
            <Copy size={15} className="text-red-500" />
            <h3 className="text-sm font-semibold text-slate-800 dark:text-white">
              You already own {dupes.length === 1 ? 'a' : dupes.length} similar {dupes.length === 1 ? 'item' : 'items'}
            </h3>
          </div>
          <div className="flex gap-3 overflow-x-auto pb-1">
            {dupes.map(item => (
              <div key={item.id} className="flex-shrink-0 w-20 space-y-1">
                <div className="relative">
                  <LazyImage
                    src={item.image_url ? resolveUploadUrl(item.image_url) : null}
                    alt={item.name}
                    aspect="aspect-square"
                    rounded="rounded-xl"
                    wrapperClassName="w-20 ring-2 ring-red-400"
                    fallback={<Package size={22} className="text-slate-300 dark:text-white/20" />}
                  />
                  <div className="absolute inset-0 bg-red-500/20 flex items-center justify-center rounded-xl pointer-events-none">
                    <span className="text-[9px] font-bold text-red-600 dark:text-red-400 bg-white dark:bg-slate-900 px-1 rounded">OWNED</span>
                  </div>
                </div>
                <p className="text-[10px] text-slate-600 dark:text-white/60 truncate text-center leading-tight">{item.name}</p>
              </div>
            ))}
          </div>
        </GlassCard>
      )}

      {/* Compatibility — what this genuinely pairs with (NOT embedding similarity) */}
      {pairings.length > 0 && (
        <GlassCard className="p-4 space-y-3">
          <div className="flex items-center gap-2">
            <Package size={15} className="text-emerald-500" />
            <h3 className="text-sm font-semibold text-slate-800 dark:text-white">
              Pairs with {pairings.length} {pairings.length === 1 ? 'item' : 'items'} you own
            </h3>
          </div>
          <div className="flex gap-3 overflow-x-auto pb-1">
            {pairings.map(item => (
              <div key={item.id} className="flex-shrink-0 w-20 space-y-1">
                <LazyImage
                  src={item.image_url ? resolveUploadUrl(item.image_url) : null}
                  alt={item.name}
                  aspect="aspect-square"
                  rounded="rounded-xl"
                  wrapperClassName="w-20"
                  fallback={<Package size={22} className="text-slate-300 dark:text-white/20" />}
                />
                <p className="text-[10px] text-slate-600 dark:text-white/60 truncate text-center leading-tight">{item.name}</p>
                <p className="text-[10px] text-emerald-500/80 text-center">
                  {Math.round(item.similarity_score * 100)}% match
                </p>
              </div>
            ))}
          </div>
        </GlassCard>
      )}

      {/* Ask 2 — build the best outfits from items the user already owns */}
      <OutfitBuilderSection checkId={result.check_id} anchorImg={previewUrl} />

      {/* Purchase decision */}
      <GlassCard className="p-4 space-y-3">
        {bought === null ? (
          <PurchasePrompt checkId={result.check_id} onDecision={b => setBought(b)} />
        ) : (
          <div className={cn(
            'flex items-center gap-2 justify-center text-sm font-medium py-1',
            bought
              ? 'text-emerald-600 dark:text-emerald-400'
              : 'text-slate-500 dark:text-white/50',
          )}>
            {bought ? <CheckCircle size={15} /> : <XCircle size={15} />}
            {bought ? 'Great pick! Added to your purchase history.' : 'Good call — your closet thanks you!'}
          </div>
        )}
        {/* Always show "Add to Closet" so they can save it regardless of decision */}
        <AddToClosetButton checkId={result.check_id} />
      </GlassCard>

      {/* Repeat-paste nudge — the retention/viral signal made visible */}
      {result.input_type !== 'photo' && (result.url_check_count ?? 0) >= 2 && (
        <p className="text-center text-xs text-slate-400 dark:text-white/35">
          That’s {result.url_check_count} links you’ve run past FANI — it’s learning your taste.
        </p>
      )}

      {/* Check another */}
      <button
        onClick={() => { shoppingCheckApi.logEvent(result.check_id, 'paste_again'); onReset() }}
        className="w-full flex items-center justify-center gap-2 py-3 rounded-xl text-sm font-semibold
                   text-brand-600 dark:text-brand-400
                   hover:bg-brand-50 dark:hover:bg-brand-900/20
                   border border-brand-200 dark:border-brand-700/40
                   transition-colors"
      >
        <RotateCcw size={14} />
        Check another item
      </button>
    </div>
  )
}

// ── History card (compact) ────────────────────────────────────────────────────

function historyCheckId(entry: ShoppingHistoryEntry): string {
  return entry.check_id ?? String((entry as ShoppingHistoryEntry & { id?: string }).id ?? '')
}

function HistoryCard({
  entry,
  onDeleted,
}: {
  entry: ShoppingHistoryEntry
  onDeleted: (checkId: string) => void
}) {
  const checkId = historyCheckId(entry)
  const [confirming, setConfirming] = useState(false)
  const [deleting, setDeleting] = useState(false)

  const ratingColor = ratingColorOf(entry.rating_color, entry.rating)
  const rec = RATING_CONFIG[ratingColor]
  const RecIcon = rec.icon
  const analysis = entry.item_analysis as Record<string, unknown>

  const handleDelete = async () => {
    if (!checkId) return
    setDeleting(true)
    try {
      await shoppingCheckApi.deleteCheck(checkId)
      onDeleted(checkId)
    } catch {
      setConfirming(false)
    } finally {
      setDeleting(false)
    }
  }

  return (
    <GlassCard className="overflow-hidden">
      <div className="p-3 flex items-center gap-3 group">
        {entry.image_url && (
          <LazyImage
            src={resolveUploadUrl(entry.image_url)}
            alt={String(analysis.name || analysis.category || 'Checked item')}
            aspect="aspect-square"
            rounded="rounded-xl"
            wrapperClassName="w-14 h-14 flex-shrink-0"
          />
        )}
        <div className="flex-1 min-w-0">
          <p className="text-sm font-semibold text-slate-800 dark:text-white capitalize truncate">
            {String(analysis.name || analysis.category || 'Item')}
          </p>
          <p className="text-xs text-slate-400 dark:text-white/40 truncate capitalize">
            {String(analysis.primary_color || analysis.color || '')}
            {analysis.material ? ` · ${String(analysis.material)}` : ''}
          </p>
          <div className="mt-1 flex items-center gap-2 flex-wrap">
            <span className={cn('text-[11px] font-semibold px-2 py-0.5 rounded-full flex items-center gap-1', rec.classes)}>
              <RecIcon size={10} />
              {rec.label}
            </span>
            <span className="text-[11px] text-slate-400 dark:text-white/40">
              Rating: {entry.rating.toFixed(1)} / 10
            </span>
            {entry.purchase_decision !== null && (
              <span className={cn(
                'text-[11px] px-2 py-0.5 rounded-full font-medium',
                entry.purchase_decision
                  ? 'bg-emerald-100 text-emerald-700 dark:bg-emerald-900/20 dark:text-emerald-400'
                  : 'bg-slate-100 text-slate-500 dark:bg-white/[0.06] dark:text-white/40',
              )}>
                {entry.purchase_decision ? 'Bought' : 'Not bought'}
              </span>
            )}
          </div>
        </div>
        <div className="flex items-center gap-1 flex-shrink-0">
          <div className="text-right">
            <p className="text-lg font-bold" style={{ color: RATING_HEX[ratingColor] }}>
              {entry.rating.toFixed(1)}
            </p>
            <p className="text-[10px] text-slate-400 dark:text-white/30">/ 10</p>
          </div>
          {checkId && (
            <button
              type="button"
              onClick={() => setConfirming(c => !c)}
              disabled={deleting}
              title="Delete this check"
              aria-label={`Delete check for ${String(analysis.name || analysis.category || 'item')}`}
              className={cn(
                'p-2 min-h-[40px] min-w-[40px] flex items-center justify-center rounded-lg transition-all',
                'focus:outline-none focus-visible:ring-2 focus-visible:ring-red-400/60',
                // Visible on touch; emphasised on hover/focus for pointer users
                confirming
                  ? 'text-red-500 bg-red-50 dark:bg-red-900/20'
                  : 'text-slate-400 hover:text-red-500 hover:bg-red-50 dark:hover:bg-red-900/20 md:opacity-60 md:group-hover:opacity-100 md:focus-visible:opacity-100',
              )}
            >
              {deleting
                ? <Loader2 size={14} className="animate-spin" />
                : <Trash2 size={14} />}
            </button>
          )}
        </div>
      </div>

      {confirming && (
        <div className="flex items-center justify-between gap-2 px-3 py-2 bg-red-50 dark:bg-red-900/20 border-t border-red-100 dark:border-red-800/40">
          <p className="text-xs text-red-700 dark:text-red-400 font-medium">
            Remove this check from history?
          </p>
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={() => setConfirming(false)}
              disabled={deleting}
              className="text-[11px] font-medium text-slate-500 dark:text-slate-400 hover:text-slate-700 dark:hover:text-slate-200"
            >
              Cancel
            </button>
            <button
              type="button"
              onClick={handleDelete}
              disabled={deleting}
              className="text-[11px] font-bold text-white bg-red-500 hover:bg-red-600 px-2.5 py-1 rounded-lg disabled:opacity-50"
            >
              Delete
            </button>
          </div>
        </div>
      )}
    </GlassCard>
  )
}

// ── Upload zone ───────────────────────────────────────────────────────────────

function UploadZone({ onFile }: { onFile: (f: File) => void }) {
  const inputRef = useRef<HTMLInputElement>(null)
  const [dragging, setDragging] = useState(false)

  const handle = (file: File) => {
    if (!file.type.startsWith('image/')) return
    onFile(file)
  }

  return (
    <GlassCard
      role="button"
      tabIndex={0}
      aria-label="Upload or take a photo of an item to check"
      className={cn(
        'p-6 sm:p-10 flex flex-col items-center justify-center gap-4 cursor-pointer',
        'border-2 border-dashed transition-colors',
        'focus:outline-none focus-visible:ring-2 focus-visible:ring-brand-500/60 focus-visible:ring-offset-2 focus-visible:ring-offset-cream-100 dark:focus-visible:ring-offset-slate-950',
        dragging
          ? 'border-brand-400 bg-brand-50/50 dark:bg-brand-900/10'
          : 'border-slate-300 dark:border-white/20 hover:border-brand-400',
      )}
      onClick={() => inputRef.current?.click()}
      onKeyDown={e => {
        if (e.key === 'Enter' || e.key === ' ') {
          e.preventDefault()
          inputRef.current?.click()
        }
      }}
      onDragOver={e => { e.preventDefault(); setDragging(true) }}
      onDragLeave={() => setDragging(false)}
      onDrop={e => {
        e.preventDefault()
        setDragging(false)
        const f = e.dataTransfer.files[0]
        if (f) handle(f)
      }}
    >
      <input
        ref={inputRef}
        type="file"
        accept="image/*"
        capture="environment"
        className="hidden"
        onChange={e => { const f = e.target.files?.[0]; if (f) handle(f) }}
      />

      <div className="w-16 h-16 rounded-2xl bg-gradient-to-br from-brand-600 to-brand-700
                      flex items-center justify-center shadow-glow-sm">
        <Camera size={30} className="text-white" />
      </div>

      <div className="text-center space-y-1">
        <p className="font-semibold text-slate-800 dark:text-white">
          Take a photo or upload from gallery
        </p>
        <p className="text-sm text-slate-500 dark:text-white/50">
          Point your camera at any store item to get an instant fit rating
        </p>
      </div>

      <div className="flex items-center gap-3 text-xs text-slate-400 dark:text-white/30">
        <span className="flex items-center gap-1"><Camera size={12} /> Camera</span>
        <span>·</span>
        <span className="flex items-center gap-1"><Upload size={12} /> Gallery</span>
        <span>·</span>
        <span>JPEG / PNG / WebP</span>
      </div>
    </GlassCard>
  )
}

// ── URL paste bar ─────────────────────────────────────────────────────────────

function UrlPasteBar({ onSubmit, disabled }: { onSubmit: (url: string) => void; disabled: boolean }) {
  const [url, setUrl] = useState('')
  const valid = /^https?:\/\/.+\..+/i.test(url.trim())

  const submit = () => {
    if (valid && !disabled) onSubmit(url.trim())
  }

  return (
    <GlassCard className="p-4 space-y-2">
      <div className="flex items-center gap-2">
        <Link2 size={15} className="text-brand-500" />
        <h3 className="text-sm font-semibold text-slate-800 dark:text-white">Paste a product link</h3>
      </div>
      <label htmlFor="shopping-url" className="sr-only">Product link to check</label>
      <div className="flex gap-2">
        <input
          id="shopping-url"
          type="url"
          inputMode="url"
          value={url}
          onChange={e => setUrl(e.target.value)}
          onKeyDown={e => { if (e.key === 'Enter') submit() }}
          placeholder="https://brand.com/the-jacket-you-want"
          disabled={disabled}
          className="flex-1 min-w-0 px-3 py-2.5 rounded-xl text-sm
                     bg-white dark:bg-white/[0.04] border border-slate-200 dark:border-white/10
                     text-slate-800 dark:text-white placeholder:text-slate-400 dark:placeholder:text-white/30
                     focus:outline-none focus:ring-2 focus:ring-brand-400 disabled:opacity-50"
        />
        <button
          onClick={submit}
          disabled={!valid || disabled}
          className="flex-shrink-0 px-4 py-2.5 rounded-xl text-sm font-semibold
                     bg-brand-600 text-white hover:bg-brand-700 transition-colors
                     disabled:opacity-40 disabled:cursor-not-allowed"
        >
          Check it
        </button>
      </div>
      <p className="text-[11px] text-slate-400 dark:text-white/35">
        FANI reads the product page and gives one honest verdict against your closet.
      </p>
    </GlassCard>
  )
}

// ── Main page ─────────────────────────────────────────────────────────────────

export default function ShoppingCheck() {
  const [preview, setPreview] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [result, setResult] = useState<ShoppingCheckResult | null>(null)

  // Cached, de-duped history — served instantly across visits, refreshed after a check.
  const {
    data: history,
    loading: historyLoading,
    refetch: refetchHistory,
    mutate: mutateHistory,
  } = useCachedQuery<ShoppingHistoryEntry[]>(
    HISTORY_KEY,
    () => shoppingCheckApi.getHistory(10),
    { ttl: 60_000 },
  )

  const handleFile = async (file: File) => {
    setPreview(URL.createObjectURL(file))
    setResult(null)
    setError(null)
    setLoading(true)
    try {
      const res = await shoppingCheckApi.checkItem(file)
      setResult(res)
      // Refresh history after a new check
      void refetchHistory()
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Analysis failed. Please try again.')
    } finally {
      setLoading(false)
    }
  }

  const handleUrl = async (url: string) => {
    setPreview(null)
    setResult(null)
    setError(null)
    setLoading(true)
    try {
      const res = await shoppingCheckApi.checkUrl(url)
      setPreview(res.image_url ? (resolveUploadUrl(res.image_url) ?? null) : null)
      setResult(res)
      void refetchHistory()
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Couldn’t read that link. Try a direct product page.')
    } finally {
      setLoading(false)
    }
  }

  const reset = () => {
    setPreview(null)
    setResult(null)
    setError(null)
  }

  const handleHistoryDeleted = (checkId: string) => {
    const next = (history ?? []).filter(e => historyCheckId(e) !== checkId)
    mutateHistory(next)
    invalidateQuery(HISTORY_KEY)
  }

  return (
    <Container size="sm" className="space-y-6">
      <BackButton fallback="/dashboard" label="Back to Dashboard" />

      {/* Page header */}
      <PageHeader
        icon={<ShoppingCart size={18} />}
        chipClassName="bg-gradient-to-br from-green-500 to-emerald-600 shadow-glow-sm"
        iconColor="text-white"
        title="Shop with FANI"
        subtitle="Paste a product link or snap an item — FANI tells you if it belongs in your closet"
        actions={
          <a
            href="/closet-match"
            className="flex-shrink-0 flex items-center gap-1.5 px-3 py-2 rounded-xl text-xs font-semibold
                       bg-brand-50 dark:bg-brand-900/20 text-brand-700 dark:text-brand-400
                       border border-brand-200 dark:border-brand-700/40 hover:bg-brand-100
                       dark:hover:bg-brand-900/40 transition-colors whitespace-nowrap"
          >
            <Shirt size={13} />
            Fit Match
          </a>
        }
      />

      {/* How it works strip */}
      {!result && !loading && (
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
          {[
            { icon: Camera, label: 'Snap a photo', desc: 'Point at any item you like' },
            { icon: Star, label: 'Get a rating', desc: '0–10 fit rating with colour' },
            { icon: TrendingUp, label: 'See the impact', desc: 'How it completes your closet' },
          ].map(({ icon: Icon, label, desc }) => (
            <GlassCard
              key={label}
              className="p-3 flex items-center gap-3 text-left sm:flex-col sm:items-center sm:gap-1.5 sm:text-center"
            >
              <Icon size={20} className="flex-shrink-0 sm:mx-auto text-brand-500 dark:text-brand-400" />
              <div className="sm:contents">
                <p className="text-sm sm:text-xs font-semibold text-slate-800 dark:text-white">{label}</p>
                <p className="text-xs sm:text-[11px] text-slate-500 dark:text-white/45">{desc}</p>
              </div>
            </GlassCard>
          ))}
        </div>
      )}

      {/* URL paste + Upload zone */}
      {!result && !loading && !error && (
        <div className="space-y-4">
          <UrlPasteBar onSubmit={handleUrl} disabled={loading} />
          <div className="flex items-center gap-3">
            <div className="flex-1 h-px bg-slate-200 dark:bg-white/10" />
            <span className="text-[11px] font-medium text-slate-400 dark:text-white/30 uppercase tracking-wider">or</span>
            <div className="flex-1 h-px bg-slate-200 dark:bg-white/10" />
          </div>
          <UploadZone onFile={handleFile} />
        </div>
      )}

      {/* Loading state */}
      {loading && (
        <GlassCard className="p-6 sm:p-8 flex flex-col items-center gap-5">
          <LazyImage
            src={preview}
            alt="Item being analysed"
            aspect="aspect-square"
            rounded="rounded-2xl"
            wrapperClassName="w-24 h-24"
            eager
            fallback={<Link2 size={26} className="text-slate-300 dark:text-white/20" />}
          />
          <FaniLoader
            size="md"
            messages={[preview ? 'Analysing your item…' : 'Reading the product page…']}
            subline="Checking against your closet and computing compatibility"
          />
        </GlassCard>
      )}

      {/* Error */}
      {error && (
        <GlassCard className="p-5 space-y-3">
          <div className="flex items-center gap-2 text-red-600 dark:text-red-400">
            <AlertCircle size={18} />
            <p className="text-sm font-medium">{error}</p>
          </div>
          <button onClick={reset} className="text-sm text-brand-600 dark:text-brand-400 hover:underline">
            Try again
          </button>
        </GlassCard>
      )}

      {/* Result */}
      {result && (
        <ResultCard result={result} previewUrl={preview} onReset={reset} />
      )}

      {/* Recent checks */}
      {!loading && !result && (
        <div className="space-y-3">
          <div className="flex items-center justify-between">
            <h2 className="text-sm font-semibold text-slate-700 dark:text-white/70 uppercase tracking-wider">
              Recent checks
            </h2>
            {historyLoading && <Loader2 size={14} className="animate-spin text-slate-400" />}
          </div>
          {history && history.length === 0 && (
            <p className="text-sm text-slate-400 dark:text-white/30 text-center py-4">
              No checks yet — snap your first item above!
            </p>
          )}
          {history && history.map(entry => (
            <HistoryCard
              key={historyCheckId(entry) || String(entry.created_at)}
              entry={entry}
              onDeleted={handleHistoryDeleted}
            />
          ))}
        </div>
      )}
    </Container>
  )
}
