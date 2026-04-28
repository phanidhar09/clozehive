import { useState, useRef, useCallback } from 'react'
import {
  Upload as UploadIcon, Image, Sparkles, CheckCircle, X,
  Leaf, AlertTriangle, Shirt, Plus, Check, HelpCircle,
} from 'lucide-react'
import Button from '@/components/ui/Button'
import Input, { Select } from '@/components/ui/Input'
import Badge from '@/components/ui/Badge'
import { useApp } from '@/store'
import { closetApi } from '@/lib/api'
import { cn, ecoScoreBg } from '@/lib/utils'
import type { ClosetItem } from '@/types'

const CATEGORY_OPTIONS = [
  { value: 'tops', label: 'Tops' },
  { value: 'bottoms', label: 'Bottoms' },
  { value: 'shoes', label: 'Shoes' },
  { value: 'outerwear', label: 'Outerwear' },
  { value: 'dresses', label: 'Dresses' },
  { value: 'accessories', label: 'Accessories' },
]

interface VisionResult {
  garment_type?: string
  fabric?: string
  color_primary?: string
  pattern?: string
  season?: string
  occasion?: string[]
  care_instructions?: string[]
  wearing_tips?: string[]
  eco_score?: number
}

interface DetectedItem {
  garment_type: string
  suggested_name: string
  category: string
  fabric: string
  color_primary: string
  color_secondary: string
  pattern: string
  season: string
  occasion: string[]
  eco_score: number
  description: string
}

type ItemDecision = 'pending' | 'add_new' | 'already_have'

interface OutfitItemState {
  item: DetectedItem
  decision: ItemDecision
  created?: ClosetItem
}

export default function Upload() {
  const { addClosetItem, closetItems } = useApp()

  const [dragging, setDragging] = useState(false)
  const [file, setFile] = useState<File | null>(null)
  const [preview, setPreview] = useState<string | null>(null)
  const [processedPreview, setProcessedPreview] = useState<string | null>(null)

  const [uploading, setUploading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  // Single item flow
  const [vision, setVision] = useState<VisionResult | null>(null)
  const [createdItem, setCreatedItem] = useState<ClosetItem | null>(null)
  const [saving, setSaving] = useState(false)
  const [saved, setSaved] = useState(false)
  const [form, setForm] = useState({
    name: '', brand: '', size: '', price: '', notes: '',
    category: 'tops',
  })

  // Outfit detection flow
  const [isOutfitMode, setIsOutfitMode] = useState(false)
  const [outfitItems, setOutfitItems] = useState<OutfitItemState[]>([])
  const [outfitProcessedUrl, setOutfitProcessedUrl] = useState<string | null>(null)
  const [savingOutfit, setSavingOutfit] = useState(false)
  const [outfitSaved, setOutfitSaved] = useState(false)

  const inputRef = useRef<HTMLInputElement>(null)

  const handleFile = useCallback((f: File) => {
    setFile(f)
    setPreview(URL.createObjectURL(f))
    setProcessedPreview(null)
    setSaved(false)
    setOutfitSaved(false)
    setVision(null)
    setCreatedItem(null)
    setIsOutfitMode(false)
    setOutfitItems([])
    setOutfitProcessedUrl(null)
    setError(null)
  }, [])

  const onDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault()
    setDragging(false)
    const f = e.dataTransfer.files[0]
    if (f && f.type.startsWith('image/')) handleFile(f)
  }, [handleFile])

  const analyse = async () => {
    if (!file) return
    setUploading(true)
    setError(null)
    try {
      const fd = new FormData()
      fd.append('file', file)
      if (form.category) fd.append('category', form.category)
      if (form.name) fd.append('name', form.name)
      fd.append('is_outfit', 'false')

      const data = await closetApi.upload(fd) as Record<string, unknown>

      if (data.processed_image_base64) {
        const mt = (data.processed_image_media_type as string) || 'image/png'
        setProcessedPreview(`data:${mt};base64,${data.processed_image_base64}`)
      }

      const item = data.item as ClosetItem
      const va = data.vision_analysis as VisionResult

      setCreatedItem(item)
      addClosetItem(item)
      setVision(va)
      setForm(f => ({
        ...f,
        name: item.name || f.name,
        category: item.category || f.category,
        brand: item.brand || f.brand || '',
        notes: item.notes || f.notes || '',
      }))
    } catch (err: unknown) {
      type ApiErr = { response?: { data?: { message?: string; error?: string; detail?: string | Array<{ loc?: (string | number)[]; msg?: string }> } } }
      const d = (err as ApiErr)?.response?.data
      let msg: string | undefined
      if (typeof d?.detail === 'string') msg = d.detail
      else if (Array.isArray(d?.detail)) {
        msg = d.detail.map(e => {
          const field = Array.isArray(e.loc) ? e.loc.slice(1).join('.') : ''
          return field ? `${field}: ${e.msg ?? ''}` : (e.msg ?? '')
        }).filter(Boolean).join(' · ')
      }
      msg = msg ?? d?.message ?? d?.error ?? (err instanceof Error ? err.message : 'Upload failed')
      setError(`Upload failed: ${msg}`)
    } finally {
      setUploading(false)
    }
  }

  const analyseOutfit = async () => {
    if (!file) return
    setUploading(true)
    setError(null)
    try {
      const fd = new FormData()
      fd.append('file', file)
      fd.append('is_outfit', 'true')

      const data = await closetApi.upload(fd) as Record<string, unknown>

      if (data.processed_image_base64) {
        const mt = (data.processed_image_media_type as string) || 'image/png'
        setProcessedPreview(`data:${mt};base64,${data.processed_image_base64}`)
      }
      if (data.processed_image_url) {
        setOutfitProcessedUrl(data.processed_image_url as string)
      }

      const detected = (data.detected_items as DetectedItem[]) || []
      setOutfitItems(detected.map(item => ({ item, decision: 'pending' })))
      setIsOutfitMode(true)
    } catch (err: unknown) {
      setError(`Upload failed: ${err instanceof Error ? err.message : 'Unknown error'}`)
    } finally {
      setUploading(false)
    }
  }

  const save = async () => {
    if (!createdItem) return
    setSaving(true)
    setError(null)
    try {
      await closetApi.update(createdItem.id, {
        name: form.name || createdItem.name,
        category: form.category,
        brand: form.brand || undefined,
        notes: form.notes || undefined,
      })
      setSaved(true)
    } catch (err: unknown) {
      setError(`Could not update item: ${err instanceof Error ? err.message : 'Save failed'}`)
    } finally {
      setSaving(false)
    }
  }

  const setDecision = (index: number, decision: ItemDecision) => {
    setOutfitItems(prev => prev.map((s, i) => i === index ? { ...s, decision } : s))
  }

  const confirmOutfitItems = async () => {
    const toCreate = outfitItems.filter(s => s.decision === 'add_new')
    if (toCreate.length === 0) {
      setOutfitSaved(true)
      return
    }
    setSavingOutfit(true)
    setError(null)
    try {
      const created: ClosetItem[] = []
      for (const state of toCreate) {
        const item = await closetApi.create({
          name: state.item.suggested_name || state.item.garment_type || 'New Item',
          category: state.item.category || 'tops',
          color: state.item.color_primary,
          occasion: state.item.occasion,
          eco_score: state.item.eco_score,
          image_url: outfitProcessedUrl || undefined,
          tags: [state.item.fabric, ...(state.item.occasion || [])].filter(Boolean),
        })
        addClosetItem(item)
        created.push(item)
      }
      let ci = 0
      setOutfitItems(prev => prev.map(s =>
        s.decision === 'add_new' ? { ...s, created: created[ci++] } : s
      ))
      setOutfitSaved(true)
    } catch (err) {
      setError(`Could not save items: ${err instanceof Error ? err.message : 'Unknown error'}`)
    } finally {
      setSavingOutfit(false)
    }
  }

  const findSimilar = (item: DetectedItem): ClosetItem | undefined =>
    closetItems.find(ci =>
      (ci.category || '').toLowerCase() === (item.category || '').toLowerCase() &&
      item.color_primary &&
      (ci.color || '').toLowerCase().includes(item.color_primary.toLowerCase())
    )

  const reset = () => {
    setFile(null); setPreview(null); setProcessedPreview(null)
    setVision(null); setCreatedItem(null)
    setSaved(false); setOutfitSaved(false)
    setIsOutfitMode(false); setOutfitItems([]); setOutfitProcessedUrl(null)
    setError(null)
    setForm({ name: '', brand: '', size: '', price: '', notes: '', category: 'tops' })
  }

  const allDecided = outfitItems.length > 0 && outfitItems.every(s => s.decision !== 'pending')
  const displayPreview = processedPreview || preview

  return (
    <div className="max-w-4xl animate-slide-up space-y-6">
      <div>
        <h2 className="font-display font-bold text-xl text-slate-800 dark:text-slate-100">Upload Clothing Item</h2>
        <p className="text-sm text-slate-400 mt-0.5">
          AI analyses your item, removes the background automatically.
          Upload an outfit photo to detect and add all items at once.
        </p>
      </div>

      {error && (
        <div className="card p-3 bg-red-50 dark:bg-red-900/20 border-red-200 dark:border-red-800 text-red-700 dark:text-red-300 text-sm flex items-start gap-2">
          <AlertTriangle size={15} className="flex-shrink-0 mt-0.5" />
          <span>{error}</span>
        </div>
      )}

      <div className={cn('grid gap-6', isOutfitMode ? 'md:grid-cols-1' : 'md:grid-cols-2')}>
        {/* Drop zone */}
        <div className="space-y-4">
          <div
            className={cn(
              'relative border-2 border-dashed rounded-2xl transition-all duration-200 cursor-pointer',
              dragging ? 'drop-zone-active' : 'border-cream-300 dark:border-slate-600 hover:border-brand-400',
              displayPreview ? (isOutfitMode ? 'aspect-[3/4] max-w-xs mx-auto' : 'aspect-[3/4]') : 'aspect-square',
            )}
            onDragOver={e => { e.preventDefault(); setDragging(true) }}
            onDragLeave={() => setDragging(false)}
            onDrop={onDrop}
            onClick={() => !displayPreview && inputRef.current?.click()}
          >
            {displayPreview ? (
              <>
                <img
                  src={displayPreview}
                  alt="preview"
                  className={cn(
                    'w-full h-full rounded-2xl',
                    processedPreview ? 'object-contain' : 'object-cover',
                  )}
                  style={processedPreview ? {
                    backgroundImage: 'repeating-conic-gradient(#e2e8f0 0% 25%, #fff 0% 50%) 0 0 / 16px 16px',
                  } : undefined}
                />
                {processedPreview && (
                  <div className="absolute top-2 left-2">
                    <Badge variant="purple">BG Removed</Badge>
                  </div>
                )}
                {!createdItem && !isOutfitMode && (
                  <div className="absolute inset-0 rounded-2xl bg-black/30 opacity-0 hover:opacity-100 transition-opacity flex items-center justify-center">
                    <button
                      onClick={e => { e.stopPropagation(); reset() }}
                      className="p-2 rounded-full bg-white/20 hover:bg-white/30 transition-colors"
                    >
                      <X size={18} className="text-white" />
                    </button>
                  </div>
                )}
                {createdItem && (
                  <div className="absolute top-2 right-2">
                    <Badge variant="green">✓ Saved</Badge>
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
                <p className="text-[11px] text-slate-300 dark:text-slate-600">JPG, PNG, WEBP · Max 10MB</p>
              </div>
            )}
          </div>

          <input ref={inputRef} type="file" accept="image/*" className="hidden"
            onChange={e => e.target.files?.[0] && handleFile(e.target.files[0])} />

          {file && !createdItem && !isOutfitMode && !outfitItems.length && (
            <div className="flex gap-2">
              <Button className="flex-1" loading={uploading} icon={<Sparkles size={15} />} onClick={analyse}>
                {uploading ? 'Analysing…' : 'Single Item'}
              </Button>
              <Button className="flex-1" variant="secondary" loading={uploading} icon={<Shirt size={15} />} onClick={analyseOutfit}>
                {uploading ? 'Analysing…' : 'Full Outfit'}
              </Button>
            </div>
          )}

          {(saved || outfitSaved) && (
            <Button className="w-full" variant="secondary" onClick={reset}>
              + Add another item
            </Button>
          )}
        </div>

        {/* Single item form */}
        {!isOutfitMode && (
          <div className="space-y-4">
            {vision && Object.keys(vision).length > 0 && (
              <div className="card p-4 bg-brand-50 dark:bg-brand-900/20 border-brand-200 dark:border-brand-800 space-y-3 animate-slide-up">
                <div className="flex items-center justify-between">
                  <p className="text-xs font-semibold text-brand-700 dark:text-brand-300 uppercase tracking-wide flex items-center gap-1.5">
                    <Sparkles size={11} /> AI Detection results
                  </p>
                  <Badge variant="purple">Auto-filled</Badge>
                </div>
                <div className="grid grid-cols-2 gap-2">
                  {[
                    { label: 'Type', value: vision.garment_type },
                    { label: 'Fabric', value: vision.fabric },
                    { label: 'Color', value: vision.color_primary },
                    { label: 'Pattern', value: vision.pattern },
                  ].filter(a => a.value).map(a => (
                    <div key={a.label} className="bg-white dark:bg-slate-800 rounded-lg p-2">
                      <p className="text-[10px] text-slate-400 uppercase font-medium">{a.label}</p>
                      <p className="text-sm font-semibold text-slate-700 dark:text-slate-200 capitalize">{a.value}</p>
                    </div>
                  ))}
                </div>
                {vision.eco_score != null && (
                  <div className="flex items-center gap-2">
                    <Leaf size={13} className="text-emerald-500" />
                    <span className="text-xs font-medium text-slate-600 dark:text-slate-300">Eco score:</span>
                    <span className={`badge text-xs ${ecoScoreBg(vision.eco_score)}`}>{vision.eco_score}/10</span>
                  </div>
                )}
                {vision.care_instructions && vision.care_instructions.length > 0 && (
                  <div>
                    <p className="text-[10px] text-slate-400 uppercase font-medium mb-1.5">Care instructions</p>
                    <div className="flex gap-1 flex-wrap">
                      {vision.care_instructions.map(c => <Badge key={c} variant="gray">{c}</Badge>)}
                    </div>
                  </div>
                )}
                {vision.wearing_tips && vision.wearing_tips.length > 0 && (
                  <div>
                    <p className="text-[10px] text-slate-400 uppercase font-medium mb-1.5">Wearing tips</p>
                    {vision.wearing_tips.map(t => (
                      <p key={t} className="text-xs text-slate-600 dark:text-slate-300 flex items-start gap-1.5 mb-1">
                        <span className="text-brand-400 mt-0.5">•</span>{t}
                      </p>
                    ))}
                  </div>
                )}
              </div>
            )}

            {createdItem && (!vision || Object.keys(vision).length === 0) && (
              <div className="card p-3 bg-amber-50 dark:bg-amber-900/20 border-amber-200 dark:border-amber-800 text-amber-700 dark:text-amber-300 text-xs flex items-center gap-2">
                <AlertTriangle size={13} />
                Vision AI unavailable — item saved without auto-detection.
              </div>
            )}

            <div className="card p-4 space-y-3">
              <p className="text-sm font-semibold text-slate-700 dark:text-slate-300">Item details</p>
              <Input label="Item name" value={form.name}
                onChange={e => setForm(f => ({ ...f, name: e.target.value }))}
                placeholder="e.g. White Oxford Shirt" />
              <Select label="Category" options={CATEGORY_OPTIONS}
                value={form.category} onChange={e => setForm(f => ({ ...f, category: e.target.value }))} />
              <div className="grid grid-cols-2 gap-3">
                <Input label="Brand" value={form.brand}
                  onChange={e => setForm(f => ({ ...f, brand: e.target.value }))} placeholder="e.g. Uniqlo" />
                <Input label="Size" value={form.size}
                  onChange={e => setForm(f => ({ ...f, size: e.target.value }))} placeholder="e.g. M / 32" />
              </div>
              <Input label="Price" value={form.price}
                onChange={e => setForm(f => ({ ...f, price: e.target.value }))}
                placeholder="0.00" type="number" />
              <div>
                <label className="label">Notes</label>
                <textarea rows={2} className="input resize-none" value={form.notes}
                  onChange={e => setForm(f => ({ ...f, notes: e.target.value }))}
                  placeholder="Care instructions, notes…" />
              </div>

              {saved ? (
                <div className="flex items-center gap-2 text-emerald-600 font-semibold text-sm py-2 justify-center">
                  <CheckCircle size={18} /> Item saved to wardrobe!
                </div>
              ) : createdItem ? (
                <Button className="w-full" loading={saving} onClick={save} icon={<CheckCircle size={15} />}>
                  {saving ? 'Saving details…' : 'Save details'}
                </Button>
              ) : (
                <Button className="w-full" onClick={() => inputRef.current?.click()} disabled={!!file} icon={<UploadIcon size={15} />}>
                  {file ? 'Click "Single Item" or "Full Outfit" above' : 'Choose a photo to start'}
                </Button>
              )}
            </div>
          </div>
        )}
      </div>

      {/* Outfit detection: item decision cards */}
      {isOutfitMode && outfitItems.length > 0 && (
        <div className="space-y-4 animate-slide-up">
          <div className="flex items-center justify-between">
            <div>
              <p className="font-semibold text-slate-800 dark:text-slate-100">
                {outfitItems.length} item{outfitItems.length !== 1 ? 's' : ''} detected in your outfit
              </p>
              <p className="text-xs text-slate-400 mt-0.5">
                Choose "Add new" or "Already have" for each item.
              </p>
            </div>
            {allDecided && !outfitSaved && (
              <Button loading={savingOutfit} icon={<CheckCircle size={15} />} onClick={confirmOutfitItems}>
                {savingOutfit ? 'Saving…' : 'Confirm all'}
              </Button>
            )}
          </div>

          <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-4">
            {outfitItems.map((state, idx) => {
              const similar = findSimilar(state.item)
              const { item, decision, created } = state

              return (
                <div key={idx} className={cn(
                  'card p-4 space-y-3 transition-all',
                  decision === 'add_new' && 'ring-2 ring-brand-400 ring-offset-1',
                  decision === 'already_have' && 'opacity-60',
                  created && 'ring-2 ring-emerald-400 ring-offset-1',
                )}>
                  <div className="flex items-start justify-between gap-2">
                    <div>
                      <p className="font-semibold text-sm text-slate-800 dark:text-slate-100 capitalize">
                        {item.suggested_name || item.garment_type}
                      </p>
                      <p className="text-xs text-slate-400 capitalize">{item.category}</p>
                    </div>
                    <span className={`badge text-xs ${ecoScoreBg(item.eco_score)}`}>
                      <Leaf size={10} className="inline mr-0.5" />{item.eco_score}/10
                    </span>
                  </div>

                  <div className="grid grid-cols-2 gap-1.5">
                    {[
                      { label: 'Color', value: item.color_primary },
                      { label: 'Fabric', value: item.fabric },
                      { label: 'Pattern', value: item.pattern },
                      { label: 'Season', value: item.season },
                    ].filter(a => a.value).map(a => (
                      <div key={a.label} className="bg-slate-50 dark:bg-slate-800 rounded-lg px-2 py-1">
                        <p className="text-[9px] text-slate-400 uppercase font-medium">{a.label}</p>
                        <p className="text-xs font-medium text-slate-700 dark:text-slate-200 capitalize">{a.value}</p>
                      </div>
                    ))}
                  </div>

                  {item.occasion?.length > 0 && (
                    <div className="flex gap-1 flex-wrap">
                      {item.occasion.map(o => <Badge key={o} variant="gray">{o}</Badge>)}
                    </div>
                  )}

                  {similar && decision === 'pending' && (
                    <div className="flex items-start gap-1.5 text-amber-600 dark:text-amber-400 bg-amber-50 dark:bg-amber-900/20 rounded-lg p-2">
                      <HelpCircle size={13} className="flex-shrink-0 mt-0.5" />
                      <p className="text-[11px]">
                        Looks similar to <span className="font-semibold">"{similar.name}"</span> in your wardrobe.
                      </p>
                    </div>
                  )}

                  {created ? (
                    <div className="flex items-center gap-1.5 text-emerald-600 text-xs font-semibold pt-1">
                      <CheckCircle size={14} /> Added to wardrobe
                    </div>
                  ) : outfitSaved && decision === 'already_have' ? (
                    <div className="flex items-center gap-1.5 text-slate-400 text-xs pt-1">
                      <Check size={14} /> Already in wardrobe
                    </div>
                  ) : !outfitSaved && (
                    <div className="grid grid-cols-2 gap-2 pt-1">
                      <button
                        onClick={() => setDecision(idx, 'add_new')}
                        className={cn(
                          'flex items-center justify-center gap-1.5 rounded-lg py-1.5 text-xs font-semibold border transition-colors',
                          decision === 'add_new'
                            ? 'bg-brand-500 text-white border-brand-500'
                            : 'border-slate-200 dark:border-slate-700 text-slate-600 dark:text-slate-300 hover:border-brand-400',
                        )}
                      >
                        <Plus size={12} /> Add new
                      </button>
                      <button
                        onClick={() => setDecision(idx, 'already_have')}
                        className={cn(
                          'flex items-center justify-center gap-1.5 rounded-lg py-1.5 text-xs font-semibold border transition-colors',
                          decision === 'already_have'
                            ? 'bg-slate-600 text-white border-slate-600'
                            : 'border-slate-200 dark:border-slate-700 text-slate-600 dark:text-slate-300 hover:border-slate-400',
                        )}
                      >
                        <Check size={12} /> Already have
                      </button>
                    </div>
                  )}
                </div>
              )
            })}
          </div>

          {outfitSaved && (
            <div className="card p-4 bg-emerald-50 dark:bg-emerald-900/20 border-emerald-200 dark:border-emerald-800 flex items-center gap-3">
              <CheckCircle size={20} className="text-emerald-500 flex-shrink-0" />
              <div>
                <p className="font-semibold text-emerald-700 dark:text-emerald-300 text-sm">
                  {outfitItems.filter(s => s.decision === 'add_new').length} item{outfitItems.filter(s => s.decision === 'add_new').length !== 1 ? 's' : ''} added to wardrobe!
                </p>
                <p className="text-xs text-emerald-600 dark:text-emerald-400">
                  {outfitItems.filter(s => s.decision === 'already_have').length} skipped (already in wardrobe)
                </p>
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  )
}
