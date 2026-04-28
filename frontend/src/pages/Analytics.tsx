import { useMemo } from 'react'
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
  PieChart, Pie, Cell,
} from 'recharts'
import { TrendingUp, Shirt, Leaf, Star, Award, Loader2 } from 'lucide-react'
import { useApp } from '@/store'
import Badge from '@/components/ui/Badge'

const CustomTooltip = ({ active, payload, label }: any) => {
  if (active && payload?.length) {
    return (
      <div className="bg-white dark:bg-slate-800 border border-cream-300 dark:border-slate-700 rounded-xl p-3 shadow-card text-sm">
        <p className="font-semibold text-slate-700 dark:text-slate-200 mb-1">{label}</p>
        <p className="text-brand-600 font-bold">{payload[0].value} wears</p>
      </div>
    )
  }
  return null
}

const PALETTE = ['#534AB7', '#7670F1', '#A78BFA', '#C4B5FD', '#DDD6FE', '#EDE9FE']

export default function Analytics() {
  const { closetItems, closetLoading } = useApp()

  // Derive all stats from real closet data
  const stats = useMemo(() => {
    if (closetItems.length === 0) return null

    const totalItems = closetItems.length
    const avgEco = closetItems.reduce((s, i) => s + (i.eco_score ?? 0), 0) / totalItems
    const totalWears = closetItems.reduce((s, i) => s + i.wear_count, 0)
    const totalValue = closetItems.reduce((s, i) => s + (i.price ?? 0), 0)
    const costPerWear = totalWears > 0 ? (totalValue / totalWears).toFixed(2) : '—'

    // Wear stats (top 8)
    const wearStats = [...closetItems]
      .sort((a, b) => b.wear_count - a.wear_count)
      .slice(0, 8)
      .map(i => ({ name: i.name.length > 16 ? i.name.slice(0, 14) + '…' : i.name, wears: i.wear_count }))

    // Color stats
    const colorCounts: Record<string, number> = {}
    closetItems.forEach(i => {
      if (i.color) {
        const c = i.color.split(/[,/]/)[0].trim()
        colorCounts[c] = (colorCounts[c] || 0) + 1
      }
    })
    const colorStats = Object.entries(colorCounts)
      .sort((a, b) => b[1] - a[1])
      .slice(0, 6)
      .map(([name, count], idx) => ({
        name,
        value: Math.round((count / totalItems) * 100),
        fill: PALETTE[idx] ?? '#A78BFA',
      }))

    // Category stats
    const catCounts: Record<string, number> = {}
    closetItems.forEach(i => { catCounts[i.category] = (catCounts[i.category] || 0) + 1 })
    const categoryStats = Object.entries(catCounts)
      .map(([category, count]) => ({
        category: category.charAt(0).toUpperCase() + category.slice(1),
        count,
      }))
      .sort((a, b) => b.count - a.count)

    const topWorn = [...closetItems].sort((a, b) => b.wear_count - a.wear_count).slice(0, 5)

    return { totalItems, avgEco, costPerWear, wearStats, colorStats, categoryStats, topWorn }
  }, [closetItems])

  if (closetLoading && closetItems.length === 0) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="text-center space-y-3">
          <Loader2 size={32} className="animate-spin text-brand-500 mx-auto" />
          <p className="text-slate-500 dark:text-slate-400 text-sm">Loading analytics…</p>
        </div>
      </div>
    )
  }

  if (!stats) {
    return (
      <div className="space-y-6 max-w-5xl animate-slide-up">
        <div>
          <h2 className="font-display font-bold text-xl text-slate-800 dark:text-slate-100">Analytics</h2>
          <p className="text-sm text-slate-400 mt-0.5">Insights about your wardrobe & style habits</p>
        </div>
        <div className="card p-16 text-center">
          <div className="text-5xl mb-4">📊</div>
          <p className="font-semibold text-slate-600 dark:text-slate-400">No data yet</p>
          <p className="text-sm text-slate-400 mt-1 mb-4">Add items to your wardrobe to see analytics</p>
          <a href="/upload" className="btn-primary inline-flex items-center gap-2 px-4 py-2 rounded-xl text-sm">
            + Upload your first item
          </a>
        </div>
      </div>
    )
  }

  const STAT_CARDS = [
    { label: 'Total Items',     value: stats.totalItems,                  sub: `${new Set(closetItems.map(i=>i.category)).size} categories`,  icon: Shirt,     color: 'text-brand-600',   bg: 'bg-brand-50 dark:bg-brand-900/20' },
    { label: 'Avg Eco Score',   value: stats.avgEco.toFixed(1),           sub: 'Out of 10',          icon: Leaf,      color: 'text-emerald-600', bg: 'bg-emerald-50 dark:bg-emerald-900/20' },
    { label: 'Total Wears',     value: closetItems.reduce((s,i)=>s+i.wear_count,0), sub: 'Across all items',  icon: Star,      color: 'text-amber-600',   bg: 'bg-amber-50 dark:bg-amber-900/20' },
    { label: 'Cost Per Wear',   value: `$${stats.costPerWear}`,           sub: 'Based on prices',    icon: TrendingUp, color: 'text-sky-600',    bg: 'bg-sky-50 dark:bg-sky-900/20' },
  ]

  return (
    <div className="space-y-6 max-w-5xl animate-slide-up">
      <div>
        <h2 className="font-display font-bold text-xl text-slate-800 dark:text-slate-100">Analytics</h2>
        <p className="text-sm text-slate-400 mt-0.5">Insights about your wardrobe & style habits</p>
      </div>

      {/* Stat cards */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        {STAT_CARDS.map(s => (
          <div key={s.label} className="card p-4 space-y-3">
            <div className={`w-10 h-10 rounded-xl ${s.bg} flex items-center justify-center`}>
              <s.icon size={18} className={s.color} />
            </div>
            <div>
              <p className={`text-2xl font-bold ${s.color}`}>{s.value}</p>
              <p className="text-sm font-medium text-slate-700 dark:text-slate-300 mt-0.5">{s.label}</p>
              <p className="text-xs text-slate-400 mt-0.5">{s.sub}</p>
            </div>
          </div>
        ))}
      </div>

      {/* Charts row */}
      <div className="grid lg:grid-cols-2 gap-6">
        {/* Most worn bar chart */}
        <div className="card p-5 space-y-4">
          <div className="flex items-center justify-between">
            <h3 className="font-semibold text-slate-700 dark:text-slate-300">Most worn items</h3>
            <Badge variant="purple">All time</Badge>
          </div>
          {stats.wearStats.length === 0 ? (
            <div className="h-[220px] flex items-center justify-center text-slate-400 text-sm">No wear data yet</div>
          ) : (
            <ResponsiveContainer width="100%" height={220}>
              <BarChart data={stats.wearStats} layout="vertical" margin={{ left: 8, right: 16 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#E8E6E0" horizontal={false} />
                <XAxis type="number" tick={{ fontSize: 11, fill: '#94a3b8' }} axisLine={false} tickLine={false} />
                <YAxis type="category" dataKey="name" tick={{ fontSize: 10, fill: '#94a3b8' }} width={110} axisLine={false} tickLine={false} />
                <Tooltip content={<CustomTooltip />} />
                <Bar dataKey="wears" radius={[0, 6, 6, 0]} maxBarSize={18}>
                  {stats.wearStats.map((_, i) => (
                    <Cell key={i} fill={`url(#barGrad)`} />
                  ))}
                  <defs>
                    <linearGradient id="barGrad" x1="0" y1="0" x2="1" y2="0">
                      <stop offset="0%" stopColor="#534AB7" />
                      <stop offset="100%" stopColor="#7670F1" />
                    </linearGradient>
                  </defs>
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          )}
        </div>

        {/* Color distribution donut */}
        <div className="card p-5 space-y-4">
          <div className="flex items-center justify-between">
            <h3 className="font-semibold text-slate-700 dark:text-slate-300">Color distribution</h3>
            <Badge variant="gray">By % share</Badge>
          </div>
          {stats.colorStats.length === 0 ? (
            <div className="h-[200px] flex items-center justify-center text-slate-400 text-sm">No color data</div>
          ) : (
            <div className="flex items-center gap-4">
              <ResponsiveContainer width="55%" height={200}>
                <PieChart>
                  <Pie data={stats.colorStats} cx="50%" cy="50%" innerRadius={55} outerRadius={80} paddingAngle={3} dataKey="value">
                    {stats.colorStats.map((entry, index) => (
                      <Cell key={index} fill={entry.fill} />
                    ))}
                  </Pie>
                  <Tooltip formatter={(v: number) => [`${v}%`, 'Share']} />
                </PieChart>
              </ResponsiveContainer>
              <div className="flex-1 space-y-2">
                {stats.colorStats.map(c => (
                  <div key={c.name} className="flex items-center gap-2">
                    <div className="w-3 h-3 rounded-full flex-shrink-0" style={{ backgroundColor: c.fill }} />
                    <span className="text-xs text-slate-600 dark:text-slate-400 flex-1">{c.name}</span>
                    <span className="text-xs font-semibold text-slate-700 dark:text-slate-300">{c.value}%</span>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      </div>

      {/* Category breakdown + Top items */}
      <div className="grid lg:grid-cols-2 gap-6">
        {/* Category */}
        <div className="card p-5 space-y-4">
          <h3 className="font-semibold text-slate-700 dark:text-slate-300">Category breakdown</h3>
          <div className="space-y-3">
            {stats.categoryStats.map(c => {
              const pct = Math.round((c.count / stats.totalItems) * 100)
              return (
                <div key={c.category} className="space-y-1">
                  <div className="flex justify-between text-sm">
                    <span className="text-slate-600 dark:text-slate-400">{c.category}</span>
                    <span className="font-semibold text-slate-700 dark:text-slate-300">{c.count} items · {pct}%</span>
                  </div>
                  <div className="h-2 bg-cream-200 dark:bg-slate-700 rounded-full overflow-hidden">
                    <div
                      className="h-full bg-gradient-brand rounded-full transition-all duration-700"
                      style={{ width: `${pct}%` }}
                    />
                  </div>
                </div>
              )
            })}
          </div>
        </div>

        {/* Top 5 hero items */}
        <div className="card p-5 space-y-4">
          <div className="flex items-center gap-2">
            <Award size={15} className="text-amber-500" />
            <h3 className="font-semibold text-slate-700 dark:text-slate-300">Hall of fame</h3>
          </div>
          <div className="space-y-3">
            {stats.topWorn.map((item, i) => (
              <div key={item.id} className="flex items-center gap-3">
                <div className={`w-7 h-7 rounded-full flex items-center justify-center text-xs font-bold flex-shrink-0 ${
                  i === 0 ? 'bg-amber-100 text-amber-600' :
                  i === 1 ? 'bg-slate-100 text-slate-500' :
                  i === 2 ? 'bg-orange-100 text-orange-600' :
                  'bg-cream-100 text-slate-400'
                }`}>
                  {i + 1}
                </div>
                <div className="w-10 h-10 rounded-lg overflow-hidden bg-cream-100 dark:bg-slate-700 flex-shrink-0">
                  {item.image_url
                    ? <img src={item.image_url} alt={item.name} className="w-full h-full object-cover" />
                    : <div className="w-full h-full flex items-center justify-center text-lg">👕</div>}
                </div>
                <div className="flex-1 min-w-0">
                  <p className="text-sm font-medium text-slate-700 dark:text-slate-200 truncate">{item.name}</p>
                  <p className="text-xs text-slate-400">{item.brand || item.category}</p>
                </div>
                <div className="text-right flex-shrink-0">
                  <p className="text-sm font-bold text-brand-600">{item.wear_count}×</p>
                  <p className="text-[10px] text-slate-400">wears</p>
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  )
}
