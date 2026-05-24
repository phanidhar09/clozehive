/**
 * useBackNavigation — go back to the previous route or a safe fallback.
 *
 * Priority:
 *   1. location.state.from (set by the referring page via <Link state={{ from: '/closet' }}>)
 *   2. browser history (window.history.length > 1 means there IS a previous entry)
 *   3. provided fallback string (default '/')
 */

import { useCallback } from 'react'
import { useNavigate, useLocation } from 'react-router-dom'

interface UseBackNavigationOptions {
  /** Route to navigate to when there's no history and no state.from */
  fallback?: string
}

export function useBackNavigation(options: UseBackNavigationOptions = {}) {
  const { fallback = '/' } = options
  const navigate = useNavigate()
  const location = useLocation()

  const goBack = useCallback(() => {
    const from = (location.state as { from?: string } | null)?.from
    if (from) {
      navigate(from)
    } else if (window.history.length > 1) {
      navigate(-1)
    } else {
      navigate(fallback)
    }
  }, [navigate, location.state, fallback])

  return goBack
}
