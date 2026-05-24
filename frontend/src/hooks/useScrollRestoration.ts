/**
 * useScrollRestoration — save the scroll position of a container (or window)
 * when the component unmounts and restore it when it mounts again.
 *
 * Usage:
 *   const ref = useScrollRestoration<HTMLDivElement>('closet-scroll')
 *   <div ref={ref} className="overflow-y-auto"> ... </div>
 *
 *   // Window scroll variant — pass null as the containerRef
 *   useScrollRestoration('closet-scroll', null)
 */

import { useRef, useEffect } from 'react'

const STORAGE_KEY_PREFIX = 'scroll:'

function readPos(key: string): number {
  try {
    return Number(sessionStorage.getItem(STORAGE_KEY_PREFIX + key) ?? 0)
  } catch {
    return 0
  }
}

function savePos(key: string, y: number): void {
  try {
    sessionStorage.setItem(STORAGE_KEY_PREFIX + key, String(y))
  } catch {
    // no-op
  }
}

/**
 * Returns a ref to attach to a scrollable container element.
 * Restores scroll on mount and saves on unmount.
 */
export function useScrollRestoration<T extends HTMLElement = HTMLDivElement>(
  key: string,
): React.RefObject<T> {
  const ref = useRef<T>(null)

  useEffect(() => {
    const el = ref.current
    if (!el) return

    // Restore on mount — defer to next tick so content has rendered
    const y = readPos(key)
    if (y) {
      requestAnimationFrame(() => {
        el.scrollTop = y
      })
    }

    // Save on unmount
    return () => {
      savePos(key, el.scrollTop)
    }
  }, [key])

  return ref
}

/**
 * Window-level scroll restoration (no ref needed).
 * Call at the top of a page component.
 */
export function useWindowScrollRestoration(key: string): void {
  useEffect(() => {
    const y = readPos(key)
    if (y) {
      requestAnimationFrame(() => {
        window.scrollTo(0, y)
      })
    }

    const handleUnload = () => savePos(key, window.scrollY)
    window.addEventListener('scroll', handleUnload, { passive: true })

    return () => {
      savePos(key, window.scrollY)
      window.removeEventListener('scroll', handleUnload)
    }
  }, [key])
}
