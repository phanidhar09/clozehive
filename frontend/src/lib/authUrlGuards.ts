/**
 * Paths that must not trigger access-token refresh on 401 (avoid loops / wrong UX).
 * `url` is axios `config.url` — typically relative to baseURL (e.g. `/auth/refresh`).
 */
export function skipRefreshOn401(url: string | undefined): boolean {
  if (url == null || url === '') return true
  const u = url.split('?')[0] ?? url
  return (
    u.includes('/auth/refresh')
    || u.includes('/auth/login')
    || u.includes('/auth/signup')
    || u.includes('/auth/register')
    || u.includes('/auth/google/')
  )
}
