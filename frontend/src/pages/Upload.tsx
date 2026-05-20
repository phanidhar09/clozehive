import { useState, useRef, useCallback, useMemo } from 'react'
import { Image, Sparkles, CheckCircle, X } from 'lucide-react'
import Button from '@/components/ui/Button'
import Input, { Select } from '@/components/ui/Input'
import Badge from '@/components/ui/Badge'
import { useApp } from '@/store'
import { closetApi, resolveUploadUrl, type ClosetPreviewItem } from '@/lib/api'
import { cn } from '@/lib/utils'
import { InlineError } from '@/components/system/InlineError'
import { LoadingSpinner } from '@/components/system/LoadingSpinner'

const CATEGORY_OPTIONS = [
  { value: 'tops', label: 'Tops' },
  { value: 'bottoms', label: 'Bottoms' },
  { value: 'shoes', label: 'Shoes' },
  { value: 'outerwear', label: 'Outerwear' },
  { value: 'dresses', label: 'Dresses' },
  { value: 'accessories', label: 'Accessories' },
  { value: 'other', label: 'Other' },
]

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

export default function Upload() {
  const { fetchClosetItems } = useApp()
  const [dragging, setDragging] = useState(false)
  const [files, setFiles] = useState<File[]>([])
  const [preview, setPreview] = useState<string | null>(null)
  const [uploading, setUploading] = useState(false)
  const [uploadProgress, setUploadProgress] = useState<string | null>(null)
  const [previewGroups, setPreviewGroups] = useState<PreviewGroup[]>([])
  const [analyzeFailures, setAnalyzeFailures] = useState<{ filename: string; error: string }[]>([])
  const [savingSessionId, setSavingSessionId] = useState<string | null>(null)
  const [saveOkMessage, setSaveOkMessage] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const inputRef = useRef<HTMLInputElement>(null)

  const inPreview = previewGroups.length > 0
  const hasFailures = analyzeFailures.length > 0

  const totalDetections = useMemo(
    () => previewGroups.reduce((n, g) => n + g.drafts.length, 0),
    [previewGroups],
  )

  const handleFiles = useCallback((selected: File[]) => {
    const images = selected.filter(f => f.type.startsWith('image/')).slice(0, 20)
    setFiles(images)
    if (preview) URL.revokeObjectURL(preview)
    setPreview(images[0] ? URL.createObjectURL(images[0]) : null)
    setPreviewGroups([])
    setAnalyzeFailures([])
    setSaveOkMessage(null)
    setError(null)
  }, [preview])

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
    setUploadProgress(files.length > 1 ? `Analyzing ${files.length} photos…` : 'Analyzing…')
    try {
      if (files.length > 1) {
        const { results, failed } = await closetApi.bulkAnalyzePreview(files)
        setAnalyzeFailures(failed)
        setPreviewGroups(
          results.flatMap(r => {
            const p = r.preview
            if (!p?.preview_session_id) return []
            return [
              {
                filename: r.filename,
                sessionId: p.preview_session_id,
                drafts: draftsFromPreviewItems(p.items),
              },
            ]
          }),
        )
        if (results.length === 0 && failed.length > 0) {
          setError('Could not analyze any files. Check errors below.')
        }
        return
      }

      const res = await closetApi.analyzePreview(files[0])
      setPreviewGroups([
        {
          filename: files[0].name || 'upload',
          sessionId: res.preview_session_id,
          drafts: draftsFromPreviewItems(res.items),
        },
      ])
      if (!res.items.length) {
        setError(
          'No items detected. Confirm the api-gateway is rebuilt/restarted, OPENAI_API_KEY is set for it, and Redis (closet preview) is up — then try again. You can still fill details manually after saving.',
        )
      }
    } catch (err: unknown) {
      setError(`Analysis failed: ${extractErr(err)}`)
      console.error(err)
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

  const confirmGroup = async (group: PreviewGroup) => {
    setSavingSessionId(group.sessionId)
    setError(null)
    setSaveOkMessage(null)
    const selected = group.drafts.filter(d => d.selected)
    if (selected.length === 0) {
      setError('Select at least one item to save.')
      setSavingSessionId(null)
      return
    }
    try {
      const priceNum = (s: string): number | undefined => {
        const t = s.trim()
        if (!t) return undefined
        const n = Number(t)
        return Number.isFinite(n) ? n : undefined
      }
      const { saved, total_saved } = await closetApi.confirmPreview({
        preview_session_id: group.sessionId,
        items: group.drafts.map(d => ({
          slot_index: d.slot_index,
          // Send detected_item_id so backend can validate image↔metadata correlation.
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
      await fetchClosetItems()
      setSaveOkMessage(`Saved ${total_saved} item(s) to your closet.`)
      setPreviewGroups(gs => gs.map(g => (g.sessionId === group.sessionId ? { ...g, saved: true } : g)))
      if (saved.length) {
        /* keep preview visible with saved badge; user can discard to upload more */
      }
    } catch (err: unknown) {
      setError(`Save failed: ${extractErr(err)}`)
    } finally {
      setSavingSessionId(null)
    }
  }

  const discardPreview = () => {
    resetAll()
  }

  return (
    <div className="max-w-3xl space-y-6">
      <div>
        <h2 className="font-display font-bold text-xl text-slate-800 dark:text-slate-100">Upload Clothing Item</h2>
        <p className="text-sm text-slate-400 mt-0.5">
          AI analyzes your photo — review and confirm before anything is added to your closet
        </p>
      </div>

      {error && <InlineError message={error} className="mb-4" />}
      {saveOkMessage && (
        <div className="card p-3 bg-emerald-50 dark:bg-emerald-900/20 border-emerald-200 text-emerald-800 dark:text-emerald-200 text-sm flex items-center gap-2">
          <CheckCircle size={16} />
          {saveOkMessage}
        </div>
      )}

      <div className="grid md:grid-cols-2 gap-6">
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

        <div className="space-y-4">
          {!inPreview && files.length === 0 && (
            <div className="card p-6 text-center text-slate-500 dark:text-slate-400 text-sm">
              Choose one or more photos to see AI-detected items. Nothing is saved until you confirm.
            </div>
          )}

          {inPreview && (
            <>
              <div className="flex items-center justify-between flex-wrap gap-2">
                <p className="text-sm font-semibold text-slate-700 dark:text-slate-200">
                  {totalDetections} detected item{totalDetections === 1 ? '' : 's'} — edit, uncheck to skip, then save
                </p>
                {previewGroups.some(g => g.saved) && (
                  <Badge variant="green">Saved</Badge>
                )}
              </div>

              {previewGroups.map(group => (
                <div key={group.sessionId} className="card p-4 space-y-4 border border-cream-200 dark:border-slate-700">
                  <div className="flex items-center justify-between gap-2 flex-wrap">
                    <p className="text-xs font-semibold text-slate-500 uppercase tracking-wide">{group.filename}</p>
                    {group.saved && <Badge variant="green">In closet</Badge>}
                  </div>

                  {group.drafts.length === 0 && (
                    <p className="text-sm text-amber-600 dark:text-amber-400">No items for this file.</p>
                  )}

                  {group.drafts.map(d => {
                    const imgSrc = resolveUploadUrl(d.preview_image_url) ?? d.preview_image_url
                    return (
                      <div
                        key={`${group.sessionId}-${d.detected_item_id}`}
                        className="rounded-xl border border-slate-200 dark:border-slate-600 p-3 space-y-3 bg-white/50 dark:bg-slate-900/40"
                      >
                        <label className="flex items-start gap-3 cursor-pointer">
                          <input
                            type="checkbox"
                            className="mt-1 rounded border-slate-300"
                            checked={d.selected}
                            onChange={e => updateDraft(group.sessionId, d.slot_index, { selected: e.target.checked })}
                          />
                          <div className="flex gap-3 flex-1 min-w-0">
                            {imgSrc && (
                              <img
                                src={imgSrc}
                                alt=""
                                className="w-20 h-24 object-cover rounded-lg shrink-0 bg-slate-100 dark:bg-slate-800"
                              />
                            )}
                            <div className="space-y-1 min-w-0">
                              <p className="text-sm font-semibold text-slate-800 dark:text-slate-100 truncate">{d.name}</p>
                              <div className="flex flex-wrap gap-1">
                                <Badge variant="purple">{d.category}</Badge>
                                {d.subcategory.trim() ? <Badge variant="gray">{d.subcategory}</Badge> : null}
                                {d.background_removed && <Badge variant="gray">BG removed</Badge>}
                                <span className="text-[10px] text-slate-400">conf {(d.confidence * 100).toFixed(0)}%</span>
                              </div>
                              {d.bg_status && d.bg_status !== 'success_rembg' && d.bg_status !== 'success_pil' && (
                                <p className="text-[10px] text-slate-400">BG: {d.bg_status}</p>
                              )}
                            </div>
                          </div>
                        </label>

                        <div className="grid gap-2 sm:grid-cols-2">
                          <Input
                            label="Name"
                            value={d.name}
                            onChange={e => updateDraft(group.sessionId, d.slot_index, { name: e.target.value })}
                          />
                          <Select
                            label="Category"
                            options={CATEGORY_OPTIONS}
                            value={d.category}
                            onChange={e => updateDraft(group.sessionId, d.slot_index, { category: e.target.value })}
                          />
                          <Input
                            label="Color"
                            value={d.color}
                            onChange={e => updateDraft(group.sessionId, d.slot_index, { color: e.target.value })}
                          />
                          <Input
                            label="Material"
                            value={d.material}
                            onChange={e => updateDraft(group.sessionId, d.slot_index, { material: e.target.value })}
                          />
                          <Input
                            label="Pattern"
                            value={d.pattern}
                            onChange={e => updateDraft(group.sessionId, d.slot_index, { pattern: e.target.value })}
                          />
                          <Input
                            label="Season (comma-separated)"
                            value={d.seasonStr}
                            onChange={e => updateDraft(group.sessionId, d.slot_index, { seasonStr: e.target.value })}
                            placeholder="spring, summer"
                          />
                          <Input
                            label="Occasion (comma-separated)"
                            value={d.occasionStr}
                            onChange={e => updateDraft(group.sessionId, d.slot_index, { occasionStr: e.target.value })}
                            placeholder="casual, work"
                          />
                          <Input
                            label="Brand"
                            value={d.brand}
                            onChange={e => updateDraft(group.sessionId, d.slot_index, { brand: e.target.value })}
                          />
                          <Input
                            label="Size"
                            value={d.size}
                            onChange={e => updateDraft(group.sessionId, d.slot_index, { size: e.target.value })}
                          />
                          <Input
                            label="Price"
                            value={d.priceStr}
                            onChange={e => updateDraft(group.sessionId, d.slot_index, { priceStr: e.target.value })}
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
                            onChange={e => updateDraft(group.sessionId, d.slot_index, { notes: e.target.value })}
                          />
                        </div>
                      </div>
                    )
                  })}

                  {!group.saved && (
                    <Button
                      className="w-full"
                      loading={savingSessionId === group.sessionId}
                      icon={<CheckCircle size={15} />}
                      onClick={() => confirmGroup(group)}
                    >
                      Save selected items from this photo
                    </Button>
                  )}
                </div>
              ))}
            </>
          )}
        </div>
      </div>
    </div>
  )
}
