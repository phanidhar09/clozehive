import { useState, useRef, useCallback } from 'react'
import { Upload as UploadIcon, Image, Sparkles, CheckCircle, X, Leaf, Loader2, AlertTriangle } from 'lucide-react'
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
                        
export default function Upload() {
  const { addClosetItem } = useApp()
  const [dragging, setDragging] = useState(false)
  const [file, setFile] = useState<File | null>(null)
  const [preview, setPreview] = useState<string | null>(null)
  const [uploading, setUploading] = useState(false)
  const [vision, setVision] = useState<VisionResult | null>(null)
  const [createdItem, setCreatedItem] = useState<ClosetItem | null>(null)
  const [saving, setSaving] = useState(false)
  const [saved, setSaved] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [form, setForm] = useState({
    name: '', brand: '', size: '', price: '', notes: '',
    category: 'tops',
  })
  const inputRef = useRef<HTMLInputElement>(null)

  const handleFile = useCallback((f: File) => {
    setFile(f)
    setPreview(URL.createObjectURL(f))
    setSaved(false)
    setVision(null)
    setCreatedItem(null)
    setError(null)
  }, [])

  const onDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault()
    setDragging(false)
    const f = e.dataTransfer.files[0]
    if (f && f.type.startsWith('image/')) handleFile(f)
  }, [handleFile])

  // Step 1: Upload image → backend → vision AI analysis → item created in DB
  const analyse = async () => {
    if (!file) return
    setUploading(true)
    setError(null)
    try {
      const fd = new FormData()
      fd.append('file', file)
      if (form.category) fd.append('category', form.category)
      if (form.name) fd.append('name', form.name)

      const { item, vision_analysis } = await closetApi.upload(fd)

      setCreatedItem(item)
      addClosetItem(item)

      const v = vision_analysis as VisionResult
      setVision(v)

      // Auto-fill form from AI results + item
      setForm(f => ({
        ...f,
        name: item.name || f.name,
        category: item.category || f.category,
        brand: item.brand || f.brand || '',
        size: item.size || f.size || '',
        price: item.price != null ? String(item.price) : f.price,
        notes: item.notes || f.notes || '',
      }))
    } catch (err: unknown) {
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
      msg = msg ?? d?.message ?? d?.error ?? (err instanceof Error ? err.message : 'Upload failed')
      setError(`Upload failed: ${msg}`)
      console.error('Upload error:', err)
    } finally {
      setUploading(false)
    }
  }

  // Step 2: Save updated form details via PATCH
  const save = async () => {
    if (!createdItem) return
    setSaving(true)
    setError(null)
    try {
      await closetApi.update(createdItem.id, {
        name: form.name || createdItem.name,
        category: form.category,
        brand: form.brand || undefined,
        size: form.size || undefined,
        notes: form.notes || undefined,
      })
      setSaved(true)
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Save failed'
      setError(`Could not update item: ${msg}`)
    } finally {
      setSaving(false)
    }
  }

  const reset = () => {
    setFile(null)
    setPreview(null)
    setVision(null)
    setCreatedItem(null)
    setSaved(false)
    setError(null)
    setForm({ name: '', brand: '', size: '', price: '', notes: '', category: 'tops' })
  }

  return (
    <div className="max-w-3xl animate-slide-up space-y-6">
      <div>
        <h2 className="font-display font-bold text-xl text-slate-800 dark:text-slate-100">Upload Clothing Item</h2>
        <p className="text-sm text-slate-400 mt-0.5">AI will automatically detect fabric, color, pattern and more</p>
      </div>

      {error && (
        <div className="card p-3 bg-red-50 dark:bg-red-900/20 border-red-200 dark:border-red-800 text-red-700 dark:text-red-300 text-sm flex items-start gap-2">
          <AlertTriangle size={15} className="flex-shrink-0 mt-0.5" />
          <span>{error}</span>
        </div>
      )}

      <div className="grid md:grid-cols-2 gap-6">
        {/* Drop zone */}
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
            onClick={() => !preview && inputRef.current?.click()}
          >
            {preview ? (
              <>
                <img src={preview} alt="preview" className="w-full h-full object-cover rounded-2xl" />
                {!createdItem && (
                  <div className="absolute inset-0 rounded-2xl bg-black/30 opacity-0 hover:opacity-100 transition-opacity flex items-center justify-center gap-3">
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
          <input ref={inputRef} type="file" accept="image/*" className="hidden" onChange={e => e.target.files?.[0] && handleFile(e.target.files[0])} />

          {/* Analyse button — shown when image selected but not yet uploaded */}
          {file && !createdItem && (
            <Button className="w-full" loading={uploading} icon={<Sparkles size={15} />} onClick={analyse}>
              {uploading ? 'Uploading & analysing…' : 'Analyse with Vision AI'}
            </Button>
          )}

          {/* Add another item */}
          {saved && (
            <Button className="w-full" variant="secondary" onClick={reset}>
              + Add another item
            </Button>
          )}
        </div>

        {/* Form + Vision result */}
        <div className="space-y-4">
          {/* AI Vision result */}
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

          {/* No vision result notice */}
          {createdItem && (!vision || Object.keys(vision).length === 0) && (
            <div className="card p-3 bg-amber-50 dark:bg-amber-900/20 border-amber-200 dark:border-amber-800 text-amber-700 dark:text-amber-300 text-xs flex items-center gap-2">
              <AlertTriangle size={13} />
              Vision AI unavailable — item saved without auto-detection. Fill in details manually.
            </div>
          )}

          {/* Manual form */}
          <div className="card p-4 space-y-3">
            <p className="text-sm font-semibold text-slate-700 dark:text-slate-300">Item details</p>
            <Input
              label="Item name"
              value={form.name}
              onChange={e => setForm(f => ({ ...f, name: e.target.value }))}
              placeholder="e.g. White Oxford Shirt"
            />
            <div className="grid grid-cols-2 gap-3">
              <Select label="Category" options={CATEGORY_OPTIONS} value={form.category} onChange={e => setForm(f => ({ ...f, category: e.target.value }))} />
            </div>
            <div className="grid grid-cols-2 gap-3">
              <Input label="Brand" value={form.brand} onChange={e => setForm(f => ({ ...f, brand: e.target.value }))} placeholder="e.g. Uniqlo" />
              <Input label="Size" value={form.size} onChange={e => setForm(f => ({ ...f, size: e.target.value }))} placeholder="e.g. M / 32" />
            </div>
            <Input label="Price" value={form.price} onChange={e => setForm(f => ({ ...f, price: e.target.value }))} placeholder="0.00" type="number" />
            <div>
              <label className="label">Notes</label>
              <textarea
                rows={2}
                className="input resize-none"
                value={form.notes}
                onChange={e => setForm(f => ({ ...f, notes: e.target.value }))}
                placeholder="Care instructions, notes…"
              />
            </div>

            {saved ? (
              <div className="flex items-center gap-2 text-emerald-600 font-semibold text-sm py-2 justify-center">
                <CheckCircle size={18} /> Item saved to wardrobe!
              </div>
            ) : createdItem ? (
              /* Item exists in DB → update metadata */
              <Button className="w-full" loading={saving} onClick={save} icon={<CheckCircle size={15} />}>
                {saving ? 'Saving details…' : 'Save details'}
              </Button>
            ) : (
              /* No item yet → prompt to upload */
              <Button className="w-full" onClick={() => inputRef.current?.click()} disabled={!!file} icon={<UploadIcon size={15} />}>
                {file ? 'Click "Analyse" above first' : 'Choose a photo to start'}
              </Button>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}
