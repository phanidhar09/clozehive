import { NavLink, useLocation } from 'react-router-dom'
import { Home, Shirt, Plus, Sparkles, Wand2, Menu, type LucideIcon } from 'lucide-react'
import { useApp } from '@/store'
import { cn } from '@/lib/utils'

type Tab = { to: string; label: string; icon: LucideIcon; primary?: boolean; end?: boolean }

/**
 * Mobile bottom tab bar — the primary navigation on small screens.
 * Hidden on desktop (`lg:hidden`), where the sidebar takes over.
 * The center "+" is an elevated primary action (Add items).
 * The trailing "More" opens the sidebar and stays highlighted on any
 * page not covered by the other tabs, so users never lose orientation.
 */

const TABS: Tab[] = [
  { to: '/dashboard',  label: 'Home',   icon: Home,     end: true },
  { to: '/closet',     label: 'Closet', icon: Shirt },
  { to: '/upload',     label: 'Add',    icon: Plus,     primary: true },
  { to: '/outfit-builder', label: 'Outfit', icon: Wand2 },
  { to: '/ai-stylist', label: 'FANI',   icon: Sparkles },
]

// Routes that own a dedicated tab above.
const TAB_PATHS = ['/dashboard', '/closet', '/upload', '/outfit-builder', '/ai-stylist']

export default function BottomNav() {
  const { setSidebarOpen } = useApp()
  const { pathname } = useLocation()
  const navInKnownRoute = TAB_PATHS.some(p => pathname === p || pathname.startsWith(p + '/'))

  return (
    <nav
      className="md:hidden fixed bottom-0 inset-x-0 z-40
                 bg-white/90 dark:bg-slate-950/90 backdrop-blur-xl
                 border-t border-cream-200 dark:border-white/[0.08]"
      style={{ paddingBottom: 'env(safe-area-inset-bottom)' }}
      aria-label="Primary"
    >
      <div className="flex items-end gap-1 overflow-x-auto px-2 pt-1.5 pb-1.5 scrollbar-hide">
        {TABS.map(({ to, label, icon: Icon, primary, end }) =>
          primary ? (
            <NavLink
              key={to}
              to={to}
              className="flex flex-col items-center justify-end gap-1 px-2 -mt-5"
              aria-label={label}
            >
              <span className="w-12 h-12 rounded-2xl bg-gradient-to-br from-brand-500 to-brand-600
                               text-white flex items-center justify-center
                               shadow-lg shadow-brand-500/40 ring-4 ring-brand-500/25 dark:ring-brand-500/30
                               active:scale-95 transition-transform">
                <Icon size={22} />
              </span>
              <span className="text-[10px] font-medium text-slate-400 dark:text-white/40">{label}</span>
            </NavLink>
          ) : (
            <NavLink
              key={to}
              to={to}
              end={end}
              className={({ isActive }) =>
                cn(
                  'flex flex-col items-center justify-center gap-0.5 min-w-[56px] py-1.5 rounded-xl flex-shrink-0',
                  'transition-colors active:scale-95',
                  isActive
                    ? 'text-brand-600 dark:text-brand-400'
                    : 'text-slate-400 dark:text-white/40 hover:text-slate-600 dark:hover:text-white/70',
                )
              }
            >
              <Icon size={20} />
              <span className="text-[10px] font-medium">{label}</span>
            </NavLink>
          ),
        )}

        {/* Overflow access for non-primary destinations */}
        <button
          onClick={() => setSidebarOpen(true)}
          aria-label="More destinations"
          className={cn(
            'flex flex-col items-center justify-center gap-0.5 min-w-[56px] py-1.5 rounded-xl flex-shrink-0',
            'transition-colors active:scale-95',
            !navInKnownRoute
              ? 'text-brand-600 dark:text-brand-400'
              : 'text-slate-400 dark:text-white/40 hover:text-slate-600 dark:hover:text-white/70',
          )}
        >
          <Menu size={20} />
          <span className="text-[10px] font-medium">More</span>
        </button>
      </div>
    </nav>
  )
}
