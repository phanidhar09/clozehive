import type { LucideIcon } from 'lucide-react'
import { Upload, Wand2, Plane, BarChart3, Sparkles, Shirt } from 'lucide-react'

export const DASHBOARD_QUICK_ACTIONS: {
  label: string
  desc: string
  icon: LucideIcon
  to: string
  gradient: string
}[] = [
  { label: 'Add to Closet',   desc: 'Upload new pieces',       icon: Upload,    to: '/upload',         gradient: 'from-emerald-500 to-teal-600'   },
  { label: 'Outfit Builder',  desc: 'Mix & match looks',       icon: Wand2,     to: '/outfit-builder', gradient: 'from-pink-500 to-rose-600'      },
  { label: 'FANI AI Stylist', desc: 'Get AI styling advice',   icon: Sparkles,  to: '/ai-stylist',     gradient: 'from-violet-500 to-fuchsia-600' },
  { label: 'My Closet',       desc: 'Browse your wardrobe',    icon: Shirt,     to: '/closet',         gradient: 'from-indigo-500 to-blue-600'    },
  { label: 'Travel Packing',  desc: 'Smart packing lists',     icon: Plane,     to: '/travel',         gradient: 'from-sky-500 to-cyan-600'       },
  { label: 'Style Insights',  desc: 'Wear analytics & trends', icon: BarChart3, to: '/analytics',      gradient: 'from-amber-500 to-orange-600'   },
]
