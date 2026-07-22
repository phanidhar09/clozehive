import { useEffect, useRef, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import {
  Camera, Upload, ShoppingCart, Check, X, Minus, CheckCircle, XCircle,
  Loader2, RotateCcw, TrendingUp, Package, Sparkles, Trash2, ArrowRight,
  Shirt, Link2, ExternalLink, Copy, Bookmark, AlertCircle,
} from 'lucide-react'
import BackButton from '@/components/ui/BackButton'
import GlassCard from '@/components/ui/GlassCard'
import PageHeader from '@/components/ui/PageHeader'
import Container from '@/components/ui/Container'
import LazyImage from '@/components/ui/LazyImage'
import { FaniLoader } from '@/components/system/FaniLoader'
import { useCachedQuery, invalidateQuery } from '@/hooks/useCachedQuery'
import { shoppingCheckApi, type ShoppingCheckResult, type ShoppingHistoryEntry,
  type BuiltOutfit, type GapSuggestion } from '@/lib/api'
import { resolveUploadUrl } from '@/lib/api'
import { cn } from '@/lib/utils'
import { toastStore } from '@/store/notificationStore'
import { useApp } from '@/store'

const HISTORY_KEY = 'shopping:history'

// ── Verdict ─────────────────────────────────────────────────────────────────
//
// The headline verdict maps directly to the backend's `buy_recommendation`
// band. Score shown is `buy_score` on a 0–100 scale (matches the ring).

type Verdict = 'buy' | 'consider' | 'skip'

const VERDICT: Record<Verdict, {
  label: string
  glyph: typeof Check
  hex: string
  ringTrack: string
  badge: string
  chip: string
  line: string
}> = {
  buy: {
    label: 'BUY IT',
    glyph: Check,
    hex: '#10b981',
    ringTrack: 'text-emerald-100 dark:text-emerald-500/15',
    badge: 'bg-emerald-500 text-white',
    chip: 'bg-emerald-100 text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-400',
    line: 'A genuine gap-filler — it works with what you already own and earns its place.',
  },
  consider: {
    label: 'THINK ABOUT IT',
    glyph: Minus,
    hex: '#f59e0b',
    ringTrack: 'text-amber-100 dark:text-amber-500/15',
    badge: 'bg-amber-500 text-white',
    chip: 'bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-400',
    line: 'Tempting, but it overlaps with what you own. Sleep on this one.',
  },
  skip: {
    label: 'SKIP IT',
    glyph: X,
    hex: '#ef4444',
    ringTrack: 'text-red-100 dark:text-red-500/15',
    badge: 'bg-red-500 text-white',
    chip: 'bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400',
    line: 'You already own its job. Your money is better spent elsewhere.',
  },
}

// A few older responses may be missing buy_recommendation — fall back to the
// colour band so the verdict never renders blank.
function verdictOf(result: Pick<ShoppingCheckResult, 'buy_recommendation' | 'rating_color'>): Verdict {
  if (result.buy_recommendation) return result.buy_recommendation
  return result.rating_color === 'green' ? 'buy' : result.rating_color === 'amber' ? 'consider' : 'skip'
}

// ── Score ring (0–100) ────────────────────────────────────────────────────────

function ScoreRing({ score, hex, track }: { score: number; hex: string; track: string }) {
  const [mounted, setMounted] = useState(false)
  useEffect(() => {
    const t = requestAnimationFrame(() => setMounted(true))
    return () => cancelAnimationFrame(t)
  }, [])

  const r = 52
  const circ = 2 * Math.PI * r
  const fill = mounted ? (Math.max(0, Math.min(100, score)) / 100) * circ : 0

  return (
    <div className="relative w-[128px] h-[128px] flex-shrink-0">
      <svg width={128} height={128} className="rotate-[-90deg]">
        <circle cx={64} cy={64} r={r} fill="none" stroke="currentColor"
          strokeWidth={10} className={track} />
        <circle cx={64} cy={64} r={r} fill="none" stroke={hex}
          strokeWidth={10} strokeLinecap="round"
          strokeDasharray={`${fill} ${circ}`}
          style={{ transition: 'stroke-dasharray 0.9s cubic-bezier(0.22,1,0.36,1)' }} />
      </svg>
      <div className="absolute inset-0 flex flex-col items-center justify-center">
        <span className="text-4xl font-extrabold tabular-nums leading-none" style={{ color: hex }}>
          {Math.round(score)}
        </span>
        <span className="text-[11px] font-semibold text-slate-400 dark:text-white/35 mt-0.5">/ 100</span>
      </div>
    </div>
  )
}

// ── "Why this score" — qualitative 2×2 grid, grounded in real factors ─────────
//
// Mirrors the mockup's grid. The mockup's fourth tile was "Value for price",
// which the backend does NOT compute — swapped for "Not a duplicate", which is
// grounded in real dupe/uniqueness data.

type Tone = 'good' | 'mid' | 'weak'

const TONE_CLASS: Record<Tone, string> = {
  good: 'text-emerald-600 dark:text-emerald-400',
  mid: 'text-amber-600 dark:text-amber-400',
  weak: 'text-red-500 dark:text-red-400',
}

function ratio(breakdown: Record<string, number> | undefined, weights: Record<string, number> | undefined, key: string): number | null {
  if (!breakdown || !(key in breakdown)) return null
  const max = weights?.[key]
  if (!max || max <= 0) return null
  return Math.max(0, Math.min(1, breakdown[key] / max))
}

function WhyThisScore({ result, pairCount }: { result: ShoppingCheckResult; pairCount: number }) {
  const { score_breakdown: bd, score_weights: w, style_match, dupe_count } = result

  // 1 — Fits your style (personal-fit sub-signal, else style factor)
  const styleR = style_match ?? ratio(bd, w, 'style_match') ?? ratio(bd, w, 'occasion_new')
  const styleTone: Tone = styleR == null ? 'mid' : styleR >= 0.6 ? 'good' : styleR >= 0.35 ? 'mid' : 'weak'
  const styleWord = styleR == null ? '—' : styleTone === 'good' ? 'Strong' : styleTone === 'mid' ? 'Fair' : 'Off'

  // 2 — Fills a real gap
  const gapR = ratio(bd, w, 'gap_fill')
  const dupes = dupe_count ?? 0
  const gapTone: Tone = gapR == null ? (dupes > 0 ? 'weak' : 'good') : gapR >= 0.6 ? 'good' : gapR >= 0.3 ? 'mid' : 'weak'
  const gapWord = gapTone === 'good' ? 'Yes' : gapTone === 'mid' ? 'Partly' : 'Overlaps'

  // 3 — Pairs with your closet (real owned-item count)
  const pairTone: Tone = pairCount >= 4 ? 'good' : pairCount >= 2 ? 'mid' : 'weak'
  const pairWord = `${pairCount} item${pairCount === 1 ? '' : 's'}`

  // 4 — Not a duplicate (grounded; replaces the mockup's ungrounded "Value for price")
  const dupTone: Tone = dupes > 0 ? 'weak' : 'good'
  const dupWord = dupes > 0 ? `${dupes} owned` : 'Unique'

  const tiles: { label: string; value: string; tone: Tone }[] = [
    { label: 'Fits your style', value: styleWord, tone: styleTone },
    { label: 'Fills a real gap', value: gapWord, tone: gapTone },
    { label: 'Pairs with your closet', value: pairWord, tone: pairTone },
    { label: 'Not a duplicate', value: dupWord, tone: dupTone },
  ]

  return (
    <GlassCard className="p-4 space-y-3">
      <h3 className="text-sm font-semibold text-slate-800 dark:text-white">Why this score</h3>
      <div className="grid grid-cols-2 gap-2.5">
        {tiles.map(t => (
          <div key={t.label} className="rounded-2xl bg-slate-50 dark:bg-white/[0.04] px-3 py-2.5">
            <p className="text-[11px] text-slate-500 dark:text-white/45 leading-tight">{t.label}</p>
            <p className={cn('text-sm font-bold mt-0.5', TONE_CLASS[t.tone])}>{t.value}</p>
          </div>
        ))}
      </div>
    </GlassCard>
  )
}

// ── Outfit builder (unchanged, grounded) ──────────────────────────────────────

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

function OutfitBuilderSection({
  checkId, anchorImg, pairCount, open, onOpen,
}: {
  checkId: string
  anchorImg: string | null
  pairCount: number
  open: boolean
  onOpen: () => void
}) {
  const [status, setStatus] = useState<'idle' | 'loading' | 'done' | 'error'>('idle')
  const [outfits, setOutfits] = useState<BuiltOutfit[]>([])
  const [missing, setMissing] = useState<string[]>([])
  const [gaps, setGaps] = useState<GapSuggestion[]>([])
  const [completesN, setCompletesN] = useState(0)

  const load = async () => {
    onOpen()
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

  // Collapsed teaser — the mockup's "Pairs with N items · Build an outfit ›"
  if (!open) {
    return (
      <button
        onClick={load}
        className="w-full flex items-center justify-between gap-3 px-4 py-3.5 rounded-2xl
                   bg-brand-50 dark:bg-brand-900/20 border border-brand-200 dark:border-brand-700/40
                   hover:bg-brand-100 dark:hover:bg-brand-900/40 transition-colors group"
      >
        <span className="text-sm font-semibold text-brand-700 dark:text-brand-300">
          Pairs with {pairCount} item{pairCount === 1 ? '' : 's'} you own
        </span>
        <span className="flex items-center gap-1 text-sm font-semibold text-brand-600 dark:text-brand-400">
          Build an outfit
          <ArrowRight size={15} className="group-hover:translate-x-0.5 transition-transform" />
        </span>
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
      {status === 'done' && <GapSuggestionCard gaps={gaps} />}
      {status === 'done' && outfits.length > 0 && gaps.length === 0 && missing.length > 0 && (
        <p className="text-[11px] text-amber-600 dark:text-amber-400">
          Add a {missing.join(' and ')} to unlock more complete outfits.
        </p>
      )}
    </GlassCard>
  )
}

// ── Decision row ("Making the call?") ─────────────────────────────────────────

function DecisionRow({ checkId }: { checkId: string }) {
  const navigate = useNavigate()
  const { fetchClosetItems } = useApp()
  const [decision, setDecision] = useState<'bought' | 'skipped' | null>(null)
  const [saving, setSaving] = useState<'idle' | 'loading' | 'done' | 'error'>('idle')
  const [busy, setBusy] = useState(false)

  const refreshCloset = () => {
    void fetchClosetItems()
  }

  const decide = async (bought: boolean) => {
    if (busy || decision !== null) return
    setBusy(true)
    if (bought) setSaving('loading')
    try {
      const result = await shoppingCheckApi.recordDecision(checkId, bought)
      setDecision(bought ? 'bought' : 'skipped')
      if (bought) {
        let closetItem = result.closet_item
        // Fallback: decision logged but closet insert didn't return an item.
        if (!closetItem?.id) {
          try {
            const saved = await shoppingCheckApi.addToCloset(checkId)
            closetItem = saved.closet_item
          } catch {
            closetItem = undefined
          }
        }
        if (closetItem?.id) {
          setSaving('done')
          invalidateQuery(HISTORY_KEY)
          refreshCloset()
          const itemName = String(closetItem.name || 'Item')
          toastStore.add({
            variant: 'success',
            icon: '👕',
            title: 'Added to your closet',
            body: `"${itemName}" is saved — open Closet (try Bottoms / Other if filtered).`,
          })
        } else {
          setSaving('error')
          toastStore.add({
            variant: 'error',
            icon: '👕',
            title: 'Could not save to closet',
            body: 'Decision logged — try Save to add it manually.',
          })
        }
      } else {
        invalidateQuery(HISTORY_KEY)
      }
    } catch {
      if (bought) setSaving('idle')
      toastStore.add({
        variant: 'error',
        icon: '❌',
        title: 'Could not record decision',
        body: 'Please try again.',
      })
    } finally {
      setBusy(false)
    }
  }

  const save = async () => {
    if (saving === 'loading' || saving === 'done') return
    setSaving('loading')
    try {
      const saved = await shoppingCheckApi.addToCloset(checkId)
      setSaving('done')
      invalidateQuery(HISTORY_KEY)
      refreshCloset()
      toastStore.add({
        variant: 'success',
        icon: '👕',
        title: 'Added to your closet',
        body: saved.closet_item?.name
          ? `"${String(saved.closet_item.name)}" is in your Closet.`
          : undefined,
      })
    } catch {
      setSaving('error')
      toastStore.add({
        variant: 'error',
        icon: '👕',
        title: 'Could not save to closet',
        body: 'Please try again.',
      })
    }
  }

  const btn = 'flex-1 flex items-center justify-center gap-1.5 py-2.5 rounded-xl text-sm font-semibold border transition-colors disabled:opacity-50'

  return (
    <GlassCard className="p-4 space-y-3">
      <div>
        <h3 className="text-sm font-semibold text-slate-800 dark:text-white">Making the call?</h3>
        <p className="text-xs text-slate-500 dark:text-white/50 mt-0.5">
          “I bought it” adds the item to your closet and sharpens future recommendations.
        </p>
      </div>

      {decision && (
        <div className={cn(
          'flex items-center gap-2 text-sm font-medium',
          decision === 'bought' ? 'text-emerald-600 dark:text-emerald-400' : 'text-slate-500 dark:text-white/55',
        )}>
          {decision === 'bought' ? <CheckCircle size={15} /> : <XCircle size={15} />}
          {decision === 'bought'
            ? (saving === 'done'
              ? 'Bought and saved to your closet!'
              : saving === 'error'
                ? 'Logged as bought — closet save failed.'
                : 'Logging purchase…')
            : 'Logged as skipped — your closet thanks you.'}
        </div>
      )}

      <div className="flex gap-2">
        <button
          onClick={() => decide(true)}
          disabled={busy || decision !== null}
          className={cn(btn,
            'bg-emerald-50 dark:bg-emerald-900/20 text-emerald-700 dark:text-emerald-400 border-emerald-200 dark:border-emerald-700/40 hover:bg-emerald-100 dark:hover:bg-emerald-900/40')}
        >
          {(busy || saving === 'loading') && decision !== 'skipped'
            ? <Loader2 size={14} className="animate-spin" />
            : <Check size={14} />}
          I bought it
        </button>
        <button
          onClick={() => decide(false)}
          disabled={busy || decision !== null}
          className={cn(btn,
            'bg-slate-100 dark:bg-white/[0.06] text-slate-600 dark:text-white/60 border-slate-200 dark:border-white/10 hover:bg-slate-200 dark:hover:bg-white/10')}
        >
          <X size={14} />
          Skipped it
        </button>
        <button
          onClick={() => (saving === 'done' ? navigate('/closet') : save())}
          disabled={saving === 'loading'}
          className={cn(btn,
            'bg-brand-50 dark:bg-brand-900/20 text-brand-700 dark:text-brand-400 border-brand-200 dark:border-brand-700/40 hover:bg-brand-100 dark:hover:bg-brand-900/40')}
        >
          {saving === 'loading'
            ? <Loader2 size={14} className="animate-spin" />
            : saving === 'done' ? <Shirt size={14} /> : <Bookmark size={14} />}
          {saving === 'done' ? 'View closet' : 'Save'}
        </button>
      </div>
    </GlassCard>
  )
}

// ── Result view ───────────────────────────────────────────────────────────────

function ResultView({
  result, previewUrl, onReset,
}: {
  result: ShoppingCheckResult
  previewUrl: string | null
  onReset: () => void
}) {
  const [builderOpen, setBuilderOpen] = useState(false)
  const verdict = verdictOf(result)
  const v = VERDICT[verdict]
  const Glyph = v.glyph

  useEffect(() => {
    shoppingCheckApi.logEvent(result.check_id, 'verdict_viewed', {
      recommendation: result.buy_recommendation,
      input_type: result.input_type,
    })
  }, [result.check_id, result.buy_recommendation, result.input_type])

  const analysis = result.item_analysis as Record<string, unknown>
  const name = String(analysis.name || analysis.category || 'This item')
  const brand = result.source_brand
  const price = result.source_price
  const subline = [brand, price].filter(Boolean).join(' · ')

  const dupes = result.matched_items.filter(m => m.is_duplicate)
  const pairings = result.matched_items.filter(m => !m.is_duplicate)

  return (
    <div className="space-y-4">
      {/* Verdict header — product, score ring, big badge */}
      <GlassCard className="p-5 space-y-4">
        <div className="flex items-start gap-4">
          <LazyImage
            src={previewUrl}
            alt={name}
            aspect="aspect-square"
            rounded="rounded-2xl"
            wrapperClassName="w-16 h-16 flex-shrink-0 shadow-sm"
            fallback={<ShoppingCart size={22} className="text-slate-300 dark:text-white/20" />}
          />
          <div className="min-w-0 flex-1 pt-0.5">
            <h2 className="text-base font-bold text-slate-900 dark:text-white leading-snug truncate">{name}</h2>
            {subline && <p className="text-sm text-slate-500 dark:text-white/50 truncate">{subline}</p>}
          </div>
        </div>

        <div className="flex flex-col items-center text-center gap-3 pt-1">
          <ScoreRing score={result.buy_score} hex={v.hex} track={v.ringTrack} />
          <div className={cn('inline-flex items-center gap-1.5 px-4 py-1.5 rounded-full text-sm font-extrabold tracking-wide', v.badge)}>
            <Glyph size={16} strokeWidth={3} />
            {v.label}
          </div>
          <p className="text-sm text-slate-600 dark:text-white/65 leading-snug max-w-xs">{v.line}</p>
        </div>

        {result.closet_boost_pct > 0 && (
          <div className="flex items-center gap-2 px-3 py-2 rounded-xl bg-brand-50 dark:bg-brand-900/20 border border-brand-100 dark:border-brand-800/30">
            <TrendingUp size={15} className="text-brand-500 flex-shrink-0" />
            <p className="text-sm text-brand-700 dark:text-brand-400">
              Adds <span className="font-bold">+{result.closet_boost_pct}%</span> to your wardrobe completeness.
            </p>
          </div>
        )}
      </GlassCard>

      {/* FANI's take */}
      <GlassCard className="p-4 space-y-2">
        <div className="flex items-center gap-2">
          <Sparkles size={15} className="text-brand-500" />
          <h3 className="text-sm font-semibold text-slate-800 dark:text-white">FANI's take</h3>
          {result.fani_take?.grounded && (
            <span className="ml-auto inline-flex items-center gap-1 text-[10px] font-semibold px-2 py-0.5 rounded-full bg-brand-50 dark:bg-brand-900/20 text-brand-600 dark:text-brand-400">
              <Sparkles size={9} /> Grounded
            </span>
          )}
        </div>
        <p className="text-sm text-slate-600 dark:text-white/70 leading-relaxed">
          {result.fani_take?.take || result.reasoning}
        </p>
        {result.fani_take?.take && result.reasoning && (
          <p className="text-xs text-slate-400 dark:text-white/40 leading-relaxed">{result.reasoning}</p>
        )}
        {result.fani_take?.cited_titles && result.fani_take.cited_titles.length > 0 && (
          <p className="text-[10px] text-slate-400 dark:text-white/35 leading-tight">
            Grounded in: {result.fani_take.cited_titles.join(' · ')}
          </p>
        )}
      </GlassCard>

      {/* Why this score */}
      <WhyThisScore result={result} pairCount={pairings.length} />

      {/* Source attribution — URL / screenshot checks */}
      {result.source_url && (
        <a
          href={result.source_url}
          target="_blank"
          rel="noopener noreferrer"
          className="flex items-center gap-2 px-3 py-2 rounded-xl text-xs bg-slate-50 dark:bg-white/[0.04] border border-slate-200 dark:border-white/10 text-slate-600 dark:text-white/60 hover:bg-slate-100 dark:hover:bg-white/[0.08] transition-colors"
        >
          <Link2 size={13} className="flex-shrink-0 text-brand-500" />
          <span className="truncate flex-1">
            {result.source_title || result.source_site || result.source_url}
          </span>
          {result.input_type === 'screenshot' && (
            <span className="text-[10px] text-slate-400 dark:text-white/30 flex-shrink-0">via screenshot</span>
          )}
          <ExternalLink size={12} className="flex-shrink-0 text-slate-400" />
        </a>
      )}

      {/* You already own something close (only when there are real dupes) */}
      {dupes.length > 0 && (
        <GlassCard className="p-4 space-y-3 border-red-200/70 dark:border-red-700/30">
          <div className="flex items-center gap-2">
            <Copy size={15} className="text-red-500" />
            <h3 className="text-sm font-semibold text-slate-800 dark:text-white">
              You already own something close
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

      {/* Pairs with N items + Build an outfit */}
      {pairings.length > 0 && (
        <OutfitBuilderSection
          checkId={result.check_id}
          anchorImg={previewUrl}
          pairCount={pairings.length}
          open={builderOpen}
          onOpen={() => setBuilderOpen(true)}
        />
      )}

      {/* Making the call? */}
      <DecisionRow checkId={result.check_id} />

      {/* Repeat-paste nudge */}
      {result.input_type !== 'photo' && (result.url_check_count ?? 0) >= 2 && (
        <p className="text-center text-xs text-slate-400 dark:text-white/35">
          That’s {result.url_check_count} links you’ve run past FANI — it’s learning your taste.
        </p>
      )}

      <button
        onClick={() => { shoppingCheckApi.logEvent(result.check_id, 'paste_again'); onReset() }}
        className="w-full flex items-center justify-center gap-2 py-3 rounded-xl text-sm font-semibold text-brand-600 dark:text-brand-400 hover:bg-brand-50 dark:hover:bg-brand-900/20 border border-brand-200 dark:border-brand-700/40 transition-colors"
      >
        <RotateCcw size={14} />
        Check another item
      </button>
    </div>
  )
}

// ── Loading state — the mockup's "FANI is sizing it up" checklist ─────────────

const LOADING_STEPS = ['Reading the product', 'Matching against your closet', 'Checking for duplicates']

function LoadingView({ previewUrl }: { previewUrl: string | null }) {
  const [step, setStep] = useState(0)
  useEffect(() => {
    const id = setInterval(() => setStep(s => Math.min(s + 1, LOADING_STEPS.length)), 900)
    return () => clearInterval(id)
  }, [])

  return (
    <GlassCard className="p-6 sm:p-8 flex flex-col items-center gap-5 text-center">
      <LazyImage
        src={previewUrl}
        alt="Item being analysed"
        aspect="aspect-square"
        rounded="rounded-2xl"
        wrapperClassName="w-24 h-24"
        eager
        fallback={<Link2 size={26} className="text-slate-300 dark:text-white/20" />}
      />
      <div className="space-y-1">
        <h2 className="text-lg font-bold text-slate-900 dark:text-white">FANI is sizing it up…</h2>
        <p className="text-sm text-slate-500 dark:text-white/50">Comparing against everything in your closet</p>
      </div>
      <div className="w-full max-w-xs space-y-2 text-left">
        {LOADING_STEPS.map((label, i) => {
          const done = i < step
          const active = i === step
          return (
            <div key={label} className="flex items-center gap-2.5">
              <span className={cn(
                'w-5 h-5 rounded-full flex items-center justify-center flex-shrink-0 transition-colors',
                done ? 'bg-emerald-500 text-white' : active ? 'bg-brand-100 dark:bg-brand-900/30' : 'bg-slate-100 dark:bg-white/[0.06]',
              )}>
                {done ? <Check size={12} strokeWidth={3} /> : active ? <Loader2 size={12} className="animate-spin text-brand-500" /> : null}
              </span>
              <span className={cn(
                'text-sm transition-colors',
                done ? 'text-slate-700 dark:text-white/80 font-medium' : active ? 'text-slate-700 dark:text-white/70' : 'text-slate-400 dark:text-white/35',
              )}>
                {label}
              </span>
            </div>
          )
        })}
      </div>
    </GlassCard>
  )
}

// ── Landing hero ──────────────────────────────────────────────────────────────
//
// Layout mirrors the "Shop with FANI" mockup: a camera-first dashed dropzone on
// the left, upload + paste-a-link cards stacked on the right, then the 3-step
// strip. Extras beyond the mockup: drag-and-drop an image onto the hero, and
// paste (⌘V) an image or product URL anywhere on the landing.

function LandingHero({ onFile, onUrl, disabled }: {
  onFile: (f: File) => void
  onUrl: (url: string) => void
  disabled: boolean
}) {
  const cameraRef = useRef<HTMLInputElement>(null)
  const uploadRef = useRef<HTMLInputElement>(null)
  const [url, setUrl] = useState('')
  const [dragging, setDragging] = useState(false)
  const valid = /^https?:\/\/.+\..+/i.test(url.trim())

  const pick = (e: React.ChangeEvent<HTMLInputElement>) => {
    const f = e.target.files?.[0]
    if (f && f.type.startsWith('image/')) onFile(f)
    e.target.value = ''
  }

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault()
    setDragging(false)
    if (disabled) return
    const f = e.dataTransfer.files?.[0]
    if (f && f.type.startsWith('image/')) onFile(f)
  }

  // Paste an image (screenshot) or a product URL anywhere on the landing.
  useEffect(() => {
    const onPaste = (e: ClipboardEvent) => {
      if (disabled) return
      const items = e.clipboardData?.items
      const img = items && Array.from(items).find(i => i.type.startsWith('image/'))
      if (img) {
        const f = img.getAsFile()
        if (f) { e.preventDefault(); onFile(f) }
        return
      }
      // Let text paste into inputs behave normally; elsewhere, catch URLs.
      const target = e.target as HTMLElement | null
      if (target && (target.tagName === 'INPUT' || target.tagName === 'TEXTAREA')) return
      const text = e.clipboardData?.getData('text')?.trim() ?? ''
      if (/^https?:\/\/.+\..+/i.test(text)) setUrl(text)
    }
    window.addEventListener('paste', onPaste)
    return () => window.removeEventListener('paste', onPaste)
  }, [disabled, onFile])

  return (
    <div className="space-y-4 animate-slide-up">
      <input ref={cameraRef} type="file" accept="image/*" capture="environment" className="hidden" onChange={pick} />
      <input ref={uploadRef} type="file" accept="image/*" className="hidden" onChange={pick} />

      <div className="grid md:grid-cols-[1.55fr_1fr] gap-4">
        {/* Camera-first dashed hero / dropzone */}
        <button
          type="button"
          onClick={() => cameraRef.current?.click()}
          disabled={disabled}
          onDragOver={e => { e.preventDefault(); setDragging(true) }}
          onDragLeave={() => setDragging(false)}
          onDrop={handleDrop}
          className={cn(
            'min-h-[280px] md:min-h-[330px] flex flex-col items-center justify-center gap-4 p-8 text-center',
            'rounded-2xl border-2 border-dashed border-cream-300 dark:border-white/15 cursor-pointer',
            'transition-colors duration-200 hover:border-brand-400 hover:bg-brand-50 dark:hover:bg-brand-900/15',
            'focus:outline-none focus-visible:ring-2 focus-visible:ring-brand-400/60 disabled:opacity-60',
            dragging && 'border-brand-400 bg-brand-50 dark:bg-brand-900/15',
          )}
        >
          <span className="w-16 h-16 rounded-[20px] bg-gradient-to-br from-brand-600 to-brand-700 flex items-center justify-center shadow-glow-sm">
            <Camera size={30} className="text-white" />
          </span>
          <span className="block">
            <span className="block font-display font-bold text-lg text-slate-900 dark:text-white">
              Snap it before you buy
            </span>
            <span className="block text-[13px] text-slate-400 dark:text-white/45 max-w-[300px] mt-1.5">
              Point your camera at any store item and FANI scores it against the clothes you already own.
            </span>
          </span>
          <span className="inline-flex items-center gap-2 px-5 py-2.5 rounded-xl text-sm font-semibold text-white bg-gradient-to-r from-brand-600 to-brand-700 shadow-glow-sm hover:shadow-glow-md transition-shadow">
            <Camera size={16} /> Take a photo
          </span>
          <span className="text-[11px] text-slate-400 dark:text-white/30">
            {dragging ? 'Drop it here' : 'JPEG · PNG · WebP — or drop / paste an image'}
          </span>
        </button>

        {/* Upload + Paste a link */}
        <div className="flex flex-col gap-4">
          <GlassCard
            hover
            className="p-[18px] flex flex-col gap-3 flex-1"
            role="button"
            tabIndex={0}
            onClick={() => { if (!disabled) uploadRef.current?.click() }}
            onKeyDown={e => { if ((e.key === 'Enter' || e.key === ' ') && !disabled) { e.preventDefault(); uploadRef.current?.click() } }}
          >
            <div className="flex items-center gap-3">
              <span className="w-10 h-10 rounded-xl bg-brand-50 dark:bg-brand-900/25 text-brand-500 flex items-center justify-center flex-shrink-0">
                <Upload size={20} />
              </span>
              <h3 className="font-display font-bold text-[15px] text-slate-900 dark:text-white">Upload a photo</h3>
            </div>
            <p className="text-xs text-slate-400 dark:text-white/45 leading-relaxed flex-1">
              Already have a screenshot or product pic? Add it from your device.
            </p>
            <span className="w-full inline-flex items-center justify-center gap-2 px-4 py-2.5 rounded-xl text-sm font-semibold text-slate-700 dark:text-white/75 bg-white dark:bg-white/[0.06] border border-cream-300 dark:border-white/10 hover:bg-cream-50 dark:hover:bg-white/10 transition-colors">
              <Upload size={15} /> Browse files
            </span>
          </GlassCard>

          <GlassCard className="p-[18px] flex flex-col gap-3">
            <div className="flex items-center gap-3">
              <span className="w-10 h-10 rounded-xl bg-brand-50 dark:bg-brand-900/25 text-brand-500 flex items-center justify-center flex-shrink-0">
                <Link2 size={20} />
              </span>
              <h3 className="font-display font-bold text-[15px] text-slate-900 dark:text-white">Paste a link</h3>
            </div>
            <p className="text-xs text-slate-400 dark:text-white/45 leading-relaxed">
              Drop a product URL — FANI reads the page for you.
            </p>
            <div className="flex items-center gap-2 px-3 rounded-xl bg-white dark:bg-white/[0.04] border border-cream-300 dark:border-white/10 transition-shadow focus-within:border-brand-400 focus-within:ring-[3px] focus-within:ring-brand-400/20">
              <Link2 size={15} className="text-slate-400 flex-shrink-0" />
              <label htmlFor="shopping-url" className="sr-only">Product link to check</label>
              <input
                id="shopping-url"
                type="url"
                inputMode="url"
                value={url}
                onChange={e => setUrl(e.target.value)}
                onKeyDown={e => { if (e.key === 'Enter' && valid && !disabled) onUrl(url.trim()) }}
                placeholder="https://brand.com/the-jacket…"
                disabled={disabled}
                className="flex-1 min-w-0 py-2.5 bg-transparent text-sm text-slate-800 dark:text-white placeholder:text-slate-400 dark:placeholder:text-white/30 focus:outline-none disabled:opacity-50"
              />
            </div>
            <button
              onClick={() => { if (valid && !disabled) onUrl(url.trim()) }}
              disabled={!valid || disabled}
              className="w-full inline-flex items-center justify-center gap-2 px-4 py-2.5 rounded-xl text-sm font-semibold text-white bg-gradient-to-r from-brand-600 to-brand-700 shadow-glow-sm hover:shadow-glow-md active:scale-[0.97] transition-all disabled:opacity-40 disabled:cursor-not-allowed disabled:shadow-none"
            >
              Check it
            </button>
          </GlassCard>
        </div>
      </div>

      {/* 3-step how it works */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
        {[
          { n: '01', title: 'Snap or paste', desc: 'Any item, any store' },
          { n: '02', title: 'FANI scores it', desc: '0–100 vs your closet' },
          { n: '03', title: 'Decide with proof', desc: 'See what it pairs with' },
        ].map(s => (
          <div key={s.n} className="rounded-2xl bg-white dark:bg-white/[0.04] border border-cream-200 dark:border-white/[0.08] p-4 space-y-0.5">
            <p className="text-[11px] font-bold text-brand-500">{s.n}</p>
            <p className="font-display text-[13.5px] font-bold text-slate-800 dark:text-white leading-tight">{s.title}</p>
            <p className="text-[11.5px] text-slate-400 dark:text-white/45 leading-snug">{s.desc}</p>
          </div>
        ))}
      </div>
    </div>
  )
}

// ── Recent checks ─────────────────────────────────────────────────────────────

function historyCheckId(entry: ShoppingHistoryEntry): string {
  return entry.check_id ?? String((entry as ShoppingHistoryEntry & { id?: string }).id ?? '')
}

function timeAgo(iso: string): string {
  const then = new Date(iso).getTime()
  if (Number.isNaN(then)) return ''
  const mins = Math.round((Date.now() - then) / 60000)
  if (mins < 1) return 'Just now'
  if (mins < 60) return `${mins} min ago`
  const hrs = Math.round(mins / 60)
  if (hrs < 24) return `${hrs}h ago`
  const days = Math.round(hrs / 24)
  return days === 1 ? 'Yesterday' : `${days} days ago`
}

function RecentCheckRow({ entry, onDeleted }: {
  entry: ShoppingHistoryEntry
  onDeleted: (checkId: string) => void
}) {
  const checkId = historyCheckId(entry)
  const [confirming, setConfirming] = useState(false)
  const [deleting, setDeleting] = useState(false)
  const verdict = verdictOf(entry)
  const v = VERDICT[verdict]
  const analysis = entry.item_analysis as Record<string, unknown>
  const name = String(analysis.name || analysis.category || 'Item')

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
        <LazyImage
          src={entry.image_url ? resolveUploadUrl(entry.image_url) : null}
          alt={name}
          aspect="aspect-square"
          rounded="rounded-xl"
          wrapperClassName="w-12 h-12 flex-shrink-0"
          fallback={<Shirt size={18} className="text-slate-300 dark:text-white/20" />}
        />
        <div className="flex-1 min-w-0">
          <p className="text-sm font-semibold text-slate-800 dark:text-white capitalize truncate">{name}</p>
          <p className="text-[11px] text-slate-400 dark:text-white/40">{timeAgo(entry.created_at)}</p>
        </div>
        <div className="flex items-center gap-2 flex-shrink-0">
          <div className="text-right">
            <p className="text-lg font-extrabold tabular-nums leading-none" style={{ color: v.hex }}>
              {Math.round(entry.buy_score)}
            </p>
            <span className={cn('text-[9px] font-bold px-1.5 py-0.5 rounded-full', v.chip)}>{v.label}</span>
          </div>
          {checkId && (
            <button
              type="button"
              onClick={() => setConfirming(c => !c)}
              disabled={deleting}
              title="Delete this check"
              aria-label={`Delete check for ${name}`}
              className={cn(
                'p-2 min-h-[40px] min-w-[40px] flex items-center justify-center rounded-lg transition-all',
                'focus:outline-none focus-visible:ring-2 focus-visible:ring-red-400/60',
                confirming
                  ? 'text-red-500 bg-red-50 dark:bg-red-900/20'
                  : 'text-slate-400 hover:text-red-500 hover:bg-red-50 dark:hover:bg-red-900/20 md:opacity-60 md:group-hover:opacity-100 md:focus-visible:opacity-100',
              )}
            >
              {deleting ? <Loader2 size={14} className="animate-spin" /> : <Trash2 size={14} />}
            </button>
          )}
        </div>
      </div>

      {confirming && (
        <div className="flex items-center justify-between gap-2 px-3 py-2 bg-red-50 dark:bg-red-900/20 border-t border-red-100 dark:border-red-800/40">
          <p className="text-xs text-red-700 dark:text-red-400 font-medium">Remove this check?</p>
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

// ── Main page ─────────────────────────────────────────────────────────────────

export default function ShoppingCheck() {
  const [preview, setPreview] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [result, setResult] = useState<ShoppingCheckResult | null>(null)

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

  // Revoke stale object URLs when the preview changes or the page unmounts.
  useEffect(() => () => {
    if (preview?.startsWith('blob:')) URL.revokeObjectURL(preview)
  }, [preview])

  const handleFile = async (file: File) => {
    setPreview(URL.createObjectURL(file))
    setResult(null)
    setError(null)
    setLoading(true)
    window.scrollTo({ top: 0, behavior: 'smooth' })
    try {
      const res = await shoppingCheckApi.checkItem(file)
      setResult(res)
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
    window.scrollTo({ top: 0, behavior: 'smooth' })
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

  const idle = !result && !loading && !error

  return (
    <Container size="md" className="space-y-5">
      <BackButton fallback="/dashboard" label="Back to Dashboard" />

      <PageHeader
        icon={<ShoppingCart size={18} />}
        chipClassName="bg-gradient-to-br from-green-500 to-emerald-600 shadow-glow-sm"
        iconColor="text-white"
        title="Shop with FANI"
        subtitle="Should it earn a spot in your closet? Ask before you buy — snap, upload or paste a link and FANI scores it 0–100 against everything you already own."
        actions={
          <Link
            to="/closet-match"
            className="flex-shrink-0 flex items-center gap-1.5 px-3.5 py-2 rounded-xl text-xs font-semibold bg-brand-50 dark:bg-brand-900/20 text-brand-700 dark:text-brand-400 border border-brand-100 dark:border-brand-700/40 hover:bg-brand-100 dark:hover:bg-brand-900/40 transition-colors whitespace-nowrap"
          >
            <Shirt size={13} />
            Fit Match
          </Link>
        }
      />

      {idle && <LandingHero onFile={handleFile} onUrl={handleUrl} disabled={loading} />}

      {loading && (
        <div className="max-w-2xl mx-auto animate-slide-up">
          <LoadingView previewUrl={preview} />
        </div>
      )}

      {error && (
        <GlassCard className="max-w-2xl mx-auto p-5 space-y-3 animate-slide-up">
          <div className="flex items-center gap-2 text-red-600 dark:text-red-400">
            <AlertCircle size={18} />
            <p className="text-sm font-medium">{error}</p>
          </div>
          <button onClick={reset} className="text-sm text-brand-600 dark:text-brand-400 hover:underline">
            Try again
          </button>
        </GlassCard>
      )}

      {result && (
        <div className="max-w-2xl mx-auto animate-slide-up">
          <ResultView result={result} previewUrl={preview} onReset={reset} />
        </div>
      )}

      {/* Recent checks */}
      {!loading && !result && (
        <div className="space-y-3">
          <div className="flex items-center justify-between">
            <h2 className="text-sm font-semibold text-slate-700 dark:text-white/70">Recent checks</h2>
            {historyLoading && <Loader2 size={14} className="animate-spin text-slate-400" />}
          </div>
          {history && history.length === 0 && (
            <p className="text-sm text-slate-400 dark:text-white/30 text-center py-4">
              No checks yet — snap or paste your first item above.
            </p>
          )}
          {history && history.map(entry => (
            <RecentCheckRow
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
