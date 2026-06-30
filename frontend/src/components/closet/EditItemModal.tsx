import { useState } from 'react'
import { Loader2, Save, X, Heart } from 'lucide-react'
import { closetApi } from '@/lib/api'
import Modal from '@/components/ui/Modal'
import type { ClosetItem } from '@/types'
import { cn } from '@/lib/utils'

// ── Constants ─────────────────────────────────────────────────────────────────

const CATEGORIES = [
  'tops', 'bottoms', 'shoes', 'outerwear', 'dresses', 'accessories', 'other',
] as const

const SEASONS = ['spring', 'summer', 'fall', 'winter'] as const
const OCCASIONS = ['casual', 'formal', 'work', 'sport', 'evening', 'travel'] as const
// Fit drives outfit proportion matching (see outfit_compatibility.fit_volume).
// '' = unspecified; the rest map onto the engine's slim/regular/relaxed volume scale.
const FITS = ['slim', 'tailored', 'regular', 'relaxed', 'oversized'] as const

// ── Helpers ───────────────────────────────────────────────────────────────────

function parseSeason(season?: string | string[]): string[] {
  if (!season) return []
  if (Array.isArray(season)) return season.filter(Boolean)
  return season.split(',').map(s => s.trim()).filter(Boolean)
}

function toggleArrayItem(arr: string[], value: string): string[] {
  return arr.includes(value) ? arr.filter(v => v !== value) : [...arr, value]
}

// ── Field components ──────────────────────────────────────────────────────────

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex flex-col gap-1.5">
      <label className="text-[11px] font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400">
        {label}
      </label>
      {children}
    </div>
  )
}

const inputCls = 'w-full rounded-xl border border-cream-300 dark:border-white/10 bg-white dark:bg-slate-800 px-3 py-2 text-sm text-slate-800 dark:text-white placeholder-slate-400 dark:placeholder-white/30 focus:outline-none focus:ring-2 focus:ring-brand-400/50 transition'

function TogglePill({
  label, active, onClick,
}: { label: string; active: boolean; onClick: () => void }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        'px-3 py-1.5 rounded-full text-xs font-semibold transition-all capitalize',
        active
          ? 'bg-brand-500 text-white shadow-sm shadow-brand-500/30'
          : 'bg-slate-100 dark:bg-white/[0.06] text-slate-600 dark:text-slate-300 hover:bg-slate-200 dark:hover:bg-white/10 border border-slate-200 dark:border-white/10',
      )}
    >
      {label}
    </button>
  )
}

// ── Main component ────────────────────────────────────────────────────────────

interface Props {
  item: ClosetItem
  open: boolean
  onClose: () => void
  onSaved: (updated: ClosetItem) => void
}

export default function EditItemModal({ item, open, onClose, onSaved }: Props) {
  const [form, setForm] = useState({
    name:     item.name,
    brand:    item.brand     ?? '',
    category: item.category  ?? 'tops',
    color:    item.color     ?? '',
    fabric:   item.fabric    ?? '',
    pattern:  item.pattern   ?? '',
    size:     item.size      ?? '',
    fit:      item.fit       ?? '',
    price:    item.price != null ? String(item.price) : '',
    notes:      item.notes       ?? '',
    seasons:    parseSeason(item.season),
    occasions:  item.occasion    ?? [],
    is_favorite: item.is_favorite ?? false,
  })

  const [saving, setSaving] = useState(false)
  const [error,  setError]  = useState<string | null>(null)

  const set = <K extends keyof typeof form>(key: K, value: typeof form[K]) =>
    setForm(prev => ({ ...prev, [key]: value }))

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!form.name.trim()) { setError('Name is required.'); return }
    setError(null)
    setSaving(true)
    try {
      const patch: Partial<ClosetItem> = {
        name:     form.name.trim(),
        brand:    form.brand.trim()   || undefined,
        category: form.category,
        color:    form.color.trim()   || undefined,
        fabric:   form.fabric.trim()  || undefined,
        pattern:  form.pattern.trim() || undefined,
        size:     form.size.trim()    || undefined,
        fit:      form.fit            || undefined,
        price:    form.price !== '' ? Number(form.price) : undefined,
        notes:    form.notes.trim()   || undefined,
        season:      form.seasons.length > 0 ? form.seasons : undefined,
        occasion:    form.occasions,
        is_favorite: form.is_favorite,
      }
      const updated = await closetApi.update(item.id, patch)
      onSaved(updated)
      onClose()
    } catch {
      setError('Failed to save changes. Please try again.')
    } finally {
      setSaving(false)
    }
  }

  return (
    <Modal open={open} onClose={onClose} size="lg" title="Edit Item">
      <form onSubmit={handleSubmit} className="space-y-5">

        {/* ── Image preview ── */}
        {item.image_url && (
          <div className="flex justify-center">
            <img
              src={item.image_url}
              alt={item.name}
              className="h-28 w-auto max-w-[120px] rounded-2xl object-cover border border-cream-200 dark:border-white/10 shadow-sm"
            />
          </div>
        )}

        {/* ── Two-column grid ── */}
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">

          <Field label="Name *">
            <input
              className={inputCls}
              value={form.name}
              onChange={e => set('name', e.target.value)}
              placeholder="e.g. White Oxford Shirt"
              required
            />
          </Field>

          <Field label="Brand">
            <input
              className={inputCls}
              value={form.brand}
              onChange={e => set('brand', e.target.value)}
              placeholder="e.g. Zara, H&M…"
            />
          </Field>

          <Field label="Category">
            <select
              className={cn(inputCls, 'appearance-none capitalize')}
              value={form.category}
              onChange={e => set('category', e.target.value)}
            >
              {CATEGORIES.map(c => (
                <option key={c} value={c} className="capitalize">{c.charAt(0).toUpperCase() + c.slice(1)}</option>
              ))}
            </select>
          </Field>

          <Field label="Color">
            <input
              className={inputCls}
              value={form.color}
              onChange={e => set('color', e.target.value)}
              placeholder="e.g. Navy Blue"
            />
          </Field>

          <Field label="Fabric">
            <input
              className={inputCls}
              value={form.fabric}
              onChange={e => set('fabric', e.target.value)}
              placeholder="e.g. Cotton, Linen…"
            />
          </Field>

          <Field label="Pattern">
            <input
              className={inputCls}
              value={form.pattern}
              onChange={e => set('pattern', e.target.value)}
              placeholder="e.g. Solid, Striped…"
            />
          </Field>

          <Field label="Size">
            <input
              className={inputCls}
              value={form.size}
              onChange={e => set('size', e.target.value)}
              placeholder="e.g. M, 32, UK 10…"
            />
          </Field>

          <Field label="Fit">
            <select
              className={cn(inputCls, 'appearance-none capitalize')}
              value={form.fit}
              onChange={e => set('fit', e.target.value)}
            >
              <option value="">Unspecified</option>
              {FITS.map(f => (
                <option key={f} value={f} className="capitalize">
                  {f.charAt(0).toUpperCase() + f.slice(1)}
                </option>
              ))}
            </select>
          </Field>

          <Field label="Purchase Price ($)">
            <input
              className={inputCls}
              type="number"
              min="0"
              step="0.01"
              value={form.price}
              onChange={e => set('price', e.target.value)}
              placeholder="e.g. 49.99"
            />
          </Field>
        </div>

        {/* ── Seasons ── */}
        <Field label="Season">
          <div className="flex gap-2 flex-wrap">
            {SEASONS.map(s => (
              <TogglePill
                key={s}
                label={s}
                active={form.seasons.includes(s)}
                onClick={() => set('seasons', toggleArrayItem(form.seasons, s))}
              />
            ))}
          </div>
        </Field>

        {/* ── Occasions ── */}
        <Field label="Occasions">
          <div className="flex gap-2 flex-wrap">
            {OCCASIONS.map(o => (
              <TogglePill
                key={o}
                label={o}
                active={form.occasions.includes(o)}
                onClick={() => set('occasions', toggleArrayItem(form.occasions, o))}
              />
            ))}
          </div>
        </Field>

        {/* ── Notes ── */}
        <Field label="Notes">
          <textarea
            className={cn(inputCls, 'resize-none')}
            rows={3}
            value={form.notes}
            onChange={e => set('notes', e.target.value)}
            placeholder="Fit notes, alterations, care tips…"
          />
        </Field>

        {/* ── Favourite ── */}
        <button
          type="button"
          onClick={() => set('is_favorite', !form.is_favorite)}
          className={cn(
            'flex items-center gap-3 px-4 py-3 rounded-xl border text-sm font-semibold transition-all w-full',
            form.is_favorite
              ? 'bg-pink-50 dark:bg-pink-900/20 border-pink-200 dark:border-pink-700/50 text-pink-600 dark:text-pink-400'
              : 'bg-white dark:bg-slate-800 border-cream-300 dark:border-white/10 text-slate-600 dark:text-slate-300 hover:border-pink-200 dark:hover:border-pink-700/50',
          )}
        >
          <Heart
            size={16}
            className={form.is_favorite ? 'fill-pink-500 text-pink-500' : 'text-slate-400'}
          />
          {form.is_favorite ? 'Saved as favourite' : 'Add to favourites'}
        </button>

        {/* ── Error ── */}
        {error && (
          <p className="flex items-center gap-1.5 rounded-xl border border-red-200 bg-red-50 px-3 py-2 text-xs text-red-600 dark:border-red-500/30 dark:bg-red-500/10 dark:text-red-400">
            <X size={12} className="flex-shrink-0" /> {error}
          </p>
        )}

        {/* ── Actions ── */}
        <div className="flex gap-2 pt-1">
          <button
            type="button"
            onClick={onClose}
            disabled={saving}
            className="flex-1 rounded-xl border border-slate-200 dark:border-white/10 bg-white dark:bg-white/[0.04] px-4 py-2.5 text-sm font-semibold text-slate-600 dark:text-white/70 hover:bg-slate-50 dark:hover:bg-white/[0.07] transition-colors disabled:opacity-50"
          >
            Cancel
          </button>
          <button
            type="submit"
            disabled={saving}
            className="flex flex-1 items-center justify-center gap-2 rounded-xl bg-gradient-to-r from-brand-500 to-brand-600 px-4 py-2.5 text-sm font-semibold text-white shadow-sm shadow-brand-500/25 hover:opacity-90 transition-opacity disabled:opacity-50"
          >
            {saving ? <Loader2 size={14} className="animate-spin" /> : <Save size={14} />}
            {saving ? 'Saving…' : 'Save Changes'}
          </button>
        </div>

      </form>
    </Modal>
  )
}
