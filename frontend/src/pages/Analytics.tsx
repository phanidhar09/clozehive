import { useEffect, useMemo, useState } from 'react'
import {
  BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer,
  PieChart, Pie, Cell,
} from 'recharts'
import {
  TrendingUp, Shirt, Star, BarChart3, ShoppingBag,
  AlertTriangle, Palette, Layers, Sparkles,
  DollarSign, Recycle, Clock, Repeat, PiggyBank,
} from 'lucide-react'
import { useApp } from '@/store'
import Badge from '@/components/ui/Badge'
import GlassCard from '@/components/ui/GlassCard'
import EmptyState from '@/components/ui/EmptyState'
import PageHeader from '@/components/ui/PageHeader'
import SectionHeader from '@/components/ui/SectionHeader'
import { FaniLoader } from '@/components/system/FaniLoader'
import { analyticsApi } from '@/lib/api'
import { useAsyncError } from '@/hooks/useAsyncError'
import type {
  ClosetAnalytics, CategoryCoverageItem, ColorStats, PurchaseGapInsight,
  CostPerWearItem, ForgottenGem, VersatilityItem,
} from '@/types'

/** Compact currency — no decimals for round-ish totals, 2dp for per-wear figures. */
function money(n: number, dp = 0): string {
  return `$${n.toLocaleString(undefined, { minimumFractionDigits: dp, maximumFractionDigits: dp })}`
}

type TooltipChartPayload = {
  active?: boolean
  payload?: Array<{ value?: number; name?: string }>
  label?: string
}

const CustomTooltip = ({ active, payload, label }: TooltipChartPayload) => {
  if (active && payload?.length) {
    return (
      <div className="bg-white/95 dark:bg-slate-800/95 backdrop-blur border border-cream-300 dark:border-slate-700 rounded-xl px-3 py-2 shadow-card-hover text-sm">
        <p className="font-semibold text-slate-700 dark:text-slate-200 mb-0.5 capitalize">{label ?? payload[0].name}</p>
        <p className="text-brand-600 dark:text-brand-400 font-bold">{payload[0].value} items</p>
      </div>
    )
  }
  return null
}

const PALETTE = ['#0D9488', '#059669', '#14B8A6', '#2DD4BF', '#5EEAD4', '#99F6E4']

/** Common fashion color names → exact hex, so the chart references the real colour. */
const COLOR_HEX: Record<string, string> = {
  black: '#111827', white: '#F9FAFB', grey: '#9CA3AF', gray: '#9CA3AF',
  silver: '#C0C0C0', charcoal: '#374151', navy: '#1E3A5F', blue: '#3B82F6',
  'light blue': '#7DD3FC', 'sky blue': '#7DD3FC', teal: '#14B8A6', cyan: '#06B6D4',
  green: '#22C55E', olive: '#708238', mint: '#A7F3D0', red: '#EF4444',
  maroon: '#7F1D1D', burgundy: '#7F1D1D', pink: '#EC4899', purple: '#A855F7',
  lavender: '#C4B5FD', orange: '#F97316', yellow: '#FACC15', gold: '#D4AF37',
  brown: '#8B5E3C', tan: '#D2B48C', beige: '#E8D9C0', cream: '#F5EFE0',
  khaki: '#C3B091', denim: '#3B5A78', multicolor: '#94A3B8', multi: '#94A3B8',
}

/** Resolve a stored color string to an exact CSS color; fall back to the palette. */
function colorToCss(raw: string | undefined, index: number): string {
  const c = (raw || '').trim().toLowerCase()
  if (!c) return PALETTE[index % PALETTE.length]
  if (/^#([0-9a-f]{3}|[0-9a-f]{6})$/i.test(c)) return c           // hex passthrough
  if (c in COLOR_HEX) return COLOR_HEX[c]                          // known fashion name
  if (/^[a-z]+$/.test(c)) return c                                // plain CSS color name
  return PALETTE[index % PALETTE.length]
}

/* ── Wardrobe health score ring ─────────────────────────────────────────────── */
function ScoreRing({ value, size = 132, stroke = 11 }: { value: number; size?: number; stroke?: number }) {
  const radius = (size - stroke) / 2
  const circ = 2 * Math.PI * radius
  const offset = circ - (Math.min(Math.max(value, 0), 100) / 100) * circ
  return (
    <div className="relative" style={{ width: size, height: size }}>
      <svg width={size} height={size} className="-rotate-90">
        <circle
          cx={size / 2} cy={size / 2} r={radius} fill="none"
          strokeWidth={stroke}
          className="stroke-slate-200/80 dark:stroke-white/10"
        />
        <circle
          cx={size / 2} cy={size / 2} r={radius} fill="none"
          stroke="url(#scoreGrad)" strokeWidth={stroke} strokeLinecap="round"
          strokeDasharray={circ} strokeDashoffset={offset}
          style={{ transition: 'stroke-dashoffset 0.8s cubic-bezier(0.16,1,0.3,1)' }}
        />
        <defs>
          <linearGradient id="scoreGrad" x1="0%" y1="0%" x2="100%" y2="100%">
            <stop offset="0%" stopColor="#14B8A6" />
            <stop offset="100%" stopColor="#059669" />
          </linearGradient>
        </defs>
      </svg>
      <div className="absolute inset-0 flex flex-col items-center justify-center">
        <span className="text-3xl font-bold text-slate-800 dark:text-white leading-none">{value}</span>
        <span className="text-[10px] font-semibold text-slate-400 dark:text-white/40 uppercase tracking-wider mt-1">/ 100</span>
      </div>
    </div>
  )
}

/* ── Premium stat tile ──────────────────────────────────────────────────────── */
function StatTile({
  icon, label, value, accent = 'text-brand-500', chipBg = 'bg-brand-50 dark:bg-brand-500/10',
  swatch,
}: {
  icon: React.ReactNode
  label: string
  value: string
  accent?: string
  chipBg?: string
  swatch?: string
}) {
  return (
    <GlassCard padding="md" className="flex items-center gap-3.5">
      <div className={`shrink-0 w-11 h-11 rounded-xl flex items-center justify-center ${chipBg} ${accent}`}>
        {swatch
          ? <span className="w-5 h-5 rounded-full ring-2 ring-white/70 dark:ring-white/20" style={{ backgroundColor: swatch }} />
          : icon}
      </div>
      <div className="min-w-0">
        <p className="text-[11px] font-semibold text-slate-400 dark:text-white/40 uppercase tracking-wider">{label}</p>
        <p className="text-lg font-bold text-slate-800 dark:text-white capitalize truncate leading-tight mt-0.5">{value}</p>
      </div>
    </GlassCard>
  )
}

export default function Analytics() {
  const { closetItems, closetLoading } = useApp()
  const throwAsyncError = useAsyncError()
  const [analytics, setAnalytics] = useState<ClosetAnalytics | null>(null)
  const [loading, setLoading] = useState(false)
  const [isMobile, setIsMobile] = useState(() => window.innerWidth < 640)

  useEffect(() => {
    const media = window.matchMedia('(max-width: 639px)')
    const handler = (event: MediaQueryListEvent) => setIsMobile(event.matches)
    setIsMobile(media.matches)
    media.addEventListener('change', handler)
    return () => media.removeEventListener('change', handler)
  }, [])

  useEffect(() => {
    const loadAnalytics = async () => {
      if (closetItems.length === 0) return
      setLoading(true)
      try {
        const data = await analyticsApi.getClosetAnalytics()
        setAnalytics(data)
      } catch (err) {
        setAnalytics(null)
        throwAsyncError(err instanceof Error ? err : new Error('Failed to load analytics'))
      } finally {
        setLoading(false)
      }
    }
    loadAnalytics()
  }, [closetItems.length, throwAsyncError])

  /* Resolve item thumbnails from the already-loaded (signed) closet store by id,
     so analytics never has to re-sign image URLs. */
  const imageById = useMemo(() => {
    const m = new Map<string, string | undefined>()
    for (const it of closetItems) m.set(it.id, it.image_url ?? undefined)
    return m
  }, [closetItems])

  /* Wardrobe health score — avg coverage across categories, capped per category at 100% */
  const score = useMemo(() => {
    const cov = analytics?.category_coverage ?? []
    if (cov.length === 0) return 0
    const total = cov.reduce((sum, c) => sum + Math.min(c.count / Math.max(c.recommended_minimum, 1), 1), 0)
    return Math.round((total / cov.length) * 100)
  }, [analytics])

  const scoreLabel = score >= 80 ? 'Excellent' : score >= 60 ? 'Versatile' : score >= 40 ? 'Developing' : 'Getting started'
  const scoreBlurb =
    score >= 80 ? 'Your wardrobe covers nearly every essential. Great range to style from.'
    : score >= 60 ? 'A solid, versatile wardrobe. A few targeted pieces would round it out.'
    : score >= 40 ? 'Good foundation — fill the gaps below to unlock more outfits.'
    : 'Add more essentials to start building a flexible wardrobe.'

  if (closetLoading && closetItems.length === 0) {
    return (
      <div className="flex items-center justify-center h-64">
        <FaniLoader size="md" messages={['Loading closet data…']} />
      </div>
    )
  }

  if (closetItems.length === 0) {
    return (
      <EmptyState
        icon={<BarChart3 />}
        title="No insights yet"
        description="Add clothing items to your closet to unlock wear analytics, category breakdowns, and style trends."
        primaryAction={{ label: 'Add to Your Closet', href: '/upload' }}
        secondaryAction={{ label: 'View My Closet', href: '/closet' }}
        variant="card"
      />
    )
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <FaniLoader size="md" messages={['Analyzing your closet…']} />
      </div>
    )
  }

  if (!analytics) return null

  const value = analytics.value_insights

  /* Thumbnail resolved from the closet store; falls back to a shirt glyph. */
  const thumb = (id: string, name: string) => {
    const src = imageById.get(id)
    return src
      ? <img src={src} alt={name} loading="lazy" decoding="async" className="w-10 h-10 rounded-lg object-cover shrink-0 ring-1 ring-black/5 dark:ring-white/10" />
      : (
        <div className="w-10 h-10 rounded-lg bg-slate-100 dark:bg-white/10 flex items-center justify-center shrink-0">
          <Shirt size={16} className="text-slate-300 dark:text-white/30" />
        </div>
      )
  }

  return (
    <div className="space-y-8 max-w-6xl mx-auto">
      {/* ── Header ───────────────────────────────────────────────────────────── */}
      <PageHeader
        icon={<BarChart3 size={18} />}
        title="Closet Insights"
        subtitle="A clear read on your wardrobe — coverage, color balance, and where to invest next."
      />

      {/* ── Hero: Health score + key stats ───────────────────────────────────── */}
      <div className="grid lg:grid-cols-3 gap-4">
        {/* Score ring — premium centerpiece */}
        <GlassCard padding="lg" className="lg:col-span-1 flex items-center gap-5 bg-gradient-to-br from-brand-50/60 to-transparent dark:from-brand-500/[0.06]">
          <ScoreRing value={score} />
          <div className="min-w-0">
            <p className="text-[11px] font-semibold text-brand-600 dark:text-brand-400 uppercase tracking-wider flex items-center gap-1">
              <Sparkles size={12} /> Wardrobe Score
            </p>
            <p className="text-xl font-bold text-slate-800 dark:text-white mt-1">{scoreLabel}</p>
            <p className="text-xs text-slate-500 dark:text-white/50 mt-1.5 leading-snug">{scoreBlurb}</p>
          </div>
        </GlassCard>

        {/* Key stats — 2x2 */}
        <div className="lg:col-span-2 grid grid-cols-2 gap-4">
          <StatTile
            icon={<Shirt size={18} />}
            label="Total Items"
            value={String(analytics.summary.total_items)}
          />
          <StatTile
            icon={<TrendingUp size={18} />}
            label="Top Category"
            value={analytics.summary.strongest_category || '—'}
          />
          <StatTile
            icon={<Palette size={18} />}
            label="Top Color"
            value={analytics.summary.most_common_color || '—'}
            swatch={analytics.summary.most_common_color || undefined}
          />
          <StatTile
            icon={<Star size={18} />}
            label="Best Occasion"
            value={analytics.summary.best_covered_occasion || '—'}
            accent="text-amber-500"
            chipBg="bg-amber-50 dark:bg-amber-500/10"
          />
        </div>
      </div>

      {/* ── Category Coverage ───────────────────────────────────────────────── */}
      <section>
        <SectionHeader icon={<Layers size={16} />} title="Category Coverage" />
        <GlassCard padding="lg" className="divide-y divide-cream-200/70 dark:divide-white/[0.06]">
          {analytics.category_coverage.map((cat: CategoryCoverageItem, i: number) => {
            const percentage = Math.min((cat.count / Math.max(cat.recommended_minimum, 1)) * 100, 100)
            const barColor = cat.status === 'good' ? 'bg-emerald-500' : cat.status === 'low' ? 'bg-amber-500' : 'bg-rose-500'
            const badgeVariant = cat.status === 'good' ? 'green' : cat.status === 'low' ? 'amber' : 'red'
            return (
              <div key={cat.category} className={`flex items-center gap-4 ${i === 0 ? 'pb-3.5' : 'py-3.5'} ${i === analytics.category_coverage.length - 1 ? 'pb-0' : ''}`}>
                <div className="w-28 sm:w-32 shrink-0">
                  <p className="font-semibold text-sm text-slate-800 dark:text-white capitalize">{cat.category}</p>
                  <p className="text-[11px] text-slate-400 dark:text-white/40">{cat.count} / {cat.recommended_minimum}</p>
                </div>
                <div className="flex-1 h-2 rounded-full bg-slate-100 dark:bg-white/10 overflow-hidden">
                  <div
                    className={`h-full rounded-full ${barColor}`}
                    style={{ width: `${percentage}%`, transition: 'width 0.7s cubic-bezier(0.16,1,0.3,1)' }}
                  />
                </div>
                <Badge variant={badgeVariant} >{cat.status}</Badge>
              </div>
            )
          })}
        </GlassCard>
      </section>

      {/* ── Color + Category charts ─────────────────────────────────────────── */}
      <div className="grid lg:grid-cols-2 gap-4">
        {/* Color distribution */}
        {analytics.color_stats.length > 0 && (
          <section>
            <SectionHeader icon={<Palette size={16} />} title="Color Distribution" />
            <GlassCard padding="lg">
              <div className="flex flex-col sm:flex-row items-center gap-5">
                <div className="h-44 w-44 shrink-0">
                  <ResponsiveContainer width="100%" height="100%">
                    <PieChart>
                      <Pie
                        data={analytics.color_stats}
                        cx="50%" cy="50%"
                        labelLine={false}
                        label={isMobile ? false : ({ percentage }) => `${percentage}%`}
                        innerRadius={42}
                        outerRadius={72}
                        paddingAngle={2}
                        dataKey="percentage"
                        stroke="#ffffff"
                        strokeWidth={1}
                      >
                        {analytics.color_stats.map((entry: ColorStats, index: number) => (
                          <Cell key={`cell-${index}`} fill={colorToCss(entry.color, index)} />
                        ))}
                      </Pie>
                      <Tooltip />
                    </PieChart>
                  </ResponsiveContainer>
                </div>
                <div className="flex-1 w-full space-y-2.5">
                  {analytics.color_stats.slice(0, 6).map((stat: ColorStats, i: number) => {
                    const css = colorToCss(stat.color, i)
                    return (
                      <div key={stat.color} className="flex items-center justify-between text-sm">
                        <div className="flex items-center gap-2 min-w-0">
                          <span
                            className="w-3.5 h-3.5 rounded-full shrink-0 ring-1 ring-black/10 dark:ring-white/15"
                            style={{ backgroundColor: css }}
                          />
                          <span className="capitalize text-slate-700 dark:text-white/90 truncate">{stat.color}</span>
                        </div>
                        <span className="text-slate-400 dark:text-white/40 tabular-nums shrink-0">{stat.count} · {stat.percentage}%</span>
                      </div>
                    )
                  })}
                </div>
              </div>
            </GlassCard>
          </section>
        )}

        {/* Category breakdown bar */}
        {analytics.category_stats.length > 0 && (
          <section>
            <SectionHeader icon={<Layers size={16} />} title="Category Breakdown" />
            <GlassCard padding="lg">
              <div className="h-44">
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={analytics.category_stats} margin={{ top: 4, right: 4, left: -24, bottom: 0 }}>
                    <XAxis
                      dataKey="category"
                      tick={{ fontSize: 11, fill: 'currentColor' }}
                      className="text-slate-400 dark:text-white/40"
                      axisLine={false} tickLine={false}
                    />
                    <YAxis
                      tick={{ fontSize: 11, fill: 'currentColor' }}
                      className="text-slate-400 dark:text-white/40"
                      axisLine={false} tickLine={false} allowDecimals={false}
                    />
                    <Tooltip content={<CustomTooltip />} cursor={{ fill: 'rgba(13,148,136,0.06)' }} />
                    <Bar dataKey="count" fill="#0D9488" radius={[6, 6, 0, 0]} maxBarSize={44} />
                  </BarChart>
                </ResponsiveContainer>
              </div>
            </GlassCard>
          </section>
        )}
      </div>

      {/* ── Outfit Readiness ────────────────────────────────────────────────── */}
      <section>
        <SectionHeader icon={<Star size={16} className="text-amber-500" />} title="Outfit Readiness" />
        <GlassCard padding="lg">
          <div className="grid sm:grid-cols-2 gap-6 items-center">
            <div className="flex items-center gap-4">
              <div className="text-5xl font-bold text-transparent bg-clip-text bg-gradient-to-br from-brand-500 to-brand-700">
                {analytics.outfit_readiness.estimated_outfits}
              </div>
              <p className="text-sm text-slate-600 dark:text-white/60 leading-snug">
                estimated unique<br />outfits you can style
              </p>
            </div>
            <div className="sm:border-l sm:border-cream-200/70 dark:sm:border-white/[0.06] sm:pl-6">
              <p className="text-[11px] font-semibold text-slate-400 dark:text-white/40 uppercase tracking-wider mb-2.5">Best Covered Occasions</p>
              <div className="flex flex-wrap gap-1.5">
                {analytics.outfit_readiness.best_covered_occasions.length > 0
                  ? analytics.outfit_readiness.best_covered_occasions.map(occ => (
                      <Badge key={occ} variant="teal">{occ}</Badge>
                    ))
                  : <span className="text-sm text-slate-400">—</span>}
              </div>
            </div>
          </div>
        </GlassCard>
      </section>

      {/* ── Value & Usage (cost-per-wear, utilization, forgotten gems) ──────── */}
      {value && (
        <section className="space-y-4">
          <SectionHeader icon={<PiggyBank size={16} className="text-emerald-500" />} title="Value & Usage" />

          {/* Headline stats */}
          <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
            <StatTile
              icon={<Recycle size={18} />}
              label="Closet Used"
              value={`${value.utilization_rate}%`}
              accent="text-emerald-500"
              chipBg="bg-emerald-50 dark:bg-emerald-500/10"
            />
            <StatTile
              icon={<Clock size={18} />}
              label="Worn (90 days)"
              value={`${value.active_rate_90d}%`}
              accent="text-sky-500"
              chipBg="bg-sky-50 dark:bg-sky-500/10"
            />
            <StatTile
              icon={<DollarSign size={18} />}
              label="Avg Cost / Wear"
              value={value.avg_cost_per_wear != null ? money(value.avg_cost_per_wear, 2) : '—'}
            />
            <StatTile
              icon={<PiggyBank size={18} />}
              label="Value Unworn"
              value={value.items_priced > 0 ? money(value.value_unworn) : '—'}
              accent="text-rose-500"
              chipBg="bg-rose-50 dark:bg-rose-500/10"
            />
          </div>

          {/* Cost-per-wear leaderboards */}
          {(value.best_value_items.length > 0 || value.worst_value_items.length > 0) && (
            <div className="grid lg:grid-cols-2 gap-4">
              {value.best_value_items.length > 0 && (
                <GlassCard padding="lg">
                  <p className="text-[11px] font-semibold text-emerald-600 dark:text-emerald-400 uppercase tracking-wider mb-3 flex items-center gap-1.5">
                    <TrendingUp size={13} /> Best Value · lowest cost-per-wear
                  </p>
                  <div className="space-y-2.5">
                    {value.best_value_items.map((it: CostPerWearItem) => (
                      <div key={it.item_id} className="flex items-center gap-3">
                        {thumb(it.item_id, it.name)}
                        <div className="min-w-0 flex-1">
                          <p className="text-sm font-medium text-slate-800 dark:text-white truncate">{it.name}</p>
                          <p className="text-[11px] text-slate-400 dark:text-white/40">worn {it.wear_count}× · {money(it.price)}</p>
                        </div>
                        <span className="text-sm font-bold text-emerald-600 dark:text-emerald-400 tabular-nums shrink-0">{money(it.cost_per_wear, 2)}<span className="text-[10px] font-normal text-slate-400">/wear</span></span>
                      </div>
                    ))}
                  </div>
                </GlassCard>
              )}
              {value.worst_value_items.length > 0 && (
                <GlassCard padding="lg">
                  <p className="text-[11px] font-semibold text-amber-600 dark:text-amber-400 uppercase tracking-wider mb-3 flex items-center gap-1.5">
                    <AlertTriangle size={13} /> Earn Their Keep · highest cost-per-wear
                  </p>
                  <div className="space-y-2.5">
                    {value.worst_value_items.map((it: CostPerWearItem) => (
                      <div key={it.item_id} className="flex items-center gap-3">
                        {thumb(it.item_id, it.name)}
                        <div className="min-w-0 flex-1">
                          <p className="text-sm font-medium text-slate-800 dark:text-white truncate">{it.name}</p>
                          <p className="text-[11px] text-slate-400 dark:text-white/40">worn {it.wear_count}× · {money(it.price)}</p>
                        </div>
                        <span className="text-sm font-bold text-amber-600 dark:text-amber-400 tabular-nums shrink-0">{money(it.cost_per_wear, 2)}<span className="text-[10px] font-normal text-slate-400">/wear</span></span>
                      </div>
                    ))}
                  </div>
                </GlassCard>
              )}
            </div>
          )}

          {/* Forgotten gems + Most versatile */}
          <div className="grid lg:grid-cols-2 gap-4">
            {value.forgotten_gems.length > 0 && (
              <GlassCard padding="lg">
                <p className="text-[11px] font-semibold text-slate-500 dark:text-white/50 uppercase tracking-wider mb-3 flex items-center gap-1.5">
                  <Clock size={13} /> Forgotten Gems · time to bring these back
                </p>
                <div className="space-y-2.5">
                  {value.forgotten_gems.map((g: ForgottenGem) => (
                    <div key={g.item_id} className="flex items-center gap-3">
                      {thumb(g.item_id, g.name)}
                      <div className="min-w-0 flex-1">
                        <p className="text-sm font-medium text-slate-800 dark:text-white truncate">{g.name}</p>
                        <p className="text-[11px] text-slate-400 dark:text-white/40 capitalize">{g.category}</p>
                      </div>
                      <Badge variant={g.wear_count === 0 ? 'red' : 'amber'}>
                        {g.wear_count === 0 ? 'never worn' : `${g.days_since_worn}d ago`}
                      </Badge>
                    </div>
                  ))}
                </div>
              </GlassCard>
            )}
            {value.most_versatile.length > 0 && (
              <GlassCard padding="lg">
                <p className="text-[11px] font-semibold text-slate-500 dark:text-white/50 uppercase tracking-wider mb-3 flex items-center gap-1.5">
                  <Repeat size={13} /> Most Versatile · powers the most outfits
                </p>
                <div className="space-y-2.5">
                  {value.most_versatile.map((it: VersatilityItem) => (
                    <div key={it.item_id} className="flex items-center gap-3">
                      {thumb(it.item_id, it.name)}
                      <div className="min-w-0 flex-1">
                        <p className="text-sm font-medium text-slate-800 dark:text-white truncate">{it.name}</p>
                        <p className="text-[11px] text-slate-400 dark:text-white/40 capitalize">{it.category}</p>
                      </div>
                      <span className="text-sm font-bold text-brand-600 dark:text-brand-400 tabular-nums shrink-0">
                        {it.outfit_count}<span className="text-[10px] font-normal text-slate-400 ml-0.5">outfits</span>
                      </span>
                    </div>
                  ))}
                </div>
              </GlassCard>
            )}
          </div>

          {value.items_priced === 0 && (
            <p className="text-xs text-slate-400 dark:text-white/40 flex items-center gap-1.5">
              <DollarSign size={12} /> Add prices to your items (or paste a product URL) to unlock cost-per-wear and value insights.
            </p>
          )}
        </section>
      )}

      {/* ── AI Purchase Gap Insights (RAG) ──────────────────────────────────── */}
      {(analytics.purchase_gap_insights ?? []).length > 0 && (
        <section>
          <div className="flex items-center gap-2 mb-2">
            <ShoppingBag size={16} className="text-rose-500" />
            <h3 className="font-semibold text-slate-800 dark:text-white">Wardrobe Gaps</h3>
            <span className="text-[10px] font-semibold text-brand-600 dark:text-brand-400 bg-brand-50 dark:bg-brand-900/30 px-2 py-0.5 rounded-full">
              AI · Vector Search
            </span>
          </div>
          <p className="text-xs text-slate-500 dark:text-white/40 mb-4">
            FANI analysed your wardrobe semantically and flagged these missing pieces.
          </p>
          <div className="grid sm:grid-cols-2 gap-3">
            {(analytics.purchase_gap_insights ?? []).map((gap: PurchaseGapInsight, i: number) => {
              const high = gap.priority_score >= 0.8
              const med = gap.priority_score >= 0.6
              return (
                <GlassCard key={i} padding="md" hover className="flex items-start gap-3">
                  <div className={`mt-0.5 shrink-0 w-8 h-8 rounded-lg flex items-center justify-center ${high ? 'bg-rose-50 dark:bg-rose-500/10' : med ? 'bg-amber-50 dark:bg-amber-500/10' : 'bg-slate-100 dark:bg-white/5'}`}>
                    <AlertTriangle size={15} className={high ? 'text-rose-500' : med ? 'text-amber-500' : 'text-slate-400'} />
                  </div>
                  <div className="min-w-0 flex-1">
                    <p className="font-semibold text-slate-800 dark:text-white capitalize text-sm">
                      {gap.missing_category}
                      <span className="ml-2 text-xs text-slate-400 capitalize font-normal">({gap.gap_type.replace('_', ' ')})</span>
                    </p>
                    <p className="text-xs text-slate-500 dark:text-white/50 mt-1 leading-snug">{gap.reason}</p>
                    {gap.suggested_attributes && Object.keys(gap.suggested_attributes).length > 0 && (
                      <div className="flex flex-wrap gap-1 mt-2">
                        {Object.entries(gap.suggested_attributes).map(([k, v]) => (
                          <span key={k} className="text-[10px] bg-slate-100 dark:bg-white/10 text-slate-600 dark:text-white/60 rounded px-1.5 py-0.5 capitalize">
                            {k}: {v}
                          </span>
                        ))}
                      </div>
                    )}
                  </div>
                  <div className="shrink-0 text-right">
                    <span className="text-sm font-bold text-slate-700 dark:text-white/80">
                      {Math.round(gap.priority_score * 100)}%
                    </span>
                    <p className="text-[10px] text-slate-400 dark:text-white/30">priority</p>
                  </div>
                </GlassCard>
              )
            })}
          </div>
        </section>
      )}
    </div>
  )
}
