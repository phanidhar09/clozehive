import { useEffect, useState } from 'react'
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
  PieChart, Pie, Cell,
} from 'recharts'
import { TrendingUp, Shirt, Star, Loader2, BarChart3 } from 'lucide-react'
import { useApp } from '@/store'
import Badge from '@/components/ui/Badge'
import GlassCard from '@/components/ui/GlassCard'
import { analyticsApi } from '@/lib/api'
import { useAsyncError } from '@/hooks/useAsyncError'
import type { ClosetAnalytics, CategoryCoverageItem, ColorStats } from '@/types'

type TooltipChartPayload = {
  active?: boolean
  payload?: Array<{ value?: number }>
  label?: string
}

const CustomTooltip = ({ active, payload, label }: TooltipChartPayload) => {
  if (active && payload?.length) {
    return (
      <div className="bg-white dark:bg-slate-800 border border-cream-300 dark:border-slate-700 rounded-xl p-3 shadow-card text-sm">
        <p className="font-semibold text-slate-700 dark:text-slate-200 mb-1">{label}</p>
        <p className="text-brand-600 font-bold">{payload[0].value}</p>
      </div>
    )
  }
  return null
}

const PALETTE = ['#534AB7', '#7670F1', '#A78BFA', '#C4B5FD', '#DDD6FE', '#EDE9FE']

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

  if (closetLoading && closetItems.length === 0) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="text-center space-y-3">
          <Loader2 size={32} className="animate-spin text-brand-500 mx-auto" />
          <p className="text-slate-500 dark:text-slate-400 text-sm">Loading closet data…</p>
        </div>
      </div>
    )
  }

  if (closetItems.length === 0) {
    return (
      <div className="text-center py-12 space-y-3">
        <Shirt size={40} className="text-slate-300 dark:text-white/20 mx-auto" />
        <h3 className="font-semibold text-slate-700 dark:text-white">Your closet is empty</h3>
        <p className="text-sm text-slate-500 dark:text-white/40">Add items to see closet insights and analytics</p>
      </div>
    )
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="text-center space-y-3">
          <Loader2 size={32} className="animate-spin text-brand-500 mx-auto" />
          <p className="text-slate-500 dark:text-slate-400 text-sm">Analyzing your closet…</p>
        </div>
      </div>
    )
  }

  if (!analytics) return null

  return (
    <div className="space-y-6 max-w-6xl">
      <div>
        <h2 className="font-display font-bold text-xl text-slate-800 dark:text-slate-100 flex items-center gap-2">
          <BarChart3 size={20} className="text-brand-500" /> Closet Insights
        </h2>
        <p className="text-sm text-slate-400 mt-0.5">
          Analyze your wardrobe and discover gaps in your collection
        </p>
      </div>

      {/* ── Summary Stats ───────────────────────────────────────────────────── */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        <GlassCard padding="md">
          <div className="flex items-center gap-2 mb-2">
            <Shirt size={14} className="text-brand-500" />
            <span className="text-xs font-semibold text-slate-500 dark:text-white/40 uppercase tracking-wider">Total Items</span>
          </div>
          <p className="text-2xl font-bold text-slate-800 dark:text-white">{analytics.summary.total_items}</p>
        </GlassCard>

        <GlassCard padding="md">
          <div className="flex items-center gap-2 mb-2">
            <TrendingUp size={14} className="text-violet-500" />
            <span className="text-xs font-semibold text-slate-500 dark:text-white/40 uppercase tracking-wider">Top Category</span>
          </div>
          <p className="text-lg font-bold text-slate-800 dark:text-white capitalize">{analytics.summary.strongest_category || '—'}</p>
        </GlassCard>

        <GlassCard padding="md">
          <div className="flex items-center gap-2 mb-2">
            <div className="w-3 h-3 rounded-full" style={{ backgroundColor: analytics.summary.most_common_color || '#999' }} />
            <span className="text-xs font-semibold text-slate-500 dark:text-white/40 uppercase tracking-wider">Top Color</span>
          </div>
          <p className="text-lg font-bold text-slate-800 dark:text-white capitalize">{analytics.summary.most_common_color || '—'}</p>
        </GlassCard>

        <GlassCard padding="md">
          <div className="flex items-center gap-2 mb-2">
            <Star size={14} className="text-amber-500" />
            <span className="text-xs font-semibold text-slate-500 dark:text-white/40 uppercase tracking-wider">Best Occasion</span>
          </div>
          <p className="text-lg font-bold text-slate-800 dark:text-white capitalize">{analytics.summary.best_covered_occasion || '—'}</p>
        </GlassCard>
      </div>

      {/* ── Category Coverage ───────────────────────────────────────────────── */}
      <div>
        <h3 className="font-semibold text-slate-800 dark:text-white mb-3">Category Coverage</h3>
        <div className="grid gap-3">
          {analytics.category_coverage.map((cat: CategoryCoverageItem) => {
            const percentage = (cat.count / cat.recommended_minimum) * 100
            const statusColor = cat.status === 'good' ? 'bg-emerald-500' : cat.status === 'low' ? 'bg-amber-500' : 'bg-red-500'
            const badgeVariant = cat.status === 'good' ? 'green' : cat.status === 'low' ? 'amber' : 'red'
            return (
              <GlassCard key={cat.category} padding="md">
                <div className="flex items-center justify-between mb-2">
                  <div>
                    <p className="font-semibold text-slate-800 dark:text-white capitalize">{cat.category}</p>
                    <p className="text-xs text-slate-500 dark:text-white/40">{cat.count} items (recommended: {cat.recommended_minimum})</p>
                  </div>
                  <Badge variant={badgeVariant}>
                    {cat.status}
                  </Badge>
                </div>
                <div className="w-full h-2 rounded-full bg-slate-200 dark:bg-white/10 overflow-hidden">
                  <div
                    className={`h-full ${statusColor} transition-all duration-300`}
                    style={{ width: `${Math.min(percentage, 100)}%` }}
                  />
                </div>
              </GlassCard>
            )
          })}
        </div>
      </div>

      {/* ── Color Distribution ──────────────────────────────────────────────── */}
      {analytics.color_stats.length > 0 && (
        <div className="grid lg:grid-cols-2 gap-6">
          <div>
            <h3 className="font-semibold text-slate-800 dark:text-white mb-3">Color Distribution</h3>
            <div className="h-48 sm:h-64 md:h-80">
              <ResponsiveContainer width="100%" height="100%">
                <PieChart>
                  <Pie
                    data={analytics.color_stats}
                    cx="50%"
                    cy="50%"
                    labelLine={false}
                    label={isMobile ? false : ({ percentage }) => `${percentage}%`}
                    outerRadius={80}
                    fill="#8884d8"
                    dataKey="percentage"
                  >
                    {analytics.color_stats.map((entry: ColorStats, index: number) => (
                      <Cell key={`cell-${index}`} fill={PALETTE[index % PALETTE.length]} />
                    ))}
                  </Pie>
                  <Tooltip />
                </PieChart>
              </ResponsiveContainer>
            </div>
          </div>

          <div className="space-y-2">
            <h3 className="font-semibold text-slate-800 dark:text-white mb-3">Color Breakdown</h3>
            {analytics.color_stats.map((stat: ColorStats) => (
              <div key={stat.color} className="flex items-center justify-between text-sm">
                <div className="flex items-center gap-2">
                  <div className="w-3 h-3 rounded-full" style={{ backgroundColor: stat.color || '#999' }} />
                  <span className="capitalize text-slate-700 dark:text-white">{stat.color}</span>
                </div>
                <div className="text-slate-500 dark:text-white/40">
                  {stat.count} items ({stat.percentage}%)
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* ── Category Breakdown ──────────────────────────────────────────────── */}
      {analytics.category_stats.length > 0 && (
        <div>
          <h3 className="font-semibold text-slate-800 dark:text-white mb-3">Category Breakdown</h3>
          <div className="h-48 sm:h-64 md:h-80">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={analytics.category_stats}>
                <CartesianGrid strokeDasharray="3 3" />
                <XAxis dataKey="category" />
                <YAxis />
                <Tooltip content={<CustomTooltip />} />
                <Bar dataKey="count" fill="#8B5CF6" radius={[8, 8, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>
      )}

      {/* ── Outfit Readiness ────────────────────────────────────────────────── */}
      <GlassCard padding="lg">
        <h3 className="font-semibold text-slate-800 dark:text-white mb-4 flex items-center gap-2">
          <Star size={16} className="text-amber-500" /> Outfit Readiness
        </h3>
        <div className="grid sm:grid-cols-2 gap-6">
          <div>
            <div className="text-4xl font-bold text-brand-600 dark:text-brand-400 mb-2">
              {analytics.outfit_readiness.estimated_outfits}
            </div>
            <p className="text-sm text-slate-600 dark:text-white/60">Estimated unique outfits</p>
          </div>
          <div>
            <p className="text-xs font-semibold text-slate-700 dark:text-white/80 uppercase tracking-wider mb-3">Best Covered Occasions</p>
            <div className="flex flex-wrap gap-1.5">
              {analytics.outfit_readiness.best_covered_occasions.map(occ => (
                <Badge key={occ}>{occ}</Badge>
              ))}
            </div>
          </div>
        </div>
      </GlassCard>
    </div>
  )
}
