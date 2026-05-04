/**
 * SmartUpload — AI-powered bulk closet ingestion
 *
 * 4-step flow:
 *   upload  →  processing  →  review  →  done
 *
 * Step 1 (upload)    : Drag-and-drop or click to select up to 20 images.
 * Step 2 (processing): Poll job status every 2 s; animated progress bar.
 * Step 3 (review)    : Grid of AI-detected items. Edit metadata inline,
 *                      reject bad detections, bulk-select, then approve.
 * Step 4 (done)      : Summary card + "View Closet" CTA.
 */

import { useCallback, useEffect, useRef, useState } from 'react'
import {
  AlertCircle,
  CheckCircle2,
  ChevronDown,
  Edit3,
  Loader2,
  Package,
  Sparkles,
  Trash2,
  Upload,
  X,
} from 'lucide-react'
import { useApp } from '@/store'
import { smartIngestApi } from '@/lib/api'
import type { IngestJob, ReviewItem } from '@/types'

// ── Constants ──────────────────────────────────────────────────────────────────

const MAX_FILES = 20
const POLL_INTERVAL_MS = 2_000

const CATEGORY_OPTIONS = [
  'tops', 'bottoms', 'shoes', 'outerwear', 'dresses', 'accessories', 'other',
]

// ── Helpers ────────────────────────────────────────────────────────────────────

function confidenceBadge(score: number) {
  if (score >= 0.85) return { label: `${Math.round(score * 100)}%`, cls: 'bg-emerald-100 text-emerald-700 dark:bg-emerald-500/20 dark:text-emerald-300' }
  if (score >= 0.65) return { label: `${Math.round(score * 100)}%`, cls: 'bg-amber-100 text-amber-700 dark:bg-amber-500/20 dark:text-amber-300' }
  return { label: `${Math.round(score * 100)}%`, cls: 'bg-red-100 text-red-700 dark:bg-red-500/20 dark:text-red-300' }
}

function ItemImageCell({ item }: { item: ReviewItem }) {
  const src = item.processed_image_url || item.original_crop_url
  return (
    <div className="relative aspect-square overflow-hidden rounded-2xl bg-[repeating-conic-gradient(#f3f4f6_0%_25%,transparent_0%_50%)_0_0/16px_16px] dark:bg-[repeating-conic-gradient(#1e293b_0%_25%,transparent_0%_50%)_0_0/16px_16px]">
      {src
        ? <img src={src} alt={item.name} className="h-full w-full object-contain" />
        : <div className="flex h-full w-full items-center justify-center text-3xl">👕</div>
      }
      {item.needs_review && (
        <div className="absolute right-1.5 top-1.5 rounded-full bg-amber-500 p-1" title="Low confidence — review recommended">
          <AlertCircle size={10} className="text-white" />
        </div>
      )}
    </div>
  )
}

// ── Inline edit panel ──────────────────────────────────────────────────────────

interface EditPanelProps {
  item: ReviewItem
  onSave: (updates: Partial<ReviewItem>) => Promise<void>
  onClose: () => void
}

function EditPanel({ item, onSave, onClose }: EditPanelProps) {
  const [form, setForm] = useState({
    name: item.name,
    category: item.category,
    subcategory: item.subcategory,
    primary_color: item.primary_color,
    material: item.material,
    pattern: item.pattern,
    brand: item.brand,
    fit: item.fit,
  })
  const [saving, setSaving] = useState(false)

  const handle = async () => {
    setSaving(true)
    await onSave(form)
    setSaving(false)
    onClose()
  }

  return (
    <div className="mt-3 rounded-2xl border border-brand-200 bg-brand-50/60 p-3 dark:border-brand-500/30 dark:bg-brand-900/20 space-y-2.5">
      <div className="grid grid-cols-2 gap-2">
        <div className="col-span-2">
          <label className="text-[10px] font-semibold uppercase tracking-wide text-slate-500">Name</label>
          <input className="input mt-0.5 text-sm" value={form.name} onChange={e => setForm(f => ({ ...f, name: e.target.value }))} />
        </div>
        <div>
          <label className="text-[10px] font-semibold uppercase tracking-wide text-slate-500">Category</label>
          <select className="input mt-0.5 text-sm" value={form.category} onChange={e => setForm(f => ({ ...f, category: e.target.value }))}>
            {CATEGORY_OPTIONS.map(o => <option key={o} value={o}>{o}</option>)}
          </select>
        </div>
        <div>
          <label className="text-[10px] font-semibold uppercase tracking-wide text-slate-500">Subcategory</label>
          <input className="input mt-0.5 text-sm" value={form.subcategory} onChange={e => setForm(f => ({ ...f, subcategory: e.target.value }))} placeholder="e.g. T-Shirt" />
        </div>
        <div>
          <label className="text-[10px] font-semibold uppercase tracking-wide text-slate-500">Color</label>
          <input className="input mt-0.5 text-sm" value={form.primary_color} onChange={e => setForm(f => ({ ...f, primary_color: e.target.value }))} />
        </div>
        <div>
          <label className="text-[10px] font-semibold uppercase tracking-wide text-slate-500">Material</label>
          <input className="input mt-0.5 text-sm" value={form.material} onChange={e => setForm(f => ({ ...f, material: e.target.value }))} />
        </div>
        <div>
          <label className="text-[10px] font-semibold uppercase tracking-wide text-slate-500">Brand</label>
          <input className="input mt-0.5 text-sm" value={form.brand} onChange={e => setForm(f => ({ ...f, brand: e.target.value }))} />
        </div>
        <div>
          <label className="text-[10px] font-semibold uppercase tracking-wide text-slate-500">Fit</label>
          <select className="input mt-0.5 text-sm" value={form.fit} onChange={e => setForm(f => ({ ...f, fit: e.target.value }))}>
            {['Slim', 'Regular', 'Relaxed', 'Oversized', 'Tailored'].map(o => <option key={o} value={o}>{o}</option>)}
          </select>
        </div>
      </div>
      <div className="flex gap-2">
        <button
          className="flex-1 rounded-xl bg-brand-600 py-2 text-xs font-semibold text-white hover:bg-brand-700 disabled:opacity-50 transition"
          onClick={handle}
          disabled={saving}
        >
          {saving ? <Loader2 size={13} className="mx-auto animate-spin" /> : 'Save'}
        </button>
        <button className="rounded-xl border border-slate-200 px-3 py-2 text-xs text-slate-500 hover:bg-slate-50 dark:border-slate-700 dark:hover:bg-slate-800" onClick={onClose}>
          Cancel
        </button>
      </div>
    </div>
  )
}

// ── Review item card ───────────────────────────────────────────────────────────

interface ReviewCardProps {
  item: ReviewItem
  selected: boolean
  onToggle: () => void
  onEdit: (updates: Partial<ReviewItem>) => Promise<void>
  onReject: () => void
}

function ReviewCard({ item, selected, onToggle, onEdit, onReject }: ReviewCardProps) {
  const [editOpen, setEditOpen] = useState(false)
  const [tagsOpen, setTagsOpen] = useState(false)
  const badge = confidenceBadge(item.confidence_score)

  return (
    <div
      className={`relative rounded-3xl border p-3 transition-all duration-200 ${
        selected
          ? 'border-brand-500 bg-brand-50/50 shadow-md dark:border-brand-400 dark:bg-brand-900/20'
          : 'border-cream-200 bg-white dark:border-white/10 dark:bg-white/[0.04]'
      }`}
    >
      {/* Selection checkbox */}
      <button
        onClick={onToggle}
        className={`absolute left-3 top-3 z-10 flex h-6 w-6 items-center justify-center rounded-full border-2 transition ${
          selected
            ? 'border-brand-500 bg-brand-500 text-white'
            : 'border-slate-300 bg-white dark:border-slate-600 dark:bg-slate-800'
        }`}
        aria-label={selected ? 'Deselect' : 'Select'}
      >
        {selected && <CheckCircle2 size={13} />}
      </button>

      {/* Confidence badge */}
      <div className={`absolute right-3 top-3 z-10 rounded-full px-2 py-0.5 text-[10px] font-bold ${badge.cls}`}>
        {badge.label}
      </div>

      {/* Image */}
      <div className="mt-2">
        <ItemImageCell item={item} />
      </div>

      {/* Metadata */}
      <div className="mt-2.5 space-y-1">
        <p className="truncate text-sm font-semibold text-slate-800 dark:text-white">{item.name}</p>
        <div className="flex flex-wrap gap-1">
          <span className="rounded-full bg-slate-100 px-2 py-0.5 text-[10px] capitalize text-slate-600 dark:bg-slate-800 dark:text-slate-300">
            {item.category}
          </span>
          {item.subcategory && (
            <span className="rounded-full bg-slate-100 px-2 py-0.5 text-[10px] text-slate-500 dark:bg-slate-800 dark:text-slate-400">
              {item.subcategory}
            </span>
          )}
          {item.primary_color && (
            <span className="rounded-full bg-slate-100 px-2 py-0.5 text-[10px] text-slate-500 dark:bg-slate-800 dark:text-slate-400">
              {item.primary_color}
            </span>
          )}
        </div>

        {/* Style/occasion tags (collapsed) */}
        {(item.style_tags.length > 0 || item.occasion_tags.length > 0) && (
          <button
            onClick={() => setTagsOpen(o => !o)}
            className="flex items-center gap-1 text-[10px] text-brand-500 hover:text-brand-600"
          >
            {tagsOpen ? 'Hide' : 'Show'} tags <ChevronDown size={10} className={tagsOpen ? 'rotate-180' : ''} />
          </button>
        )}
        {tagsOpen && (
          <div className="flex flex-wrap gap-1 pt-0.5">
            {[...item.style_tags, ...item.occasion_tags].map((tag, i) => (
              <span key={i} className="rounded-full bg-brand-50 px-2 py-0.5 text-[10px] text-brand-600 dark:bg-brand-900/30 dark:text-brand-300">
                {tag}
              </span>
            ))}
          </div>
        )}

        {/* Warnings */}
        {item.warnings.length > 0 && (
          <div className="flex items-start gap-1 text-[10px] text-amber-600 dark:text-amber-400">
            <AlertCircle size={10} className="mt-0.5 flex-shrink-0" />
            {item.warnings[0]}
          </div>
        )}
      </div>

      {/* Actions */}
      <div className="mt-2 flex gap-1.5">
        <button
          onClick={() => setEditOpen(o => !o)}
          className="flex flex-1 items-center justify-center gap-1.5 rounded-xl border border-slate-200 py-1.5 text-xs font-medium text-slate-600 transition hover:bg-slate-50 dark:border-slate-700 dark:text-slate-300 dark:hover:bg-slate-800"
        >
          <Edit3 size={11} /> Edit
        </button>
        <button
          onClick={onReject}
          className="flex h-8 w-8 items-center justify-center rounded-xl border border-red-200 text-red-400 transition hover:bg-red-50 hover:text-red-600 dark:border-red-800 dark:hover:bg-red-900/20"
          aria-label="Reject item"
        >
          <Trash2 size={11} />
        </button>
      </div>

      {editOpen && (
        <EditPanel
          item={item}
          onSave={async updates => { await onEdit(updates); setEditOpen(false) }}
          onClose={() => setEditOpen(false)}
        />
      )}
    </div>
  )
}

// ── Main page ──────────────────────────────────────────────────────────────────

type Step = 'upload' | 'processing' | 'review' | 'done'

export default function SmartUpload() {
  const { fetchClosetItems } = useApp()

  const [step, setStep] = useState<Step>('upload')
  const [dragging, setDragging] = useState(false)
  const [files, setFiles] = useState<File[]>([])
  const [previews, setPreviews] = useState<string[]>([])
  const [uploading, setUploading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  // Processing state
  const [jobId, setJobId] = useState<string | null>(null)
  const [jobStatus, setJobStatus] = useState<IngestJob | null>(null)
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null)

  // Review state
  const [items, setItems] = useState<ReviewItem[]>([])
  const [selected, setSelected] = useState<Set<string>>(new Set())
  const [approving, setApproving] = useState(false)
  const [approveResult, setApproveResult] = useState<{ approved: number; failed: number } | null>(null)

  const inputRef = useRef<HTMLInputElement>(null)

  // ── File selection ──────────────────────────────────────────────────────────

  const handleFiles = useCallback((selected: File[]) => {
    const images = selected.filter(f => f.type.startsWith('image/')).slice(0, MAX_FILES)
    setFiles(images)
    setPreviews(images.slice(0, 6).map(f => URL.createObjectURL(f)))
    setError(null)
  }, [])

  const onDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault()
    setDragging(false)
    handleFiles(Array.from(e.dataTransfer.files))
  }, [handleFiles])

  // ── Start upload ────────────────────────────────────────────────────────────

  const startUpload = async () => {
    if (!files.length) return
    setUploading(true)
    setError(null)
    try {
      const result = await smartIngestApi.start(files)
      setJobId(result.job_id)
      setStep('processing')
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Upload failed. Please try again.')
    } finally {
      setUploading(false)
    }
  }

  // ── Poll status ─────────────────────────────────────────────────────────────

  useEffect(() => {
    if (step !== 'processing' || !jobId) return

    const poll = async () => {
      try {
        const status = await smartIngestApi.getStatus(jobId)
        setJobStatus(status)

        if (status.status === 'completed') {
          clearInterval(pollRef.current!)
          const results = await smartIngestApi.getResults(jobId)
          setItems(results.items)
          setSelected(new Set(results.items.map(i => i.temp_item_id)))
          setStep('review')
        } else if (status.status === 'failed') {
          clearInterval(pollRef.current!)
          setError('Processing failed. Please try again.')
          setStep('upload')
        }
      } catch {
        // Network hiccup — keep polling
      }
    }

    poll()   // immediate first poll
    pollRef.current = setInterval(poll, POLL_INTERVAL_MS)
    return () => clearInterval(pollRef.current!)
  }, [step, jobId])

  // ── Review actions ──────────────────────────────────────────────────────────

  const editItem = async (itemId: string, updates: Partial<ReviewItem>) => {
    if (!jobId) return
    const updated = await smartIngestApi.updateItem(jobId, itemId, updates)
    setItems(prev => prev.map(i => i.temp_item_id === itemId ? updated : i))
  }

  const rejectItem = async (itemId: string) => {
    if (!jobId) return
    await smartIngestApi.rejectItem(jobId, itemId)
    setItems(prev => prev.filter(i => i.temp_item_id !== itemId))
    setSelected(prev => { const next = new Set(prev); next.delete(itemId); return next })
  }

  const toggleSelect = (itemId: string) => {
    setSelected(prev => {
      const next = new Set(prev)
      next.has(itemId) ? next.delete(itemId) : next.add(itemId)
      return next
    })
  }

  const selectAll = () => setSelected(new Set(items.map(i => i.temp_item_id)))
  const deselectAll = () => setSelected(new Set())

  const approve = async () => {
    if (!jobId || selected.size === 0) return
    setApproving(true)
    try {
      const result = await smartIngestApi.approve(jobId, Array.from(selected))
      setApproveResult({ approved: result.approved, failed: result.failed })
      await fetchClosetItems()
      setStep('done')
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Approval failed.')
    } finally {
      setApproving(false)
    }
  }

  const reset = () => {
    setStep('upload')
    setFiles([])
    setPreviews([])
    setJobId(null)
    setJobStatus(null)
    setItems([])
    setSelected(new Set())
    setApproveResult(null)
    setError(null)
  }

  // ── Progress helpers ────────────────────────────────────────────────────────

  const progressPct = jobStatus
    ? Math.round((jobStatus.processed_images / Math.max(jobStatus.total_images, 1)) * 100)
    : 0

  // ── Render ──────────────────────────────────────────────────────────────────

  return (
    <div className="space-y-6">
      {/* Header */}
      <div>
        <h2 className="font-display text-xl font-bold text-slate-800 dark:text-slate-100">
          Smart Closet Scan
        </h2>
        <p className="mt-0.5 text-sm text-slate-400">
          Upload multiple clothing photos — AI detects items, removes backgrounds, and extracts metadata.
        </p>
      </div>

      {/* Step indicator */}
      <div className="flex items-center gap-2">
        {(['upload', 'processing', 'review', 'done'] as Step[]).map((s, i) => {
          const idx = ['upload', 'processing', 'review', 'done'].indexOf(step)
          const done = i < idx
          const active = s === step
          return (
            <div key={s} className="flex items-center gap-2">
              <div className={`flex h-6 w-6 items-center justify-center rounded-full text-xs font-bold transition ${
                done ? 'bg-emerald-500 text-white'
                : active ? 'bg-brand-600 text-white'
                : 'bg-slate-200 text-slate-500 dark:bg-slate-700 dark:text-slate-400'
              }`}>
                {done ? '✓' : i + 1}
              </div>
              <span className={`text-xs capitalize hidden sm:block ${active ? 'font-semibold text-slate-800 dark:text-white' : 'text-slate-400'}`}>
                {s}
              </span>
              {i < 3 && <div className="h-px w-8 bg-slate-200 dark:bg-slate-700" />}
            </div>
          )
        })}
      </div>

      {/* Error banner */}
      {error && (
        <div className="flex items-start gap-2 rounded-2xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700 dark:border-red-500/30 dark:bg-red-500/10 dark:text-red-300">
          <AlertCircle size={15} className="mt-0.5 flex-shrink-0" />
          <span>{error}</span>
          <button onClick={() => setError(null)} className="ml-auto flex-shrink-0 hover:opacity-70"><X size={14} /></button>
        </div>
      )}

      {/* ── Step 1: Upload ─────────────────────────────────────────────────── */}
      {step === 'upload' && (
        <div className="space-y-4">
          <div
            onDragOver={e => { e.preventDefault(); setDragging(true) }}
            onDragLeave={() => setDragging(false)}
            onDrop={onDrop}
            onClick={() => inputRef.current?.click()}
            className={`flex min-h-48 cursor-pointer flex-col items-center justify-center gap-4 rounded-3xl border-2 border-dashed p-8 transition-all ${
              dragging
                ? 'border-brand-500 bg-brand-50 dark:bg-brand-500/10'
                : 'border-cream-300 hover:border-brand-400 dark:border-white/20 dark:hover:border-brand-400'
            }`}
          >
            <div className="flex h-16 w-16 items-center justify-center rounded-2xl bg-brand-100 dark:bg-brand-900/40">
              <Upload size={28} className="text-brand-500" />
            </div>
            <div className="text-center">
              <p className="font-semibold text-slate-700 dark:text-slate-200">
                Drop clothing photos here
              </p>
              <p className="mt-1 text-sm text-slate-400">or click to browse · JPEG / PNG / WebP · max 10 MB · up to {MAX_FILES} files</p>
            </div>
          </div>
          <input
            ref={inputRef}
            type="file"
            accept="image/*"
            multiple
            className="hidden"
            onChange={e => handleFiles(Array.from(e.target.files ?? []))}
          />

          {/* Preview strip */}
          {previews.length > 0 && (
            <div className="space-y-3">
              <div className="flex gap-2 overflow-x-auto pb-1">
                {previews.map((src, i) => (
                  <div key={i} className="h-20 w-20 flex-shrink-0 overflow-hidden rounded-xl bg-cream-100 dark:bg-slate-800">
                    <img src={src} alt="" className="h-full w-full object-cover" />
                  </div>
                ))}
                {files.length > 6 && (
                  <div className="flex h-20 w-20 flex-shrink-0 items-center justify-center rounded-xl bg-slate-100 text-sm font-semibold text-slate-500 dark:bg-slate-800">
                    +{files.length - 6}
                  </div>
                )}
              </div>
              <p className="text-xs text-slate-500 dark:text-slate-400">{files.length} file{files.length !== 1 ? 's' : ''} selected</p>
            </div>
          )}

          <div className="flex gap-3">
            <button
              className="flex items-center gap-2 rounded-2xl bg-gradient-to-r from-brand-500 to-violet-500 px-5 py-2.5 text-sm font-semibold text-white shadow transition hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-50"
              disabled={files.length === 0 || uploading}
              onClick={startUpload}
            >
              {uploading ? <Loader2 size={15} className="animate-spin" /> : <Sparkles size={15} />}
              {uploading ? 'Uploading…' : `Scan ${files.length || ''} Photo${files.length !== 1 ? 's' : ''}`}
            </button>
            {files.length > 0 && (
              <button className="rounded-2xl border border-slate-200 px-4 py-2.5 text-sm text-slate-500 transition hover:bg-slate-50 dark:border-slate-700 dark:hover:bg-slate-800" onClick={reset}>
                Clear
              </button>
            )}
          </div>
        </div>
      )}

      {/* ── Step 2: Processing ─────────────────────────────────────────────── */}
      {step === 'processing' && (
        <div className="rounded-3xl border border-cream-200 bg-white/80 p-8 dark:border-white/10 dark:bg-white/[0.04]">
          <div className="mx-auto max-w-sm space-y-6 text-center">
            <div className="mx-auto flex h-20 w-20 items-center justify-center rounded-full bg-gradient-to-br from-brand-100 to-violet-100 dark:from-brand-900/40 dark:to-violet-900/40">
              <Sparkles size={32} className="animate-pulse text-brand-500" />
            </div>
            <div>
              <p className="text-lg font-bold text-slate-800 dark:text-white">AI is analysing your photos</p>
              <p className="mt-1 text-sm text-slate-400">
                {jobStatus
                  ? `Processed ${jobStatus.processed_images} of ${jobStatus.total_images} images · ${jobStatus.items_detected} items detected so far`
                  : 'Starting analysis…'}
              </p>
            </div>

            {/* Progress bar */}
            <div className="h-2 overflow-hidden rounded-full bg-slate-100 dark:bg-slate-800">
              <div
                className="h-full rounded-full bg-gradient-to-r from-brand-500 to-violet-500 transition-all duration-500"
                style={{ width: `${Math.max(progressPct, 5)}%` }}
              />
            </div>
            <p className="text-xs text-slate-400">{progressPct}% complete</p>

            {/* Steps explanation */}
            <div className="grid grid-cols-3 gap-3 text-center text-xs text-slate-400">
              {[
                { icon: '🔍', label: 'Detecting items' },
                { icon: '✂️', label: 'Removing backgrounds' },
                { icon: '🏷️', label: 'Generating metadata' },
              ].map(({ icon, label }) => (
                <div key={label} className="space-y-1.5">
                  <div className="text-2xl">{icon}</div>
                  <p>{label}</p>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}

      {/* ── Step 3: Review ─────────────────────────────────────────────────── */}
      {step === 'review' && (
        <div className="space-y-4">
          {/* Toolbar */}
          <div className="flex flex-wrap items-center justify-between gap-3 rounded-2xl border border-cream-200 bg-white/80 px-4 py-3 dark:border-white/10 dark:bg-white/[0.04]">
            <div>
              <p className="text-sm font-bold text-slate-800 dark:text-white">
                AI detected {items.length} item{items.length !== 1 ? 's' : ''}
              </p>
              <p className="text-xs text-slate-400">{selected.size} selected for approval</p>
            </div>
            <div className="flex flex-wrap gap-2">
              <button
                onClick={selected.size === items.length ? deselectAll : selectAll}
                className="rounded-xl border border-slate-200 px-3 py-1.5 text-xs font-medium text-slate-600 transition hover:bg-slate-50 dark:border-slate-700 dark:text-slate-300 dark:hover:bg-slate-800"
              >
                {selected.size === items.length ? 'Deselect all' : 'Select all'}
              </button>
              <button
                onClick={approve}
                disabled={selected.size === 0 || approving}
                className="flex items-center gap-2 rounded-xl bg-gradient-to-r from-brand-500 to-violet-500 px-4 py-1.5 text-xs font-semibold text-white shadow transition hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-50"
              >
                {approving ? <Loader2 size={13} className="animate-spin" /> : <CheckCircle2 size={13} />}
                {approving ? 'Saving…' : `Approve ${selected.size} item${selected.size !== 1 ? 's' : ''}`}
              </button>
            </div>
          </div>

          {items.length === 0 ? (
            <div className="rounded-3xl border border-dashed border-slate-300 p-12 text-center dark:border-slate-700">
              <Package size={32} className="mx-auto mb-3 text-slate-300" />
              <p className="text-slate-500">No items to review</p>
            </div>
          ) : (
            <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5">
              {items.map(item => (
                <ReviewCard
                  key={item.temp_item_id}
                  item={item}
                  selected={selected.has(item.temp_item_id)}
                  onToggle={() => toggleSelect(item.temp_item_id)}
                  onEdit={updates => editItem(item.temp_item_id, updates)}
                  onReject={() => rejectItem(item.temp_item_id)}
                />
              ))}
            </div>
          )}
        </div>
      )}

      {/* ── Step 4: Done ───────────────────────────────────────────────────── */}
      {step === 'done' && (
        <div className="flex flex-col items-center gap-6 rounded-3xl border border-emerald-200 bg-emerald-50/50 p-10 text-center dark:border-emerald-500/30 dark:bg-emerald-500/10">
          <div className="flex h-20 w-20 items-center justify-center rounded-full bg-emerald-100 dark:bg-emerald-900/40">
            <CheckCircle2 size={40} className="text-emerald-500" />
          </div>
          <div>
            <p className="text-xl font-bold text-slate-800 dark:text-white">
              {approveResult?.approved ?? 0} item{(approveResult?.approved ?? 0) !== 1 ? 's' : ''} added to your closet!
            </p>
            {(approveResult?.failed ?? 0) > 0 && (
              <p className="mt-1 text-sm text-amber-600 dark:text-amber-400">
                {approveResult?.failed} item{(approveResult?.failed ?? 0) !== 1 ? 's' : ''} could not be saved.
              </p>
            )}
            <p className="mt-2 text-sm text-slate-400">
              Your new items are ready in the Closet and Outfit Builder.
            </p>
          </div>
          <div className="flex flex-wrap gap-3">
            <a
              href="/closet"
              className="rounded-2xl bg-brand-600 px-6 py-2.5 text-sm font-semibold text-white shadow transition hover:bg-brand-700"
            >
              View Closet
            </a>
            <button
              onClick={reset}
              className="rounded-2xl border border-slate-200 px-6 py-2.5 text-sm font-medium text-slate-600 transition hover:bg-slate-50 dark:border-slate-700 dark:text-slate-300 dark:hover:bg-slate-800"
            >
              Upload More
            </button>
          </div>
        </div>
      )}
    </div>
  )
}
