import { useState, useRef, useEffect } from 'react'
import { Menu, Bell, Search, LogOut, User, Settings, UserPlus, UserCheck, Loader2, X } from 'lucide-react'
import { useApp } from '@/store'
import { useLocation, useNavigate } from 'react-router-dom'
import { socialApi } from '@/lib/api'
import type { SocialUser } from '@/types'

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

  const initials = currentUser?.display_name
    ? currentUser.display_name.split(' ').map((n: string) => n[0]).join('').slice(0, 2).toUpperCase()
    : 'U'

  return (
    <div
      ref={ref}
      className="absolute right-0 top-full mt-2 w-56 bg-white dark:bg-slate-800 rounded-2xl shadow-card-hover border border-cream-300 dark:border-slate-700 overflow-hidden z-50 animate-slide-up"
    >
      {/* User info */}
      <div className="px-4 py-3 border-b border-cream-200 dark:border-slate-700">
        <p className="text-sm font-semibold text-slate-800 dark:text-slate-100 truncate">
          {currentUser?.display_name ?? 'User'}
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

function UserSearch() {
  const navigate = useNavigate()
  const wrapRef = useRef<HTMLDivElement>(null)
  const [query, setQuery] = useState('')
  const [results, setResults] = useState<SocialUser[]>([])
  const [loading, setLoading] = useState(false)
  const [open, setOpen] = useState(false)
  const [pendingFollow, setPendingFollow] = useState<string | null>(null)

  useEffect(() => {
    const q = query.trim()
    if (!q) { setResults([]); return }
    setLoading(true)
    const t = setTimeout(async () => {
      try { setResults(await socialApi.searchUsers(q, 8)) }
      catch { setResults([]) }
      finally { setLoading(false) }
    }, 300)
    return () => clearTimeout(t)
  }, [query])

  useEffect(() => {
    function handler(e: MouseEvent) {
      if (wrapRef.current && !wrapRef.current.contains(e.target as Node)) setOpen(false)
    }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [])

  const toggleFollow = async (u: SocialUser) => {
    setPendingFollow(u.id)
    try {
      if (u.is_following) await socialApi.unfollow(u.id)
      else await socialApi.follow(u.id)
      setResults(rs => rs.map(r => r.id === u.id ? { ...r, is_following: !u.is_following } : r))
    } catch {
      /* keep list as-is on failure */
    } finally {
      setPendingFollow(null)
    }
  }

  const goToGroupInvite = (u: SocialUser) => {
    navigate(`/groups?invite=${encodeURIComponent(u.username)}`)
    setOpen(false)
    setQuery('')
  }

  return (
    <div ref={wrapRef} className="relative hidden sm:block">
      <div className="flex items-center gap-2 px-3 py-2 rounded-xl bg-cream-100 dark:bg-slate-800 border border-cream-300 dark:border-slate-700 focus-within:border-brand-400 transition-colors w-56">
        <Search size={14} className="text-slate-400 flex-shrink-0" />
        <input
          value={query}
          onChange={e => { setQuery(e.target.value); setOpen(true) }}
          onFocus={() => setOpen(true)}
          placeholder="Search users by @username…"
          className="flex-1 bg-transparent text-sm text-slate-700 dark:text-slate-200 placeholder-slate-400 focus:outline-none"
        />
        {query && (
          <button
            onClick={() => { setQuery(''); setResults([]) }}
            className="text-slate-400 hover:text-slate-600 dark:hover:text-slate-300 transition-colors"
            aria-label="Clear search"
          >
            <X size={14} />
          </button>
        )}
      </div>

      {open && (query.trim() || loading) && (
        <div className="absolute right-0 top-full mt-2 w-80 max-h-96 overflow-y-auto bg-white dark:bg-slate-800 rounded-2xl shadow-card-hover border border-cream-300 dark:border-slate-700 z-50 animate-slide-up">
          {loading && (
            <div className="flex items-center justify-center gap-2 py-6 text-xs text-slate-400">
              <Loader2 size={14} className="animate-spin" /> Searching…
            </div>
          )}

          {!loading && results.length === 0 && query.trim() && (
            <div className="py-6 text-center text-xs text-slate-400">
              No users match “{query.trim()}”
            </div>
          )}

          {!loading && results.map(u => {
            const displayName = u.display_name || u.username
            const initials = displayName.split(' ').map((n: string) => n[0]).join('').slice(0, 2).toUpperCase()
            return (
              <div key={u.id} className="flex items-center gap-3 px-3 py-2.5 hover:bg-cream-50 dark:hover:bg-slate-700/60 transition-colors">
                <div className="w-9 h-9 rounded-full bg-gradient-brand flex items-center justify-center text-xs font-bold text-white flex-shrink-0 overflow-hidden">
                  {u.avatar_url
                    ? <img src={u.avatar_url} alt="" className="w-full h-full object-cover" />
                    : initials}
                </div>
                <button
                  onClick={() => goToGroupInvite(u)}
                  className="flex-1 text-left min-w-0"
                  title="Invite to a group"
                >
                  <p className="text-sm font-semibold text-slate-800 dark:text-slate-100 truncate">{displayName}</p>
                  <p className="text-xs text-slate-400 truncate">@{u.username}</p>
                </button>
                <button
                  onClick={() => toggleFollow(u)}
                  disabled={pendingFollow === u.id}
                  className={`flex items-center gap-1 px-2.5 py-1.5 rounded-lg text-xs font-semibold transition-colors flex-shrink-0 ${
                    u.is_following
                      ? 'bg-cream-100 dark:bg-slate-700 text-slate-600 dark:text-slate-300 hover:bg-red-50 hover:text-red-600 dark:hover:bg-red-900/20'
                      : 'bg-brand-500 text-white hover:bg-brand-600'
                  } disabled:opacity-50`}
                >
                  {pendingFollow === u.id
                    ? <Loader2 size={12} className="animate-spin" />
                    : u.is_following
                      ? <><UserCheck size={12} /> Following</>
                      : <><UserPlus size={12} /> Follow</>}
                </button>
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}

export default function Navbar() {
  const { setSidebarOpen, currentUser } = useApp()
  const location = useLocation()
  const [showMenu, setShowMenu] = useState(false)

  const title = TITLES[location.pathname] ?? 'ClozéHive'
  const initials = currentUser?.display_name
    ? currentUser.display_name.split(' ').map((n: string) => n[0]).join('').slice(0, 2).toUpperCase()
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
            Welcome, <span className="font-semibold text-slate-700 dark:text-slate-200">{currentUser.display_name}</span> 👋
          </span>
        )}

        {/* User search */}
        <UserSearch />

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
