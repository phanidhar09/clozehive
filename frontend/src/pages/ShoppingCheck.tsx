import { useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  Camera, Upload, ShoppingCart, CheckCircle, XCircle, AlertCircle,
  Loader2, RotateCcw, Star, TrendingUp, Package, Sparkles, Trash2,
  PlusCircle, Shirt,
} from 'lucide-react'
import BackButton from '@/components/ui/BackButton'
import GlassCard from '@/components/ui/GlassCard'
import PageHeader from '@/components/ui/PageHeader'
import Badge from '@/components/ui/Badge'
import { shoppingCheckApi, type ShoppingCheckResult, type ShoppingHistoryEntry } from '@/lib/api'
import { resolveUploadUrl } from '@/lib/api'
import { cn } from '@/lib/utils'

// ── Score ring ────────────────────────────────────────────────────────────────

function ScoreRing({ score }: { score: number }) {
  const r = 42
  const circ = 2 * Math.PI * r
  const fill = (score / 100) * circ
  const color =
    score >= 75 ? '#10b981' :
    score >= 50 ? '#f59e0b' : '#ef4444'

  return (
    <svg width={110} height={110} className="rotate-[-90deg]">
      <circle cx={55} cy={55} r={r} fill="none" stroke="currentColor"
        strokeWidth={9} className="text-slate-200 dark:text-white/10" />
      <circle cx={55} cy={55} r={r} fill="none" stroke={color}
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
          fill: color,
        }}>
        {Math.round(score)}
      </text>
    </svg>
  )
}

// ── Recommendation badge ──────────────────────────────────────────────────────

const REC_CONFIG = {
  buy: {
    label: 'Buy it!',
    icon: CheckCircle,
    classes: 'bg-emerald-100 text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-400',
    border: 'border-emerald-200 dark:border-emerald-700/40',
  },
  consider: {
    label: 'Think about it',
    icon: AlertCircle,
    classes: 'bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-400',
    border: 'border-amber-200 dark:border-amber-700/40',
  },
  skip: {
    label: 'Skip it',
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

function ResultCard({
  result,
  previewUrl,
  onReset,
}: {
  result: ShoppingCheckResult
  previewUrl: string
  onReset: () => void
}) {
  const [bought, setBought] = useState<boolean | null>(null)
  const rec = REC_CONFIG[result.buy_recommendation]
  const RecIcon = rec.icon

  const analysis = result.item_analysis as Record<string, unknown>

  return (
    <div className="space-y-5">
      {/* Header strip */}
      <GlassCard className="p-5">
        <div className="flex gap-5 items-start">
          {/* Item photo */}
          <div className="w-28 h-28 rounded-2xl overflow-hidden bg-slate-100 dark:bg-white/[0.06] flex-shrink-0 shadow-md">
            <img src={previewUrl} alt="Shopping item" className="w-full h-full object-cover" />
          </div>

          {/* Score + recommendation */}
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-3 flex-wrap">
              <ScoreRing score={result.buy_score} />
              <div>
                <div className={cn(
                  'inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full text-sm font-bold border',
                  rec.classes, rec.border,
                )}>
                  <RecIcon size={15} />
                  {rec.label}
                </div>
                <p className="mt-2 text-[11px] text-slate-500 dark:text-white/40 uppercase tracking-wider font-semibold">
                  Buy Score
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

      {/* Reasoning */}
      <GlassCard className="p-4 space-y-2">
        <div className="flex items-center gap-2">
          <Sparkles size={15} className="text-brand-500" />
          <h3 className="text-sm font-semibold text-slate-800 dark:text-white">FANI's Take</h3>
        </div>
        <p className="text-sm text-slate-600 dark:text-white/70 leading-relaxed">{result.reasoning}</p>
      </GlassCard>

      {/* Matched closet items */}
      {result.matched_items.length > 0 && (
        <GlassCard className="p-4 space-y-3">
          <div className="flex items-center gap-2">
            <Package size={15} className="text-slate-500 dark:text-white/50" />
            <h3 className="text-sm font-semibold text-slate-800 dark:text-white">
              {result.matched_items.some(m => m.is_duplicate)
                ? 'Similar items in your closet'
                : 'Pairs well with these items'}
            </h3>
          </div>
          <div className="flex gap-3 overflow-x-auto pb-1">
            {result.matched_items.map(item => (
              <div key={item.id} className="flex-shrink-0 w-20 space-y-1">
                <div className={cn(
                  'w-20 h-20 rounded-xl overflow-hidden bg-slate-100 dark:bg-white/[0.06] relative',
                  item.is_duplicate && 'ring-2 ring-red-400',
                )}>
                  {item.image_url
                    ? <img src={resolveUploadUrl(item.image_url)} alt={item.name}
                        className="w-full h-full object-cover" />
                    : <div className="w-full h-full flex items-center justify-center">
                        <Package size={22} className="text-slate-300 dark:text-white/20" />
                      </div>
                  }
                  {item.is_duplicate && (
                    <div className="absolute inset-0 bg-red-500/20 flex items-center justify-center rounded-xl">
                      <span className="text-[9px] font-bold text-red-600 dark:text-red-400 bg-white dark:bg-slate-900 px-1 rounded">
                        OWNED
                      </span>
                    </div>
                  )}
                </div>
                <p className="text-[10px] text-slate-600 dark:text-white/60 truncate text-center leading-tight">
                  {item.name}
                </p>
                <p className="text-[10px] text-slate-400 dark:text-white/30 text-center">
                  {Math.round(item.similarity_score * 100)}% match
                </p>
              </div>
            ))}
          </div>
        </GlassCard>
      )}

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

      {/* Check another */}
      <button
        onClick={onReset}
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

  const rec = REC_CONFIG[entry.buy_recommendation] ?? REC_CONFIG.consider
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
          <div className="w-14 h-14 rounded-xl overflow-hidden bg-slate-100 dark:bg-white/[0.06] flex-shrink-0">
            <img src={resolveUploadUrl(entry.image_url)} alt="" className="w-full h-full object-cover" />
          </div>
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
              Score: {Math.round(entry.buy_score)}
            </span>
            {entry.purchase_decision !== null && (
              <span className={cn(
                'text-[11px] px-2 py-0.5 rounded-full font-medium',
                entry.purchase_decision
                  ? 'bg-emerald-100 text-emerald-700 dark:bg-emerald-900/20 dark:text-emerald-400'
                  : 'bg-slate-100 text-slate-500 dark:bg-white/[0.06] dark:text-white/40',
              )}>
                {entry.purchase_decision ? 'Bought' : 'Skipped'}
              </span>
            )}
          </div>
        </div>
        <div className="flex items-center gap-1 flex-shrink-0">
          <div className="text-right">
            <p className="text-lg font-bold" style={{
              color: entry.buy_score >= 75 ? '#10b981' : entry.buy_score >= 50 ? '#f59e0b' : '#ef4444',
            }}>
              {Math.round(entry.buy_score)}
            </p>
            <p className="text-[10px] text-slate-400 dark:text-white/30">/ 100</p>
          </div>
          {checkId && (
            <button
              type="button"
              onClick={() => setConfirming(c => !c)}
              disabled={deleting}
              title="Delete this check"
              className={cn(
                'p-2 rounded-lg transition-all',
                confirming
                  ? 'text-red-500 bg-red-50 dark:bg-red-900/20'
                  : 'text-slate-400 opacity-0 group-hover:opacity-100 hover:text-red-500 hover:bg-red-50 dark:hover:bg-red-900/20',
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
      className={cn(
        'p-10 flex flex-col items-center justify-center gap-4 cursor-pointer',
        'border-2 border-dashed transition-colors',
        dragging
          ? 'border-brand-400 bg-brand-50/50 dark:bg-brand-900/10'
          : 'border-slate-300 dark:border-white/20 hover:border-brand-400',
      )}
      onClick={() => inputRef.current?.click()}
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
          Point your camera at any store item to get an instant buy recommendation
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

// ── Main page ─────────────────────────────────────────────────────────────────

export default function ShoppingCheck() {
  const [preview, setPreview] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [result, setResult] = useState<ShoppingCheckResult | null>(null)
  const [history, setHistory] = useState<ShoppingHistoryEntry[] | null>(null)
  const [historyLoading, setHistoryLoading] = useState(false)

  const loadHistory = async () => {
    setHistoryLoading(true)
    try {
      setHistory(await shoppingCheckApi.getHistory(10))
    } catch {
      /* silently ignore */
    } finally {
      setHistoryLoading(false)
    }
  }

  const handleFile = async (file: File) => {
    setPreview(URL.createObjectURL(file))
    setResult(null)
    setError(null)
    setLoading(true)
    try {
      const res = await shoppingCheckApi.checkItem(file)
      setResult(res)
      // Refresh history after a new check
      loadHistory()
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Analysis failed. Please try again.')
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
    setHistory(prev => prev?.filter(e => historyCheckId(e) !== checkId) ?? prev)
  }

  // Load history on first render
  if (history === null && !historyLoading) {
    loadHistory()
  }

  return (
    <div className="max-w-2xl space-y-6">
      <BackButton fallback="/dashboard" label="Back to Dashboard" />

      {/* Page header */}
      <PageHeader
        icon={<ShoppingCart size={18} />}
        chipClassName="bg-gradient-to-br from-green-500 to-emerald-600 shadow-glow-sm"
        iconColor="text-white"
        title="Shop with FANI"
        subtitle="Snap any item in-store — FANI tells you if it belongs in your closet"
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
        <div className="grid grid-cols-3 gap-3">
          {[
            { icon: Camera, label: 'Snap a photo', desc: 'Point at any item you like' },
            { icon: Star, label: 'Get a score', desc: '0–100 buy recommendation' },
            { icon: TrendingUp, label: 'See the impact', desc: 'How it completes your closet' },
          ].map(({ icon: Icon, label, desc }) => (
            <GlassCard key={label} className="p-3 text-center space-y-1.5">
              <Icon size={20} className="mx-auto text-brand-500 dark:text-brand-400" />
              <p className="text-xs font-semibold text-slate-800 dark:text-white">{label}</p>
              <p className="text-[11px] text-slate-500 dark:text-white/45">{desc}</p>
            </GlassCard>
          ))}
        </div>
      )}

      {/* Upload zone */}
      {!result && !loading && !error && <UploadZone onFile={handleFile} />}

      {/* Loading state */}
      {loading && preview && (
        <GlassCard className="p-8 flex flex-col items-center gap-4">
          <div className="relative">
            <div className="w-24 h-24 rounded-2xl overflow-hidden">
              <img src={preview} alt="" className="w-full h-full object-cover" />
            </div>
            <div className="absolute inset-0 bg-black/40 rounded-2xl flex items-center justify-center">
              <Loader2 size={28} className="text-white animate-spin" />
            </div>
          </div>
          <div className="text-center space-y-1">
            <p className="font-semibold text-slate-800 dark:text-white">Analysing your item…</p>
            <p className="text-sm text-slate-500 dark:text-white/50">
              Checking against your closet and computing compatibility
            </p>
          </div>
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
      {result && preview && (
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
    </div>
  )
}
