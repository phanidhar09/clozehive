import { useState, useRef, useCallback, useMemo } from 'react'
import {
  Image, Sparkles, CheckCircle, Circle, X, ChevronLeft, ChevronRight,
  SkipForward, AlertTriangle, Info, ShieldCheck, Pencil,
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
import { cn } from '@/lib/utils'
import { CLOSET_SEASONS, CLOSET_OCCASIONS } from '@/features/closet/constants'
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
  label, aiState, id, ...rest
}: { label: string; aiState: AIProvenance; id: string } & React.InputHTMLAttributes<HTMLInputElement>) {
  return (
    <div className="w-full">
      <AIFieldLabel label={label} state={aiState} htmlFor={id} />
      <Input id={id} {...rest} />
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
  label, value, suggestions, placeholder, aiState, id, onChange,
}: {
  label: string
  value: string
  suggestions: readonly string[]
  placeholder?: string
  aiState?: AIProvenance
  id: string
  onChange: (v: string) => void
}) {
  const active = parseCommaList(value)
  return (
    <div>
      <AIFieldLabel label={label} state={aiState ?? null} htmlFor={id} />
      <Input id={id} value={value} placeholder={placeholder} onChange={e => onChange(e.target.value)} />
      <div className="flex flex-wrap gap-1.5 mt-2">
        {suggestions.map(s => {
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
        })}
      </div>
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

type WizardItem = {
  sessionId: string
  filename: string
  draft: ItemDraft
  saved: boolean
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
  const [wizardIndex, setWizardIndex] = useState(0)
  const [showMore, setShowMore] = useState(false)        // progressive disclosure of secondary fields
  const [showOverview, setShowOverview] = useState(false) // "review all" list of detected items
  const inputRef = useRef<HTMLInputElement>(null)

  // Similarity check state — keyed by detected_item_id
  const [similarItemsMap, setSimilarItemsMap] = useState<Record<string, SimilarClosetItem[]>>({})
  const [similarLoadingIds, setSimilarLoadingIds] = useState<Set<string>>(new Set())
  const [similarErrorIds, setSimilarErrorIds] = useState<Set<string>>(new Set())

  const inPreview = previewGroups.length > 0
  const hasFailures = analyzeFailures.length > 0
  const preview = filePreviews[0]?.url ?? null

  /** Flat ordered list of all items across all groups for the wizard. */
  const allWizardItems = useMemo<WizardItem[]>(
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

  const totalDetections = allWizardItems.length
  const currentWizardItem = allWizardItems[wizardIndex] ?? null
  const isFirstItem = wizardIndex === 0
  const isLastItem = wizardIndex === totalDetections - 1
  const selectedCount = allWizardItems.filter(wi => wi.draft.selected).length
  const allSaved = previewGroups.length > 0 && previewGroups.every(g => g.saved)

  const handleFiles = useCallback((selected: File[]) => {
    const incoming = Array.from(selected)
    const images = incoming.filter(f => f.type.startsWith('image/'))
    const withinSize = images.filter(f => f.size <= MAX_FILE_SIZE)
    const capped = withinSize.slice(0, MAX_FILES)

    // Error prevention: tell the user about anything we couldn't accept
    const skipped: string[] = []
    const nonImage = incoming.length - images.length
    const tooBig = images.length - withinSize.length
    const overflow = withinSize.length - capped.length
    if (nonImage) skipped.push(`${nonImage} non-image file${nonImage === 1 ? '' : 's'}`)
    if (tooBig) skipped.push(`${tooBig} over 10MB`)
    if (overflow) skipped.push(`${overflow} beyond the ${MAX_FILES}-photo limit`)
    setFileNotice(skipped.length ? `Skipped ${skipped.join(', ')}.` : null)

    // Revoke previous object URLs to avoid leaks, then build fresh previews
    filePreviews.forEach(p => URL.revokeObjectURL(p.url))
    setFiles(capped)
    setFilePreviews(capped.map(f => ({ url: URL.createObjectURL(f), name: f.name })))
    setPreviewGroups([])
    setAnalyzeFailures([])
    setSaveOkMessage(null)
    setError(null)
    setWizardIndex(0)
    setSimilarItemsMap({})
    setSimilarLoadingIds(new Set())
    setSimilarErrorIds(new Set())
  }, [filePreviews])

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
    setWizardIndex(0)
    setSimilarItemsMap({})
    setSimilarLoadingIds(new Set())
    setSimilarErrorIds(new Set())
  }, [filePreviews])

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
    setWizardIndex(0)
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

  // Wizard navigation helpers
  const wizardNext = () => {
    if (isLastItem) {
      void confirmAllGroups()
    } else {
      setWizardIndex(i => i + 1)
    }
  }

  const wizardBack = () => {
    if (!isFirstItem) setWizardIndex(i => i - 1)
  }

  const wizardSkip = () => {
    if (!currentWizardItem) return
    updateDraft(currentWizardItem.sessionId, currentWizardItem.draft.slot_index, { selected: false })
    if (isLastItem) {
      void confirmAllGroups()
    } else {
      setWizardIndex(i => i + 1)
    }
  }

  const discardPreview = () => {
    resetAll()
  }

  return (
    <div className="max-w-3xl space-y-6">
      <BackButton fallback="/closet" label="Back to Closet" />
      <PageHeader
        icon={<Image size={18} />}
        title="Add to Your Closet"
        subtitle="Upload a photo and our AI will detect your clothing items — review each one and save"
      />

      {error && <InlineError message={error} className="mb-4" />}
      {saveOkMessage && (
        <div className="card p-3 bg-emerald-50 dark:bg-emerald-900/20 border-emerald-200 text-emerald-800 dark:text-emerald-200 text-sm flex items-center gap-2">
          <CheckCircle size={16} />
          {saveOkMessage}
        </div>
      )}

      <div className="grid md:grid-cols-2 gap-6">
        {/* ── Left panel: upload zone ── */}
        <div className="space-y-4">
          <div
            role="button"
            tabIndex={inPreview || preview ? -1 : 0}
            aria-label="Upload photos. Drop images here, or press Enter to browse your files."
            className={cn(
              'relative border-2 border-dashed rounded-2xl transition-all duration-200',
              !inPreview && !preview && 'cursor-pointer focus:outline-none focus-visible:ring-2 focus-visible:ring-brand-400 focus-visible:ring-offset-2',
              dragging ? 'drop-zone-active' : 'border-cream-300 dark:border-slate-600 hover:border-brand-400',
              preview ? 'aspect-[3/4]' : 'aspect-square',
            )}
            onDragOver={e => { e.preventDefault(); setDragging(true) }}
            onDragLeave={() => setDragging(false)}
            onDrop={onDrop}
            onClick={() => !inPreview && !preview && inputRef.current?.click()}
            onKeyDown={e => {
              if ((e.key === 'Enter' || e.key === ' ') && !inPreview && !preview) {
                e.preventDefault()
                inputRef.current?.click()
              }
            }}
          >
            {preview ? (
              <>
                <img src={preview} alt={filePreviews[0]?.name ?? 'Selected photo'} className="w-full h-full object-cover rounded-2xl" />
                {!inPreview && (
                  <div className="absolute inset-0 rounded-2xl bg-black/30 opacity-0 hover:opacity-100 transition-opacity flex items-center justify-center gap-3">
                    <button
                      type="button"
                      onClick={e => { e.stopPropagation(); resetAll() }}
                      className="p-2 rounded-full bg-white/20 hover:bg-white/30 transition-colors"
                    >
                      <X size={18} className="text-white" />
                    </button>
                  </div>
                )}
              </>
            ) : (
              <div className="absolute inset-0 flex flex-col items-center justify-center gap-3 text-slate-400">
                <div className="w-14 h-14 rounded-2xl bg-brand-50 dark:bg-brand-900/30 flex items-center justify-center">
                  <Image size={24} className="text-brand-500" />
                </div>
                <div className="text-center">
                  <p className="font-semibold text-sm text-slate-600 dark:text-slate-300">Drop your photo here</p>
                  <p className="text-xs text-slate-400 mt-0.5">or click to browse</p>
                </div>
                <p className="text-[11px] text-slate-300 dark:text-slate-600">JPG, PNG, WEBP · Max 10MB each · Up to 20 files</p>
              </div>
            )}
          </div>
          <input
            ref={inputRef}
            type="file"
            accept="image/*"
            multiple
            className="hidden"
            onChange={e => handleFiles(Array.from(e.target.files ?? []))}
          />

          {/* Validation notice — what was skipped and why (error prevention) */}
          {fileNotice && !inPreview && (
            <p className="flex items-start gap-1.5 text-xs text-amber-600 dark:text-amber-400 bg-amber-50 dark:bg-amber-900/20 border border-amber-200 dark:border-amber-800 rounded-lg px-2.5 py-1.5">
              <Info size={13} className="mt-px shrink-0" />
              <span>{fileNotice}</span>
            </p>
          )}

          {/* Selected-photos strip — see and manage every photo before analyzing (visibility + control) */}
          {filePreviews.length > 0 && !inPreview && (
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

          {files.length > 0 && !inPreview && (
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

          {inPreview && (
            <div className="flex flex-col gap-2">
              <Button
                className="w-full"
                variant="secondary"
                icon={<ChevronLeft size={15} />}
                onClick={() => {
                  setPreviewGroups([])
                  setAnalyzeFailures([])
                  setSaveOkMessage(null)
                  setError(null)
                  setWizardIndex(0)
                  setSimilarItemsMap({})
                  setSimilarLoadingIds(new Set())
                  setSimilarErrorIds(new Set())
                }}
              >
                Re-analyze these photos
              </Button>
              <Button className="w-full" variant="ghost" onClick={discardPreview} icon={<X size={15} />}>
                Discard &amp; start over
              </Button>
            </div>
          )}
        </div>

        {/* ── Right panel: wizard review ── */}
        <div className="space-y-4">
          {!inPreview && files.length === 0 && (
            <div className="card p-6 text-center text-slate-500 dark:text-slate-400 text-sm">
              Choose one or more photos to see AI-detected items. Nothing is saved until you press Save.
            </div>
          )}

          {/* Wizard — one item at a time */}
          {inPreview && totalDetections === 0 && (
            <div className="card p-6 text-center text-amber-600 dark:text-amber-400 text-sm">
              No clothing items were detected.
            </div>
          )}

          {inPreview && allSaved && (
            <div className="card p-6 text-center space-y-3">
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

          {/* ── Persistent action bar — global Save is always reachable, never buried in the last card ── */}
          {inPreview && !allSaved && totalDetections > 0 && (
            <div className="sticky top-2 z-10 card p-3 flex items-center justify-between gap-3 shadow-md">
              <div className="min-w-0">
                <p className="text-sm font-semibold text-slate-700 dark:text-slate-200 leading-tight">
                  {selectedCount} of {totalDetections} selected
                </p>
                <button
                  type="button"
                  onClick={() => setShowOverview(v => !v)}
                  aria-expanded={showOverview}
                  className="text-[11px] font-medium text-brand-600 dark:text-brand-400 hover:underline"
                >
                  {showOverview ? 'Hide list' : 'Review all'}
                </button>
              </div>
              <Button
                size="sm"
                icon={<CheckCircle size={14} />}
                loading={savingAll}
                disabled={selectedCount === 0 || savingAll}
                onClick={() => void confirmAllGroups()}
              >
                Save {selectedCount > 0 ? selectedCount : ''}
              </Button>
            </div>
          )}

          {/* ── Overview list — see and triage every detected item at a glance (review all) ── */}
          {inPreview && !allSaved && showOverview && (
            <div className="card p-2 space-y-1 max-h-80 overflow-y-auto">
              {allWizardItems.map((wi, idx) => {
                const d = wi.draft
                const tier = confidenceTier(d.confidence)
                const thumb = resolveUploadUrl(d.preview_image_url) ?? d.preview_image_url
                return (
                  <div
                    key={d.detected_item_id}
                    className={cn(
                      'flex items-center gap-2.5 px-2 py-1.5 rounded-xl cursor-pointer transition-colors',
                      idx === wizardIndex ? 'bg-brand-50 dark:bg-brand-900/20' : 'hover:bg-slate-50 dark:hover:bg-slate-800/60',
                      !d.selected && 'opacity-50',
                    )}
                    onClick={() => { setWizardIndex(idx); setShowOverview(false) }}
                  >
                    {thumb && <img src={thumb} alt={d.name} className="w-9 h-11 rounded-lg object-cover bg-slate-100 dark:bg-slate-800 flex-shrink-0" />}
                    <div className="flex-1 min-w-0">
                      <p className="text-xs font-semibold text-slate-700 dark:text-slate-200 truncate">{d.name}</p>
                      <p className="text-[10px] text-slate-400 capitalize flex items-center gap-1">
                        <span className={cn('w-1.5 h-1.5 rounded-full', tier.dot)} /> {d.category}
                      </p>
                    </div>
                    <button
                      type="button"
                      onClick={e => { e.stopPropagation(); updateDraft(wi.sessionId, d.slot_index, { selected: !d.selected }) }}
                      aria-pressed={d.selected}
                      title={d.selected ? 'Included — click to skip' : 'Skipped — click to include'}
                      className={cn(
                        'flex-shrink-0 w-6 h-6 rounded-full flex items-center justify-center transition-colors',
                        d.selected
                          ? 'bg-emerald-100 text-emerald-600 dark:bg-emerald-900/40 dark:text-emerald-300'
                          : 'bg-slate-100 text-slate-400 dark:bg-slate-800',
                      )}
                    >
                      {d.selected ? <CheckCircle size={14} /> : <Circle size={14} />}
                    </button>
                  </div>
                )
              })}
            </div>
          )}

          {inPreview && !allSaved && currentWizardItem && (
            <div className="card overflow-hidden">
              {/* Progress bar */}
              <div className="px-4 pt-4 pb-2 space-y-2">
                <div className="flex items-center justify-between text-xs gap-2">
                  <span className="font-medium text-slate-600 dark:text-slate-300">
                    Item {wizardIndex + 1} <span className="text-slate-400">of {totalDetections}</span>
                  </span>
                  <div className="flex items-center gap-2 min-w-0">
                    {previewGroups.length > 1 && (
                      <span className="text-slate-400 truncate max-w-[120px]">{currentWizardItem.filename}</span>
                    )}
                    {/* Include / Skip toggle — re-includable, not skip-only (user control) */}
                    <button
                      type="button"
                      onClick={() => updateDraft(
                        currentWizardItem.sessionId,
                        currentWizardItem.draft.slot_index,
                        { selected: !currentWizardItem.draft.selected },
                      )}
                      aria-pressed={currentWizardItem.draft.selected}
                      title={currentWizardItem.draft.selected
                        ? 'This item will be saved — click to skip it'
                        : 'This item is skipped — click to include it'}
                      className={cn(
                        'inline-flex items-center gap-1 rounded-full px-2.5 py-1 text-[11px] font-semibold transition-colors',
                        currentWizardItem.draft.selected
                          ? 'bg-emerald-100 text-emerald-700 dark:bg-emerald-900/40 dark:text-emerald-300 hover:bg-emerald-200 dark:hover:bg-emerald-900/60'
                          : 'bg-slate-100 text-slate-500 dark:bg-slate-800 dark:text-slate-400 hover:bg-slate-200 dark:hover:bg-slate-700',
                      )}
                    >
                      {currentWizardItem.draft.selected
                        ? <><CheckCircle size={11} /> Including</>
                        : <><Circle size={11} /> Skipped</>}
                    </button>
                  </div>
                </div>
                {/* Step dots — jump to any item */}
                <div className="flex gap-1" role="tablist" aria-label="Detected items">
                  {allWizardItems.map((wi, idx) => (
                    <button
                      key={idx}
                      onClick={() => setWizardIndex(idx)}
                      role="tab"
                      aria-selected={idx === wizardIndex}
                      aria-label={`Go to item ${idx + 1}${wi.draft.selected ? '' : ' (skipped)'}`}
                      className={cn(
                        'h-1.5 rounded-full flex-1 transition-all focus:outline-none focus-visible:ring-2 focus-visible:ring-brand-400',
                        idx === wizardIndex
                          ? 'bg-brand-500'
                          : wi.draft.selected
                          ? 'bg-brand-200 dark:bg-brand-800'
                          : 'bg-slate-200 dark:bg-slate-700',
                      )}
                    />
                  ))}
                </div>
              </div>

              <div className="px-4 pb-4 space-y-4 border-t border-cream-100 dark:border-slate-700 pt-3">
                {/* Item image — large */}
                {(() => {
                  const d = currentWizardItem.draft
                  const imgSrc = resolveUploadUrl(d.preview_image_url) ?? d.preview_image_url
                  return (
                    <>
                      {imgSrc && (
                        <div className="flex justify-center">
                          <img
                            src={imgSrc}
                            alt={d.name}
                            className="h-44 w-auto max-w-full object-contain rounded-xl bg-slate-50 dark:bg-slate-800 border border-cream-200 dark:border-slate-700"
                          />
                        </div>
                      )}

                      {/* Name + AI provenance + confidence */}
                      <div className="space-y-1.5">
                        <p className="font-semibold text-sm text-slate-800 dark:text-slate-100">{d.name}</p>
                        <div className="flex flex-wrap items-center gap-1.5">
                          <Badge variant="purple">{d.category}</Badge>
                          {d.subcategory.trim() ? <Badge variant="gray">{d.subcategory}</Badge> : null}
                          {d.background_removed && <Badge variant="gray">Background removed</Badge>}
                          {/* Tiered confidence pill */}
                          {(() => {
                            const tier = confidenceTier(d.confidence)
                            return (
                              <span
                                title="How sure FANI is it identified this item correctly. Lower confidence means you should double-check the details below."
                                className={cn(
                                  'inline-flex items-center gap-1.5 rounded-full border px-2 py-0.5 text-[10px] font-semibold',
                                  'border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800',
                                  tier.text,
                                )}
                              >
                                <span className={cn('w-1.5 h-1.5 rounded-full', tier.dot)} />
                                {tier.label} · {(d.confidence * 100).toFixed(0)}%
                              </span>
                            )
                          })()}
                        </div>
                        {d.confidence < LOW_CONFIDENCE_THRESHOLD && (
                          <p className="flex items-start gap-1 text-[11px] text-amber-700 dark:text-amber-300 bg-amber-50 dark:bg-amber-900/20 border border-amber-200 dark:border-amber-800 rounded-md px-2 py-1">
                            <AlertTriangle className="h-3 w-3 mt-0.5 shrink-0" />
                            <span>FANI wasn't very sure about this one — please double-check the name, category, and colour before saving.</span>
                          </p>
                        )}
                      </div>

                      {/* Similarity warning — RAG vector search results */}
                      <SimilarityWarningBanner
                        loading={similarLoadingIds.has(d.detected_item_id)}
                        error={similarErrorIds.has(d.detected_item_id)}
                        items={similarItemsMap[d.detected_item_id] ?? []}
                        itemName={d.name}
                        newItemImageUrl={resolveUploadUrl(d.preview_image_url) ?? d.preview_image_url}
                      />

                      {/* AI transparency banner — sets the frame that these are editable AI suggestions */}
                      <div className="flex items-start gap-2 rounded-xl bg-brand-50 dark:bg-brand-900/20 border border-brand-200 dark:border-brand-800 px-3 py-2">
                        <Sparkles size={14} className="text-brand-500 mt-0.5 shrink-0" />
                        <p className="text-[11px] leading-relaxed text-brand-700 dark:text-brand-300">
                          These details were detected by <span className="font-semibold">FANI</span> and may not be perfect.
                          Fields tagged <span className="font-bold">AI</span> were auto-filled — edit anything to override.
                          You're always in control: nothing is saved until you press Save.
                        </p>
                      </div>

                      {/* Primary fields — what FANI is most/least sure about, always visible */}
                      <div className="grid gap-2 sm:grid-cols-2">
                        <AIInput
                          label="Name"
                          id={`f-${d.detected_item_id}-name`}
                          aiState={aiFieldState(d, 'name')}
                          value={d.name}
                          onChange={e => updateDraft(currentWizardItem.sessionId, d.slot_index, { name: e.target.value })}
                        />
                        <div className="w-full">
                          <AIFieldLabel label="Category" state={aiFieldState(d, 'category')} htmlFor={`f-${d.detected_item_id}-category`} />
                          <Select
                            id={`f-${d.detected_item_id}-category`}
                            options={CATEGORY_OPTIONS}
                            value={d.category}
                            onChange={e => updateDraft(currentWizardItem.sessionId, d.slot_index, { category: e.target.value })}
                          />
                        </div>
                        <AIInput
                          label="Color"
                          id={`f-${d.detected_item_id}-color`}
                          aiState={aiFieldState(d, 'color')}
                          value={d.color}
                          onChange={e => updateDraft(currentWizardItem.sessionId, d.slot_index, { color: e.target.value })}
                        />
                      </div>

                      {/* Season & Occasion — tap a chip or type your own (recognition over recall) */}
                      <TokenField
                        label="Season"
                        id={`f-${d.detected_item_id}-season`}
                        value={d.seasonStr}
                        suggestions={CLOSET_SEASONS}
                        placeholder="spring, summer"
                        aiState={aiFieldState(d, 'seasonStr')}
                        onChange={v => updateDraft(currentWizardItem.sessionId, d.slot_index, { seasonStr: v })}
                      />
                      <TokenField
                        label="Occasion"
                        id={`f-${d.detected_item_id}-occasion`}
                        value={d.occasionStr}
                        suggestions={CLOSET_OCCASIONS}
                        placeholder="casual, work"
                        aiState={aiFieldState(d, 'occasionStr')}
                        onChange={v => updateDraft(currentWizardItem.sessionId, d.slot_index, { occasionStr: v })}
                      />

                      {/* Secondary fields — progressive disclosure keeps the card light */}
                      {(() => {
                        const moreKeys = ['material', 'pattern', 'brand', 'size', 'priceStr'] as const
                        const filledCount = moreKeys.filter(k => (d[k] as string).trim()).length
                        return (
                          <div>
                            <button
                              type="button"
                              onClick={() => setShowMore(v => !v)}
                              aria-expanded={showMore}
                              className="flex items-center gap-1.5 text-xs font-semibold text-slate-500 dark:text-slate-400 hover:text-slate-700 dark:hover:text-slate-200 transition-colors"
                            >
                              <ChevronRight size={14} className={cn('transition-transform', showMore && 'rotate-90')} />
                              More details
                              {filledCount > 0 && (
                                <span className="text-[10px] font-bold text-brand-500">({filledCount} filled)</span>
                              )}
                            </button>
                            <div className={cn(
                              'overflow-hidden transition-all duration-200 ease-in-out',
                              showMore ? 'max-h-[28rem] opacity-100 mt-2' : 'max-h-0 opacity-0',
                            )}>
                              <div className="grid gap-2 sm:grid-cols-2">
                                <AIInput
                                  label="Material"
                                  id={`f-${d.detected_item_id}-material`}
                                  aiState={aiFieldState(d, 'material')}
                                  value={d.material}
                                  onChange={e => updateDraft(currentWizardItem.sessionId, d.slot_index, { material: e.target.value })}
                                />
                                <AIInput
                                  label="Pattern"
                                  id={`f-${d.detected_item_id}-pattern`}
                                  aiState={aiFieldState(d, 'pattern')}
                                  value={d.pattern}
                                  onChange={e => updateDraft(currentWizardItem.sessionId, d.slot_index, { pattern: e.target.value })}
                                />
                                <div className="w-full">
                                  <label htmlFor={`f-${d.detected_item_id}-brand`} className="label">Brand</label>
                                  <Input
                                    id={`f-${d.detected_item_id}-brand`}
                                    value={d.brand}
                                    onChange={e => updateDraft(currentWizardItem.sessionId, d.slot_index, { brand: e.target.value })}
                                  />
                                </div>
                                <div className="w-full">
                                  <label htmlFor={`f-${d.detected_item_id}-size`} className="label">Size</label>
                                  <Input
                                    id={`f-${d.detected_item_id}-size`}
                                    value={d.size}
                                    onChange={e => updateDraft(currentWizardItem.sessionId, d.slot_index, { size: e.target.value })}
                                  />
                                </div>
                                <div className="w-full">
                                  <label htmlFor={`f-${d.detected_item_id}-price`} className="label">Price</label>
                                  <Input
                                    id={`f-${d.detected_item_id}-price`}
                                    value={d.priceStr}
                                    onChange={e => updateDraft(currentWizardItem.sessionId, d.slot_index, { priceStr: e.target.value })}
                                    type="number"
                                    step="0.01"
                                  />
                                </div>
                              </div>
                            </div>
                          </div>
                        )
                      })()}

                      <div>
                        <AIFieldLabel label="Description" state={aiFieldState(d, 'notes')} htmlFor={`f-${d.detected_item_id}-notes`} />
                        <textarea
                          id={`f-${d.detected_item_id}-notes`}
                          rows={2}
                          className="input resize-none w-full"
                          value={d.notes}
                          onChange={e => updateDraft(currentWizardItem.sessionId, d.slot_index, { notes: e.target.value })}
                        />
                      </div>
                    </>
                  )
                })()}

                {/* Navigation */}
                <div className="flex items-center gap-2 pt-1 border-t border-cream-100 dark:border-slate-700">
                  {/* Back */}
                  <button
                    onClick={wizardBack}
                    disabled={isFirstItem || savingAll}
                    className={cn(
                      'flex items-center gap-1 px-3 py-2 rounded-xl text-xs font-medium transition-colors border',
                      isFirstItem
                        ? 'border-slate-200 dark:border-slate-700 text-slate-300 dark:text-slate-600 cursor-default'
                        : 'border-slate-200 dark:border-slate-700 text-slate-600 dark:text-slate-300 hover:bg-slate-50 dark:hover:bg-slate-800',
                    )}
                  >
                    <ChevronLeft size={14} />
                    Back
                  </button>

                  {/* Skip */}
                  <button
                    onClick={wizardSkip}
                    disabled={savingAll}
                    className="flex items-center gap-1 px-3 py-2 rounded-xl text-xs font-medium transition-colors border border-slate-200 dark:border-slate-700 text-slate-500 dark:text-slate-400 hover:bg-slate-50 dark:hover:bg-slate-800 hover:text-slate-700 disabled:opacity-40"
                    title="Skip this item (won't be saved)"
                  >
                    <SkipForward size={14} />
                    Skip
                  </button>

                  {/* Next / Save */}
                  <button
                    onClick={wizardNext}
                    disabled={savingAll}
                    className={cn(
                      'flex items-center justify-center gap-1.5 flex-1 py-2 rounded-xl text-xs font-semibold transition-all',
                      isLastItem
                        ? 'bg-gradient-brand text-white hover:opacity-90 active:scale-[0.98]'
                        : 'bg-brand-500 text-white hover:bg-brand-600 active:scale-[0.98]',
                      savingAll && 'opacity-60 cursor-default',
                    )}
                  >
                    {savingAll ? (
                      <><LoadingSpinner size="sm" /> Saving…</>
                    ) : isLastItem ? (
                      <><CheckCircle size={13} /> Save {selectedCount > 0 ? `${selectedCount} item${selectedCount === 1 ? '' : 's'}` : 'All'}</>
                    ) : (
                      <>Next <ChevronRight size={14} /></>
                    )}
                  </button>
                </div>

                {/* Persistent reassurance — recover/help */}
                <p className="text-[11px] text-slate-400 text-center">
                  {selectedCount} of {totalDetections} will be saved · skipped items are left out · nothing saves until you press Save
                </p>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
