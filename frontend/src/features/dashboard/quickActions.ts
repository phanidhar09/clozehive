import type { LucideIcon } from 'lucide-react'
import { Upload, Shirt, Wand2, Plane, BarChart3, Sparkles } from 'lucide-react'

export const DASHBOARD_QUICK_ACTIONS: {
  label: string
  desc: string
  icon: LucideIcon
  to: string
  gradient: string
}[] = [
  { label: 'Scan Wardrobe',   desc: 'Add new clothing pieces',   icon: Upload,   to: '/upload',         gradient: 'from-emerald-500 to-teal-600'   },
  { label: 'My Closet',       desc: 'Browse all your pieces',    icon: Shirt,    to: '/closet',         gradient: 'from-rose-500 to-pink-600'      },
  { label: 'Build an Outfit', desc: 'Mix & match looks',         icon: Wand2,    to: '/outfit-builder', gradient: 'from-pink-500 to-rose-600'      },
  { label: 'Ask FANI',        desc: 'Get AI outfit advice',      icon: Sparkles, to: '/ai-stylist',     gradient: 'from-violet-500 to-fuchsia-600' },
  { label: 'Pack for Travel', desc: 'Wardrobe for any trip',     icon: Plane,    to: '/travel',         gradient: 'from-sky-500 to-blue-600'       },
  { label: 'Style Insights',  desc: 'Analytics & trends',        icon: BarChart3,to: '/analytics',      gradient: 'from-amber-500 to-orange-600'   },
]
