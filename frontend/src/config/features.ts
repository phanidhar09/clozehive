/**
 * When true (default), hides non–Phase 1 pages: Groups, Avatar Builder, AI Stylist.
 * Outfit Builder (drag-and-drop) remains visible as part of MVP.
 * Set `VITE_HIDE_NON_MVP=false` to show those hidden pages.
 */
export function hideNonMvpUi(): boolean {
  const v = import.meta.env.VITE_HIDE_NON_MVP
  if (v === undefined || v === '') return true
  return v !== 'false' && v !== '0'
}
