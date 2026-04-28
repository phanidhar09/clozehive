import { NavLink, useNavigate } from 'react-router-dom'
import {
  LayoutDashboard, Shirt, Upload, Sparkles, Plane, User,
  BarChart3, X, Moon, Sun, Users, LogOut
} from 'lucide-react'
import { useApp } from '@/store'
import { cn } from '@/lib/utils'

const NAV = [
  { to: '/dashboard',  label: 'Dashboard',      icon: LayoutDashboard },
  { to: '/closet',     label: 'My Closet',       icon: Shirt },
  { to: '/upload',     label: 'Upload Item',      icon: Upload },
  { to: '/ai-stylist', label: 'AI Stylist',       icon: Sparkles },
  { to: '/travel',     label: 'Travel Planner',   icon: Plane },
  { to: '/groups',     label: 'Groups',           icon: Users },
  { to: '/avatar',     label: 'Avatar Builder',   icon: User },
  { to: '/analytics',  label: 'Analytics',        icon: BarChart3 },
]

export default function Sidebar() {
  const { sidebarOpen, setSidebarOpen, theme, toggleTheme, currentUser, logout } = useApp()
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
      {/* Mobile overlay */}
      {sidebarOpen && (
        <div
          className="fixed inset-0 bg-black/50 z-30 lg:hidden animate-fade-in"
          onClick={() => setSidebarOpen(false)}
        />
      )}

      <aside
        className={cn(
          'fixed top-0 left-0 h-screen w-[260px] z-40 flex flex-col',
          'bg-slate-900 dark:bg-slate-950 text-white',
          'transition-transform duration-300',
          sidebarOpen ? 'translate-x-0' : '-translate-x-full lg:translate-x-0',
        )}
      >
        {/* Logo */}
        <div className="flex items-center justify-between px-5 h-16 border-b border-white/10 flex-shrink-0">
          <div className="flex items-center gap-3">
            <div className="w-9 h-9 rounded-xl bg-gradient-brand flex items-center justify-center text-lg font-bold shadow-lg shadow-brand-900/40">
              C
            </div>
            <div>
              <div className="font-display font-bold text-base leading-tight">ClozéHive</div>
              <div className="text-[10px] text-slate-400 font-medium tracking-wide">AI Wardrobe</div>
            </div>
          </div>
          <button
            onClick={() => setSidebarOpen(false)}
            className="lg:hidden p-1.5 rounded-lg hover:bg-white/10 transition-colors"
          >
            <X size={18} />
          </button>
        </div>

        {/* Navigation */}
        <nav className="flex-1 overflow-y-auto py-4 px-3 space-y-0.5">
          <p className="text-[10px] font-semibold uppercase tracking-widest text-slate-500 px-3 mb-2">Menu</p>
          {NAV.map(({ to, label, icon: Icon }) => (
            <NavLink
              key={to}
              to={to}
              onClick={() => setSidebarOpen(false)}
              className={({ isActive }) => cn('nav-item', isActive && 'active')}
            >
              <Icon size={18} className="flex-shrink-0" />
              {label}
            </NavLink>
          ))}
        </nav>

        {/* Bottom */}
        <div className="px-3 pb-5 space-y-2 border-t border-white/10 pt-4 flex-shrink-0">
          {/* Theme toggle */}
          <button
            onClick={toggleTheme}
            className="w-full flex items-center gap-3 px-3 py-2.5 rounded-xl text-sm font-medium text-slate-400 hover:text-white hover:bg-white/10 transition-all"
          >
            {theme === 'dark' ? <Sun size={18} /> : <Moon size={18} />}
            {theme === 'dark' ? 'Light mode' : 'Dark mode'}
          </button>

          {/* User card */}
          {currentUser ? (
            <div className="rounded-xl bg-white/5 overflow-hidden">
              <NavLink
                to="/profile"
                onClick={() => setSidebarOpen(false)}
                className="flex items-center gap-3 px-3 py-2.5 hover:bg-white/5 transition-colors"
              >
                <div className="w-8 h-8 rounded-full bg-gradient-brand flex items-center justify-center text-xs font-bold flex-shrink-0">
                  {currentUser.avatar_url
                    ? <img src={currentUser.avatar_url} alt="" className="w-full h-full rounded-full object-cover" />
                    : initials
                  }
                </div>
                <div className="flex-1 min-w-0">
                  <div className="text-sm font-semibold truncate">{currentUser.display_name}</div>
                  <div className="text-[11px] text-slate-400 truncate">@{currentUser.username}</div>
                </div>
              </NavLink>
              <button
                onClick={handleLogout}
                className="w-full flex items-center gap-2.5 px-3 py-2 text-sm text-red-400 hover:text-red-300 hover:bg-white/5 transition-colors border-t border-white/5"
              >
                <LogOut size={14} /> Sign out
              </button>
            </div>
          ) : (
            <div className="flex items-center gap-3 px-3 py-2.5 rounded-xl bg-white/5">
              <div className="w-8 h-8 rounded-full bg-gradient-brand flex items-center justify-center text-xs font-bold">?</div>
              <div className="text-sm text-slate-400">Not signed in</div>
            </div>
          )}
        </div>
      </aside>
    </>
  )
}
