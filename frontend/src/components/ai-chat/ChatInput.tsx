import { useState, useRef, useCallback, KeyboardEvent } from 'react'
import { Send, Square, ChevronDown, CloudSun } from 'lucide-react'
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

interface Props {
  onSend: (message: string, context: AIChatContext) => void
  streaming: boolean
  onStop: () => void
  disabled?: boolean
}

export default function ChatInput({ onSend, streaming, onStop, disabled }: Props) {
  const [input, setInput] = useState('')
  const [occasion, setOccasion] = useState('')
  const [mood, setMood] = useState('')
  const [weatherOn, setWeatherOn] = useState(false)
  const [filtersOpen, setFiltersOpen] = useState(false)
  const textareaRef = useRef<HTMLTextAreaElement>(null)

  const handleSend = useCallback(() => {
    const text = input.trim()
    if (!text || streaming || disabled) return
    onSend(text, {
      occasion: occasion || undefined,
      mood: mood || undefined,
      weather_required: weatherOn,
    })
    setInput('')
    // Reset textarea height
    if (textareaRef.current) textareaRef.current.style.height = 'auto'
  }, [input, occasion, mood, weatherOn, streaming, disabled, onSend])

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

  const activeFilters = [occasion, mood, weatherOn ? 'weather' : ''].filter(Boolean).length

  return (
    <div className="space-y-2">
      {/* Filter bar */}
      <div className="flex items-center gap-2 flex-wrap">
        {/* Occasion */}
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

        {/* Mood pills */}
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

        {/* Weather toggle */}
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

      {/* Input row */}
      <div className="flex gap-2 items-end">
        <div className="flex-1 relative bg-white dark:bg-slate-800 rounded-2xl border border-cream-300 dark:border-slate-600 shadow-sm focus-within:ring-1 focus-within:ring-brand-400 focus-within:border-brand-400 transition-all">
          <textarea
            ref={textareaRef}
            rows={1}
            value={input}
            onChange={e => { setInput(e.target.value); handleInput() }}
            onKeyDown={handleKeyDown}
            placeholder="Ask about outfits, what to wear, packing…"
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
            disabled={!input.trim() || disabled}
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
