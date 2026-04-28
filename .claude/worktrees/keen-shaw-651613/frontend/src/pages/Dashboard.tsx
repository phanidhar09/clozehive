import { useState, useEffect } from 'react'
import { Link } from 'react-router-dom'
import { Sparkles, Upload, Plane, Shirt, ArrowRight, Leaf, TrendingUp, Sun, Loader2, RefreshCw } from 'lucide-react'
import { useApp } from '@/store'
import { streamOutfitGeneration } from '@/lib/api'
import OutfitCard from '@/components/outfit/OutfitCard'
import Badge from '@/components/ui/Badge'
import type { OutfitSuggestion } from '@/types'

const QUICK_ACTIONS = [
  { label: 'Ask AI Stylist',   desc: 'Get outfit ideas now',   icon: Sparkles, to: '/ai-stylist', gradient: 'from-violet-500 to-purple-600' },
  { label: 'Plan a Trip',     desc: 'Smart packing list',     icon: Plane,    to: '/travel',     gradient: 'from-sky-500 to-blue-600' },
  { label: 'Add Item',        desc: 'Upload a clothing photo', icon: Upload,   to: '/upload',     gradient: 'from-emerald-500 to-teal-600' },
  { label: 'Browse Closet',   desc: 'View all pieces',        icon: Shirt,    to: '/closet',     gradient: 'from-rose-500 to-pink-600' },
]

export default function Dashboard() {
  const { closetItems, closetLoading } = useApp()
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

    await streamOutfitGeneration(
      { occasion: 'casual', weather: 'sunny', temperature: 22 },
      {
        onStatus: (msg) => setOutfitStatus(msg),
        onResult: (data) => setOutfits(data.outfits || []),
        onError: (err) => {
          setOutfitError(err)
          setOutfitLoading(false)
          setOutfitStatus('')
        },
        onDone: () => {
          setOutfitLoading(false)
          setOutfitStatus('')
        },
      },
    )
  }

  useEffect(() => {
    if (closetItems.length > 0 && outfits.length === 0 && !outfitLoading) {
      loadOutfits()
    }
  }, [closetItems.length])

  const recentItems = closetItems.slice(0, 4)
  const totalItems = closetItems.length
  const avgEco = closetItems.length
    ? (closetItems.reduce((s, i) => s + (i.eco_score ?? 0), 0) / closetItems.length).toFixed(1)
    : '—'
  const categories = new Set(closetItems.map(i => i.category)).size
  const todayOutfit = outfits[0]

  return (
    <div className="space-y-6 max-w-6xl animate-slide-up">
      {/* Hero */}
      <div className="relative overflow-hidden rounded-2xl bg-gradient-to-br from-brand-700 via-brand-600 to-violet-500 p-6 lg:p-8 text-white shadow-xl">
        <div className="absolute inset-0 bg-[url('https://images.unsplash.com/photo-1558618666-fcd25c85cd64?w=1200&q=60')] bg-cover bg-center opacity-10" />
        <div className="relative">
          <div className="flex items-center gap-2 mb-1">
            <Sun size={16} className="text-yellow-300" />
            <span className="text-sm font-medium text-white/70">
              {new Date().toLocaleDateString('en-US', { weekday: 'long', month: 'long', day: 'numeric' })}
            </span>
          </div>
          <h2 className="font-display text-2xl lg:text-3xl font-bold mb-1">{greeting}, Alex 👋</h2>
          <p className="text-white/70 text-sm mb-6">
            {closetLoading
              ? 'Loading your wardrobe…'
              : totalItems > 0
                ? `You have ${totalItems} items in your wardrobe. Let's find the perfect look.`
                : 'Start by adding items to your wardrobe.'}
          </p>

          {/* Today's outfit preview */}
          <div className="bg-white/15 backdrop-blur-sm rounded-xl p-4 border border-white/20 max-w-sm">
            <p className="text-xs font-semibold text-white/60 uppercase tracking-wide mb-3 flex items-center gap-1.5">
              <Sparkles size={11} /> Today's AI pick
            </p>
            {outfitLoading ? (
              <div className="flex items-center gap-2 text-white/60 text-sm">
                <Loader2 size={14} className="animate-spin" />
                {outfitStatus || 'Generating outfit…'}
              </div>
            ) : outfitError ? (
              <div className="text-white/60 text-xs">
                <p>{outfitError}</p>
                {closetItems.length === 0 && (
                  <Link to="/upload" className="underline mt-1 block">Add items to get AI picks</Link>
                )}
              </div>
            ) : todayOutfit ? (
              <>
                <p className="font-semibold mb-2">{todayOutfit.name}</p>
                <div className="flex gap-2 mb-3">
                  {todayOutfit.items.slice(0, 3).map((item, i) => (
                    <div key={i} className="w-12 h-12 rounded-lg overflow-hidden bg-white/10 border border-white/20 flex-shrink-0">
                      {item.image_url
                        ? <img src={item.image_url} alt={item.name} className="w-full h-full object-cover" />
                        : <div className="w-full h-full flex items-center justify-center text-lg">👕</div>}
                    </div>
                  ))}
                </div>
                <p className="text-xs text-white/70 line-clamp-2">{todayOutfit.explanation}</p>
              </>
            ) : (
              <p className="text-white/60 text-sm">
                {totalItems === 0
                  ? 'Add items to get AI outfit picks'
                  : 'No outfit generated yet'}
              </p>
            )}
          </div>
        </div>

        <div className="absolute -top-10 -right-10 w-48 h-48 rounded-full bg-white/5 blur-2xl" />
        <div className="absolute -bottom-16 right-20 w-64 h-64 rounded-full bg-violet-500/20 blur-3xl" />
      </div>

      {/* Quick actions */}
      <div>
        <h3 className="font-display font-semibold text-base text-slate-700 dark:text-slate-300 mb-3">Quick actions</h3>
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
          {QUICK_ACTIONS.map(({ label, desc, icon: Icon, to, gradient }) => (
            <Link key={to} to={to} className="card-hover p-4 group">
              <div className={`w-10 h-10 rounded-xl bg-gradient-to-br ${gradient} flex items-center justify-center mb-3 shadow-md group-hover:scale-110 transition-transform`}>
                <Icon size={18} className="text-white" />
              </div>
              <p className="font-semibold text-sm text-slate-800 dark:text-slate-100">{label}</p>
              <p className="text-xs text-slate-400 mt-0.5">{desc}</p>
            </Link>
          ))}
        </div>
      </div>

      {/* Main content grid */}
      <div className="grid lg:grid-cols-5 gap-6">
        {/* Outfit suggestions */}
        <div className="lg:col-span-3 space-y-3">
          <div className="flex items-center justify-between">
            <h3 className="font-display font-semibold text-base text-slate-700 dark:text-slate-300">AI outfit picks</h3>
            <div className="flex items-center gap-2">
              <button
                onClick={loadOutfits}
                disabled={outfitLoading || closetItems.length === 0}
                className="btn-ghost text-xs gap-1.5 disabled:opacity-40"
              >
                <RefreshCw size={12} className={outfitLoading ? 'animate-spin' : ''} /> Regenerate
              </button>
              <Link to="/ai-stylist" className="text-xs font-medium text-brand-600 flex items-center gap-1 hover:gap-2 transition-all">
                Chat with AI <ArrowRight size={12} />
              </Link>
            </div>
          </div>

          {outfitLoading ? (
            <div className="card p-10 flex flex-col items-center gap-3 text-slate-400">
              <Loader2 size={20} className="animate-spin text-brand-500" />
              <span className="text-sm">{outfitStatus || 'Curating outfits from your wardrobe…'}</span>
            </div>
          ) : outfits.length > 0 ? (
            <div className="space-y-3">
              {outfits.map((outfit, i) => (
                <OutfitCard key={outfit.name + i} outfit={outfit} rank={i} />
              ))}
            </div>
          ) : (
            <div className="card p-10 text-center text-slate-400">
              <div className="text-4xl mb-3">✨</div>
              <p className="font-semibold text-slate-600 dark:text-slate-400">
                {closetItems.length === 0 ? 'Add items to get outfit picks' : 'No outfits generated yet'}
              </p>
              {closetItems.length === 0 && (
                <Link to="/upload" className="text-brand-500 text-sm underline mt-2 block">Upload your first item →</Link>
              )}
            </div>
          )}
        </div>

        {/* Right column */}
        <div className="lg:col-span-2 space-y-4">
          {/* Stats */}
          <div className="card p-4">
            <h3 className="font-semibold text-sm text-slate-700 dark:text-slate-300 mb-3 flex items-center gap-2">
              <TrendingUp size={14} className="text-brand-500" /> Wardrobe stats
            </h3>
            {closetLoading ? (
              <div className="grid grid-cols-2 gap-3">
                {[...Array(4)].map((_, i) => (
                  <div key={i} className="bg-cream-50 dark:bg-slate-800/60 rounded-xl p-3 animate-pulse">
                    <div className="h-6 bg-cream-200 dark:bg-slate-700 rounded mb-1" />
                    <div className="h-3 bg-cream-100 dark:bg-slate-700/50 rounded w-2/3" />
                  </div>
                ))}
              </div>
            ) : (
              <div className="grid grid-cols-2 gap-3">
                {[
                  { label: 'Total items', value: totalItems, color: 'text-brand-600' },
                  { label: 'Categories', value: categories, color: 'text-emerald-600' },
                  { label: 'Outfits saved', value: outfits.length, color: 'text-amber-600' },
                  { label: 'Avg eco score', value: avgEco, color: 'text-teal-600' },
                ].map(s => (
                  <div key={s.label} className="bg-cream-50 dark:bg-slate-800/60 rounded-xl p-3 text-center">
                    <p className={`text-xl font-bold ${s.color}`}>{s.value}</p>
                    <p className="text-[11px] text-slate-400 mt-0.5">{s.label}</p>
                  </div>
                ))}
              </div>
            )}
          </div>

          {/* Recently added */}
          <div className="card p-4">
            <div className="flex items-center justify-between mb-3">
              <h3 className="font-semibold text-sm text-slate-700 dark:text-slate-300">Recently added</h3>
              <Link to="/closet" className="text-xs text-brand-600 hover:underline">View all</Link>
            </div>
            {closetLoading ? (
              <div className="space-y-2">
                {[...Array(3)].map((_, i) => (
                  <div key={i} className="flex items-center gap-3 p-2 animate-pulse">
                    <div className="w-10 h-10 rounded-lg bg-cream-200 dark:bg-slate-700 flex-shrink-0" />
                    <div className="flex-1">
                      <div className="h-3 bg-cream-200 dark:bg-slate-700 rounded mb-1 w-3/4" />
                      <div className="h-2 bg-cream-100 dark:bg-slate-700/50 rounded w-1/2" />
                    </div>
                  </div>
                ))}
              </div>
            ) : recentItems.length === 0 ? (
              <div className="text-center py-4">
                <p className="text-sm text-slate-400">No items yet</p>
                <Link to="/upload" className="text-xs text-brand-500 underline mt-1 block">Add your first item</Link>
              </div>
            ) : (
              <div className="space-y-2">
                {recentItems.map(item => (
                  <div key={item.id} className="flex items-center gap-3 p-2 rounded-xl hover:bg-cream-50 dark:hover:bg-slate-800 transition-colors cursor-pointer">
                    <div className="w-10 h-10 rounded-lg overflow-hidden bg-cream-100 dark:bg-slate-700 flex-shrink-0">
                      {item.image_url
                        ? <img src={item.image_url} alt={item.name} className="w-full h-full object-cover" />
                        : <div className="w-full h-full flex items-center justify-center text-lg">👕</div>
                      }
                    </div>
                    <div className="flex-1 min-w-0">
                      <p className="text-sm font-medium text-slate-800 dark:text-slate-100 truncate">{item.name}</p>
                      <p className="text-xs text-slate-400">{item.brand || item.category}</p>
                    </div>
                    {item.eco_score && item.eco_score >= 8 && (
                      <Leaf size={12} className="text-emerald-500 flex-shrink-0" />
                    )}
                  </div>
                ))}
              </div>
            )}
          </div>

          {/* Eco badge */}
          {totalItems > 0 && (
            <div className="card p-4 bg-emerald-50 dark:bg-emerald-900/20 border-emerald-200 dark:border-emerald-800">
              <div className="flex items-start gap-3">
                <div className="w-10 h-10 rounded-xl bg-emerald-500 flex items-center justify-center flex-shrink-0">
                  <Leaf size={18} className="text-white" />
                </div>
                <div>
                  <p className="font-semibold text-sm text-emerald-800 dark:text-emerald-300">Good eco choices!</p>
                  <p className="text-xs text-emerald-600 dark:text-emerald-400 mt-0.5">
                    {closetItems.filter(i => (i.eco_score ?? 0) >= 7).length} of {totalItems} items score 7+ eco points.
                  </p>
                </div>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
