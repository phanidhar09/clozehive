/**
 * ClosetMatch — "Complete My Look"
 *
 * Pick any item from your wardrobe and FANI suggests what to shop for
 * next to maximise outfit potential with that piece.
 */

import { useState, useMemo } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import {
  Shirt, Sparkles, ShoppingBag, ChevronRight, Package,
  Loader2, AlertCircle, Star, TrendingUp, Tag, ArrowRight,
  Search, CheckCircle2,
} from 'lucide-react'
import BackButton from '@/components/ui/BackButton'
import GlassCard from '@/components/ui/GlassCard'
import { shoppingCheckApi, type ClosetMatchResult, type ClosetMatchSuggestion } from '@/lib/api'
import { resolveUploadUrl } from '@/lib/api'
import { useApp } from '@/store'
import { cn } from '@/lib/utils'

// ── Potential badge ───────────────────────────────────────────────────────────

const POTENTIAL_CONFIG = {
  high:   { label: 'High Potential', color: 'text-emerald-600 dark:text-emerald-400', bg: 'bg-emerald-50 dark:bg-emerald-900/20', border: 'border-emerald-200 dark:border-emerald-700/40', icon: Star },
  medium: { label: 'Good Potential', color: 'text-amber-600 dark:text-amber-400',   bg: 'bg-amber-50 dark:bg-amber-900/20',   border: 'border-amber-200 dark:border-amber-700/40',   icon: TrendingUp },
  low:    { label: 'Limited Pairing', color: 'text-slate-500 dark:text-white/50',   bg: 'bg-slate-50 dark:bg-white/[0.04]',   border: 'border-slate-200 dark:border-white/10',       icon: Tag },
}

const PRIORITY_CONFIG = {
  high:   { label: 'Must-have', classes: 'bg-rose-100 text-rose-700 dark:bg-rose-900/20 dark:text-rose-400' },
  medium: { label: 'Nice to have', classes: 'bg-amber-100 text-amber-700 dark:bg-amber-900/20 dark:text-amber-400' },
  low:    { label: 'Optional', classes: 'bg-slate-100 text-slate-600 dark:bg-white/[0.06] dark:text-white/50' },
}

// ── Suggestion card ───────────────────────────────────────────────────────────

function SuggestionCard({ s, index }: { s: ClosetMatchSuggestion; index: number }) {
  const priority = PRIORITY_CONFIG[s.priority] ?? PRIORITY_CONFIG.medium
  return (
    <motion.div
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: index * 0.06 }}
    >
      <GlassCard className="p-4 space-y-2.5 hover:shadow-md transition-shadow group">
        <div className="flex items-start justify-between gap-3">
          <div className="flex-1 min-w-0">
            <p className="text-sm font-semibold text-slate-800 dark:text-white capitalize leading-snug">
              {s.category}
            </p>
            <p className="mt-1 text-xs text-slate-500 dark:text-white/55 leading-relaxed">
              {s.reason}
            </p>
          </div>
          <span className={cn('flex-shrink-0 text-[11px] font-bold px-2 py-0.5 rounded-full', priority.classes)}>
            {priority.label}
          </span>
        </div>

        <div className="flex flex-wrap items-center gap-2">
          {/* Colors */}
          {s.colors.slice(0, 3).map(c => (
            <span key={c}
              className="text-[11px] px-2 py-0.5 rounded-full bg-slate-100 dark:bg-white/[0.06]
                         text-slate-600 dark:text-white/60 capitalize">
              {c}
            </span>
          ))}
          {/* Occasions */}
          {s.occasions.slice(0, 2).map(o => (
            <span key={o}
              className="text-[11px] px-2 py-0.5 rounded-full bg-brand-50 dark:bg-brand-900/20
                         text-brand-600 dark:text-brand-400 capitalize">
              {o}
            </span>
          ))}
          {/* Price */}
          {s.price_range && (
            <span className="ml-auto text-[11px] font-medium text-slate-400 dark:text-white/40">
              {s.price_range}
            </span>
          )}
        </div>
      </GlassCard>
    </motion.div>
  )
}

// ── Result panel ──────────────────────────────────────────────────────────────

function ResultPanel({ result, onClear }: { result: ClosetMatchResult; onClear: () => void }) {
  const potential = POTENTIAL_CONFIG[result.outfit_potential] ?? POTENTIAL_CONFIG.medium
  const PotIcon = potential.icon

  return (
    <div className="space-y-4">
      {/* Selected item + potential */}
      <GlassCard className="p-4">
        <div className="flex items-center gap-4">
          <div className="w-16 h-16 rounded-2xl overflow-hidden bg-slate-100 dark:bg-white/[0.06] flex-shrink-0">
            {result.closet_item.image_url
              ? <img src={resolveUploadUrl(result.closet_item.image_url)} alt=""
                  className="w-full h-full object-cover" />
              : <div className="w-full h-full flex items-center justify-center">
                  <Package size={22} className="text-slate-300 dark:text-white/20" />
                </div>
            }
          </div>
          <div className="flex-1 min-w-0">
            <p className="text-sm font-bold text-slate-800 dark:text-white capitalize truncate">
              {result.closet_item.name}
            </p>
            <p className="text-xs text-slate-500 dark:text-white/50 capitalize">
              {result.closet_item.category}
              {result.closet_item.color ? ` · ${result.closet_item.color}` : ''}
            </p>
            <div className={cn(
              'mt-1.5 inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full text-xs font-semibold border',
              potential.color, potential.bg, potential.border,
            )}>
              <PotIcon size={11} />
              {potential.label}
            </div>
          </div>
          <button
            onClick={onClear}
            className="flex-shrink-0 text-xs text-slate-400 dark:text-white/30 hover:text-slate-600
                       dark:hover:text-white/60 transition-colors underline"
          >
            Change
          </button>
        </div>
      </GlassCard>

      {/* FANI's styling tip */}
      {result.styling_tip && (
        <GlassCard className="p-4 flex gap-3">
          <Sparkles size={16} className="text-brand-500 flex-shrink-0 mt-0.5" />
          <p className="text-sm text-slate-600 dark:text-white/70 leading-relaxed">
            {result.styling_tip}
          </p>
        </GlassCard>
      )}

      {/* Existing pairs */}
      {result.existing_pairs.length > 0 && (
        <div className="space-y-2">
          <p className="text-xs font-semibold text-slate-500 dark:text-white/40 uppercase tracking-wider px-1">
            Already pairs with
          </p>
          <div className="flex gap-2.5 overflow-x-auto pb-1">
            {result.existing_pairs.map(p => (
              <div key={p.id} className="flex-shrink-0 w-14 space-y-1 text-center">
                <div className="w-14 h-14 rounded-xl overflow-hidden bg-slate-100 dark:bg-white/[0.06]
                                ring-2 ring-emerald-400/40">
                  {p.image_url
                    ? <img src={resolveUploadUrl(p.image_url)} alt={p.name}
                        className="w-full h-full object-cover" />
                    : <div className="w-full h-full flex items-center justify-center">
                        <Package size={18} className="text-slate-300 dark:text-white/20" />
                      </div>
                  }
                </div>
                <p className="text-[10px] text-slate-500 dark:text-white/50 truncate leading-tight">
                  {p.name}
                </p>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Shopping suggestions */}
      <div className="space-y-2">
        <div className="flex items-center gap-2 px-1">
          <ShoppingBag size={14} className="text-brand-500" />
          <p className="text-xs font-semibold text-slate-700 dark:text-white/70 uppercase tracking-wider">
            What to shop for next
          </p>
          <span className="ml-auto text-[11px] text-slate-400 dark:text-white/30">
            {result.suggestions.length} suggestions
          </span>
        </div>
        {result.suggestions.length === 0 ? (
          <GlassCard className="p-6 text-center">
            <CheckCircle2 size={24} className="mx-auto text-emerald-500 mb-2" />
            <p className="text-sm font-medium text-slate-700 dark:text-white/70">
              Your wardrobe already covers this well!
            </p>
            <p className="text-xs text-slate-400 dark:text-white/40 mt-1">
              No major gaps found for this piece.
            </p>
          </GlassCard>
        ) : (
          <div className="space-y-2">
            {result.suggestions.map((s, i) => (
              <SuggestionCard key={`${s.category}-${i}`} s={s} index={i} />
            ))}
          </div>
        )}
      </div>

      {/* CTA */}
      <a
        href="/shopping-check"
        className="flex items-center justify-center gap-2 w-full py-3 rounded-xl text-sm font-semibold
                   bg-gradient-to-r from-emerald-500 to-teal-600 text-white
                   hover:from-emerald-600 hover:to-teal-700 transition-all shadow-md hover:shadow-lg"
      >
        <ShoppingBag size={15} />
        Snap an item to check compatibility
        <ArrowRight size={14} />
      </a>
    </div>
  )
}

// ── Closet item selector ──────────────────────────────────────────────────────

function ClosetItemGrid({
  selectedId,
  onSelect,
}: {
  selectedId: string | null
  onSelect: (id: string) => void
}) {
  const { closetItems } = useApp()
  const [search, setSearch] = useState('')

  const filtered = useMemo(() => {
    const q = search.toLowerCase()
    return (closetItems ?? []).filter(item =>
      !q ||
      item.name.toLowerCase().includes(q) ||
      item.category.toLowerCase().includes(q) ||
      (item.color ?? '').toLowerCase().includes(q),
    )
  }, [closetItems, search])

  return (
    <div className="space-y-4">
      {/* Search */}
      <div className="relative">
        <Search size={15} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400 dark:text-white/30 pointer-events-none" />
        <input
          value={search}
          onChange={e => setSearch(e.target.value)}
          placeholder="Search your closet…"
          className="w-full pl-9 pr-4 py-2.5 text-sm rounded-xl
                     bg-white dark:bg-white/[0.06] border border-slate-200 dark:border-white/10
                     text-slate-800 dark:text-white placeholder:text-slate-400 dark:placeholder:text-white/30
                     focus:outline-none focus:ring-2 focus:ring-brand-400/40 transition"
        />
      </div>

      {filtered.length === 0 ? (
        <GlassCard className="p-8 text-center space-y-2">
          <Shirt size={28} className="mx-auto text-slate-300 dark:text-white/20" />
          <p className="text-sm text-slate-500 dark:text-white/50">
            {(closetItems ?? []).length === 0
              ? 'Your closet is empty — add some items first!'
              : 'No items match your search.'}
          </p>
        </GlassCard>
      ) : (
        <div className="grid grid-cols-3 sm:grid-cols-4 gap-2.5">
          {filtered.map(item => {
            const isSelected = item.id === selectedId
            return (
              <button
                key={item.id}
                onClick={() => onSelect(item.id)}
                className={cn(
                  'relative rounded-2xl overflow-hidden group transition-all duration-200 text-left',
                  'focus:outline-none focus:ring-2 focus:ring-brand-400/50',
                  isSelected
                    ? 'ring-2 ring-brand-500 scale-[0.97]'
                    : 'hover:scale-[0.97] hover:ring-2 hover:ring-brand-300',
                )}
              >
                {/* Image */}
                <div className="aspect-square bg-slate-100 dark:bg-white/[0.06]">
                  {item.image_url
                    ? <img src={resolveUploadUrl(item.image_url)} alt={item.name}
                        className="w-full h-full object-cover" />
                    : <div className="w-full h-full flex items-center justify-center">
                        <Package size={22} className="text-slate-300 dark:text-white/20" />
                      </div>
                  }
                </div>

                {/* Label */}
                <div className="absolute inset-x-0 bottom-0 bg-gradient-to-t from-black/70 to-transparent p-2">
                  <p className="text-[11px] font-semibold text-white truncate leading-tight">
                    {item.name}
                  </p>
                  <p className="text-[10px] text-white/70 capitalize truncate">
                    {item.category}
                  </p>
                </div>

                {/* Selected overlay */}
                {isSelected && (
                  <div className="absolute top-1.5 right-1.5 w-5 h-5 rounded-full bg-brand-500
                                  flex items-center justify-center">
                    <CheckCircle2 size={12} className="text-white" />
                  </div>
                )}
              </button>
            )
          })}
        </div>
      )}
    </div>
  )
}

// ── Main page ─────────────────────────────────────────────────────────────────

export default function ClosetMatch() {
  const [selectedItemId, setSelectedItemId] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [result, setResult] = useState<ClosetMatchResult | null>(null)

  const handleSelect = async (itemId: string) => {
    if (itemId === selectedItemId && result) return   // already loaded
    setSelectedItemId(itemId)
    setResult(null)
    setError(null)
    setLoading(true)
    try {
      const res = await shoppingCheckApi.getClosetMatchSuggestions(itemId)
      setResult(res)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Analysis failed. Please try again.')
    } finally {
      setLoading(false)
    }
  }

  const handleClear = () => {
    setSelectedItemId(null)
    setResult(null)
    setError(null)
  }

  return (
    <div className="max-w-5xl">
      <BackButton fallback="/shopping-check" label="Back to Shop Smart Check" />

      {/* Page header */}
      <div className="flex items-center gap-3 mt-1 mb-6">
        <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-brand-500 to-brand-600
                        flex items-center justify-center shadow-glow-sm">
          <Sparkles size={20} className="text-white" />
        </div>
        <div>
          <h1 className="text-xl font-bold text-slate-900 dark:text-white">Complete My Look</h1>
          <p className="text-sm text-slate-500 dark:text-white/50">
            Pick a wardrobe piece — FANI tells you what to shop for next
          </p>
        </div>
        <a
          href="/shopping-check"
          className="ml-auto flex-shrink-0 flex items-center gap-1.5 px-3 py-2 rounded-xl text-xs
                     font-semibold bg-emerald-50 dark:bg-emerald-900/20 text-emerald-700
                     dark:text-emerald-400 border border-emerald-200 dark:border-emerald-700/40
                     hover:bg-emerald-100 dark:hover:bg-emerald-900/40 transition-colors whitespace-nowrap"
        >
          <ShoppingBag size={13} />
          Shop Smart Check
        </a>
      </div>

      {/* How it works — show only when nothing selected */}
      {!result && !loading && !selectedItemId && (
        <div className="grid grid-cols-3 gap-3 mb-6">
          {[
            { icon: Shirt,       step: '1', label: 'Pick an item',    desc: 'Choose any piece from your closet' },
            { icon: Sparkles,    step: '2', label: 'AI analyses gaps', desc: 'FANI checks outfit compatibility' },
            { icon: ShoppingBag, step: '3', label: 'Shop smarter',    desc: 'Get a prioritised shopping list' },
          ].map(({ icon: Icon, step, label, desc }) => (
            <GlassCard key={step} className="p-3 text-center space-y-1.5">
              <div className="w-7 h-7 rounded-full bg-gradient-to-br from-brand-500 to-brand-600
                              text-white text-xs font-bold flex items-center justify-center mx-auto">
                {step}
              </div>
              <Icon size={18} className="mx-auto text-brand-500 dark:text-brand-400" />
              <p className="text-xs font-semibold text-slate-800 dark:text-white">{label}</p>
              <p className="text-[11px] text-slate-500 dark:text-white/45">{desc}</p>
            </GlassCard>
          ))}
        </div>
      )}

      {/* Two-column layout on desktop */}
      <div className={cn(
        'gap-6',
        result || loading
          ? 'grid grid-cols-1 lg:grid-cols-2'
          : 'block',
      )}>
        {/* Left: closet picker */}
        <div>
          {(result || loading) && (
            <p className="text-xs font-semibold text-slate-500 dark:text-white/40 uppercase tracking-wider mb-3">
              Your Closet
            </p>
          )}
          <ClosetItemGrid selectedId={selectedItemId} onSelect={handleSelect} />
        </div>

        {/* Right: results */}
        <AnimatePresence mode="wait">
          {loading && (
            <motion.div
              key="loading"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              className="flex flex-col items-center justify-center gap-4 py-16"
            >
              <div className="w-14 h-14 rounded-2xl bg-gradient-to-br from-brand-500 to-brand-600
                              flex items-center justify-center shadow-glow-sm">
                <Loader2 size={26} className="text-white animate-spin" />
              </div>
              <div className="text-center">
                <p className="font-semibold text-slate-800 dark:text-white">Analysing your wardrobe…</p>
                <p className="text-sm text-slate-500 dark:text-white/50 mt-1">
                  FANI is finding the perfect pairings
                </p>
              </div>
            </motion.div>
          )}

          {error && !loading && (
            <motion.div
              key="error"
              initial={{ opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0 }}
            >
              <GlassCard className="p-5 space-y-3">
                <div className="flex items-center gap-2 text-red-600 dark:text-red-400">
                  <AlertCircle size={18} />
                  <p className="text-sm font-medium">{error}</p>
                </div>
                <button
                  onClick={handleClear}
                  className="text-sm text-brand-600 dark:text-brand-400 hover:underline"
                >
                  Try another item
                </button>
              </GlassCard>
            </motion.div>
          )}

          {result && !loading && (
            <motion.div
              key="result"
              initial={{ opacity: 0, x: 20 }}
              animate={{ opacity: 1, x: 0 }}
              exit={{ opacity: 0 }}
            >
              {(result || loading) && (
                <p className="text-xs font-semibold text-slate-500 dark:text-white/40 uppercase tracking-wider mb-3">
                  Shopping Guide
                </p>
              )}
              <ResultPanel result={result} onClear={handleClear} />
            </motion.div>
          )}

          {!result && !loading && !error && (
            <motion.div
              key="prompt"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              className="hidden lg:flex flex-col items-center justify-center gap-3 py-16 text-center"
            >
              <div className="w-16 h-16 rounded-2xl border-2 border-dashed border-slate-200
                              dark:border-white/10 flex items-center justify-center">
                <ChevronRight size={24} className="text-slate-300 dark:text-white/20" />
              </div>
              <p className="text-sm text-slate-400 dark:text-white/30">
                Select a closet item to see shopping suggestions
              </p>
            </motion.div>
          )}
        </AnimatePresence>
      </div>
    </div>
  )
}
