import { useState, useRef, useCallback, useMemo } from 'react'
import { Image, Sparkles, CheckCircle, X, ChevronLeft, ChevronRight, SkipForward, AlertTriangle } from 'lucide-react'
import Button from '@/components/ui/Button'
import BackButton from '@/components/ui/BackButton'
import PageHeader from '@/components/ui/PageHeader'
import Input, { Select } from '@/components/ui/Input'
import Badge from '@/components/ui/Badge'
import { useApp } from '@/store'
import { closetApi, closetSimilarityApi, resolveUploadUrl, type ClosetPreviewItem, type SimilarClosetItem } from '@/lib/api'
import { cn } from '@/lib/utils'
import { InlineError } from '@/components/system/InlineError'
import { LoadingSpinner } from '@/components/system/LoadingSpinner'
import SimilarityWarningBanner from '@/components/closet/SimilarityWarningBanner'

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
  return (items ?? []).map(it => ({
    slot_index: it.slot_index,
    temp_id: it.temp_id,
    detected_item_id: it.detected_item_id ?? it.temp_id,
    selected: true,
    name: it.name,
    category: it.category,
    color: it.color ?? '',
    subcategory: it.subcategory ?? '',
    material: it.material ?? '',
    pattern: it.pattern ?? '',
    seasonStr: (it.season ?? []).join(', '),
    occasionStr: (it.occasions ?? []).join(', '),
    notes: it.description ?? '',
    brand: it.brand ?? '',
    size: '',
    priceStr: '',
    preview_image_url: it.preview_image_url,
    confidence: it.confidence,
    background_removed: it.background_removed,
    bg_status: it.background_removal_status ?? undefined,
  }))
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
  bg_status?: string
}

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
  const [preview, setPreview] = useState<string | null>(null)
  const [uploading, setUploading] = useState(false)
  const [uploadProgress, setUploadProgress] = useState<string | null>(null)
  const [previewGroups, setPreviewGroups] = useState<PreviewGroup[]>([])
  const [analyzeFailures, setAnalyzeFailures] = useState<{ filename: string; error: string }[]>([])
  const [savingAll, setSavingAll] = useState(false)
  const [saveOkMessage, setSaveOkMessage] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [wizardIndex, setWizardIndex] = useState(0)
  const inputRef = useRef<HTMLInputElement>(null)

  // Similarity check state — keyed by detected_item_id
  const [similarItemsMap, setSimilarItemsMap] = useState<Record<string, SimilarClosetItem[]>>({})
  const [similarLoadingIds, setSimilarLoadingIds] = useState<Set<string>>(new Set())
  const [similarErrorIds, setSimilarErrorIds] = useState<Set<string>>(new Set())

  const inPreview = previewGroups.length > 0
  const hasFailures = analyzeFailures.length > 0

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
    const images = selected.filter(f => f.type.startsWith('image/')).slice(0, 20)
    setFiles(images)
    if (preview) URL.revokeObjectURL(preview)
    setPreview(images[0] ? URL.createObjectURL(images[0]) : null)
    setPreviewGroups([])
    setAnalyzeFailures([])
    setSaveOkMessage(null)
    setError(null)
    setWizardIndex(0)
    setSimilarItemsMap({})
    setSimilarLoadingIds(new Set())
    setSimilarErrorIds(new Set())
  }, [preview])

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
    setFiles([])
    if (preview) URL.revokeObjectURL(preview)
    setPreview(null)
    setPreviewGroups([])
    setAnalyzeFailures([])
    setUploadProgress(null)
    setSaveOkMessage(null)
    setError(null)
    setWizardIndex(0)
    setSimilarItemsMap({})
    setSimilarLoadingIds(new Set())
    setSimilarErrorIds(new Set())
  }, [preview])

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

  /** Save every group that has at least one selected item. */
  const confirmAllGroups = async () => {
    setSavingAll(true)
    setError(null)
    setSaveOkMessage(null)
    try {
      let totalSaved = 0
      for (const group of previewGroups) {
        if (!group.saved && group.drafts.some(d => d.selected)) {
          totalSaved += await confirmGroup(group)
        }
      }
      await fetchClosetItems()
      if (totalSaved > 0) {
        setSaveOkMessage(`${totalSaved} item${totalSaved === 1 ? '' : 's'} saved to your closet!`)
      } else {
        setError('No items were selected to save. Skip or go back and select some.')
      }
    } catch (err: unknown) {
      setError(`Save failed: ${extractErr(err)}`)
    } finally {
      setSavingAll(false)
    }
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
            className={cn(
              'relative border-2 border-dashed rounded-2xl transition-all duration-200 cursor-pointer',
              dragging ? 'drop-zone-active' : 'border-cream-300 dark:border-slate-600 hover:border-brand-400',
              preview ? 'aspect-[3/4]' : 'aspect-square',
            )}
            onDragOver={e => { e.preventDefault(); setDragging(true) }}
            onDragLeave={() => setDragging(false)}
            onDrop={onDrop}
            onClick={() => !inPreview && !preview && inputRef.current?.click()}
          >
            {preview ? (
              <>
                <img src={preview} alt="preview" className="w-full h-full object-cover rounded-2xl" />
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

          {files.length > 0 && !inPreview && (
            <p className="text-xs font-medium text-slate-500 dark:text-slate-400 text-center">
              {files.length} of 20 files selected
            </p>
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
            <Button className="w-full" disabled={uploading} icon={<Sparkles size={15} />} onClick={analyze}>
              {uploading ? 'Analyzing…' : files.length > 1 ? 'Analyze with FANI (preview)' : 'Analyze with FANI'}
            </Button>
          )}

          {inPreview && (
            <div className="flex flex-col gap-2">
              <Button
                className="w-full"
                variant="secondary"
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
                Back — adjust photos & analyze again
              </Button>
              <Button className="w-full" variant="secondary" onClick={discardPreview} icon={<X size={15} />}>
                Discard & start over
              </Button>
            </div>
          )}
        </div>

        {/* ── Right panel: wizard review ── */}
        <div className="space-y-4">
          {!inPreview && files.length === 0 && (
            <div className="card p-6 text-center text-slate-500 dark:text-slate-400 text-sm">
              Choose one or more photos to see AI-detected items. Nothing is saved until you confirm.
            </div>
          )}

          {/* Wizard — one item at a time */}
          {inPreview && totalDetections === 0 && (
            <div className="card p-6 text-center text-amber-600 dark:text-amber-400 text-sm">
              No clothing items were detected.
            </div>
          )}

          {inPreview && allSaved && (
            <div className="card p-6 text-center space-y-2">
              <CheckCircle size={32} className="text-emerald-500 mx-auto" />
              <p className="font-semibold text-slate-700 dark:text-slate-200">All items saved!</p>
              <p className="text-sm text-slate-400">Upload another photo to keep growing your closet.</p>
            </div>
          )}

          {inPreview && !allSaved && currentWizardItem && (
            <div className="card overflow-hidden">
              {/* Progress bar */}
              <div className="px-4 pt-4 pb-2 space-y-2">
                <div className="flex items-center justify-between text-xs">
                  <span className="font-medium text-slate-600 dark:text-slate-300">
                    Item {wizardIndex + 1} <span className="text-slate-400">of {totalDetections}</span>
                  </span>
                  <div className="flex items-center gap-2">
                    {previewGroups.length > 1 && (
                      <span className="text-slate-400 truncate max-w-[120px]">{currentWizardItem.filename}</span>
                    )}
                    {currentWizardItem.draft.selected ? (
                      <Badge variant="green">Include</Badge>
                    ) : (
                      <Badge variant="gray">Skipped</Badge>
                    )}
                  </div>
                </div>
                {/* Step dots */}
                <div className="flex gap-1">
                  {allWizardItems.map((wi, idx) => (
                    <button
                      key={idx}
                      onClick={() => setWizardIndex(idx)}
                      className={cn(
                        'h-1.5 rounded-full flex-1 transition-all',
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

                      {/* Name + badges */}
                      <div className="space-y-1.5">
                        <p className="font-semibold text-sm text-slate-800 dark:text-slate-100">{d.name}</p>
                        <div className="flex flex-wrap gap-1">
                          <Badge variant="purple">{d.category}</Badge>
                          {d.subcategory.trim() ? <Badge variant="gray">{d.subcategory}</Badge> : null}
                          {d.background_removed && <Badge variant="gray">BG removed</Badge>}
                          <span
                            className={
                              d.confidence < LOW_CONFIDENCE_THRESHOLD
                                ? 'text-[10px] font-medium text-amber-600 dark:text-amber-400 self-center'
                                : 'text-[10px] text-slate-400 self-center'
                            }
                          >
                            {(d.confidence * 100).toFixed(0)}% confidence
                          </span>
                        </div>
                        {d.confidence < LOW_CONFIDENCE_THRESHOLD && (
                          <p className="flex items-start gap-1 text-[11px] text-amber-700 dark:text-amber-300 bg-amber-50 dark:bg-amber-900/20 border border-amber-200 dark:border-amber-800 rounded-md px-2 py-1">
                            <AlertTriangle className="h-3 w-3 mt-0.5 shrink-0" />
                            <span>Low detection confidence — please review the details below before saving.</span>
                          </p>
                        )}
                        {d.bg_status && d.bg_status !== 'success_rembg' && d.bg_status !== 'success_pil' && (
                          <p className="text-[10px] text-slate-400">BG: {d.bg_status}</p>
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

                      {/* Editable fields */}
                      <div className="grid gap-2 sm:grid-cols-2">
                        <Input
                          label="Name"
                          value={d.name}
                          onChange={e => updateDraft(currentWizardItem.sessionId, d.slot_index, { name: e.target.value })}
                        />
                        <Select
                          label="Category"
                          options={CATEGORY_OPTIONS}
                          value={d.category}
                          onChange={e => updateDraft(currentWizardItem.sessionId, d.slot_index, { category: e.target.value })}
                        />
                        <Input
                          label="Color"
                          value={d.color}
                          onChange={e => updateDraft(currentWizardItem.sessionId, d.slot_index, { color: e.target.value })}
                        />
                        <Input
                          label="Material"
                          value={d.material}
                          onChange={e => updateDraft(currentWizardItem.sessionId, d.slot_index, { material: e.target.value })}
                        />
                        <Input
                          label="Pattern"
                          value={d.pattern}
                          onChange={e => updateDraft(currentWizardItem.sessionId, d.slot_index, { pattern: e.target.value })}
                        />
                        <Input
                          label="Season"
                          value={d.seasonStr}
                          onChange={e => updateDraft(currentWizardItem.sessionId, d.slot_index, { seasonStr: e.target.value })}
                          placeholder="spring, summer"
                        />
                        <Input
                          label="Occasion"
                          value={d.occasionStr}
                          onChange={e => updateDraft(currentWizardItem.sessionId, d.slot_index, { occasionStr: e.target.value })}
                          placeholder="casual, work"
                        />
                        <Input
                          label="Brand"
                          value={d.brand}
                          onChange={e => updateDraft(currentWizardItem.sessionId, d.slot_index, { brand: e.target.value })}
                        />
                        <Input
                          label="Size"
                          value={d.size}
                          onChange={e => updateDraft(currentWizardItem.sessionId, d.slot_index, { size: e.target.value })}
                        />
                        <Input
                          label="Price"
                          value={d.priceStr}
                          onChange={e => updateDraft(currentWizardItem.sessionId, d.slot_index, { priceStr: e.target.value })}
                          type="number"
                          step="0.01"
                        />
                      </div>
                      <div>
                        <label className="label">Description</label>
                        <textarea
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
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
