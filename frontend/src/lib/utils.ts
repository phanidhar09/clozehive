import clsx, { type ClassValue } from 'clsx'

/** Merge class names (clsx). */
export function cn(...inputs: ClassValue[]): string {
  return clsx(inputs)
}

/** Tailwind-friendly background for eco score pills. */
export function ecoScoreBg(score?: number | null): string {
  if (score == null) return 'bg-slate-400 text-slate-950'
  if (score >= 8) return 'bg-emerald-400 text-emerald-950'
  if (score >= 5) return 'bg-amber-300 text-amber-950'
  return 'bg-rose-400 text-rose-950'
}

export function formatDate(iso: string | Date | undefined | null): string {
  if (!iso) return '—'
  try {
    const d = typeof iso === 'string' ? new Date(iso) : iso
    return d.toLocaleDateString(undefined, { year: 'numeric', month: 'short', day: 'numeric' })
  } catch {
    return String(iso)
  }
}

export function timeAgo(iso: string | Date | undefined | null): string {
  if (!iso) return ''
  const d = typeof iso === 'string' ? new Date(iso) : iso
  const s = Math.floor((Date.now() - d.getTime()) / 1000)
  if (s < 60) return 'just now'
  if (s < 3600) return `${Math.floor(s / 60)}m ago`
  if (s < 86400) return `${Math.floor(s / 3600)}h ago`
  if (s < 604800) return `${Math.floor(s / 86400)}d ago`
  return formatDate(d)
}

/** Emoji hint for closet category (used on cards / modals). */
export function categoryIcon(category?: string | null): string {
  const c = (category ?? '').toLowerCase()
  if (c.includes('shoe') || c === 'shoes') return '👟'
  if (c.includes('bottom') || c.includes('pant') || c.includes('jean')) return '👖'
  if (c.includes('outer') || c.includes('jacket') || c.includes('coat')) return '🧥'
  if (c.includes('dress')) return '👗'
  if (c.includes('access')) return '👜'
  if (c.includes('hat') || c.includes('cap')) return '🧢'
  return '👕'
}

export function generateId(): string {
  return `${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 11)}`
}
