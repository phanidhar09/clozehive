/**
 * Shared parser for FastAPI / axios auth errors.
 * Handles string `detail`, Pydantic validation arrays, and message/error fields.
 */
export function parseAuthError(err: unknown, fallback: string): string {
  type ApiErr = {
    response?: {
      data?: {
        message?: string
        error?: string
        detail?: string | Array<{ loc?: (string | number)[]; msg?: string }>
      }
    }
  }
  const d = (err as ApiErr)?.response?.data
  let msg: string | undefined
  if (typeof d?.detail === 'string') {
    msg = d.detail
  } else if (Array.isArray(d?.detail)) {
    msg = d.detail
      .map(e => {
        const field = Array.isArray(e.loc) ? e.loc.slice(1).join('.') : ''
        return field ? `${field}: ${e.msg ?? ''}` : (e.msg ?? '')
      })
      .filter(Boolean)
      .join(' · ')
  }
  return msg ?? d?.message ?? d?.error ?? (err instanceof Error ? err.message : fallback)
}
