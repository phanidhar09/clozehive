import { useEffect, useState } from 'react'
import { Sparkles } from 'lucide-react'
import { cn } from '@/lib/utils'

type Size = 'md' | 'lg'

/** Per-letter config for the fAnI brand mark. */
const LETTERS = [
  { char: 'f', color: 'text-brand-600', dot: 'bg-brand-600' },
  { char: 'A', color: 'text-brand-500', dot: 'bg-brand-500' },
  { char: 'n', color: 'text-brand-700', dot: 'bg-brand-700' },
  { char: 'I', color: 'text-highlight-500', dot: 'bg-highlight-500' },
] as const

/** Stagger between each letter's pop-in, in seconds. */
const STAGGER = 0.16

const sizeMap: Record<Size, { text: string; dot: string; gap: string; star: number; glow: string }> = {
  md: { text: 'text-4xl', dot: 'h-1.5 w-1.5', gap: 'gap-2.5', star: 16, glow: 'h-24 w-24' },
  lg: { text: 'text-6xl', dot: 'h-2   w-2',   gap: 'gap-3.5', star: 22, glow: 'h-32 w-32' },
}

/**
 * Clozehive `brand` loading variant — the fAnI wordmark whose letters pop in one
 * by one (each dropping a colored dot beneath it, a star sparkling above the I),
 * hold, then peel away letter by letter. For large/fullscreen loading states.
 * For small inline loading use the `ellipsis` variant in Button.
 */
export function FaniLoader({
  size = 'lg',
  messages,
  subline = 'Hang tight — good taste takes a sec',
  className,
}: {
  size?: Size
  /** Rotating status lines tied to the work in progress. */
  messages?: string[]
  /** Static reassurance line under the rotating message. */
  subline?: string
  className?: string
}) {
  const s = sizeMap[size]
  const [msgIndex, setMsgIndex] = useState(0)

  useEffect(() => {
    if (!messages || messages.length < 2) return
    const id = setInterval(() => {
      setMsgIndex(i => (i + 1) % messages.length)
    }, 2200)
    return () => clearInterval(id)
  }, [messages])

  const current = messages?.[msgIndex]

  return (
    <div
      className={cn('flex flex-col items-center justify-center gap-5', className)}
      role="status"
      aria-live="polite"
      aria-busy="true"
    >
      <div className="relative flex flex-col items-center gap-3">
        {/* Brand glow that breathes in behind the mark during the hold */}
        <div
          aria-hidden="true"
          className={cn(
            'pointer-events-none absolute -top-8 rounded-full opacity-0 animate-fani-glow',
            'bg-[radial-gradient(circle,rgba(20,184,166,0.35),rgba(20,184,166,0)_70%)]',
            s.glow,
          )}
        />

        {/* The fAnI wordmark */}
        <div className={cn('relative flex font-display font-semibold tracking-tight', s.text)}>
          {LETTERS.map((l, i) => (
            <span
              key={l.char}
              className={cn('relative inline-block animate-fani-letter', l.color)}
              style={{ animationDelay: `${i * STAGGER}s` }}
            >
              {l.char}
              {l.char === 'I' && (
                <Sparkles
                  aria-hidden="true"
                  size={s.star}
                  className="absolute -right-3 -top-2 text-highlight-400 animate-fani-star"
                  style={{ animationDelay: `${i * STAGGER}s` }}
                />
              )}
            </span>
          ))}
        </div>

        {/* One dot per letter, popping in beneath it */}
        <div className={cn('flex', s.gap)} aria-hidden="true">
          {LETTERS.map((l, i) => (
            <span
              key={l.char}
              className={cn('inline-block rounded-full animate-fani-dot', l.dot, s.dot)}
              style={{ animationDelay: `${i * STAGGER}s` }}
            />
          ))}
        </div>
      </div>

      {(current || subline) && (
        <div className="text-center">
          {current && (
            <p
              key={current}
              className="font-medium text-slate-800 animate-fade-in dark:text-white"
            >
              {current}
            </p>
          )}
          {subline && (
            <p className="mt-1 text-sm text-slate-500 dark:text-white/50">{subline}</p>
          )}
        </div>
      )}

      <span className="sr-only">Loading</span>
    </div>
  )
}
