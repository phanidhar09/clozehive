import { useState, useEffect, type CSSProperties } from 'react'
import { Link } from 'react-router-dom'
import {
  Sparkles, Upload, Plane, Shirt, ArrowRight,
  Leaf, TrendingUp, Sun, Loader2, RefreshCw,
} from 'lucide-react'
import { useApp } from '@/store'
import { streamOutfit } from '@/lib/api'
import OutfitCard from '@/components/outfit/OutfitCard'
import GlassCard from '@/components/ui/GlassCard'
import WeeklyPlanner from '@/components/dashboard/WeeklyPlanner'
import { useCursorGlow } from '@/hooks/useCursorGlow'
import type { OutfitSuggestion } from '@/types'

const QUICK_ACTIONS = [
  { label: 'Ask AI Stylist', desc: 'Get outfit ideas now',     icon: Sparkles, to: '/ai-stylist', gradient: 'from-violet-500 to-purple-600' },
  { label: 'Plan a Trip',    desc: 'Smart packing list',       icon: Plane,    to: '/travel',     gradient: 'from-sky-500 to-blue-600' },
  { label: 'Add Item',       desc: 'Upload a clothing photo',  icon: Upload,   to: '/upload',     gradient: 'from-emerald-500 to-teal-600' },
  { label: 'Browse Closet',  desc: 'View all pieces',          icon: Shirt,    to: '/closet',     gradient: 'from-rose-500 to-pink-600' },
]

export default function Dashboard() {
  const { closetItems, closetLoading, currentUser } = useApp()
  const { containerRef, glowRef } = useCursorGlow({ lerpFactor: 0.08, orbitRadius: 320 }) // orbitRadius = half of 640px glow
  const [hour] = useState(new Date().getHours())
  const greeting = hour < 12 ? 'Good morning' : hour < 17 ? 'Good afternoon' : 'Good evening'

  const [outfits, setOutfits] = useState<OutfitSuggestion[]>([])
  const [outfitLoading, setOutfitLoading] = useState(false)
  const [outfitStatus, setOutfitStatus] = useState('')
  const [outfitError, setOutfitError] = useState<string | null>(null)

  const loadOutfits = async () => {
    if (closetItems.length === 0) return
    setOutfitLoading(true)
    setOutfitStatus('Analysing your wardrobe…')
    setOutfitError(null)
    setOutfits([])

    await streamOutfit(
      {
        occasion: 'casual',
        weather: 'Sunny',
        temperature: 22,
        user_profile: {
          body_profile: currentUser?.body_profile ?? null,
          style_profile: currentUser?.style_profile ?? null,
          preferences: currentUser?.preferences ?? null,
        },
      },
      {
        onStatus: (msg: string) => setOutfitStatus(msg),
        onResult: (data: { outfits: OutfitSuggestion[] }) => setOutfits(data.outfits || []),
        onError:  (err: string) => { setOutfitError(err); setOutfitLoading(false); setOutfitStatus('') },
        onDone:   ()             => { setOutfitLoading(false); setOutfitStatus('') },
      },
    )
  }

  useEffect(() => {
    if (closetItems.length > 0 && outfits.length === 0 && !outfitLoading) loadOutfits()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [closetItems.length])

  const recentItems = closetItems.slice(0, 4)
  const totalItems  = closetItems.length
  const avgEco      = closetItems.length
    ? (closetItems.reduce((s, i) => s + (i.eco_score ?? 0), 0) / closetItems.length).toFixed(1)
    : '—'
  const categories  = new Set(closetItems.map(i => i.category)).size
  const todayOutfit = outfits[0]

  return (
    <div className="space-y-6 max-w-6xl animate-slide-up">

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
                ? `You have ${totalItems} curated piece${totalItems === 1 ? '' : 's'}. Let's craft today's look.`
                : 'Start by adding a few favorites — your AI stylist will take it from there.'}
          </p>

          <div className="flex flex-wrap items-stretch gap-4">
            {/* Spinning AI badge */}
            <div className="relative flex-shrink-0 w-[120px] h-[120px] flex items-center justify-center">
              <div className="absolute inset-0 rounded-full border border-white/20 animate-spin-ring" />
              <div className="absolute inset-3 rounded-full border border-dashed border-white/30 animate-spin-ring-rev" />
              <div className="absolute inset-6 rounded-full border border-white/10 animate-spin-ring" />
              <div className="relative w-14 h-14 rounded-full bg-white/15 backdrop-blur-md
                              flex items-center justify-center shadow-glow-sm animate-glow-pulse">
                <Sparkles size={20} className="text-white" />
              </div>
            </div>

            {/* AI pick card */}
            <div className="flex-1 min-w-[260px] bg-white/10 backdrop-blur-md
                            rounded-2xl p-4 border border-white/15">
              <p className="text-[10px] font-bold text-white/60 uppercase tracking-[0.15em] mb-3 flex items-center gap-1.5">
                <Sparkles size={11} /> Today's AI pick
              </p>
              {outfitLoading ? (
                <div className="flex items-center gap-2 text-white/70 text-sm">
                  <Loader2 size={14} className="animate-spin" />
                  {outfitStatus || 'Generating outfit…'}
                </div>
              ) : outfitError ? (
                <div className="text-white/70 text-xs">
                  <p>{outfitError}</p>
                  {closetItems.length === 0 && (
                    <Link to="/upload" className="underline mt-1 block">Add items to get AI picks</Link>
                  )}
                </div>
              ) : todayOutfit ? (
                <>
                  <p className="font-semibold mb-2.5">{todayOutfit.name}</p>
                  <div className="flex gap-2 mb-3">
                    {todayOutfit.items.slice(0, 4).map((item, i) => (
                      <div key={i} className="w-12 h-12 rounded-xl overflow-hidden bg-white/10 border border-white/20 flex-shrink-0">
                        {item.image_url
                          ? <img src={item.image_url} alt={item.name} className="w-full h-full object-cover" />
                          : <div className="w-full h-full flex items-center justify-center text-lg">👕</div>}
                      </div>
                    ))}
                  </div>
                  <p className="text-xs text-white/70 line-clamp-2 leading-relaxed">{todayOutfit.explanation}</p>
                </>
              ) : (
                <p className="text-white/70 text-sm">
                  {totalItems === 0 ? 'Add items to get AI outfit picks' : 'No outfit generated yet'}
                </p>
              )}
            </div>
          </div>
        </div>
      </div>

      {/* ── Quick actions ─────────────────────────────────────────────────── */}
      <div>
        <h3 className="font-display font-semibold text-sm uppercase tracking-widest
                       text-slate-500 dark:text-white/40 mb-3">
          Quick actions
        </h3>
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-3 stagger">
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

      {/* ── Weekly planner ────────────────────────────────────────────────── */}
      <WeeklyPlanner />

      {/* ── Main grid ─────────────────────────────────────────────────────── */}
      <div className="grid lg:grid-cols-5 gap-6">

        {/* AI outfit picks */}
        <div className="lg:col-span-3 space-y-3">
          <div className="flex items-center justify-between">
            <h3 className="font-display font-semibold text-sm uppercase tracking-widest
                           text-slate-500 dark:text-white/40">
              AI outfit picks
            </h3>
            <div className="flex items-center gap-2">
              <button
                onClick={loadOutfits}
                disabled={outfitLoading || closetItems.length === 0}
                className="btn-ghost text-xs gap-1.5 disabled:opacity-40 !py-1.5 !px-3"
              >
                <RefreshCw size={12} className={outfitLoading ? 'animate-spin' : ''} /> Regenerate
              </button>
              <Link
                to="/ai-stylist"
                className="text-xs font-semibold text-indigo-600 dark:text-indigo-400
                           flex items-center gap-1 hover:gap-2 transition-all"
              >
                Chat with AI <ArrowRight size={12} />
              </Link>
            </div>
          </div>

          {outfitLoading ? (
            <GlassCard padding="lg" className="flex flex-col items-center gap-3 text-center py-12">
              <div className="relative w-12 h-12 flex items-center justify-center">
                <div className="absolute inset-0 rounded-full border border-indigo-400/30 animate-spin-ring" />
                <div className="absolute inset-2 rounded-full border border-dashed border-violet-400/40 animate-spin-ring-rev" />
                <Loader2 size={18} className="text-indigo-500 animate-spin" />
              </div>
              <span className="text-sm text-slate-500 dark:text-white/50">
                {outfitStatus || 'Curating outfits from your wardrobe…'}
              </span>
            </GlassCard>
          ) : outfits.length > 0 ? (
            <div className="space-y-3 stagger">
              {outfits.map((outfit, i) => (
                <div key={outfit.name + i} style={{ '--i': i } as CSSProperties}>
                  <OutfitCard outfit={outfit} rank={i} />
                </div>
              ))}
            </div>
          ) : (
            <GlassCard padding="lg" className="text-center py-12">
              <div className="text-4xl mb-3">✨</div>
              <p className="font-semibold text-slate-700 dark:text-white/80">
                {closetItems.length === 0 ? 'Add items to get outfit picks' : 'No outfits generated yet'}
              </p>
              {closetItems.length === 0 && (
                <Link to="/upload" className="text-indigo-500 dark:text-indigo-400 text-sm underline mt-2 inline-block">
                  Upload your first item →
                </Link>
              )}
            </GlassCard>
          )}
        </div>

        {/* Right column */}
        <div className="lg:col-span-2 space-y-4">

          {/* Stats */}
          <GlassCard padding="md">
            <h3 className="font-semibold text-sm text-slate-700 dark:text-white/80 mb-3 flex items-center gap-2">
              <TrendingUp size={14} className="text-indigo-500" /> Wardrobe stats
            </h3>
            {closetLoading ? (
              <div className="grid grid-cols-2 gap-3">
                {[...Array(4)].map((_, i) => (
                  <div key={i} className="rounded-xl p-3 shimmer-bg h-[58px]" />
                ))}
              </div>
            ) : (
              <div className="grid grid-cols-2 gap-3 stagger">
                {[
                  { label: 'Total items',    value: totalItems,     color: 'from-indigo-400 to-violet-500' },
                  { label: 'Categories',     value: categories,     color: 'from-emerald-400 to-teal-500' },
                  { label: 'Outfits saved',  value: outfits.length, color: 'from-amber-400 to-orange-500' },
                  { label: 'Avg eco score',  value: avgEco,         color: 'from-cyan-400 to-sky-500' },
                ].map((s, i) => (
                  <div
                    key={s.label}
                    style={{ '--i': i } as CSSProperties}
                    className="relative rounded-xl p-3 text-center
                               bg-cream-50/70 dark:bg-white/[0.03]
                               border border-cream-200 dark:border-white/[0.06]
                               hover:border-cream-300 dark:hover:border-white/[0.12]
                               transition-colors overflow-hidden"
                  >
                    <p className={`text-2xl font-bold bg-gradient-to-br ${s.color} bg-clip-text text-transparent`}>
                      {s.value}
                    </p>
                    <p className="text-[11px] text-slate-500 dark:text-white/40 mt-0.5">{s.label}</p>
                  </div>
                ))}
              </div>
            )}
          </GlassCard>

          {/* Recently added */}
          <GlassCard padding="md">
            <div className="flex items-center justify-between mb-3">
              <h3 className="font-semibold text-sm text-slate-700 dark:text-white/80">Recently added</h3>
              <Link to="/closet" className="text-xs font-semibold text-indigo-600 dark:text-indigo-400 hover:underline">
                View all
              </Link>
            </div>
            {closetLoading ? (
              <div className="space-y-2">
                {[...Array(3)].map((_, i) => (
                  <div key={i} className="flex items-center gap-3 p-2">
                    <div className="w-10 h-10 rounded-lg shimmer-bg flex-shrink-0" />
                    <div className="flex-1 space-y-1.5">
                      <div className="h-3 shimmer-bg rounded w-3/4" />
                      <div className="h-2 shimmer-bg rounded w-1/2" />
                    </div>
                  </div>
                ))}
              </div>
            ) : recentItems.length === 0 ? (
              <div className="text-center py-4">
                <p className="text-sm text-slate-400 dark:text-white/40">No items yet</p>
                <Link to="/upload" className="text-xs text-indigo-500 dark:text-indigo-400 underline mt-1 block">
                  Add your first item
                </Link>
              </div>
            ) : (
              <div className="space-y-1.5 stagger">
                {recentItems.map((item, i) => (
                  <div
                    key={item.id}
                    style={{ '--i': i } as CSSProperties}
                    className="flex items-center gap-3 p-2 rounded-xl
                               hover:bg-cream-50 dark:hover:bg-white/[0.05]
                               transition-colors cursor-pointer group"
                  >
                    <div className="w-10 h-10 rounded-lg overflow-hidden
                                    bg-cream-100 dark:bg-white/[0.06]
                                    border border-cream-200 dark:border-white/[0.06]
                                    flex-shrink-0
                                    group-hover:scale-105 transition-transform">
                      {item.image_url
                        ? <img src={item.image_url} alt={item.name} className="w-full h-full object-cover" />
                        : <div className="w-full h-full flex items-center justify-center text-lg">👕</div>}
                    </div>
                    <div className="flex-1 min-w-0">
                      <p className="text-sm font-medium text-slate-800 dark:text-white truncate">{item.name}</p>
                      <p className="text-xs text-slate-400 dark:text-white/40">{item.brand || item.category}</p>
                    </div>
                    {item.eco_score && item.eco_score >= 8 && (
                      <Leaf size={12} className="text-emerald-500 flex-shrink-0" />
                    )}
                  </div>
                ))}
              </div>
            )}
          </GlassCard>

          {/* Eco badge */}
          {totalItems > 0 && (
            <GlassCard
              padding="md"
              className="!bg-gradient-to-br !from-emerald-50 !to-teal-50
                         dark:!from-emerald-500/[0.08] dark:!to-teal-500/[0.05]
                         !border-emerald-200/60 dark:!border-emerald-500/20"
            >
              <div className="flex items-start gap-3">
                <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-emerald-500 to-teal-600
                                flex items-center justify-center flex-shrink-0
                                shadow-[0_0_20px_rgba(16,185,129,0.35)]">
                  <Leaf size={18} className="text-white" />
                </div>
                <div>
                  <p className="font-semibold text-sm text-emerald-800 dark:text-emerald-200">Good eco choices!</p>
                  <p className="text-xs text-emerald-700/80 dark:text-emerald-300/70 mt-0.5">
                    {closetItems.filter(i => (i.eco_score ?? 0) >= 7).length} of {totalItems} items score 7+ eco points.
                  </p>
                </div>
              </div>
            </GlassCard>
          )}
        </div>
      </div>
    </div>
  )
}
