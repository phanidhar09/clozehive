import { NavLink, useNavigate } from 'react-router-dom'
import { motion } from 'framer-motion'
import {
  Home, Shirt, Plus, Plane, Heart,
  X, Moon, Sun, LogOut,
  Sparkles, Wand2, ShoppingCart, ShoppingBag,
  BarChart3, Layers, CalendarDays,
  type LucideIcon,
} from 'lucide-react'
import { useApp } from '@/store'
import { useColorScheme } from '@/hooks/useColorScheme'
import { cn } from '@/lib/utils'

type SidebarNavItem = {
  to: string
  label: string
  icon: LucideIcon
}

type SidebarNavGroup = {
  heading: string
  items: SidebarNavItem[]
}

// Top-level item shown alone above the grouped sections.
const NAV_TOP: SidebarNavItem = { to: '/dashboard', label: 'Home', icon: Home }

// Grouped destinations — every feature stays visible, parsed as 4 short sections.
const NAV_GROUPS: SidebarNavGroup[] = [
  {
    heading: 'Wardrobe',
    items: [
      { to: '/closet', label: 'My Closet', icon: Shirt },
      { to: '/upload', label: 'Add Items', icon: Plus },
    ],
  },
  {
    heading: 'Create',
    items: [
      { to: '/outfit-builder', label: 'Build Outfit',   icon: Wand2 },
      { to: '/planner',        label: 'Weekly Planner', icon: CalendarDays },
      { to: '/saved-outfits',  label: 'Saved Outfits',  icon: Heart },
      { to: '/travel',         label: 'Travel Planner', icon: Plane },
    ],
  },
  {
    heading: 'FANI · AI',
    items: [
      { to: '/ai-stylist',     label: 'FANI',           icon: Sparkles },
      { to: '/shopping-check', label: 'Shop with FANI', icon: ShoppingCart },
      { to: '/closet-match',   label: 'Fit Match',      icon: Layers },
    ],
  },
  {
    heading: 'Insights',
    items: [
      { to: '/analytics',     label: 'Style Insights', icon: BarChart3 },
      { to: '/purchase-gaps', label: 'Wardrobe Gaps',  icon: ShoppingBag },
    ],
  },
]

/** Single sidebar link — neutral icon; teal accent comes from `.nav-item.active`.
 *  On the md tablet rail only the icon shows (labels hidden), so we expose the
 *  label via `title` + `aria-label` for hover tooltips and screen readers. */
function NavItem({ item, onNavigate }: { item: SidebarNavItem; onNavigate: () => void }) {
  const { to, label, icon: Icon } = item
  return (
    <NavLink
      to={to}
      onClick={onNavigate}
      title={label}
      aria-label={label}
      className={({ isActive }) =>
        cn(
          'nav-item relative overflow-hidden md:justify-center lg:justify-start',
          isActive && 'active',
        )
      }
    >
      {({ isActive }) => (
        <>
          {isActive && (
            <motion.div
              layoutId="sidebar-active-main"
              className="absolute inset-0 rounded-xl bg-slate-100 dark:bg-white/[0.10]"
              transition={{ duration: 0.18, ease: 'easeOut' }}
            />
          )}
          <span className="relative z-10 flex-shrink-0">
            <Icon size={17} />
          </span>
          <span className="relative z-10 md:hidden lg:inline">{label}</span>
        </>
      )}
    </NavLink>
  )
}

export default function Sidebar() {
  const { sidebarOpen, setSidebarOpen, currentUser, logout } = useApp()
  const { colorScheme, toggleColorScheme } = useColorScheme()
  const navigate = useNavigate()

  const displayLabel = currentUser?.display_name || currentUser?.username || ''
  const initials = displayLabel
    ? displayLabel.split(' ').map((n: string) => n[0]).join('').slice(0, 2).toUpperCase()
    : 'U'

  const handleLogout = () => {
    logout()
    navigate('/login', { replace: true })
    setSidebarOpen(false)
  }

  return (
    <>
      {/* Mobile backdrop */}
      {sidebarOpen && (
        <div
          className="fixed inset-0 bg-black/50 backdrop-blur-sm z-40 md:hidden animate-fade-in"
          onClick={() => setSidebarOpen(false)}
        />
      )}

      <aside
        aria-label="Sidebar"
        className={cn(
          // Mobile drawer = full 260px; md = compact icon rail (80px); lg = full panel
          'fixed top-0 left-0 h-screen w-[260px] md:w-20 lg:w-[260px] z-50 flex flex-col',
          // Glass panel — sits on top of the background orbs
          'bg-white/80 dark:bg-slate-950/80 backdrop-blur-xl',
          'border-r border-cream-200 dark:border-white/[0.07]',
          'transition-transform duration-300 ease-in-out',
          // Off-canvas below md; always visible from md up (rail), full at lg
          sidebarOpen ? 'translate-x-0' : '-translate-x-full md:translate-x-0',
        )}
      >
        {/* ── Logo ─────────────────────────────────────────────────────── */}
        <div className="flex items-center justify-between md:justify-center lg:justify-between px-5 md:px-0 lg:px-5 h-16 border-b border-cream-200 dark:border-white/[0.07] flex-shrink-0">
          <div className="flex items-center gap-3">
            {/* Logo mark with glow */}
            <div className="relative w-9 h-9 rounded-xl bg-gradient-to-br from-brand-600 to-brand-700
                            flex items-center justify-center text-sm font-bold text-white
                            shadow-glow-sm">
              <span className="relative z-10">C</span>
            </div>
            <div className="md:hidden lg:block">
              <div className="font-display font-bold text-base leading-tight text-slate-900 dark:text-white">
                ClozéHive
              </div>
              <div className="text-[10px] text-slate-400 dark:text-white/40 font-medium tracking-wide">
                AI Wardrobe
              </div>
            </div>
          </div>
          <button
            onClick={() => setSidebarOpen(false)}
            aria-label="Close menu"
            className="md:hidden p-1.5 min-h-[44px] min-w-[44px] rounded-lg text-slate-400 dark:text-white/40
                       hover:text-slate-700 dark:hover:text-white hover:bg-slate-100 dark:hover:bg-white/10
                       transition-colors"
          >
            <X size={18} />
          </button>
        </div>

        {/* ── Navigation ───────────────────────────────────────────────── */}
        <nav className="flex-1 overflow-y-auto py-4 px-3 md:px-2 lg:px-3 space-y-0.5">
          {/* Dashboard — top-level, above the grouped sections */}
          <NavItem item={NAV_TOP} onNavigate={() => setSidebarOpen(false)} />

          {NAV_GROUPS.map(({ heading, items }) => (
            <div key={heading} className="pt-4 first:pt-3">
              {/* On the md rail, replace text headings with a subtle divider */}
              <p className="px-3 pb-1.5 text-[10px] font-bold uppercase tracking-widest
                            text-slate-400 dark:text-white/30 md:hidden lg:block">
                {heading}
              </p>
              <div className="hidden md:block lg:hidden mx-2 mb-1.5 h-px bg-cream-200 dark:bg-white/[0.07]" aria-hidden />
              {items.map((item) => (
                <NavItem key={item.to} item={item} onNavigate={() => setSidebarOpen(false)} />
              ))}
            </div>
          ))}
        </nav>

        {/* ── Bottom ───────────────────────────────────────────────────── */}
        <div className="px-3 md:px-2 lg:px-3 pb-5 space-y-1.5 border-t border-cream-200 dark:border-white/[0.07] pt-4 flex-shrink-0">
          {/* Theme toggle */}
          <button
              onClick={toggleColorScheme}
              title={colorScheme === 'dark' ? 'Light mode' : 'Dark mode'}
              aria-label={colorScheme === 'dark' ? 'Switch to light mode' : 'Switch to dark mode'}
              className="w-full flex items-center gap-3 px-3 py-2.5 min-h-[44px] rounded-xl text-sm font-medium
                       text-slate-500 dark:text-white/45
                       hover:text-slate-800 dark:hover:text-white
                       hover:bg-slate-100 dark:hover:bg-white/[0.07]
                       transition-all duration-150
                       md:justify-center lg:justify-start"
          >
            {colorScheme === 'dark'
              ? <Sun size={16} className="text-amber-400" />
              : <Moon size={16} className="text-brand-400" />}
            <span className="md:hidden lg:inline">
              {colorScheme === 'dark' ? 'Light mode' : 'Dark mode'}
            </span>
          </button>

          {/* User card */}
          {currentUser ? (
            <div className="rounded-xl bg-slate-50 dark:bg-white/[0.04] md:bg-transparent lg:bg-slate-50 dark:lg:bg-white/[0.04]
                            border border-cream-200 dark:border-white/[0.07] md:border-transparent lg:border-cream-200 dark:lg:border-white/[0.07]
                            overflow-hidden">
              <NavLink
                to="/profile"
                onClick={() => setSidebarOpen(false)}
                title={currentUser.display_name || currentUser.username}
                aria-label="View profile"
                className="flex items-center gap-3 px-3 py-2.5 min-h-[44px] md:justify-center lg:justify-start
                           hover:bg-slate-100 dark:hover:bg-white/[0.05] transition-colors rounded-xl"
              >
                <div className="w-8 h-8 rounded-full bg-gradient-to-br from-brand-600 to-brand-700
                                flex items-center justify-center text-xs font-bold text-white flex-shrink-0
                                ring-2 ring-brand-400/20 overflow-hidden">
                  {currentUser.avatar_url
                    ? <img src={currentUser.avatar_url} alt="" className="w-full h-full object-cover" />
                    : initials}
                </div>
                <div className="flex-1 min-w-0 md:hidden lg:block">
                  <div className="text-sm font-semibold text-slate-800 dark:text-white truncate">
                    {currentUser.display_name || currentUser.username}
                  </div>
                  <div className="text-[11px] text-slate-400 dark:text-white/40 truncate">
                    @{currentUser.username}
                  </div>
                </div>
              </NavLink>
              <button
                onClick={handleLogout}
                title="Sign out"
                aria-label="Sign out"
                className="w-full flex items-center gap-2.5 px-3 py-2 min-h-[44px] text-sm
                           text-red-500 dark:text-red-400 md:justify-center lg:justify-start
                           hover:bg-red-50 dark:hover:bg-red-500/10
                           border-t border-cream-200 dark:border-white/[0.05] md:border-transparent lg:border-cream-200 dark:lg:border-white/[0.05]
                           transition-colors rounded-xl"
              >
                <LogOut size={13} /> <span className="md:hidden lg:inline">Sign out</span>
              </button>
            </div>
          ) : (
            <div className="flex items-center gap-3 px-3 py-2.5 rounded-xl
                            bg-slate-50 dark:bg-white/[0.04]
                            border border-cream-200 dark:border-white/[0.07]">
              <div className="w-8 h-8 rounded-full bg-gradient-to-br from-brand-600 to-brand-700
                              flex items-center justify-center text-xs font-bold text-white">?</div>
              <div className="text-sm text-slate-400 dark:text-white/40">Not signed in</div>
            </div>
          )}
        </div>
      </aside>
    </>
  )
}
