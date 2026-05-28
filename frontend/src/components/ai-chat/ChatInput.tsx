import { useState, useRef, useCallback, KeyboardEvent } from 'react'
import { Send, Square, ChevronDown, CloudSun, ImagePlus, X } from 'lucide-react'
import { cn } from '@/lib/utils'
import type { AIChatContext } from '@/types'

const OCCASIONS = [
  { value: '', label: 'Any occasion' },
  { value: 'casual', label: 'Casual' },
  { value: 'smart casual', label: 'Smart Casual' },
  { value: 'office', label: 'Office / Work' },
  { value: 'business', label: 'Business' },
  { value: 'dinner', label: 'Dinner' },
  { value: 'date night', label: 'Date Night' },
  { value: 'cocktail', label: 'Cocktail' },
  { value: 'formal', label: 'Formal' },
  { value: 'weekend', label: 'Weekend' },
  { value: 'athleisure', label: 'Athleisure' },
]

const MOODS = [
  { value: '', emoji: '✨', label: 'Any vibe' },
  { value: 'confident', emoji: '💪', label: 'Confident' },
  { value: 'relaxed', emoji: '😌', label: 'Relaxed' },
  { value: 'bold', emoji: '🔥', label: 'Bold' },
  { value: 'minimal', emoji: '⬜', label: 'Minimal' },
  { value: 'romantic', emoji: '🌸', label: 'Romantic' },
  { value: 'professional', emoji: '💼', label: 'Professional' },
  { value: 'playful', emoji: '🎨', label: 'Playful' },
]

const MAX_IMAGES = 3

function compressImage(file: File, maxPx = 1120, quality = 0.82): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader()
    reader.onload = (e) => {
      const img = new Image()
      img.onload = () => {
        const scale = Math.min(1, maxPx / Math.max(img.width, img.height))
        const canvas = document.createElement('canvas')
        canvas.width = Math.round(img.width * scale)
        canvas.height = Math.round(img.height * scale)
        const ctx = canvas.getContext('2d')
        if (!ctx) { reject(new Error('canvas')); return }
        ctx.drawImage(img, 0, 0, canvas.width, canvas.height)
        resolve(canvas.toDataURL('image/jpeg', quality))
      }
      img.onerror = reject
      img.src = e.target!.result as string
    }
    reader.onerror = reject
    reader.readAsDataURL(file)
  })
}

interface Props {
  onSend: (message: string, context: AIChatContext, images?: string[]) => void
  streaming: boolean
  onStop: () => void
  disabled?: boolean
}

export default function ChatInput({ onSend, streaming, onStop, disabled }: Props) {
  const [input, setInput] = useState('')
  const [occasion, setOccasion] = useState('')
  const [mood, setMood] = useState('')
  const [weatherOn, setWeatherOn] = useState(false)
  const [images, setImages] = useState<string[]>([])
  const textareaRef = useRef<HTMLTextAreaElement>(null)
  const fileInputRef = useRef<HTMLInputElement>(null)

  const handleSend = useCallback(() => {
    const text = input.trim()
    if ((!text && images.length === 0) || streaming || disabled) return
    onSend(
      text || '(see attached image)',
      { occasion: occasion || undefined, mood: mood || undefined, weather_required: weatherOn },
      images.length > 0 ? images : undefined,
    )
    setInput('')
    setImages([])
    if (textareaRef.current) textareaRef.current.style.height = 'auto'
  }, [input, images, occasion, mood, weatherOn, streaming, disabled, onSend])

  const handleKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSend()
    }
  }

  const handleInput = () => {
    const ta = textareaRef.current
    if (!ta) return
    ta.style.height = 'auto'
    ta.style.height = `${Math.min(ta.scrollHeight, 140)}px`
  }

  const handleFileChange = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = Array.from(e.target.files ?? [])
    if (!files.length) return
    const remaining = MAX_IMAGES - images.length
    const toProcess = files.slice(0, remaining)
    const compressed = await Promise.all(toProcess.map(f => compressImage(f)))
    setImages(prev => [...prev, ...compressed])
    e.target.value = ''
  }

  const removeImage = (idx: number) => setImages(prev => prev.filter((_, i) => i !== idx))

  const canSend = (input.trim().length > 0 || images.length > 0) && !disabled

  return (
    <div className="space-y-2">
      {/* Filter bar */}
      <div className="flex items-center gap-2 flex-wrap">
        <div className="relative">
          <select
            value={occasion}
            onChange={e => setOccasion(e.target.value)}
            className="appearance-none pl-3 pr-7 py-1.5 text-xs rounded-full border border-cream-300 dark:border-slate-600 bg-white dark:bg-slate-800 text-slate-700 dark:text-slate-200 focus:outline-none focus:ring-1 focus:ring-brand-400 cursor-pointer"
          >
            {OCCASIONS.map(o => (
              <option key={o.value} value={o.value}>{o.label}</option>
            ))}
          </select>
          <ChevronDown size={11} className="absolute right-2 top-1/2 -translate-y-1/2 text-slate-400 pointer-events-none" />
        </div>

        <div className="flex gap-1 overflow-x-auto">
          {MOODS.map(m => (
            <button
              key={m.value}
              onClick={() => setMood(mood === m.value ? '' : m.value)}
              className={cn(
                'flex-shrink-0 flex items-center gap-1 px-2.5 py-1 rounded-full text-xs border transition-colors',
                mood === m.value
                  ? 'bg-brand-500 border-brand-500 text-white'
                  : 'border-cream-300 dark:border-slate-600 bg-white dark:bg-slate-800 text-slate-600 dark:text-slate-300 hover:border-brand-300',
              )}
            >
              <span>{m.emoji}</span>
              <span className="hidden sm:inline">{m.label}</span>
            </button>
          ))}
        </div>

        <button
          onClick={() => setWeatherOn(v => !v)}
          className={cn(
            'flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs border transition-colors',
            weatherOn
              ? 'bg-sky-500 border-sky-500 text-white'
              : 'border-cream-300 dark:border-slate-600 bg-white dark:bg-slate-800 text-slate-600 dark:text-slate-300 hover:border-sky-300',
          )}
          title="Use my location weather"
        >
          <CloudSun size={12} />
          <span>Weather</span>
        </button>
      </div>

      {/* Image thumbnails */}
      {images.length > 0 && (
        <div className="flex gap-2 flex-wrap">
          {images.map((src, i) => (
            <div key={i} className="relative group w-16 h-16 rounded-xl overflow-hidden border border-cream-300 dark:border-slate-600 shadow-sm flex-shrink-0">
              <img src={src} alt="" className="w-full h-full object-cover" />
              <button
                type="button"
                onClick={() => removeImage(i)}
                className="absolute top-0.5 right-0.5 w-5 h-5 rounded-full bg-black/60 text-white flex items-center justify-center opacity-0 group-hover:opacity-100 transition-opacity"
              >
                <X size={10} />
              </button>
            </div>
          ))}
          {images.length < MAX_IMAGES && (
            <button
              type="button"
              onClick={() => fileInputRef.current?.click()}
              className="w-16 h-16 rounded-xl border-2 border-dashed border-cream-300 dark:border-slate-600 flex items-center justify-center text-slate-400 hover:border-brand-400 hover:text-brand-500 transition-colors flex-shrink-0"
            >
              <ImagePlus size={18} />
            </button>
          )}
        </div>
      )}

      {/* Input row */}
      <div className="flex gap-2 items-end">
        {/* Image upload button */}
        <button
          type="button"
          onClick={() => fileInputRef.current?.click()}
          disabled={disabled || images.length >= MAX_IMAGES}
          title="Attach photo of your outfit"
          className={cn(
            'w-11 h-11 rounded-2xl border flex items-center justify-center flex-shrink-0 transition-colors',
            images.length > 0
              ? 'bg-brand-50 dark:bg-brand-900/30 border-brand-300 dark:border-brand-700 text-brand-600 dark:text-brand-400'
              : 'border-cream-300 dark:border-slate-600 bg-white dark:bg-slate-800 text-slate-500 dark:text-slate-400 hover:border-brand-400 hover:text-brand-500',
            (disabled || images.length >= MAX_IMAGES) && 'opacity-40 cursor-not-allowed',
          )}
        >
          <ImagePlus size={17} />
        </button>
        <input
          ref={fileInputRef}
          type="file"
          accept="image/*"
          multiple
          className="hidden"
          onChange={handleFileChange}
        />

        <div className="flex-1 relative bg-white dark:bg-slate-800 rounded-2xl border border-cream-300 dark:border-slate-600 shadow-sm focus-within:ring-1 focus-within:ring-brand-400 focus-within:border-brand-400 transition-all">
          <textarea
            ref={textareaRef}
            rows={1}
            value={input}
            onChange={e => { setInput(e.target.value); handleInput() }}
            onKeyDown={handleKeyDown}
            placeholder={images.length > 0 ? 'Add a note or ask about this outfit…' : 'Ask about outfits, what to wear, packing…'}
            disabled={disabled}
            className="w-full bg-transparent px-4 py-3 text-sm text-slate-800 dark:text-slate-100 placeholder-slate-400 resize-none focus:outline-none leading-relaxed max-h-[140px] overflow-y-auto disabled:opacity-50"
          />
        </div>

        {streaming ? (
          <button
            onClick={onStop}
            className="w-11 h-11 rounded-2xl bg-red-500 hover:bg-red-600 flex items-center justify-center shadow-md active:scale-95 transition-all flex-shrink-0"
            title="Stop generating"
          >
            <Square size={14} className="text-white fill-white" />
          </button>
        ) : (
          <button
            onClick={handleSend}
            disabled={!canSend}
            className="w-11 h-11 rounded-2xl bg-gradient-brand flex items-center justify-center shadow-md hover:opacity-90 active:scale-95 transition-all disabled:opacity-40 flex-shrink-0"
            title="Send"
          >
            <Send size={16} className="text-white" />
          </button>
        )}
      </div>
    </div>
  )
}
