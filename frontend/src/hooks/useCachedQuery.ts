import { useCallback, useEffect, useRef, useState } from 'react'
import { fetchCached, getEntry, invalidate, setCache, subscribe } from '@/lib/queryCache'

interface Options {
  /** Milliseconds the cached value is considered fresh. Default 60s. */
  ttl?: number
  /** Skip fetching (e.g. until a dependency is ready). Default true. */
  enabled?: boolean
}

interface Result<T> {
  data: T | undefined
  error: unknown
  loading: boolean
  /** Force a network refresh, bypassing TTL. */
  refetch: () => Promise<void>
  /** Optimistically write to the cache. */
  mutate: (data: T) => void
}

/**
 * SWR-style data hook backed by the in-memory `queryCache`. Fresh data is served
 * instantly across mounts/pages; stale data is served immediately and refreshed
 * in the background. Concurrent callers of the same key share one request.
 */
export function useCachedQuery<T>(
  key: string | null,
  fetcher: () => Promise<T>,
  { ttl = 60_000, enabled = true }: Options = {},
): Result<T> {
  const entry = key ? getEntry<T>(key) : undefined
  const [data, setData] = useState<T | undefined>(entry?.data)
  const [error, setError] = useState<unknown>(entry?.error)
  const [loading, setLoading] = useState<boolean>(enabled && entry?.data === undefined)

  // Keep a stable ref to the fetcher so callers can pass inline functions.
  const fetcherRef = useRef(fetcher)
  fetcherRef.current = fetcher

  const run = useCallback(
    async (force: boolean) => {
      if (!key) return
      setLoading(getEntry<T>(key)?.data === undefined)
      try {
        const result = await fetchCached<T>(key, () => fetcherRef.current(), { ttl, force })
        setData(result)
        setError(undefined)
      } catch (err) {
        setError(err)
      } finally {
        setLoading(false)
      }
    },
    [key, ttl],
  )

  useEffect(() => {
    if (!key || !enabled) return
    // Sync from cache when another consumer updates the same key.
    const unsub = subscribe(key, () => {
      const next = getEntry<T>(key)
      setData(next?.data)
      setError(next?.error)
    })
    void run(false)
    return unsub
  }, [key, enabled, run])

  const refetch = useCallback(async () => {
    await run(true)
  }, [run])

  const mutate = useCallback(
    (next: T) => {
      if (key) setCache(key, next)
      setData(next)
    },
    [key],
  )

  return { data, error, loading, refetch, mutate }
}

export { invalidate as invalidateQuery }
