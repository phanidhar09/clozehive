import { useEffect, useState, type CSSProperties } from 'react'
import { Link } from 'react-router-dom'
import {
  Upload, Plane, Shirt, ArrowRight,
  Leaf, TrendingUp, Sun, BarChart3, Wand2,
} from 'lucide-react'
import { useApp } from '@/store'
import { weatherApi, type CurrentWeatherResponse } from '@/lib/api'
import GlassCard from '@/components/ui/GlassCard'
import { useCursorGlow } from '@/hooks/useCursorGlow'
const QUICK_ACTIONS = [
  { label: 'Smart Closet Scan', desc: 'Bulk upload items',      icon: Upload, to: '/upload',    gradient: 'from-emerald-500 to-teal-600' },
  { label: 'My Closet',         desc: 'View all pieces',        icon: Shirt,  to: '/closet',    gradient: 'from-rose-500 to-pink-600' },
  { label: 'Outfit Builder',    desc: 'Drag-and-drop looks',    icon: Wand2,  to: '/outfit-builder', gradient: 'from-pink-500 to-rose-600' },
  { label: 'Travel Packing',    desc: 'Plan your trip',        icon: Plane,  to: '/travel',    gradient: 'from-sky-500 to-blue-600' },
  { label: 'Closet Insights',   desc: 'View your analytics',   icon: BarChart3, to: '/analytics', gradient: 'from-violet-500 to-purple-600' },
]

export default function Dashboard() {
  const { closetItems, closetLoading, currentUser } = useApp()
  const { containerRef, glowRef } = useCursorGlow({ lerpFactor: 0.08, orbitRadius: 320 })
  const [hour] = useState(new Date().getHours())
  const [weather, setWeather] = useState<CurrentWeatherResponse | null>(null)
  const greeting = hour < 12 ? 'Good morning' : hour < 17 ? 'Good afternoon' : 'Good evening'

  const totalItems = closetItems.length
  const categories = new Set(closetItems.map(i => i.category)).size
  const avgEco = closetItems.length
    ? (closetItems.reduce((s, i) => s + (i.eco_score ?? 0), 0) / closetItems.length).toFixed(1)
    : 0

  const stats = [
    { label: 'Total Items', value: totalItems, icon: Shirt, color: 'from-rose-500 to-pink-500' },
    { label: 'Categories', value: categories, icon: TrendingUp, color: 'from-violet-500 to-purple-500' },
    { label: 'Eco Score', value: typeof avgEco === 'string' ? avgEco : avgEco.toFixed(1), icon: Leaf, color: 'from-emerald-500 to-teal-500' },
  ]

  useEffect(() => {
    if (!currentUser?.permissions?.location) return
    let cancelled = false
    weatherApi.current()
      .then(data => { if (!cancelled) setWeather(data) })
      .catch(() => { if (!cancelled) setWeather(null) })
    return () => { cancelled = true }
  }, [currentUser?.permissions?.location])

  return (
    <div className="space-y-6 max-w-6xl">

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
                ? `You have ${totalItems} curated piece${totalItems === 1 ? '' : 's'}. Start planning your next trip or get closet insights!`
                : 'Start by scanning your closet to build your digital wardrobe.'}
          </p>

          {weather && (
            <div className="mb-5 inline-flex flex-wrap items-center gap-3 rounded-2xl border border-white/15 bg-white/10 px-4 py-3 text-sm backdrop-blur-md">
              <span className="text-lg">☁️</span>
              <span className="font-semibold">{Math.round(weather.temp_c)}°C</span>
              <span className="text-white/75">{weather.condition}</span>
              <span className="text-white/60">Perfect day for weather-aware styling.</span>
            </div>
          )}

          <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
            {stats.map(({ label, value, icon: Icon, color }) => (
              <div key={label} className="bg-white/10 backdrop-blur-md rounded-xl p-3 border border-white/15">
                <div className="flex items-center gap-3">
                  <div className={`w-10 h-10 rounded-lg bg-gradient-to-br ${color} flex items-center justify-center flex-shrink-0`}>
                    <Icon size={16} className="text-white" />
                  </div>
                  <div>
                    <p className="text-[10px] font-bold text-white/60 uppercase tracking-wider">{label}</p>
                    <p className="text-xl font-bold text-white">{value}</p>
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* ── Quick actions ─────────────────────────────────────────────────── */}
      <div>
        <h3 className="font-display font-semibold text-sm uppercase tracking-widest
                       text-slate-500 dark:text-white/40 mb-3">
          Quick actions
        </h3>
        <div className="grid grid-cols-2 lg:grid-cols-5 gap-3 stagger">
          {QUICK_ACTIONS.map(({ label, desc, icon: Icon, to, gradient }, idx) => (
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
              Recent items
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
                  <p className="text-xs text-slate-500 dark:text-white/40 mt-0.5">{item.category}</p>
                </div>
              </GlassCard>
            ))}
          </div>
        </div>
      )}

      {/* ── Empty state ───────────────────────────────────────────────────── */}
      {totalItems === 0 && !closetLoading && (
        <div className="rounded-2xl border border-dashed border-slate-300 dark:border-white/10 p-8 text-center">
          <Shirt size={40} className="text-slate-300 dark:text-white/20 mx-auto mb-3" />
          <h3 className="font-semibold text-slate-700 dark:text-white mb-2">Your closet is empty</h3>
          <p className="text-sm text-slate-500 dark:text-white/40 mb-4">
            Scan your closet to add your first items and unlock closet insights and travel packing features.
          </p>
          <Link to="/upload" className="inline-flex items-center gap-2 px-4 py-2 rounded-lg bg-brand-600 text-white hover:bg-brand-700 transition-colors text-sm font-medium">
            <Upload size={16} /> Start Smart Closet Scan
          </Link>
        </div>
      )}
    </div>
  )
}
