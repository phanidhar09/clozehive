import type { LucideIcon } from 'lucide-react'
import { Upload, Shirt, Wand2, Plane, BarChart3 } from 'lucide-react'

export const DASHBOARD_QUICK_ACTIONS: {
  label: string
  desc: string
  icon: LucideIcon
  to: string
  gradient: string
}[] = [
  { label: 'Smart Closet Scan', desc: 'Bulk upload items',      icon: Upload,    to: '/upload',        gradient: 'from-emerald-500 to-teal-600' },
  { label: 'My Closet',         desc: 'View all pieces',       icon: Shirt,     to: '/closet',        gradient: 'from-rose-500 to-pink-600' },
  { label: 'Outfit Builder',    desc: 'Drag-and-drop looks',   icon: Wand2,     to: '/outfit-builder', gradient: 'from-pink-500 to-rose-600' },
  { label: 'Travel Packing',    desc: 'Plan your trip',       icon: Plane,     to: '/travel',        gradient: 'from-sky-500 to-blue-600' },
  { label: 'Closet Insights',   desc: 'View your analytics',   icon: BarChart3, to: '/analytics',     gradient: 'from-violet-500 to-purple-600' },
]
