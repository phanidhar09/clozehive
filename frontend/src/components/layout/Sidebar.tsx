import { NavLink, useNavigate } from 'react-router-dom'
import { motion } from 'framer-motion'
import {
  LayoutDashboard, Shirt, Plane, User,
  BarChart3, X, Moon, Sun, LogOut, Wand2, PlusCircle,
  type LucideIcon,
} from 'lucide-react'
import { useApp } from '@/store'
import { useColorScheme } from '@/hooks/useColorScheme'
import { cn } from '@/lib/utils'

type SidebarNavItem = {
  to: string
  label: string
  icon: LucideIcon
  gradient?: string
}

const NAV: SidebarNavItem[] = [
  { to: '/dashboard',       label: 'Dashboard',           icon: LayoutDashboard },
  { to: '/closet',          label: 'My Closet',           icon: Shirt },
  { to: '/outfit-builder',  label: 'Outfit Builder',      icon: Wand2,        gradient: 'from-pink-500 to-rose-600' },
  { to: '/upload',          label: 'Add to Your Closet',  icon: PlusCircle,   gradient: 'from-violet-500 to-indigo-600' },
  { to: '/travel',          label: 'Travel Packing',      icon: Plane },
  { to: '/analytics',       label: 'Closet Insights',     icon: BarChart3 },
]

export default function Sidebar() {
  const { sidebarOpen, setSidebarOpen, currentUser, logout } = useApp()
  const { colorScheme, toggleColorScheme } = useColorScheme()
  const navigate = useNavigate()

  const initials = currentUser?.display_name
    ? currentUser.display_name.split(' ').map((n: string) => n[0]).join('').slice(0, 2).toUpperCase()
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
          className="fixed inset-0 bg-black/50 backdrop-blur-sm z-40 lg:hidden animate-fade-in"
          onClick={() => setSidebarOpen(false)}
        />
      )}

      <aside
        className={cn(
          'fixed top-0 left-0 h-screen w-[260px] z-50 flex flex-col',
          // Glass panel — sits on top of the background orbs
          'bg-white/80 dark:bg-slate-950/80 backdrop-blur-xl',
          'border-r border-cream-200 dark:border-white/[0.07]',
          'transition-transform duration-300 ease-in-out',
          sidebarOpen ? 'translate-x-0' : '-translate-x-full lg:translate-x-0',
        )}
      >
        {/* ── Logo ─────────────────────────────────────────────────────── */}
        <div className="flex items-center justify-between px-5 h-16 border-b border-cream-200 dark:border-white/[0.07] flex-shrink-0">
          <div className="flex items-center gap-3">
            {/* Logo mark with glow */}
            <div className="relative w-9 h-9 rounded-xl bg-gradient-to-br from-indigo-500 to-violet-600
                            flex items-center justify-center text-sm font-bold text-white
                            shadow-glow-sm">
              <span className="relative z-10">C</span>
            </div>
            <div>
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
            className="lg:hidden p-1.5 min-h-[44px] min-w-[44px] rounded-lg text-slate-400 dark:text-white/40
                       hover:text-slate-700 dark:hover:text-white hover:bg-slate-100 dark:hover:bg-white/10
                       transition-colors"
          >
            <X size={18} />
          </button>
        </div>

        {/* ── Navigation ───────────────────────────────────────────────── */}
        <nav className="flex-1 overflow-y-auto py-4 px-3 space-y-0.5">
          <p className="text-[10px] font-semibold uppercase tracking-widest
                        text-slate-400 dark:text-white/25 px-3 mb-2">
            Menu
          </p>
          {NAV.map(({ to, label, icon: Icon, gradient }) => (
            <NavLink
              key={to}
              to={to}
              onClick={() => setSidebarOpen(false)}
              className={({ isActive }) => cn('nav-item relative overflow-hidden', isActive && 'active')}
            >
              {({ isActive }) => (
                <>
                  {isActive && (
                    <motion.div
                      layoutId="sidebar-active"
                      className="absolute inset-0 rounded-xl bg-slate-100 dark:bg-white/[0.10]"
                      transition={{ duration: 0.18, ease: 'easeOut' }}
                    />
                  )}
                  <span className={cn('relative z-10', gradient && `flex h-7 w-7 flex-shrink-0 items-center justify-center rounded-lg bg-gradient-to-br ${gradient} text-white`)}>
                    <Icon size={17} className="flex-shrink-0" />
                  </span>
                  <span className="relative z-10">{label}</span>
                </>
              )}
            </NavLink>
          ))}
        </nav>

        {/* ── Bottom ───────────────────────────────────────────────────── */}
        <div className="px-3 pb-5 space-y-1.5 border-t border-cream-200 dark:border-white/[0.07] pt-4 flex-shrink-0">
          {/* Theme toggle */}
          <button
              onClick={toggleColorScheme}
              className="w-full flex items-center gap-3 px-3 py-2.5 min-h-[44px] rounded-xl text-sm font-medium
                       text-slate-500 dark:text-white/45
                       hover:text-slate-800 dark:hover:text-white
                       hover:bg-slate-100 dark:hover:bg-white/[0.07]
                       transition-all duration-150"
          >
            {colorScheme === 'dark'
              ? <Sun size={16} className="text-amber-400" />
              : <Moon size={16} className="text-indigo-400" />}
            {colorScheme === 'dark' ? 'Light mode' : 'Dark mode'}
          </button>

          {/* User card */}
          {currentUser ? (
            <div className="rounded-xl bg-slate-50 dark:bg-white/[0.04]
                            border border-cream-200 dark:border-white/[0.07] overflow-hidden">
              <NavLink
                to="/profile"
                onClick={() => setSidebarOpen(false)}
                className="flex items-center gap-3 px-3 py-2.5 min-h-[44px]
                           hover:bg-slate-100 dark:hover:bg-white/[0.05] transition-colors"
              >
                <div className="w-8 h-8 rounded-full bg-gradient-to-br from-indigo-500 to-violet-600
                                flex items-center justify-center text-xs font-bold text-white flex-shrink-0
                                ring-2 ring-indigo-400/20 overflow-hidden">
                  {currentUser.avatar_url
                    ? <img src={currentUser.avatar_url} alt="" className="w-full h-full object-cover" />
                    : initials}
                </div>
                <div className="flex-1 min-w-0">
                  <div className="text-sm font-semibold text-slate-800 dark:text-white truncate">
                    {currentUser.display_name}
                  </div>
                  <div className="text-[11px] text-slate-400 dark:text-white/40 truncate">
                    @{currentUser.username}
                  </div>
                </div>
              </NavLink>
              <button
                onClick={handleLogout}
                className="w-full flex items-center gap-2.5 px-3 py-2 min-h-[44px] text-sm
                           text-red-500 dark:text-red-400
                           hover:bg-red-50 dark:hover:bg-red-500/10
                           border-t border-cream-200 dark:border-white/[0.05]
                           transition-colors"
              >
                <LogOut size={13} /> Sign out
              </button>
            </div>
          ) : (
            <div className="flex items-center gap-3 px-3 py-2.5 rounded-xl
                            bg-slate-50 dark:bg-white/[0.04]
                            border border-cream-200 dark:border-white/[0.07]">
              <div className="w-8 h-8 rounded-full bg-gradient-to-br from-indigo-500 to-violet-600
                              flex items-center justify-center text-xs font-bold text-white">?</div>
              <div className="text-sm text-slate-400 dark:text-white/40">Not signed in</div>
            </div>
          )}
        </div>
      </aside>
    </>
  )
}
