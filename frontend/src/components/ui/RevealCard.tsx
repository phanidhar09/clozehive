import { useState, useEffect } from 'react'
import type { ClosetItem } from '@/types'
import { categoryIcon, cn } from '@/lib/utils'

interface RevealCardProps {
  item: ClosetItem
  onOpen?: (item: ClosetItem) => void
  /** Kept for API compatibility; edit is handled by the always-visible action bar below the card. */
  onEdit?: (item: ClosetItem) => void
  className?: string
}

function fallbackIcon(category?: string) {
  return categoryIcon(category)
}

/**
 * Clean garment thumbnail.
 *  - Click / Enter / Space opens the detail modal (via onOpen).
 *  - Subtle image zoom on hover; the card lift is handled by the parent.
 *  - No slide-up overlay panel — name, brand, color, and actions are shown
 *    permanently below the card, so an on-hover panel would just duplicate them
 *    and wouldn't work on touch devices.
 */
export default function RevealCard({ item, onOpen, className }: RevealCardProps) {
  const [imgFailed, setImgFailed] = useState(false)
  const showImage = Boolean(item.image_url) && !imgFailed

  useEffect(() => {
    setImgFailed(false)
  }, [item.id, item.image_url])

  return (
    <article
      className={cn(
        'group relative aspect-[4/5] overflow-hidden rounded-2xl bg-slate-950 shadow-sm ring-1 ring-black/5 cursor-pointer',
        className,
      )}
      onClick={() => onOpen?.(item)}
      onKeyDown={event => {
        if (event.key === 'Enter' || event.key === ' ') {
          event.preventDefault()
          onOpen?.(item)
        }
      }}
      tabIndex={0}
      role="button"
      aria-label={`View details for ${item.name}`}
    >
      {showImage ? (
        <img
          src={item.image_url}
          alt={item.name}
          loading="lazy"
          onError={() => setImgFailed(true)}
          className="h-full w-full object-cover transition-transform duration-300 ease-out group-hover:scale-[1.03]"
        />
      ) : (
        <div className="flex h-full w-full flex-col items-center justify-center bg-gradient-to-br from-cream-100 to-cream-200 text-slate-400 dark:from-slate-800 dark:to-slate-900">
          <span className="text-6xl">{fallbackIcon(item.category)}</span>
          <span className="mt-2 text-xs font-semibold uppercase tracking-wide">{item.category}</span>
        </div>
      )}
    </article>
  )
}
