import { useState } from 'react'
import { cn } from '@/lib/utils'

interface LazyImageProps
  extends Omit<React.ImgHTMLAttributes<HTMLImageElement>, 'onError' | 'onLoad' | 'src'> {
  src?: string | null
  alt: string
  /** Tailwind aspect ratio for the wrapper, e.g. 'aspect-square', 'aspect-[4/5]'. */
  aspect?: string
  /** Rounding for the wrapper + image. */
  rounded?: string
  /** Rendered when there is no src or the image fails to load. */
  fallback?: React.ReactNode
  /** Extra classes on the wrapper element. */
  wrapperClassName?: string
  /** Load eagerly (above-the-fold hero images). Defaults to lazy. */
  eager?: boolean
}

/**
 * Image with built-in lazy loading, async decode, a shimmer skeleton while
 * loading and a graceful fallback on error / missing src. Central helper so
 * every list/grid image across the app gets consistent perf + polish.
 */
export default function LazyImage({
  src,
  alt,
  aspect = 'aspect-square',
  rounded = 'rounded-2xl',
  fallback,
  wrapperClassName,
  eager = false,
  className,
  ...rest
}: LazyImageProps) {
  const [loaded, setLoaded] = useState(false)
  const [failed, setFailed] = useState(false)
  const showImage = Boolean(src) && !failed

  return (
    <div
      className={cn(
        'relative overflow-hidden bg-slate-100 dark:bg-white/[0.05]',
        aspect,
        rounded,
        wrapperClassName,
      )}
    >
      {/* Skeleton shimmer until the image paints */}
      {showImage && !loaded && (
        <div className="absolute inset-0 animate-pulse bg-slate-200/80 dark:bg-white/[0.08]" aria-hidden />
      )}

      {showImage ? (
        <img
          src={src as string}
          alt={alt}
          loading={eager ? 'eager' : 'lazy'}
          decoding="async"
          onLoad={() => setLoaded(true)}
          onError={() => setFailed(true)}
          className={cn(
            'h-full w-full object-cover transition-opacity duration-300',
            loaded ? 'opacity-100' : 'opacity-0',
            className,
          )}
          {...rest}
        />
      ) : (
        <div
          className="flex h-full w-full items-center justify-center text-slate-300 dark:text-white/20"
          aria-label={alt || undefined}
          role={alt ? 'img' : undefined}
        >
          {fallback ?? null}
        </div>
      )}
    </div>
  )
}
