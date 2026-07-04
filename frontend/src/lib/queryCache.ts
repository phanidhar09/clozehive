/**
 * Tiny SWR-style client cache — no external dependency.
 *
 * Provides an in-memory store with TTL, in-flight request de-duplication and
 * manual invalidation. Used by `useCachedQuery` so navigating between pages
 * doesn't re-hit the network for data that is still fresh (e.g. Today's Look,
 * shopping history, analytics), while still allowing background refresh.
 */

interface CacheEntry<T = unknown> {
  data?: T
  error?: unknown
  updatedAt: number
  /** In-flight request, used to de-dupe concurrent callers. */
  promise?: Promise<T>
}

const store = new Map<string, CacheEntry>()
const listeners = new Map<string, Set<() => void>>()

function notify(key: string) {
  listeners.get(key)?.forEach((fn) => fn())
}

export function getEntry<T>(key: string): CacheEntry<T> | undefined {
  return store.get(key) as CacheEntry<T> | undefined
}

export function subscribe(key: string, fn: () => void): () => void {
  let set = listeners.get(key)
  if (!set) {
    set = new Set()
    listeners.set(key, set)
  }
  set.add(fn)
  return () => set!.delete(fn)
}

/**
 * Fetch through the cache. Returns cached data immediately when fresh; otherwise
 * runs the fetcher (de-duping concurrent calls) and stores the result.
 */
export async function fetchCached<T>(
  key: string,
  fetcher: () => Promise<T>,
  { ttl = 60_000, force = false }: { ttl?: number; force?: boolean } = {},
): Promise<T> {
  const existing = store.get(key) as CacheEntry<T> | undefined

  if (existing?.promise) return existing.promise

  const isFresh =
    existing && existing.error === undefined && Date.now() - existing.updatedAt < ttl
  if (existing && isFresh && !force && existing.data !== undefined) {
    return existing.data
  }

  const promise = fetcher()
    .then((data) => {
      store.set(key, { data, updatedAt: Date.now() })
      notify(key)
      return data
    })
    .catch((error) => {
      store.set(key, {
        data: existing?.data,
        error,
        updatedAt: Date.now(),
      })
      notify(key)
      throw error
    })

  store.set(key, { ...(existing ?? { updatedAt: 0 }), promise })
  return promise
}

/** Drop one key, all keys matching a prefix, or the whole cache. */
export function invalidate(key?: string, { prefix = false }: { prefix?: boolean } = {}) {
  if (!key) {
    const keys = [...store.keys()]
    store.clear()
    keys.forEach(notify)
    return
  }
  if (prefix) {
    for (const k of [...store.keys()]) {
      if (k.startsWith(key)) {
        store.delete(k)
        notify(k)
      }
    }
    return
  }
  store.delete(key)
  notify(key)
}

/** Imperatively write data into the cache (optimistic updates). */
export function setCache<T>(key: string, data: T) {
  store.set(key, { data, updatedAt: Date.now() })
  notify(key)
}
