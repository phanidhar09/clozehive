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

/* ── User dropdown ─────────────────────────────────────────────────────────── */
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
      className="absolute right-0 top-full mt-2 w-56
                 bg-white/95 dark:bg-slate-900/95
                 backdrop-blur-xl
                 rounded-2xl border border-cream-200 dark:border-white/[0.10]
                 shadow-card-hover dark:shadow-glass-card
                 overflow-hidden z-50 animate-slide-up"
    >
      {/* User info */}
      <div className="px-4 py-3 border-b border-cream-200 dark:border-white/[0.07]">
        <div className="flex items-center gap-2.5 mb-1">
          <div className="w-7 h-7 rounded-full bg-gradient-to-br from-indigo-500 to-violet-600
                          flex items-center justify-center text-[10px] font-bold text-white
                          flex-shrink-0 overflow-hidden">
            {currentUser?.avatar_url
              ? <img src={currentUser.avatar_url} alt="" className="w-full h-full object-cover" />
              : initials}
          </div>
          <div className="min-w-0">
            <p className="text-sm font-semibold text-slate-800 dark:text-white truncate">
              {currentUser?.display_name ?? 'User'}
            </p>
            <p className="text-[11px] text-slate-400 dark:text-white/40 truncate">
              @{currentUser?.username ?? '—'}
            </p>
          </div>
        </div>
      </div>

      <div className="p-1.5 space-y-0.5">
        <button
          onClick={() => { navigate('/profile'); onClose() }}
          className="w-full flex items-center gap-2.5 px-3 py-2 rounded-xl text-sm
                     text-slate-700 dark:text-white/80
                     hover:bg-slate-50 dark:hover:bg-white/[0.07] transition-colors"
        >
          <User size={14} /> View profile
        </button>
        <button
          onClick={() => { navigate('/profile?tab=settings'); onClose() }}
          className="w-full flex items-center gap-2.5 px-3 py-2 rounded-xl text-sm
                     text-slate-700 dark:text-white/80
                     hover:bg-slate-50 dark:hover:bg-white/[0.07] transition-colors"
        >
          <Settings size={14} /> Settings
        </button>
        <div className="h-px bg-cream-200 dark:bg-white/[0.06] mx-2 my-1" />
        <button
          onClick={() => { logout(); navigate('/login', { replace: true }); onClose() }}
          className="w-full flex items-center gap-2.5 px-3 py-2 rounded-xl text-sm
                     text-red-500 dark:text-red-400
                     hover:bg-red-50 dark:hover:bg-red-500/10 transition-colors"
        >
          <LogOut size={14} /> Sign out
        </button>
      </div>
    </div>
  )
}

/* ── User search ───────────────────────────────────────────────────────────── */
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
    } catch { /* keep as-is */ }
    finally { setPendingFollow(null) }
  }

  const goToGroupInvite = (u: SocialUser) => {
    navigate(`/groups?invite=${encodeURIComponent(u.username)}`)
    setOpen(false)
    setQuery('')
  }

  return (
    <div ref={wrapRef} className="relative hidden sm:block">
      {/* Input */}
      <div className="flex items-center gap-2 px-3 py-2 rounded-xl w-52
                      bg-slate-100 dark:bg-white/[0.06]
                      border border-cream-300 dark:border-white/[0.08]
                      focus-within:border-indigo-400 dark:focus-within:border-indigo-500/60
                      focus-within:bg-white dark:focus-within:bg-white/[0.09]
                      transition-all duration-200">
        <Search size={13} className="text-slate-400 dark:text-white/30 flex-shrink-0" />
        <input
          value={query}
          onChange={e => { setQuery(e.target.value); setOpen(true) }}
          onFocus={() => setOpen(true)}
          placeholder="Search users…"
          className="flex-1 bg-transparent text-sm
                     text-slate-700 dark:text-white
                     placeholder-slate-400 dark:placeholder-white/30
                     focus:outline-none"
        />
        {query && (
          <button
            onClick={() => { setQuery(''); setResults([]) }}
            className="text-slate-400 hover:text-slate-600 dark:hover:text-white/60 transition-colors"
          >
            <X size={13} />
          </button>
        )}
      </div>

      {/* Results dropdown */}
      {open && (query.trim() || loading) && (
        <div className="absolute right-0 top-full mt-2 w-80 max-h-96 overflow-y-auto
                        bg-white/95 dark:bg-slate-900/95 backdrop-blur-xl
                        rounded-2xl border border-cream-200 dark:border-white/[0.10]
                        shadow-card-hover dark:shadow-glass-card
                        z-50 animate-slide-up">
          {loading && (
            <div className="flex items-center justify-center gap-2 py-6 text-xs text-slate-400 dark:text-white/40">
              <Loader2 size={13} className="animate-spin" /> Searching…
            </div>
          )}
          {!loading && results.length === 0 && query.trim() && (
            <div className="py-6 text-center text-xs text-slate-400 dark:text-white/40">
              No users match "{query.trim()}"
            </div>
          )}
          {!loading && results.map(u => {
            const displayName = u.display_name || u.username
            const initials = displayName.split(' ').map((n: string) => n[0]).join('').slice(0, 2).toUpperCase()
            return (
              <div key={u.id} className="flex items-center gap-3 px-3 py-2.5
                                         hover:bg-slate-50 dark:hover:bg-white/[0.05]
                                         transition-colors">
                <div className="w-9 h-9 rounded-full bg-gradient-to-br from-indigo-500 to-violet-600
                                flex items-center justify-center text-xs font-bold text-white
                                flex-shrink-0 overflow-hidden">
                  {u.avatar_url ? <img src={u.avatar_url} alt="" className="w-full h-full object-cover" /> : initials}
                </div>
                <button onClick={() => goToGroupInvite(u)} className="flex-1 text-left min-w-0">
                  <p className="text-sm font-semibold text-slate-800 dark:text-white truncate">{displayName}</p>
                  <p className="text-xs text-slate-400 dark:text-white/40 truncate">@{u.username}</p>
                </button>
                <button
                  onClick={() => toggleFollow(u)}
                  disabled={pendingFollow === u.id}
                  className={`flex items-center gap-1 px-2.5 py-1.5 rounded-lg text-xs font-semibold
                              transition-all flex-shrink-0 ${
                    u.is_following
                      ? 'bg-slate-100 dark:bg-white/[0.08] text-slate-600 dark:text-white/60 hover:bg-red-50 hover:text-red-500 dark:hover:bg-red-500/15'
                      : 'bg-gradient-to-r from-indigo-500 to-violet-600 text-white shadow-glow-sm hover:shadow-glow-md'
                  } disabled:opacity-50`}
                >
                  {pendingFollow === u.id
                    ? <Loader2 size={11} className="animate-spin" />
                    : u.is_following
                      ? <><UserCheck size={11} /> Following</>
                      : <><UserPlus size={11} /> Follow</>}
                </button>
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}

/* ── Navbar ────────────────────────────────────────────────────────────────── */
export default function Navbar() {
  const { setSidebarOpen, currentUser } = useApp()
  const location = useLocation()
  const [showMenu, setShowMenu] = useState(false)

  const title = TITLES[location.pathname] ?? 'ClozéHive'
  const initials = currentUser?.display_name
    ? currentUser.display_name.split(' ').map((n: string) => n[0]).join('').slice(0, 2).toUpperCase()
    : 'U'

  return (
    <header className="h-16 flex items-center justify-between px-4 lg:px-6
                       bg-white/80 dark:bg-slate-950/80 backdrop-blur-xl
                       border-b border-cream-200 dark:border-white/[0.07]
                       sticky top-0 z-20">
      {/* Left */}
      <div className="flex items-center gap-3">
        <button
          onClick={() => setSidebarOpen(true)}
          className="lg:hidden p-2 rounded-xl
                     text-slate-500 dark:text-white/50
                     hover:text-slate-800 dark:hover:text-white
                     hover:bg-slate-100 dark:hover:bg-white/[0.08]
                     transition-colors"
        >
          <Menu size={20} />
        </button>
        <h1 className="font-display font-semibold text-lg text-slate-800 dark:text-white">
          {title}
        </h1>
      </div>

      {/* Right */}
      <div className="flex items-center gap-2">
        {currentUser && (
          <span className="hidden md:block text-sm text-slate-400 dark:text-white/40 mr-1">
            Welcome,{' '}
            <span className="font-semibold text-slate-700 dark:text-white/80">
              {currentUser.display_name}
            </span>
          </span>
        )}

        <UserSearch />

        {/* Notification bell */}
        <button className="relative p-2 rounded-xl
                           text-slate-500 dark:text-white/50
                           hover:text-slate-800 dark:hover:text-white
                           hover:bg-slate-100 dark:hover:bg-white/[0.08]
                           transition-colors">
          <Bell size={19} />
          <span className="absolute top-1.5 right-1.5 w-2 h-2 rounded-full
                           bg-indigo-500 ring-2 ring-white dark:ring-slate-950" />
        </button>

        {/* Avatar */}
        <div className="relative">
          <button
            onClick={() => setShowMenu(v => !v)}
            className="w-9 h-9 rounded-full
                       bg-gradient-to-br from-indigo-500 to-violet-600
                       flex items-center justify-center text-sm font-bold text-white
                       ring-2 ring-transparent hover:ring-indigo-400/40
                       ring-offset-1 ring-offset-white dark:ring-offset-slate-950
                       transition-all duration-200 shadow-glow-sm hover:shadow-glow-md
                       overflow-hidden"
          >
            {currentUser?.avatar_url
              ? <img src={currentUser.avatar_url} alt="" className="w-full h-full object-cover" />
              : initials}
          </button>
          {showMenu && <UserMenu onClose={() => setShowMenu(false)} />}
        </div>
      </div>
    </header>
  )
}
