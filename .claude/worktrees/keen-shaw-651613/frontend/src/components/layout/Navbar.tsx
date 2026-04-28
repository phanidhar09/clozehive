import { useState, useRef, useEffect } from 'react'
import { Menu, Bell, Search, LogOut, User, Settings } from 'lucide-react'
import { useApp } from '@/store'
import { useLocation, useNavigate, Link } from 'react-router-dom'

const TITLES: Record<string, string> = {
  '/dashboard':  'Dashboard',
  '/closet':     'My Closet',
  '/upload':     'Upload Item',
  '/ai-stylist': 'AI Stylist',
  '/travel':     'Travel Planner',
  '/avatar':     'Avatar Builder',
  '/analytics':  'Analytics',
  '/groups':     'Groups',
  '/profile':    'Profile',
}

function UserMenu({ onClose }: { onClose: () => void }) {
  const { currentUser, logout } = useApp()
  const navigate = useNavigate()
  const ref = useRef<HTMLDivElement>(null)

  useEffect(() => {
    function handler(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) onClose()
    }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [onClose])

  const initials = currentUser?.name
    ? currentUser.name.split(' ').map(n => n[0]).join('').slice(0, 2).toUpperCase()
    : 'U'

  return (
    <div
      ref={ref}
      className="absolute right-0 top-full mt-2 w-56 bg-white dark:bg-slate-800 rounded-2xl shadow-card-hover border border-cream-300 dark:border-slate-700 overflow-hidden z-50 animate-slide-up"
    >
      {/* User info */}
      <div className="px-4 py-3 border-b border-cream-200 dark:border-slate-700">
        <p className="text-sm font-semibold text-slate-800 dark:text-slate-100 truncate">
          {currentUser?.name ?? 'User'}
        </p>
        <p className="text-xs text-slate-400 truncate">
          @{currentUser?.username ?? '—'}
        </p>
      </div>

      {/* Menu items */}
      <div className="p-1.5 space-y-0.5">
        <button
          onClick={() => { navigate('/profile'); onClose() }}
          className="w-full flex items-center gap-2.5 px-3 py-2 rounded-xl text-sm text-slate-700 dark:text-slate-300 hover:bg-cream-50 dark:hover:bg-slate-700 transition-colors"
        >
          <User size={15} /> View profile
        </button>
        <button
          onClick={() => { navigate('/profile?tab=settings'); onClose() }}
          className="w-full flex items-center gap-2.5 px-3 py-2 rounded-xl text-sm text-slate-700 dark:text-slate-300 hover:bg-cream-50 dark:hover:bg-slate-700 transition-colors"
        >
          <Settings size={15} /> Settings
        </button>
        <div className="h-px bg-cream-200 dark:bg-slate-700 mx-2 my-1" />
        <button
          onClick={() => { logout(); navigate('/login', { replace: true }); onClose() }}
          className="w-full flex items-center gap-2.5 px-3 py-2 rounded-xl text-sm text-red-600 dark:text-red-400 hover:bg-red-50 dark:hover:bg-red-900/20 transition-colors"
        >
          <LogOut size={15} /> Sign out
        </button>
      </div>
    </div>
  )
}

export default function Navbar() {
  const { setSidebarOpen, currentUser } = useApp()
  const location = useLocation()
  const [showMenu, setShowMenu] = useState(false)

  const title = TITLES[location.pathname] ?? 'ClozéHive'
  const initials = currentUser?.name
    ? currentUser.name.split(' ').map(n => n[0]).join('').slice(0, 2).toUpperCase()
    : 'U'

  return (
    <header className="h-16 flex items-center justify-between px-4 lg:px-6 bg-white dark:bg-slate-900 border-b border-cream-300 dark:border-slate-700 sticky top-0 z-20">
      {/* Left */}
      <div className="flex items-center gap-3">
        <button
          onClick={() => setSidebarOpen(true)}
          className="lg:hidden p-2 rounded-xl hover:bg-cream-100 dark:hover:bg-slate-800 transition-colors"
        >
          <Menu size={20} className="text-slate-600 dark:text-slate-300" />
        </button>
        <h1 className="font-display font-semibold text-lg text-slate-800 dark:text-slate-100">{title}</h1>
      </div>

      {/* Right */}
      <div className="flex items-center gap-2">
        {/* Welcome text — hidden on very small screens */}
        {currentUser && (
          <span className="hidden md:block text-sm text-slate-500 dark:text-slate-400 mr-1">
            Welcome, <span className="font-semibold text-slate-700 dark:text-slate-200">{currentUser.name.split(' ')[0]}</span> 👋
          </span>
        )}

        {/* Search */}
        <Link
          to="/closet"
          className="hidden sm:flex items-center gap-2 px-3 py-2 rounded-xl bg-cream-100 dark:bg-slate-800 border border-cream-300 dark:border-slate-700 text-sm text-slate-400 w-44 cursor-pointer hover:border-brand-400 transition-colors"
        >
          <Search size={14} />
          <span>Search…</span>
        </Link>

        {/* Notifications */}
        <button className="relative p-2 rounded-xl hover:bg-cream-100 dark:hover:bg-slate-800 transition-colors">
          <Bell size={20} className="text-slate-500 dark:text-slate-400" />
          <span className="absolute top-1.5 right-1.5 w-2 h-2 rounded-full bg-brand-500 ring-2 ring-white dark:ring-slate-900" />
        </button>

        {/* User avatar + dropdown */}
        <div className="relative">
          <button
            onClick={() => setShowMenu(v => !v)}
            className="w-9 h-9 rounded-full bg-gradient-brand flex items-center justify-center text-sm font-bold text-white cursor-pointer hover:opacity-90 transition-opacity ring-2 ring-transparent hover:ring-brand-300 ring-offset-1"
          >
            {currentUser?.avatar_url
              ? <img src={currentUser.avatar_url} alt="" className="w-full h-full rounded-full object-cover" />
              : initials
            }
          </button>
          {showMenu && <UserMenu onClose={() => setShowMenu(false)} />}
        </div>
      </div>
    </header>
  )
}
