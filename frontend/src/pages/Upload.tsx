import { useState, useRef, useCallback, useMemo } from 'react'
import {
  Image, Sparkles, CheckCircle, Circle, X, ChevronLeft, ChevronRight,
  AlertTriangle, Info, ShieldCheck, Pencil, Plus, Check,
} from 'lucide-react'
import { Link } from 'react-router-dom'
import Button from '@/components/ui/Button'
import BackButton from '@/components/ui/BackButton'
import PageHeader from '@/components/ui/PageHeader'
import Input, { Select } from '@/components/ui/Input'
import Badge from '@/components/ui/Badge'
import { useApp } from '@/store'
import { notificationStore, toastStore } from '@/store/notificationStore'
import { closetApi, closetSimilarityApi, resolveUploadUrl, type ClosetPreviewItem, type SimilarClosetItem } from '@/lib/api'
import { CONDITION_OPTIONS, CONDITION_LABELS, type ConditionGrade } from '@/types'
import { cn } from '@/lib/utils'
import { CLOSET_SEASONS, CLOSET_OCCASIONS, CLOSET_CULTURAL_OCCASIONS } from '@/features/closet/constants'
import { InlineError } from '@/components/system/InlineError'
import { LoadingSpinner } from '@/components/system/LoadingSpinner'
import SimilarityWarningBanner from '@/components/closet/SimilarityWarningBanner'

const MAX_FILES = 20
const MAX_FILE_SIZE = 10 * 1024 * 1024 // 10MB — must match the helper text shown in the dropzone

/** Adds a token to a comma-separated string if not already present. */
function toggleToken(value: string, token: string): string {
  const list = parseCommaList(value)
  return list.includes(token)
    ? list.filter(t => t !== token).join(', ')
    : [...list, token].join(', ')
}

/** True when two comma-lists contain the same tokens regardless of order/case. */
function sameTokens(a: string, b: string): boolean {
  const norm = (s: string) => parseCommaList(s).map(t => t.toLowerCase()).sort()
  const pa = norm(a), pb = norm(b)
  return pa.length === pb.length && pa.every((v, i) => v === pb[i])
}

/** 'ai' = still FANI's value · 'edited' = user overrode it · null = AI left it blank. */
type AIProvenance = 'ai' | 'edited' | null
function aiFieldState(d: ItemDraft, key: AIFieldKey): AIProvenance {
  const original = (d.ai[key] ?? '').trim()
  if (!original) return null
  const current = ((d[key] as string) ?? '').trim()
  const unchanged = key === 'seasonStr' || key === 'occasionStr'
    ? sameTokens(original, current)
    : original.toLowerCase() === current.toLowerCase()
  return unchanged ? 'ai' : 'edited'
}

/** Field label with an AI-provenance marker — transparency about AI-generated content. */
function AIFieldLabel({ label, state, htmlFor }: { label: string; state: AIProvenance; htmlFor?: string }) {
  return (
    <div className="flex items-center justify-between gap-2 mb-1">
      <label htmlFor={htmlFor} className="label mb-0">{label}</label>
      {state === 'ai' && (
        <span
          title="Auto-filled by FANI from your photo. Edit any field to override it."
          className="inline-flex items-center gap-0.5 text-[9px] font-bold uppercase tracking-wide text-brand-500 dark:text-brand-400"
        >
          <Sparkles size={9} /> AI
        </span>
      )}
      {state === 'edited' && (
        <span
          title="You changed this from FANI's suggestion."
          className="inline-flex items-center gap-0.5 text-[9px] font-bold uppercase tracking-wide text-slate-400"
        >
          <Pencil size={9} /> Edited
        </span>
      )}
    </div>
  )
}

/** Text input carrying an AI-provenance marker above it. `id` ties the label to the field (a11y). */
function AIInput({
  label, aiState, id, leftIcon, ...rest
}: { label: string; aiState: AIProvenance; id: string; leftIcon?: React.ReactNode } & React.InputHTMLAttributes<HTMLInputElement>) {
  return (
    <div className="w-full">
      <AIFieldLabel label={label} state={aiState} htmlFor={id} />
      <Input id={id} leftIcon={leftIcon} {...rest} />
    </div>
  )
}

/** Tiered confidence presentation — show confidence levels clearly, handle uncertainty. */
function confidenceTier(c: number) {
  if (c >= 0.8) return { label: 'High confidence', dot: 'bg-emerald-500', text: 'text-emerald-600 dark:text-emerald-400' }
  if (c >= LOW_CONFIDENCE_THRESHOLD) return { label: 'Medium confidence', dot: 'bg-amber-500', text: 'text-amber-600 dark:text-amber-400' }
  return { label: 'Low confidence', dot: 'bg-red-500', text: 'text-red-600 dark:text-red-400' }
}

/**
 * Free-text field with one-click suggestion chips — recognition over recall.
 * Mirrors the pill pattern used in the closet editor for consistency.
 */
function TokenField({
  label, value, suggestions, extraSuggestions, extraSuggestionsLabel, placeholder, aiState, id, onChange,
}: {
  label: string
  value: string
  suggestions: readonly string[]
  extraSuggestions?: readonly string[]
  extraSuggestionsLabel?: string
  placeholder?: string
  aiState?: AIProvenance
  id: string
  onChange: (v: string) => void
}) {
  const [showExtra, setShowExtra] = useState(false)
  const active = parseCommaList(value)

  const renderChips = (chips: readonly string[]) =>
    chips.map(s => {
      const isOn = active.includes(s)
      return (
        <button
          key={s}
          type="button"
          onClick={() => onChange(toggleToken(value, s))}
          aria-pressed={isOn}
          className={cn(
            'px-2.5 py-1 rounded-full text-[11px] font-semibold capitalize transition-colors border',
            isOn
              ? 'bg-brand-500 text-white border-brand-500'
              : 'bg-white dark:bg-slate-800 text-slate-500 dark:text-slate-400 border-slate-200 dark:border-slate-700 hover:border-brand-300 dark:hover:border-brand-600',
          )}
        >
          {s}
        </button>
      )
    })

  return (
    <div>
      <AIFieldLabel label={label} state={aiState ?? null} htmlFor={id} />
      <Input id={id} value={value} placeholder={placeholder} onChange={e => onChange(e.target.value)} />
      <div className="flex flex-wrap gap-1.5 mt-2">
        {renderChips(suggestions)}
      </div>
      {extraSuggestions && extraSuggestions.length > 0 && (
        <div className="mt-1.5">
          <button
            type="button"
            onClick={() => setShowExtra(v => !v)}
            className="text-[10px] font-semibold text-brand-500 dark:text-brand-400 hover:underline"
          >
            {showExtra ? '▲ Hide' : '▼'} {extraSuggestionsLabel ?? 'More'}
          </button>
          {showExtra && (
            <div className="flex flex-wrap gap-1.5 mt-1.5">
              {renderChips(extraSuggestions)}
            </div>
          )}
        </div>
      )}
    </div>
  )
}

const CATEGORY_OPTIONS = [
  { value: 'tops', label: 'Tops' },
  { value: 'bottoms', label: 'Bottoms' },
  { value: 'shoes', label: 'Shoes' },
  { value: 'outerwear', label: 'Outerwear' },
  { value: 'dresses', label: 'Dresses' },
  { value: 'accessories', label: 'Accessories' },
  { value: 'other', label: 'Other' },
]

// Garment fit — drives outfit proportion matching (outfit_compatibility.fit_volume).
// '' = unspecified; values map onto the engine's slim/regular/relaxed volume scale.
const FIT_OPTIONS = ['slim', 'tailored', 'regular', 'relaxed', 'oversized'] as const
const FIT_OPTIONS_SELECT = [
  { value: '', label: 'Unspecified' },
  ...FIT_OPTIONS.map(f => ({ value: f, label: f.charAt(0).toUpperCase() + f.slice(1) })),
]

// Garment condition — a soft occasion-aware styling signal (see backend Condition enum).
const CONDITION_OPTIONS_SELECT = CONDITION_OPTIONS.map(c => ({ value: c, label: CONDITION_LABELS[c] }))

// Below this AI detection confidence we visually flag the item for manual review.
// Mirrors the backend's bulk-vision low-confidence threshold (vision_service.py).
const LOW_CONFIDENCE_THRESHOLD = 0.5

function parseCommaList(s: string): string[] {
  return s
    .split(/[,;]/)
    .map(p => p.trim())
    .filter(Boolean)
}

function draftsFromPreviewItems(items: ClosetPreviewItem[] | null | undefined): ItemDraft[] {
  return (items ?? []).map(it => {
    const name = it.name
    const category = it.category
    const color = it.color ?? ''
    const material = it.material ?? ''
    const pattern = it.pattern ?? ''
    const seasonStr = (it.season ?? []).join(', ')
    const occasionStr = (it.occasions ?? []).join(', ')
    const notes = it.description ?? ''
    return {
      slot_index: it.slot_index,
      temp_id: it.temp_id,
      detected_item_id: it.detected_item_id ?? it.temp_id,
      selected: true,
      name, category, color, material, pattern, seasonStr, occasionStr, notes,
      subcategory: it.subcategory ?? '',
      brand: it.brand ?? '',
      size: '',
      fit: it.fit ?? '',
      condition: 'good' as ConditionGrade,
      priceStr: '',
      preview_image_url: it.preview_image_url,
      confidence: it.confidence,
      background_removed: it.background_removed,
      // Snapshot of what FANI originally detected — lets us flag fields the user overrides.
      ai: { name, category, color, material, pattern, seasonStr, occasionStr, notes },
    }
  })
}

type ItemDraft = {
  slot_index: number
  temp_id: string
  /** Stable UUID from backend detection — used as React key and confirm validation. */
  detected_item_id: string
  selected: boolean
  name: string
  category: string
  subcategory: string
  color: string
  material: string
  pattern: string
  seasonStr: string
  occasionStr: string
  notes: string
  brand: string
  size: string
  fit: string
  condition: ConditionGrade
  priceStr: string
  preview_image_url: string
  confidence: number
  background_removed: boolean
  /** Original AI-detected values, for provenance markers (AI vs Edited). */
  ai: {
    name: string
    category: string
    color: string
    material: string
    pattern: string
    seasonStr: string
    occasionStr: string
    notes: string
  }
}

/** Which AI-detectable fields carry provenance markers, and their human labels. */
type AIFieldKey = keyof ItemDraft['ai']

type PreviewGroup = {
  filename: string
  sessionId: string
  drafts: ItemDraft[]
  saved?: boolean
}

type BoardItem = {
  sessionId: string
  filename: string
  draft: ItemDraft
  saved: boolean
}

type SimilarState = { loading: boolean; error: boolean; items: SimilarClosetItem[] }

/** Secondary fields hidden behind each card's "More details" disclosure. */
const MORE_KEYS = ['material', 'pattern', 'brand', 'size', 'fit', 'priceStr', 'seasonStr', 'occasionStr', 'notes'] as const

/**
 * One detected item on the review board. Collapsed, it shows the quick-triage
 * fields (name / category / colour) plus an at-a-glance status; expanded, it
 * reveals every editable field — preserving AI provenance, confidence, condition
 * and the similarity warning from the original wizard.
 */
function ItemReviewCard({
  d, filename, showFilename, similar, disabled, onPatch,
}: {
  d: ItemDraft
  filename: string
  showFilename: boolean
  similar: SimilarState
  disabled: boolean
  onPatch: (patch: Partial<ItemDraft>) => void
}) {
  const [expanded, setExpanded] = useState(false)
  const tier = confidenceTier(d.confidence)
  const imgSrc = resolveUploadUrl(d.preview_image_url) ?? d.preview_image_url
  const lowConf = d.confidence < LOW_CONFIDENCE_THRESHOLD
  const hasSimilar = similar.items.length > 0
  const needsAttention = d.selected && (lowConf || hasSimilar)
  const filledCount = MORE_KEYS.filter(k => (d[k] as string).trim()).length
  const uid = d.detected_item_id

  return (
    <div
      className={cn(
        'card p-0 overflow-hidden flex flex-col transition-all duration-300',
        !expanded && 'hover:-translate-y-0.5 hover:shadow-card-hover',
        !d.selected && 'opacity-55',
        needsAttention && 'ring-1 ring-amber-300 dark:ring-amber-500/40',
      )}
    >
      {/* ── Summary: image-forward product card ── */}
      <div className="p-3.5 flex gap-4">
        <div className="w-[92px] h-28 shrink-0 rounded-xl overflow-hidden border border-cream-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-800/60">
          {imgSrc ? (
            <img src={imgSrc} alt={d.name} className="w-full h-full object-cover" />
          ) : (
            <div
              className="w-full h-full flex items-center justify-center text-[10px] text-slate-400 dark:text-slate-500"
              style={{ backgroundImage: 'repeating-linear-gradient(45deg, rgba(148,163,184,0.14) 0 6px, transparent 6px 12px)' }}
            >
              cutout
            </div>
          )}
        </div>

        <div className="flex-1 min-w-0 flex flex-col">
          <input
            aria-label="Item name"
            value={d.name}
            disabled={disabled}
            placeholder="Name this item"
            onChange={e => onPatch({ name: e.target.value })}
            className="w-full -mx-1 px-1 py-0.5 rounded-md bg-transparent border-0 text-[15px] font-semibold leading-snug text-slate-800 dark:text-slate-100 placeholder-slate-400 focus:outline-none hover:bg-cream-100/70 dark:hover:bg-white/[0.05] focus:bg-cream-100 dark:focus:bg-white/[0.06] transition-colors"
          />
          <div className="mt-1.5 flex items-center gap-2 text-sm text-slate-500 dark:text-slate-400 min-w-0">
            <span className="capitalize truncate">{CATEGORY_OPTIONS.find(o => o.value === d.category)?.label ?? d.category}</span>
            {d.color.trim() && (
              <>
                <span className="text-slate-300 dark:text-slate-600">·</span>
                <span className="inline-flex items-center gap-1.5 min-w-0">
                  <span className="block w-3 h-3 rounded-full border border-slate-300 dark:border-slate-600 shrink-0" style={{ backgroundColor: d.color.trim() }} />
                  <span className="capitalize truncate">{d.color}</span>
                </span>
              </>
            )}
          </div>
          {needsAttention && (
            <div className="mt-auto pt-2">
              <span className="inline-flex items-center gap-1 text-[11px] font-semibold text-amber-600 dark:text-amber-400">
                <AlertTriangle size={11} /> {hasSimilar ? 'Possible duplicate' : 'Low confidence'}
              </span>
            </div>
          )}
        </div>
      </div>

      {/* ── Expanded details — full editable form with AI provenance intact ── */}
      {expanded && (
        <div className="px-4 pb-4 space-y-3 border-t border-cream-100 dark:border-slate-700 pt-3">
          {/* Confidence + meta — kept here so the board stays calm */}
          <div className="flex flex-wrap items-center gap-1.5">
            <span
              title="How sure FANI is it identified this item correctly."
              className={cn(
                'inline-flex items-center gap-1.5 rounded-full border px-2 py-0.5 text-[10px] font-semibold',
                'border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800',
                tier.text,
              )}
            >
              <span className={cn('w-1.5 h-1.5 rounded-full', tier.dot)} />
              {tier.label} · {(d.confidence * 100).toFixed(0)}%
            </span>
            {d.subcategory.trim() ? <Badge variant="gray">{d.subcategory}</Badge> : null}
            {d.background_removed && <Badge variant="gray">Cutout</Badge>}
            {showFilename && (
              <span className="text-[10px] text-slate-400 truncate max-w-[140px]" title={filename}>{filename}</span>
            )}
          </div>

          {lowConf && (
            <p className="flex items-start gap-1 text-[11px] text-amber-700 dark:text-amber-300 bg-amber-50 dark:bg-amber-900/20 border border-amber-200 dark:border-amber-800 rounded-md px-2 py-1">
              <AlertTriangle className="h-3 w-3 mt-0.5 shrink-0" />
              <span>FANI wasn't very sure about this one — please double-check the name, category, and colour before saving.</span>
            </p>
          )}

          <SimilarityWarningBanner
            loading={similar.loading}
            error={similar.error}
            items={similar.items}
            itemName={d.name}
            newItemImageUrl={imgSrc}
          />

          <div className="grid gap-2 sm:grid-cols-2">
            <div className="w-full">
              <AIFieldLabel label="Category" state={aiFieldState(d, 'category')} htmlFor={`f-${uid}-category`} />
              <Select
                id={`f-${uid}-category`}
                options={CATEGORY_OPTIONS}
                value={d.category}
                onChange={e => onPatch({ category: e.target.value })}
              />
            </div>
            <AIInput
              label="Color"
              id={`f-${uid}-color`}
              aiState={aiFieldState(d, 'color')}
              value={d.color}
              leftIcon={
              <span
                className="block w-3.5 h-3.5 rounded-full border border-slate-300 dark:border-slate-600 shadow-inner"
                style={{ backgroundColor: d.color.trim() || 'transparent' }}
              />
            }
            onChange={e => onPatch({ color: e.target.value })}
            />
          </div>

          <TokenField
            label="Season"
            id={`f-${uid}-season`}
            value={d.seasonStr}
            suggestions={CLOSET_SEASONS}
            placeholder="spring, summer"
            aiState={aiFieldState(d, 'seasonStr')}
            onChange={v => onPatch({ seasonStr: v })}
          />
          <TokenField
            label="Occasion"
            id={`f-${uid}-occasion`}
            value={d.occasionStr}
            suggestions={CLOSET_OCCASIONS}
            extraSuggestions={CLOSET_CULTURAL_OCCASIONS}
            extraSuggestionsLabel="Cultural & religious occasions"
            placeholder="casual, work, diwali…"
            aiState={aiFieldState(d, 'occasionStr')}
            onChange={v => onPatch({ occasionStr: v })}
          />

          <div className="grid gap-2 sm:grid-cols-2">
            <AIInput
              label="Material"
              id={`f-${uid}-material`}
              aiState={aiFieldState(d, 'material')}
              value={d.material}
              onChange={e => onPatch({ material: e.target.value })}
            />
            <AIInput
              label="Pattern"
              id={`f-${uid}-pattern`}
              aiState={aiFieldState(d, 'pattern')}
              value={d.pattern}
              onChange={e => onPatch({ pattern: e.target.value })}
            />
            <div className="w-full">
              <label htmlFor={`f-${uid}-brand`} className="label">Brand</label>
              <Input id={`f-${uid}-brand`} value={d.brand} onChange={e => onPatch({ brand: e.target.value })} />
            </div>
            <div className="w-full">
              <label htmlFor={`f-${uid}-size`} className="label">Size</label>
              <Input id={`f-${uid}-size`} value={d.size} onChange={e => onPatch({ size: e.target.value })} />
            </div>
            <Select
              label="Fit"
              id={`f-${uid}-fit`}
              className="capitalize"
              value={d.fit}
              onChange={e => onPatch({ fit: e.target.value })}
              options={FIT_OPTIONS_SELECT}
            />
            <Select
              label="Condition"
              id={`f-${uid}-condition`}
              value={d.condition}
              onChange={e => onPatch({ condition: e.target.value as ConditionGrade })}
              options={CONDITION_OPTIONS_SELECT}
            />
            <div className="w-full">
              <label htmlFor={`f-${uid}-price`} className="label">Price</label>
              <Input id={`f-${uid}-price`} value={d.priceStr} onChange={e => onPatch({ priceStr: e.target.value })} type="number" step="0.01" />
            </div>
          </div>

          <div>
            <AIFieldLabel label="Description" state={aiFieldState(d, 'notes')} htmlFor={`f-${uid}-notes`} />
            <textarea
              id={`f-${uid}-notes`}
              rows={2}
              className="input resize-none w-full"
              value={d.notes}
              onChange={e => onPatch({ notes: e.target.value })}
            />
          </div>
        </div>
      )}

      {/* ── Footer: more-details toggle + include/skip status ── */}
      <div className="mt-auto flex items-center justify-between gap-2 px-4 py-2.5 border-t border-cream-100 dark:border-slate-700">
        <button
          type="button"
          onClick={() => setExpanded(v => !v)}
          aria-expanded={expanded}
          className="flex items-center gap-1 text-xs font-semibold text-slate-500 dark:text-slate-400 hover:text-slate-700 dark:hover:text-slate-200 transition-colors"
        >
          <ChevronRight size={14} className={cn('transition-transform', expanded && 'rotate-90')} />
          {expanded ? 'Less' : 'More details'}
          {!expanded && filledCount > 0 && <span className="text-[10px] font-bold text-brand-500">({filledCount})</span>}
        </button>

        <button
          type="button"
          onClick={() => onPatch({ selected: !d.selected })}
          disabled={disabled}
          aria-pressed={d.selected}
          title={d.selected ? 'Included — click to skip' : 'Skipped — click to include'}
          className={cn(
            'inline-flex items-center gap-1 rounded-full px-2.5 py-1 text-[11px] font-semibold transition-colors disabled:opacity-50',
            d.selected
              ? needsAttention
                ? 'bg-amber-100 text-amber-700 dark:bg-amber-900/40 dark:text-amber-300 hover:bg-amber-200 dark:hover:bg-amber-900/60'
                : 'bg-emerald-100 text-emerald-700 dark:bg-emerald-900/40 dark:text-emerald-300 hover:bg-emerald-200 dark:hover:bg-emerald-900/60'
              : 'bg-slate-100 text-slate-500 dark:bg-slate-800 dark:text-slate-400 hover:bg-slate-200 dark:hover:bg-slate-700',
          )}
        >
          {d.selected
            ? needsAttention
              ? <><AlertTriangle size={11} /> Check details</>
              : <><Check size={11} /> Adding</>
            : <><Circle size={11} /> Skipped</>}
        </button>
      </div>
    </div>
  )
}

/** Compact "Add photos ✓ · Review · Done" progress rail shown above the board. */
function StepRail({ step }: { step: 1 | 2 | 3 }) {
  const steps = ['Add photos', 'Review', 'Done']
  return (
    <div className="flex items-center gap-2 text-xs">
      {steps.map((label, i) => {
        const n = (i + 1) as 1 | 2 | 3
        const done = n < step
        const active = n === step
        return (
          <div key={label} className="flex items-center gap-2">
            <span
              className={cn(
                'inline-flex items-center gap-1.5 font-semibold',
                active ? 'text-slate-700 dark:text-slate-200' : done ? 'text-brand-600 dark:text-brand-400' : 'text-slate-400',
              )}
            >
              <span
                className={cn(
                  'inline-flex h-5 w-5 items-center justify-center rounded-full text-[10px] font-bold',
                  active ? 'bg-brand-500 text-white' : done ? 'bg-brand-100 text-brand-600 dark:bg-brand-900/40 dark:text-brand-300' : 'bg-slate-100 text-slate-400 dark:bg-slate-800',
                )}
              >
                {done ? <Check size={11} /> : n}
              </span>
              {label}
            </span>
            {i < steps.length - 1 && <span className="w-6 h-px bg-slate-200 dark:bg-slate-700" />}
          </div>
        )
      })}
    </div>
  )
}

export default function Upload() {
  const { fetchClosetItems } = useApp()
  const [dragging, setDragging] = useState(false)
  const [files, setFiles] = useState<File[]>([])
  const [filePreviews, setFilePreviews] = useState<{ url: string; name: string }[]>([])
  const [fileNotice, setFileNotice] = useState<string | null>(null)
  const [uploading, setUploading] = useState(false)
  const [uploadProgress, setUploadProgress] = useState<string | null>(null)
  const [previewGroups, setPreviewGroups] = useState<PreviewGroup[]>([])
  const [analyzeFailures, setAnalyzeFailures] = useState<{ filename: string; error: string }[]>([])
  const [savingAll, setSavingAll] = useState(false)
  const [saveOkMessage, setSaveOkMessage] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const inputRef = useRef<HTMLInputElement>(null)

  // Similarity check state — keyed by detected_item_id
  const [similarItemsMap, setSimilarItemsMap] = useState<Record<string, SimilarClosetItem[]>>({})
  const [similarLoadingIds, setSimilarLoadingIds] = useState<Set<string>>(new Set())
  const [similarErrorIds, setSimilarErrorIds] = useState<Set<string>>(new Set())

  const inPreview = previewGroups.length > 0
  const hasFailures = analyzeFailures.length > 0
  const preview = filePreviews[0]?.url ?? null

  /** Flat ordered list of all items across all groups for the board. */
  const boardItems = useMemo<BoardItem[]>(
    () =>
      previewGroups.flatMap(g =>
        g.drafts.map(d => ({
          sessionId: g.sessionId,
          filename: g.filename,
          draft: d,
          saved: g.saved ?? false,
        })),
      ),
    [previewGroups],
  )

  const totalDetections = boardItems.length
  const selectedCount = boardItems.filter(wi => wi.draft.selected).length
  const skippedCount = totalDetections - selectedCount
  const allSaved = previewGroups.length > 0 && previewGroups.every(g => g.saved)
  const multiPhoto = previewGroups.length > 1

  const handleFiles = useCallback((selected: File[]) => {
    const incoming = Array.from(selected)
    const images = incoming.filter(f => f.type.startsWith('image/'))
    const withinSize = images.filter(f => f.size <= MAX_FILE_SIZE)

    // "+ Add more" appends to the current selection rather than replacing it.
    // De-dupe by name+size so re-picking the same photo is a no-op, then cap the total.
    const existingKeys = new Set(files.map(f => `${f.name}:${f.size}`))
    const fresh = withinSize.filter(f => !existingKeys.has(`${f.name}:${f.size}`))
    const merged = [...files, ...fresh]
    const capped = merged.slice(0, MAX_FILES)
    const acceptedFresh = capped.slice(files.length) // new files that fit under the cap

    // Error prevention: tell the user about anything we couldn't accept
    const skipped: string[] = []
    const nonImage = incoming.length - images.length
    const tooBig = images.length - withinSize.length
    const dupes = withinSize.length - fresh.length
    const overflow = merged.length - capped.length
    if (nonImage) skipped.push(`${nonImage} non-image file${nonImage === 1 ? '' : 's'}`)
    if (tooBig) skipped.push(`${tooBig} over 10MB`)
    if (dupes) skipped.push(`${dupes} already added`)
    if (overflow) skipped.push(`${overflow} beyond the ${MAX_FILES}-photo limit`)
    setFileNotice(skipped.length ? `Skipped ${skipped.join(', ')}.` : null)

    // Keep existing object URLs alive; only create previews for the newly accepted files.
    const freshPreviews = acceptedFresh.map(f => ({ url: URL.createObjectURL(f), name: f.name }))
    setFiles(capped)
    setFilePreviews(prev => [...prev, ...freshPreviews])
    setPreviewGroups([])
    setAnalyzeFailures([])
    setSaveOkMessage(null)
    setError(null)
    setSimilarItemsMap({})
    setSimilarLoadingIds(new Set())
    setSimilarErrorIds(new Set())
  }, [files])

  /** Remove a single selected photo before analysis (user control & freedom). */
  const removeFile = useCallback((index: number) => {
    setFilePreviews(prev => {
      const target = prev[index]
      if (target) URL.revokeObjectURL(target.url)
      return prev.filter((_, i) => i !== index)
    })
    setFiles(prev => prev.filter((_, i) => i !== index))
    setFileNotice(null)
  }, [])

  /** Fire similarity checks for a batch of draft items in parallel. Never throws. */
  const runSimilarityChecks = useCallback(async (drafts: ItemDraft[]) => {
    if (drafts.length === 0) return
    setSimilarLoadingIds(prev => new Set([...prev, ...drafts.map(d => d.detected_item_id)]))
    await Promise.allSettled(
      drafts.map(async d => {
        try {
          const items = await closetSimilarityApi.checkSimilarClosetItems({
            name: d.name,
            category: d.category,
            subcategory: d.subcategory || undefined,
            color: d.color || undefined,
            pattern: d.pattern || undefined,
            material: d.material || undefined,
            season_tags: parseCommaList(d.seasonStr),
            occasion_tags: parseCommaList(d.occasionStr),
            limit: 5,
          })
          setSimilarItemsMap(prev => ({ ...prev, [d.detected_item_id]: items }))
        } catch {
          setSimilarErrorIds(prev => new Set([...prev, d.detected_item_id]))
        } finally {
          setSimilarLoadingIds(prev => {
            const next = new Set(prev)
            next.delete(d.detected_item_id)
            return next
          })
        }
      }),
    )
  }, [])

  const onDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault()
    setDragging(false)
    handleFiles(Array.from(e.dataTransfer.files))
  }, [handleFiles])

  const resetAll = useCallback(() => {
    filePreviews.forEach(p => URL.revokeObjectURL(p.url))
    setFiles([])
    setFilePreviews([])
    setFileNotice(null)
    setPreviewGroups([])
    setAnalyzeFailures([])
    setUploadProgress(null)
    setSaveOkMessage(null)
    setError(null)
    setSimilarItemsMap({})
    setSimilarLoadingIds(new Set())
    setSimilarErrorIds(new Set())
  }, [filePreviews])

  /** Drop the detected board but keep the chosen photos, so the user can re-analyze. */
  const backToPhotos = useCallback(() => {
    setPreviewGroups([])
    setAnalyzeFailures([])
    setSaveOkMessage(null)
    setError(null)
    setSimilarItemsMap({})
    setSimilarLoadingIds(new Set())
    setSimilarErrorIds(new Set())
  }, [])

  const extractErr = (err: unknown): string => {
    type ApiErr = {
      response?: {
        data?: {
          message?: string
          error?: string
          detail?: string | Array<{ loc?: (string | number)[]; msg?: string }>
        }
      }
    }
    const d = (err as ApiErr)?.response?.data
    let msg: string | undefined
    if (typeof d?.detail === 'string') msg = d.detail
    else if (Array.isArray(d?.detail)) {
      msg = d.detail
        .map(e => {
          const field = Array.isArray(e.loc) ? e.loc.slice(1).join('.') : ''
          return field ? `${field}: ${e.msg ?? ''}` : (e.msg ?? '')
        })
        .filter(Boolean)
        .join(' · ')
    }
    msg = msg ?? d?.message ?? d?.error ?? (err instanceof Error ? err.message : 'Request failed')
    return msg
  }

  const analyze = async () => {
    if (files.length === 0) return
    setUploading(true)
    setError(null)
    setSaveOkMessage(null)
    setAnalyzeFailures([])
    setPreviewGroups([])
    setSimilarItemsMap({})
    setSimilarLoadingIds(new Set())
    setSimilarErrorIds(new Set())
    setUploadProgress(files.length > 1 ? `Analyzing ${files.length} photos…` : 'Analyzing…')
    try {
      if (files.length > 1) {
        const { results, failed } = await closetApi.bulkAnalyzePreview(files)
        setAnalyzeFailures(failed)
        const newGroups: PreviewGroup[] = results.flatMap(r => {
          const p = r.preview
          if (!p?.preview_session_id) return []
          return [{ filename: r.filename, sessionId: p.preview_session_id, drafts: draftsFromPreviewItems(p.items) }]
        })
        setPreviewGroups(newGroups)
        if (results.length === 0 && failed.length > 0) {
          setError('Could not analyze any files. Check errors below.')
        } else {
          void runSimilarityChecks(newGroups.flatMap(g => g.drafts))
        }
        return
      }

      const res = await closetApi.analyzePreview(files[0])
      const newGroups: PreviewGroup[] = [{
        filename: files[0].name || 'upload',
        sessionId: res.preview_session_id,
        drafts: draftsFromPreviewItems(res.items),
      }]
      setPreviewGroups(newGroups)
      if (!res.items.length) {
        setError(
          'No clothing items were detected in this photo. Try a clearer, well-lit image of a single item on a plain background.',
        )
      } else {
        void runSimilarityChecks(newGroups.flatMap(g => g.drafts))
      }
    } catch (err: unknown) {
      setError(`Analysis failed: ${extractErr(err)}`)
    } finally {
      setUploadProgress(null)
      setUploading(false)
    }
  }

  /** Bulk include/skip every detected item across all photos. */
  const setAllSelected = (selected: boolean) => {
    setPreviewGroups(groups =>
      groups.map(g => ({ ...g, drafts: g.drafts.map(d => ({ ...d, selected })) })),
    )
  }

  const updateDraft = (
    sessionId: string,
    slotIndex: number,
    patch: Partial<ItemDraft>,
  ) => {
    setPreviewGroups(groups =>
      groups.map(g => {
        if (g.sessionId !== sessionId) return g
        return {
          ...g,
          drafts: g.drafts.map(d => (d.slot_index === slotIndex ? { ...d, ...patch } : d)),
        }
      }),
    )
  }

  const confirmGroup = async (group: PreviewGroup): Promise<number> => {
    const selected = group.drafts.filter(d => d.selected)
    if (selected.length === 0) return 0
    const priceNum = (s: string): number | undefined => {
      const t = s.trim()
      if (!t) return undefined
      const n = Number(t)
      return Number.isFinite(n) ? n : undefined
    }
    const { total_saved } = await closetApi.confirmPreview({
      preview_session_id: group.sessionId,
      items: group.drafts.map(d => ({
        slot_index: d.slot_index,
        detected_item_id: d.detected_item_id,
        selected: d.selected,
        name: d.name.trim() || 'Clothing Item',
        category: d.category,
        color: d.color.trim() || undefined,
        fabric: d.material.trim() || undefined,
        material: d.material.trim() || undefined,
        pattern: d.pattern.trim() || undefined,
        season: parseCommaList(d.seasonStr),
        occasion: parseCommaList(d.occasionStr).length ? parseCommaList(d.occasionStr) : undefined,
        notes: d.notes.trim() || undefined,
        brand: d.brand.trim() || undefined,
        size: d.size.trim() || undefined,
        fit: d.fit || undefined,
        condition: d.condition,
        price: priceNum(d.priceStr),
      })),
    })
    setPreviewGroups(gs => gs.map(g => (g.sessionId === group.sessionId ? { ...g, saved: true } : g)))
    return total_saved
  }

  /**
   * Save every group that has at least one selected item.
   * Resilient to partial failure: a failing photo never blocks the others, and
   * we report exactly what saved vs. what's left to retry (failed groups stay unsaved).
   */
  const confirmAllGroups = async () => {
    setSavingAll(true)
    setError(null)
    setSaveOkMessage(null)

    let totalSaved = 0
    let attempted = 0
    const failed: { filename: string; error: string }[] = []

    for (const group of previewGroups) {
      if (group.saved || !group.drafts.some(d => d.selected)) continue
      attempted++
      try {
        totalSaved += await confirmGroup(group)
      } catch (err: unknown) {
        failed.push({ filename: group.filename, error: extractErr(err) })
      }
    }

    await fetchClosetItems().catch(() => { /* closet refresh is best-effort */ })

    if (attempted === 0) {
      setError('No items are selected to save. Include at least one item, then press Save.')
    } else if (failed.length === 0) {
      setSaveOkMessage(`${totalSaved} item${totalSaved === 1 ? '' : 's'} saved to your closet!`)
      notificationStore.push({
        channel: 'closet',
        icon: '👕',
        title: `${totalSaved} item${totalSaved === 1 ? '' : 's'} added to your closet`,
        body: 'Your new pieces are ready to style.',
      })
    } else {
      const names = failed.map(f => f.filename).join(', ')
      if (totalSaved > 0) {
        setSaveOkMessage(`${totalSaved} item${totalSaved === 1 ? '' : 's'} saved.`)
        notificationStore.push({
          channel: 'closet',
          icon: '👕',
          title: `${totalSaved} item${totalSaved === 1 ? '' : 's'} saved`,
          body: `${failed.length} photo${failed.length === 1 ? '' : 's'} failed — fix and retry.`,
        })
      }
      setError(`Couldn't save ${failed.length} photo${failed.length === 1 ? '' : 's'} (${names}). They're still here — fix any issues and press Save to retry.`)
      toastStore.add({
        variant: 'error',
        icon: '⚠️',
        title: `Failed to save ${failed.length} photo${failed.length === 1 ? '' : 's'}`,
        body: names,
      })
    }

    setSavingAll(false)
  }

  // The review panel carries its own "Add to your closet" heading, so the outer
  // page header is hidden while the board is up to avoid a duplicate title.
  const boardShowing = inPreview && !allSaved && totalDetections > 0

  return (
    <div className={cn('space-y-6', inPreview ? 'max-w-6xl' : 'max-w-2xl')}>
      <BackButton fallback="/closet" label="Back to Closet" />
      {!boardShowing && (
        <PageHeader
          icon={<Image size={18} />}
          title="Add to Your Closet"
          subtitle="Upload photos and FANI detects your clothing — review everything on one board, then save"
        />
      )}

      {/* Always-mounted file input so the board's "Add more photos" tile can reach it. */}
      <input
        ref={inputRef}
        type="file"
        accept="image/*"
        multiple
        className="hidden"
        onChange={e => handleFiles(Array.from(e.target.files ?? []))}
      />

      {error && <InlineError message={error} className="mb-4" />}
      {saveOkMessage && (
        <div className="card p-3 bg-emerald-50 dark:bg-emerald-900/20 border-emerald-200 text-emerald-800 dark:text-emerald-200 text-sm flex items-center gap-2">
          <CheckCircle size={16} />
          {saveOkMessage}
        </div>
      )}

      {/* ══ UPLOAD STATE — choose & analyze photos ══ */}
      {!inPreview && (
        <div className="space-y-4">
          <StepRail step={1} />
          <div
            role="button"
            tabIndex={preview ? -1 : 0}
            aria-label="Upload photos. Drop images here, or press Enter to browse your files."
            className={cn(
              'relative border-2 border-dashed rounded-2xl transition-all duration-200',
              !preview && 'cursor-pointer focus:outline-none focus-visible:ring-2 focus-visible:ring-brand-400 focus-visible:ring-offset-2',
              dragging ? 'drop-zone-active' : 'border-cream-300 dark:border-slate-600 hover:border-brand-400',
              preview ? 'aspect-[16/10]' : 'aspect-[16/9]',
            )}
            onDragOver={e => { e.preventDefault(); setDragging(true) }}
            onDragLeave={() => setDragging(false)}
            onDrop={onDrop}
            onClick={() => !preview && inputRef.current?.click()}
            onKeyDown={e => {
              if ((e.key === 'Enter' || e.key === ' ') && !preview) {
                e.preventDefault()
                inputRef.current?.click()
              }
            }}
          >
            {preview ? (
              <>
                <img src={preview} alt={filePreviews[0]?.name ?? 'Selected photo'} className="w-full h-full object-cover rounded-2xl" />
                <div className="absolute inset-0 rounded-2xl bg-black/30 opacity-0 hover:opacity-100 transition-opacity flex items-center justify-center gap-3">
                  <button
                    type="button"
                    onClick={e => { e.stopPropagation(); resetAll() }}
                    className="p-2 rounded-full bg-white/20 hover:bg-white/30 transition-colors"
                  >
                    <X size={18} className="text-white" />
                  </button>
                </div>
              </>
            ) : (
              <div className="absolute inset-0 flex flex-col items-center justify-center gap-3 text-slate-400">
                <div className="w-14 h-14 rounded-2xl bg-brand-50 dark:bg-brand-900/30 flex items-center justify-center">
                  <Image size={24} className="text-brand-500" />
                </div>
                <div className="text-center">
                  <p className="font-semibold text-sm text-slate-600 dark:text-slate-300">Drop your photos here</p>
                  <p className="text-xs text-slate-400 mt-0.5">or click to browse — add up to 20 at once</p>
                </div>
                <p className="text-[11px] text-slate-500 dark:text-white/40">JPG, PNG, WEBP · Max 10MB each</p>
              </div>
            )}
          </div>

          {/* Validation notice — what was skipped and why (error prevention) */}
          {fileNotice && (
            <p className="flex items-start gap-1.5 text-xs text-amber-600 dark:text-amber-400 bg-amber-50 dark:bg-amber-900/20 border border-amber-200 dark:border-amber-800 rounded-lg px-2.5 py-1.5">
              <Info size={13} className="mt-px shrink-0" />
              <span>{fileNotice}</span>
            </p>
          )}

          {/* Selected-photos strip — see and manage every photo before analyzing (visibility + control) */}
          {filePreviews.length > 0 && (
            <div className="space-y-2">
              <div className="flex items-center justify-between">
                <p className="text-xs font-medium text-slate-500 dark:text-slate-400">
                  {files.length} of {MAX_FILES} photo{files.length === 1 ? '' : 's'} selected
                </p>
                {files.length < MAX_FILES && (
                  <button
                    type="button"
                    onClick={() => inputRef.current?.click()}
                    className="text-xs font-semibold text-brand-600 dark:text-brand-400 hover:text-brand-700 dark:hover:text-brand-300"
                  >
                    + Add more
                  </button>
                )}
              </div>
              {filePreviews.length > 1 && (
                <div className="flex gap-2 overflow-x-auto pb-1 scrollbar-hide" role="list" aria-label="Selected photos">
                  {filePreviews.map((p, i) => (
                    <div key={p.url} role="listitem" className="relative flex-shrink-0">
                      <img
                        src={p.url}
                        alt={p.name}
                        className="w-14 h-14 rounded-lg object-cover border border-cream-200 dark:border-slate-700"
                      />
                      <button
                        type="button"
                        onClick={() => removeFile(i)}
                        aria-label={`Remove ${p.name}`}
                        className="absolute -top-1.5 -right-1.5 w-5 h-5 rounded-full bg-slate-900/85 text-white flex items-center justify-center shadow-sm hover:bg-red-500 transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-red-400"
                      >
                        <X size={11} />
                      </button>
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}

          {uploadProgress && (
            <div className="card p-3 bg-brand-50 dark:bg-brand-900/20 border-brand-200 dark:border-brand-800 text-brand-700 dark:text-brand-300 text-sm flex items-center gap-3">
              {uploading && <LoadingSpinner size="sm" />}
              <span>{uploadProgress}</span>
            </div>
          )}

          {hasFailures && (
            <div className="card p-3 bg-red-50 dark:bg-red-900/20 border-red-200 text-sm space-y-1">
              <p className="font-semibold text-red-700 dark:text-red-300">Some files failed analysis</p>
              {analyzeFailures.map(f => (
                <p key={f.filename} className="text-xs text-red-600 dark:text-red-400">
                  {f.filename}: {f.error}
                </p>
              ))}
            </div>
          )}

          {files.length > 0 && (
            <div className="space-y-2">
              <Button className="w-full" disabled={uploading} loading={uploading} icon={<Sparkles size={15} />} onClick={analyze}>
                {uploading
                  ? 'Analyzing…'
                  : files.length > 1 ? `Analyze ${files.length} photos with FANI` : 'Analyze with FANI'}
              </Button>
              {!uploading && (
                <p className="flex items-center justify-center gap-1.5 text-[11px] text-slate-400">
                  <ShieldCheck size={12} className="text-emerald-500" />
                  Nothing is saved yet — you'll review every item first.
                </p>
              )}
            </div>
          )}

          {files.length === 0 && !uploadProgress && (
            <div className="card p-6 text-center text-slate-500 dark:text-slate-400 text-sm">
              Choose one or more photos to see AI-detected items. Nothing is saved until you press Save.
            </div>
          )}
        </div>
      )}

      {/* ══ REVIEW BOARD — every detected item at once ══ */}
      {inPreview && allSaved && (
        <div className="card p-6 text-center space-y-3 max-w-md mx-auto">
          <CheckCircle size={32} className="text-emerald-500 mx-auto" />
          <div>
            <p className="font-semibold text-slate-700 dark:text-slate-200">All items saved!</p>
            <p className="text-sm text-slate-400">What do you want to do next?</p>
          </div>
          <div className="flex gap-2 justify-center flex-wrap">
            <Link to="/closet" className="btn-secondary text-xs px-4 py-2 rounded-xl">View my closet</Link>
            <Link to="/outfit-builder" className="btn-secondary text-xs px-4 py-2 rounded-xl">Build outfit</Link>
            <Link to="/ai-stylist" className="btn-secondary text-xs px-4 py-2 rounded-xl">Ask FANI</Link>
          </div>
          <Button size="sm" onClick={resetAll}>Upload more</Button>
        </div>
      )}

      {inPreview && !allSaved && totalDetections === 0 && (
        <div className="card p-6 text-center space-y-3 max-w-md mx-auto">
          <p className="text-amber-600 dark:text-amber-400 text-sm">No clothing items were detected in these photos.</p>
          <Button size="sm" variant="secondary" onClick={backToPhotos}>Choose different photos</Button>
        </div>
      )}

      {inPreview && !allSaved && totalDetections > 0 && (
        <div className="rounded-3xl border border-cream-200 dark:border-white/[0.08] bg-cream-50/70 dark:bg-white/[0.02] shadow-card p-4 sm:p-6 space-y-5">
          {/* Panel header — title + step rail (mock layout) */}
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div className="min-w-0">
              <h2 className="text-xl font-display font-bold text-slate-800 dark:text-slate-100">Add to your closet</h2>
              <p className="text-sm text-slate-500 dark:text-slate-400">
                FANI found {totalDetections} item{totalDetections === 1 ? '' : 's'} in {previewGroups.length} photo{previewGroups.length === 1 ? '' : 's'} — confirm what goes in.
              </p>
            </div>
            <StepRail step={2} />
          </div>

          {/* Helper + bulk include/skip */}
          <div className="flex flex-wrap items-center justify-between gap-2">
            <p className="text-xs text-slate-400 dark:text-slate-500 max-w-xl">
              Details are AI-detected — edit any field. Items flagged{' '}
              <span className="font-semibold text-amber-600 dark:text-amber-400">Check details</span> may be duplicates or low-confidence. Nothing saves until you press Save.
            </p>
            <div className="flex items-center gap-3 text-xs shrink-0">
              <button
                type="button"
                onClick={() => setAllSelected(true)}
                disabled={savingAll || selectedCount === totalDetections}
                className="font-semibold text-brand-600 dark:text-brand-400 hover:text-brand-700 dark:hover:text-brand-300 disabled:text-slate-300 dark:disabled:text-slate-600 disabled:cursor-default transition-colors"
              >
                Select all
              </button>
              <span className="text-slate-300 dark:text-slate-600">·</span>
              <button
                type="button"
                onClick={() => setAllSelected(false)}
                disabled={savingAll || selectedCount === 0}
                className="font-semibold text-slate-500 dark:text-slate-400 hover:text-slate-700 dark:hover:text-slate-200 disabled:text-slate-300 dark:disabled:text-slate-600 disabled:cursor-default transition-colors"
              >
                Skip all
              </button>
            </div>
          </div>

          {/* The board — every detected item at once */}
          <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3 items-start">
            {boardItems.map(wi => {
              const d = wi.draft
              return (
                <ItemReviewCard
                  key={d.detected_item_id}
                  d={d}
                  filename={wi.filename}
                  showFilename={multiPhoto}
                  disabled={savingAll}
                  similar={{
                    loading: similarLoadingIds.has(d.detected_item_id),
                    error: similarErrorIds.has(d.detected_item_id),
                    items: similarItemsMap[d.detected_item_id] ?? [],
                  }}
                  onPatch={patch => updateDraft(wi.sessionId, d.slot_index, patch)}
                />
              )
            })}

            {/* Add more photos tile — appends to the selection, then re-analyze */}
            {files.length < MAX_FILES && (
              <button
                type="button"
                onClick={() => inputRef.current?.click()}
                className="min-h-[11rem] flex flex-col items-center justify-center gap-1.5 rounded-2xl border-2 border-dashed border-cream-300 dark:border-slate-600 text-slate-400 hover:border-brand-400 hover:text-brand-500 hover:bg-white/40 dark:hover:bg-white/[0.03] transition-colors"
              >
                <Plus size={22} />
                <span className="text-xs font-semibold">Add more photos</span>
                <span className="text-[10px] text-slate-400">re-analyze to detect them</span>
              </button>
            )}
          </div>

          {/* Panel footer — summary + actions (mock bottom bar) */}
          <div className="flex flex-wrap items-center justify-between gap-3 border-t border-cream-200 dark:border-white/10 pt-4">
            <p className="text-sm text-slate-600 dark:text-slate-300">
              <span className="font-semibold text-slate-800 dark:text-slate-100">{selectedCount} item{selectedCount === 1 ? '' : 's'}</span> will be added
              {skippedCount > 0 && <span className="text-slate-400"> · {skippedCount} skipped</span>}
              <span className="text-slate-400"> · nothing saved yet</span>
            </p>
            <div className="flex items-center gap-1.5">
              <Button variant="ghost" size="sm" onClick={backToPhotos} icon={<ChevronLeft size={14} />}>
                Re-analyze
              </Button>
              <Button variant="ghost" size="sm" onClick={resetAll} icon={<X size={14} />}>
                Discard all
              </Button>
              <Button
                icon={<CheckCircle size={16} />}
                loading={savingAll}
                disabled={selectedCount === 0 || savingAll}
                onClick={() => void confirmAllGroups()}
              >
                Save {selectedCount > 0 ? selectedCount : ''} to closet
              </Button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
