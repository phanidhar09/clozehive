/**
 * usePageState — persist UI state (filters, active tab, step index, etc.) in
 * sessionStorage so it survives navigation but is cleared on browser refresh.
 *
 * Safety rules baked in:
 *   - Key must be namespaced (caller passes e.g. "closet-filters")
 *   - Values are serialised with JSON.stringify; the stored string is capped at
 *     MAX_BYTES (32 KB) to avoid storing large blobs or image data.
 *   - No auth tokens, no image bytes, no passwords — callers must not pass them.
 */

import { useState, useCallback, useEffect } from 'react'

const STORAGE_KEY_PREFIX = 'ps:'   // page-state namespace
const MAX_BYTES = 32 * 1024        // 32 KB hard cap

function readFromStorage<T>(key: string, defaultValue: T): T {
  try {
    const raw = sessionStorage.getItem(STORAGE_KEY_PREFIX + key)
    if (raw === null) return defaultValue
    return JSON.parse(raw) as T
  } catch {
    return defaultValue
  }
}

function writeToStorage<T>(key: string, value: T): void {
  try {
    const serialised = JSON.stringify(value)
    if (serialised.length > MAX_BYTES) {
      // Silent guard — don't crash the UI, just don't persist
      console.warn(`[usePageState] Skipping persist for "${key}": value exceeds ${MAX_BYTES} bytes`)
      return
    }
    sessionStorage.setItem(STORAGE_KEY_PREFIX + key, serialised)
  } catch {
    // sessionStorage unavailable (private browsing quota, etc.) — no-op
  }
}

/**
 * @param key      Unique key per page/component (e.g. "closet-filters")
 * @param initial  Default value used when nothing is stored yet
 */
export function usePageState<T>(key: string, initial: T): [T, (value: T | ((prev: T) => T)) => void] {
  const [state, setStateInternal] = useState<T>(() => readFromStorage<T>(key, initial))

  const setState = useCallback(
    (value: T | ((prev: T) => T)) => {
      setStateInternal((prev) => {
        const next = typeof value === 'function' ? (value as (p: T) => T)(prev) : value
        writeToStorage(key, next)
        return next
      })
    },
    [key],
  )

  // Sync to storage whenever key changes (e.g. re-use hook across different mounted pages)
  useEffect(() => {
    const stored = readFromStorage<T>(key, initial)
    setStateInternal(stored)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key])

  return [state, setState]
}

/** Imperatively clear page state for a given key (e.g. after form submit). */
export function clearPageState(key: string): void {
  try {
    sessionStorage.removeItem(STORAGE_KEY_PREFIX + key)
  } catch {
    // no-op
  }
}
