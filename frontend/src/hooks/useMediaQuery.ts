import { useEffect, useState } from 'react'

/**
 * Subscribe to a CSS media query. SSR-safe (returns `false` until mounted).
 *
 * @example const isDesktop = useMediaQuery('(min-width: 1024px)')
 */
export function useMediaQuery(query: string): boolean {
  const [matches, setMatches] = useState(() => {
    if (typeof window === 'undefined') return false
    return window.matchMedia(query).matches
  })

  useEffect(() => {
    if (typeof window === 'undefined') return
    const mql = window.matchMedia(query)
    const onChange = (e: MediaQueryListEvent) => setMatches(e.matches)
    setMatches(mql.matches)
    mql.addEventListener('change', onChange)
    return () => mql.removeEventListener('change', onChange)
  }, [query])

  return matches
}

// Tailwind default breakpoints (px), kept in sync with tailwind.config.js
export const BREAKPOINTS = {
  sm: 640,
  md: 768,
  lg: 1024,
  xl: 1280,
  '2xl': 1536,
} as const

export type Breakpoint = keyof typeof BREAKPOINTS

/** True when the viewport is at least the given Tailwind breakpoint. */
export function useBreakpoint(bp: Breakpoint): boolean {
  return useMediaQuery(`(min-width: ${BREAKPOINTS[bp]}px)`)
}
