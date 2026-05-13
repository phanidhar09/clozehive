import { useState, useEffect } from 'react'
import { Eye, Leaf } from 'lucide-react'
import type { ClosetItem } from '@/types'
import { categoryIcon, cn } from '@/lib/utils'

interface RevealCardProps {
  item: ClosetItem
  onOpen?: (item: ClosetItem) => void
  className?: string
}

function ecoTone(score?: number | null) {
  if (score == null) return 'bg-slate-400 text-slate-950'
  if (score >= 8) return 'bg-emerald-400 text-emerald-950'
  if (score >= 5) return 'bg-amber-300 text-amber-950'
  return 'bg-rose-400 text-rose-950'
}

function fallbackIcon(category?: string) {
  return categoryIcon(category)
}

export default function RevealCard({ item, onOpen, className }: RevealCardProps) {
  const [revealed, setRevealed] = useState(false)
  const [imgFailed, setImgFailed] = useState(false)
  const occasions = item.occasion?.filter(Boolean) ?? []

  const toggleReveal = () => setRevealed(value => !value)

  const showImage = Boolean(item.image_url) && !imgFailed

  useEffect(() => {
    setImgFailed(false)
  }, [item.id, item.image_url])

  return (
    <article
      className={cn(
        'group relative aspect-[4/5] overflow-hidden rounded-2xl bg-slate-950 shadow-sm ring-1 ring-black/5 cursor-pointer',
        'transition-all duration-300 ease-out hover:-translate-y-0.5 hover:shadow-xl hover:shadow-slate-900/10',
        className,
      )}
      onClick={toggleReveal}
      onKeyDown={event => {
        if (event.key === 'Enter' || event.key === ' ') {
          event.preventDefault()
          toggleReveal()
        }
      }}
      tabIndex={0}
      role="button"
      aria-pressed={revealed}
      aria-label={`Reveal details for ${item.name}`}
    >
      {showImage ? (
        <img
          src={item.image_url}
          alt={item.name}
          loading="lazy"
          onError={() => setImgFailed(true)}
          className={cn(
            'h-full w-full object-cover transition-transform duration-300 ease-out',
            'group-hover:scale-105',
            revealed && 'scale-105',
          )}
        />
      ) : (
        <div className="flex h-full w-full flex-col items-center justify-center bg-gradient-to-br from-cream-100 to-cream-200 text-slate-400 dark:from-slate-800 dark:to-slate-900">
          <span className="text-6xl">{fallbackIcon(item.category)}</span>
          <span className="mt-2 text-xs font-semibold uppercase tracking-wide">{item.category}</span>
        </div>
      )}

      <div className="absolute inset-0 bg-gradient-to-t from-black/40 via-transparent opacity-80 group-hover:opacity-100" />

      <div
        className={cn(
          'absolute inset-x-0 bottom-0 max-h-full translate-y-full p-3 text-white',
          'transition-transform duration-300 ease-out group-hover:translate-y-0',
          revealed && 'translate-y-0',
        )}
      >
        <div className="rounded-2xl border border-white/20 bg-black/65 p-3 shadow-2xl backdrop-blur-lg">
          <div className="flex items-start justify-between gap-3">
            <div className="min-w-0">
              <h3 className="truncate text-sm font-bold leading-tight">{item.name}</h3>
              <p className="mt-1 text-[11px] font-medium uppercase tracking-wide text-white/55">
                {item.category || 'Closet item'}
              </p>
            </div>
            {item.eco_score != null && (
              <span className={cn('inline-flex shrink-0 items-center gap-1 rounded-full px-2 py-1 text-[11px] font-bold', ecoTone(item.eco_score))}>
                <Leaf size={11} />
                {item.eco_score}/10
              </span>
            )}
          </div>

          <div className="mt-3 grid grid-cols-2 gap-2 text-[11px]">
            <div className="rounded-xl bg-white/10 px-2.5 py-2">
              <p className="text-white/45">Type</p>
              <p className="mt-0.5 truncate font-semibold capitalize">{item.category || 'Unknown'}</p>
            </div>
            <div className="rounded-xl bg-white/10 px-2.5 py-2">
              <p className="text-white/45">Brand</p>
              <p className="mt-0.5 truncate font-semibold">{item.brand || 'Unbranded'}</p>
            </div>
          </div>

          {item.color && (
            <div className="mt-2 inline-flex max-w-full items-center gap-1.5 rounded-full bg-white/10 px-2.5 py-1 text-[11px] font-semibold">
              {item.color_hex && (
                <span
                  className="h-2.5 w-2.5 shrink-0 rounded-full border border-white/40"
                  style={{ backgroundColor: item.color_hex }}
                />
              )}
              <span className="truncate capitalize">{item.color}</span>
            </div>
          )}

          {occasions.length > 0 && (
            <div className="mt-3 flex flex-wrap gap-1.5">
              {occasions.slice(0, 4).map(occasion => (
                <span key={occasion} className="rounded-full bg-white/15 px-2 py-0.5 text-[10px] font-semibold text-white/90">
                  {occasion}
                </span>
              ))}
            </div>
          )}

          {item.notes && (
            <p className="mt-3 line-clamp-2 text-[11px] leading-relaxed text-white/90">
              {item.notes}
            </p>
          )}

          {onOpen && (
            <button
              type="button"
              onClick={event => {
                event.stopPropagation()
                onOpen(item)
              }}
              className="mt-3 inline-flex w-full items-center justify-center gap-1.5 rounded-xl bg-white/90 px-3 py-2 text-xs font-bold text-slate-900 transition-colors hover:bg-white"
            >
              <Eye size={13} />
              View details
            </button>
          )}
        </div>
      </div>
    </article>
  )
}
