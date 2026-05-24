import { useState, useRef, useEffect, useCallback } from 'react'
import {
  Menu, Search, LogOut, User, Settings, UserPlus, UserCheck, Loader2, X,
  Moon, Sun, Sparkles, Heart, BarChart3, ShoppingBag, ChevronRight,
} from 'lucide-react'
import { useApp } from '@/store'
import { useColorScheme } from '@/hooks/useColorScheme'
import { useLocation, useNavigate } from 'react-router-dom'
import { socialApi } from '@/lib/api'
import type { SocialUser } from '@/types'
import { hideNonMvpUi } from '@/config/features'
import NotificationBell from '@/components/ui/NotificationBell'

const TITLES: Record<string, string> = {
  '/dashboard':        'Home',
  '/closet':           'My Closet',
  '/outfit-builder':   'Outfit Builder',
  '/upload':           'Add to Your Closet',
  '/fashion-analysis': 'Add to Your Closet',
  '/ai-stylist':       'FANI — AI Stylist',
  '/travel':           'Travel Planner',
  '/avatar':           'Avatar Builder',
  '/analytics':        'Style Insights',
  '/groups':           'Groups',
  '/profile':          'Profile',
  '/saved-outfits':    'Saved Outfits',
  '/purchase-gaps':    'Wardrobe Gaps',
}

/* ── Premium profile hover dropdown ────────────────────────────────────────── */

const WARDROBE_LINKS = [
  { to: '/saved-outfits',  label: 'Saved Outfits',    icon: Heart,      gradient: 'from-rose-500 to-pink-500',    desc: 'Your FANI-curated looks' },
  { to: '/analytics',      label: 'Closet Insights',  icon: BarChart3,  gradient: 'from-violet-500 to-indigo-500', desc: 'Wear analytics & trends' },
  { to: '/purchase-gaps',  label: 'Wardrobe Gaps',    icon: ShoppingBag,gradient: 'from-amber-500 to-orange-500', desc: 'What your closet is missing' },
]

function ProfileDropdown({ onNavigate }: { onNavigate: (to: string) => void }) {
  const { currentUser, logout } = useApp()
  const navigate = useNavigate()
  const { isDark, toggleColorScheme } = useColorScheme()

  const nameLabel = currentUser?.display_name || currentUser?.username || 'User'
  const initials = nameLabel !== 'User'
    ? nameLabel.split(' ').map((n: string) => n[0]).join('').slice(0, 2).toUpperCase()
    : 'U'

  const go = (to: string) => { navigate(to); onNavigate(to) }

  return (
    <div
      className="absolute right-0 top-full mt-3 w-[300px]
                 bg-white/[0.97] dark:bg-slate-900/[0.97]
                 backdrop-blur-2xl
                 rounded-3xl border border-white/60 dark:border-white/[0.09]
                 shadow-[0_24px_64px_-12px_rgba(79,70,229,0.22),0_8px_32px_-8px_rgba(0,0,0,0.18)]
                 dark:shadow-[0_24px_64px_-12px_rgba(79,70,229,0.35),0_8px_24px_-8px_rgba(0,0,0,0.55)]
                 overflow-hidden z-50
                 animate-slide-up origin-top-right"
    >
      {/* ── Header — gradient avatar banner ──────────────────────────────── */}
      <div className="relative px-5 pt-5 pb-4 bg-gradient-to-br from-indigo-600 via-violet-600 to-fuchsia-500 overflow-hidden">
        {/* Decorative blur orb */}
        <div className="pointer-events-none absolute -top-6 -right-6 w-28 h-28 rounded-full bg-white/10 blur-2xl" />

        <div className="relative flex items-center gap-3.5">
          {/* Avatar */}
          <div className="w-14 h-14 rounded-2xl bg-white/20 border-2 border-white/40
                          flex items-center justify-center text-lg font-bold text-white
                          flex-shrink-0 overflow-hidden shadow-lg">
            {currentUser?.avatar_url
              ? <img src={currentUser.avatar_url} alt="" className="w-full h-full object-cover" />
              : initials}
          </div>

          <div className="min-w-0 flex-1">
            <p className="text-base font-bold text-white leading-tight truncate">{nameLabel}</p>
            <p className="text-xs text-white/60 truncate mt-0.5">@{currentUser?.username ?? '—'}</p>
            {/* FANI member badge */}
            <div className="mt-2 inline-flex items-center gap-1 rounded-full bg-white/20 border border-white/30 px-2 py-0.5">
              <Sparkles size={9} className="text-amber-200" />
              <span className="text-[10px] font-semibold text-white/90 tracking-wide">FANI Member</span>
            </div>
          </div>
        </div>
      </div>

      {/* ── My Wardrobe section ───────────────────────────────────────────── */}
      <div className="px-3 pt-3 pb-1">
        <p className="text-[9px] font-bold uppercase tracking-[0.12em] text-slate-400 dark:text-white/30 px-2 mb-1.5">
          My Wardrobe
        </p>
        <div className="space-y-0.5">
          {WARDROBE_LINKS.map(({ to, label, icon: Icon, gradient, desc }) => (
            <button
              key={to}
              onClick={() => go(to)}
              className="w-full flex items-center gap-3 px-2.5 py-2.5 rounded-2xl text-left
                         hover:bg-slate-50 dark:hover:bg-white/[0.06]
                         transition-colors duration-150 group"
            >
              <div className={`w-9 h-9 rounded-xl bg-gradient-to-br ${gradient}
                              flex items-center justify-center flex-shrink-0
                              shadow-sm group-hover:shadow-md transition-shadow`}>
                <Icon size={15} className="text-white" />
              </div>
              <div className="flex-1 min-w-0">
                <p className="text-sm font-semibold text-slate-800 dark:text-white leading-tight">{label}</p>
                <p className="text-[11px] text-slate-400 dark:text-white/35 truncate">{desc}</p>
              </div>
              <ChevronRight size={13} className="text-slate-300 dark:text-white/20 flex-shrink-0 group-hover:text-slate-400 dark:group-hover:text-white/40 transition-colors" />
            </button>
          ))}
        </div>
      </div>

      {/* ── Divider ───────────────────────────────────────────────────────── */}
      <div className="mx-4 my-2 h-px bg-gradient-to-r from-transparent via-slate-200 dark:via-white/[0.07] to-transparent" />

      {/* ── Account section ───────────────────────────────────────────────── */}
      <div className="px-3 pb-1">
        <p className="text-[9px] font-bold uppercase tracking-[0.12em] text-slate-400 dark:text-white/30 px-2 mb-1.5">
          Account
        </p>
        <div className="space-y-0.5">
          <button
            onClick={() => go('/profile')}
            className="w-full flex items-center gap-3 px-2.5 py-2.5 rounded-2xl text-left
                       hover:bg-slate-50 dark:hover:bg-white/[0.06] transition-colors duration-150 group"
          >
            <div className="w-9 h-9 rounded-xl bg-gradient-to-br from-slate-600 to-slate-700
                            flex items-center justify-center flex-shrink-0 shadow-sm">
              <User size={15} className="text-white" />
            </div>
            <div className="flex-1 min-w-0">
              <p className="text-sm font-semibold text-slate-800 dark:text-white">View Profile</p>
              <p className="text-[11px] text-slate-400 dark:text-white/35">Style preferences & bio</p>
            </div>
            <ChevronRight size={13} className="text-slate-300 dark:text-white/20 flex-shrink-0 group-hover:text-slate-400 transition-colors" />
          </button>

          <button
            onClick={() => go('/profile?tab=settings')}
            className="w-full flex items-center gap-3 px-2.5 py-2.5 rounded-2xl text-left
                       hover:bg-slate-50 dark:hover:bg-white/[0.06] transition-colors duration-150 group"
          >
            <div className="w-9 h-9 rounded-xl bg-gradient-to-br from-slate-500 to-slate-600
                            flex items-center justify-center flex-shrink-0 shadow-sm">
              <Settings size={15} className="text-white" />
            </div>
            <div className="flex-1 min-w-0">
              <p className="text-sm font-semibold text-slate-800 dark:text-white">Settings</p>
              <p className="text-[11px] text-slate-400 dark:text-white/35">Privacy, notifications & more</p>
            </div>
            <ChevronRight size={13} className="text-slate-300 dark:text-white/20 flex-shrink-0 group-hover:text-slate-400 transition-colors" />
          </button>
        </div>
      </div>

      {/* ── Footer ────────────────────────────────────────────────────────── */}
      <div className="mx-4 my-2 h-px bg-gradient-to-r from-transparent via-slate-200 dark:via-white/[0.07] to-transparent" />

      <div className="px-3 pb-3 flex items-center gap-2">
        {/* Theme toggle */}
        <button
          onClick={toggleColorScheme}
          title={isDark ? 'Light mode' : 'Dark mode'}
          className="flex-1 flex items-center justify-center gap-1.5 py-2 rounded-xl text-xs font-medium
                     text-slate-500 dark:text-white/50
                     hover:bg-slate-50 dark:hover:bg-white/[0.06]
                     border border-slate-200 dark:border-white/[0.07]
                     transition-colors"
        >
          {isDark ? <Sun size={13} className="text-amber-400" /> : <Moon size={13} className="text-indigo-400" />}
          {isDark ? 'Light mode' : 'Dark mode'}
        </button>

        {/* Sign out */}
        <button
          onClick={() => { logout(); navigate('/login', { replace: true }); onNavigate('/login') }}
          className="flex-1 flex items-center justify-center gap-1.5 py-2 rounded-xl text-xs font-medium
                     text-red-500 dark:text-red-400
                     hover:bg-red-50 dark:hover:bg-red-500/10
                     border border-red-100 dark:border-red-500/20
                     transition-colors"
        >
          <LogOut size={13} /> Sign out
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
              No users match &ldquo;{query.trim()}&rdquo;
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
  const { isDark, toggleColorScheme } = useColorScheme()
  const location = useLocation()
  const [showMenu, setShowMenu] = useState(false)
  const hideTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  const title = TITLES[location.pathname] ?? 'ClozéHive'
  const navNameLabel = currentUser?.display_name || currentUser?.username || ''
  const initials = navNameLabel
    ? navNameLabel.split(' ').map((n: string) => n[0]).join('').slice(0, 2).toUpperCase()
    : 'U'

  const openMenu = useCallback(() => {
    if (hideTimerRef.current) clearTimeout(hideTimerRef.current)
    setShowMenu(true)
  }, [])

  const closeMenu = useCallback(() => {
    hideTimerRef.current = setTimeout(() => setShowMenu(false), 180)
  }, [])

  useEffect(() => () => { if (hideTimerRef.current) clearTimeout(hideTimerRef.current) }, [])

  return (
    <header className="h-16 flex items-center justify-between px-4 lg:px-6
                       bg-white/80 dark:bg-slate-950/80 backdrop-blur-xl
                       border-b border-cream-200 dark:border-white/[0.07]
                       sticky top-0 z-20">
      {/* Left */}
      <div className="flex items-center gap-3">
        <button
          onClick={() => setSidebarOpen(true)}
          className="lg:hidden p-2 min-h-[44px] min-w-[44px] rounded-xl
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
              {navNameLabel}
            </span>
          </span>
        )}

        {currentUser && !hideNonMvpUi() && (
          <UserSearch />
        )}

        <button
          onClick={() => window.dispatchEvent(new CustomEvent('ch:open-ai-chat'))}
          title="FANI — Fashion AI"
          aria-label="Open FANI chat"
          className="p-2 min-h-[44px] min-w-[44px] rounded-xl
                     text-slate-500 dark:text-white/50
                     hover:text-brand-600 dark:hover:text-brand-400
                     hover:bg-brand-50 dark:hover:bg-brand-900/20
                     transition-colors"
        >
          <Sparkles size={19} />
        </button>

        <button
          onClick={toggleColorScheme}
          title={isDark ? 'Switch to light mode' : 'Switch to dark mode'}
          aria-label={isDark ? 'Switch to light mode' : 'Switch to dark mode'}
          className="p-2 min-h-[44px] min-w-[44px] rounded-xl
                     text-slate-500 dark:text-white/50
                     hover:text-slate-800 dark:hover:text-white
                     hover:bg-slate-100 dark:hover:bg-white/[0.08]
                     transition-colors"
        >
          {isDark ? <Sun size={19} /> : <Moon size={19} />}
        </button>

        {/* Notification bell */}
        <NotificationBell />

        {/* Avatar — hover to open premium profile dropdown */}
        <div
          className="relative"
          onMouseEnter={openMenu}
          onMouseLeave={closeMenu}
        >
          <button
            aria-label="Open profile menu"
            className="min-h-[44px] min-w-[44px] rounded-full
                       bg-gradient-to-br from-indigo-500 to-violet-600
                       flex items-center justify-center text-sm font-bold text-white
                       ring-2 ring-transparent hover:ring-indigo-400/50
                       ring-offset-2 ring-offset-white dark:ring-offset-slate-950
                       transition-all duration-200 shadow-glow-sm hover:shadow-glow-md
                       overflow-hidden cursor-pointer"
          >
            {currentUser?.avatar_url
              ? <img src={currentUser.avatar_url} alt="" className="w-full h-full object-cover" />
              : initials}
          </button>

          {showMenu && (
            <ProfileDropdown onNavigate={() => setShowMenu(false)} />
          )}
        </div>
      </div>
    </header>
  )
}
