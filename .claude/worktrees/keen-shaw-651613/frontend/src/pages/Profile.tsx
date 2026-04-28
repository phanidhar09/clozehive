import { useState, useEffect, useCallback } from 'react'
import { useSearchParams, useNavigate } from 'react-router-dom'
import {
  Search, Users, UserCheck, Loader2, Edit3, Check, X,
  RefreshCw, Shirt
} from 'lucide-react'
import { useApp } from '@/store'
import {
  getUserProfile, searchUsers, updateMe,
  getFollowers, getFollowing
} from '@/lib/api'
import type { SocialUser } from '@/types'
import UserCard from '@/components/ui/UserCard'

type Tab = 'closet' | 'followers' | 'following' | 'discover' | 'settings'

export default function Profile() {
  const { currentUser, updateCurrentUser } = useApp()
  const [searchParams] = useSearchParams()
  const navigate = useNavigate()

  const [activeTab, setActiveTab] = useState<Tab>(
    (searchParams.get('tab') as Tab) || 'closet'
  )

  // ── Profile data ───────────────────────────────────────────
  const [profile, setProfile] = useState<SocialUser | null>(null)
  const [profileLoading, setProfileLoading] = useState(true)

  // ── Social lists ───────────────────────────────────────────
  const [followers, setFollowers] = useState<SocialUser[]>([])
  const [following, setFollowing] = useState<SocialUser[]>([])
  const [discover, setDiscover] = useState<SocialUser[]>([])
  const [socialLoading, setSocialLoading] = useState(false)
  const [searchQuery, setSearchQuery] = useState('')

  // ── Edit bio ───────────────────────────────────────────────
  const [editing, setEditing] = useState(false)
  const [editName, setEditName] = useState(currentUser?.name ?? '')
  const [editBio, setEditBio] = useState(currentUser?.bio ?? '')
  const [saveLoading, setSaveLoading] = useState(false)

  // ── Load profile ───────────────────────────────────────────
  useEffect(() => {
    if (!currentUser) return
    setProfileLoading(true)
    getUserProfile(currentUser.id)
      .then(setProfile)
      .catch(console.error)
      .finally(() => setProfileLoading(false))
  }, [currentUser])

  // ── Load social list based on tab ─────────────────────────
  const loadSocial = useCallback(async () => {
    if (!currentUser) return
    setSocialLoading(true)
    try {
      if (activeTab === 'followers') {
        setFollowers(await getFollowers(currentUser.id))
      } else if (activeTab === 'following') {
        setFollowing(await getFollowing(currentUser.id))
      } else if (activeTab === 'discover') {
        setDiscover(await searchUsers())
      }
    } catch (e) {
      console.error(e)
    } finally {
      setSocialLoading(false)
    }
  }, [activeTab, currentUser])

  useEffect(() => { loadSocial() }, [loadSocial])

  // ── Search ─────────────────────────────────────────────────
  const [searchResults, setSearchResults] = useState<SocialUser[]>([])
  const [searchLoading, setSearchLoading] = useState(false)

  useEffect(() => {
    if (!searchQuery.trim()) { setSearchResults([]); return }
    const timer = setTimeout(async () => {
      setSearchLoading(true)
      try { setSearchResults(await searchUsers(searchQuery)) }
      catch { /* ignore */ }
      finally { setSearchLoading(false) }
    }, 400)
    return () => clearTimeout(timer)
  }, [searchQuery])

  // ── Save profile edits ─────────────────────────────────────
  const saveProfile = async () => {
    setSaveLoading(true)
    try {
      const updated = await updateMe({ name: editName.trim(), bio: editBio.trim() || undefined })
      updateCurrentUser({ name: updated.name, bio: updated.bio })
      setProfile(p => p ? { ...p, name: updated.name, bio: updated.bio ?? null } : p)
      setEditing(false)
    } catch (err) {
      console.error('Profile update failed:', err)
    } finally {
      setSaveLoading(false)
    }
  }

  // ── Helpers ────────────────────────────────────────────────
  const initials = currentUser?.name
    ? currentUser.name.split(' ').map(n => n[0]).join('').slice(0, 2).toUpperCase()
    : 'U'

  const TABS: { id: Tab; label: string; icon?: React.ReactNode; count?: number }[] = [
    { id: 'closet',    label: 'Wardrobe',  icon: <Shirt size={14} />,      count: profile?.item_count },
    { id: 'followers', label: 'Followers', icon: <Users size={14} />,      count: profile?.follower_count },
    { id: 'following', label: 'Following', icon: <UserCheck size={14} />,  count: profile?.following_count },
    { id: 'discover',  label: 'Discover',  icon: <Search size={14} /> },
    { id: 'settings',  label: 'Settings',  icon: <Edit3 size={14} /> },
  ]

  const currentList =
    activeTab === 'followers' ? followers
    : activeTab === 'following' ? following
    : activeTab === 'discover' ? (searchQuery ? searchResults : discover)
    : []

  const listLoading = socialLoading || (activeTab === 'discover' && searchLoading)

  return (
    <div className="max-w-3xl space-y-6 animate-slide-up">

      {/* ── Profile header card ────────────────────────────── */}
      <div className="card overflow-hidden">
        {/* Banner */}
        <div className="h-28 bg-gradient-to-r from-brand-700 via-brand-600 to-violet-500 relative">
          <div className="absolute inset-0 bg-[url('https://images.unsplash.com/photo-1558618666-fcd25c85cd64?w=800&q=40')] bg-cover bg-center opacity-15" />
        </div>

        <div className="px-5 pb-5">
          {/* Avatar */}
          <div className="-mt-10 mb-3 flex items-end justify-between">
            <div className="w-20 h-20 rounded-full ring-4 ring-white dark:ring-slate-800 bg-gradient-brand flex items-center justify-center text-2xl font-bold text-white shadow-lg">
              {currentUser?.avatar_url
                ? <img src={currentUser.avatar_url} alt="" className="w-full h-full rounded-full object-cover" />
                : initials
              }
            </div>
            {!editing ? (
              <button
                onClick={() => { setEditing(true); setActiveTab('settings') }}
                className="btn-ghost text-xs gap-1.5"
              >
                <Edit3 size={13} /> Edit profile
              </button>
            ) : (
              <div className="flex gap-2">
                <button onClick={() => setEditing(false)} className="btn-ghost text-xs gap-1">
                  <X size={13} /> Cancel
                </button>
                <button
                  onClick={saveProfile}
                  disabled={saveLoading}
                  className="btn-primary text-xs gap-1"
                >
                  {saveLoading ? <Loader2 size={13} className="animate-spin" /> : <Check size={13} />}
                  Save
                </button>
              </div>
            )}
          </div>

          {/* Name / username */}
          <div className="space-y-0.5 mb-3">
            <h2 className="font-display font-bold text-xl text-slate-900 dark:text-white">
              {currentUser?.name}
            </h2>
            <p className="text-sm text-slate-400">@{currentUser?.username}</p>
            <p className="text-sm text-slate-500 dark:text-slate-400 mt-1">
              {currentUser?.bio || <span className="italic">No bio yet</span>}
            </p>
          </div>

          {/* Stats row */}
          {profileLoading ? (
            <div className="h-14 bg-cream-100 dark:bg-slate-800 rounded-xl animate-pulse" />
          ) : (
            <div className="flex gap-6">
              {[
                { label: 'Items', value: profile?.item_count ?? 0 },
                { label: 'Followers', value: profile?.follower_count ?? 0, tab: 'followers' as Tab },
                { label: 'Following', value: profile?.following_count ?? 0, tab: 'following' as Tab },
              ].map(s => (
                <button
                  key={s.label}
                  onClick={() => s.tab && setActiveTab(s.tab)}
                  className={`text-center ${s.tab ? 'hover:opacity-80 transition-opacity cursor-pointer' : ''}`}
                >
                  <div className="font-bold text-lg text-slate-900 dark:text-white">{s.value}</div>
                  <div className="text-xs text-slate-400">{s.label}</div>
                </button>
              ))}
            </div>
          )}
        </div>
      </div>

      {/* ── Tabs ──────────────────────────────────────────────── */}
      <div className="flex gap-1 bg-cream-100 dark:bg-slate-800 p-1 rounded-xl overflow-x-auto">
        {TABS.map(t => (
          <button
            key={t.id}
            onClick={() => setActiveTab(t.id)}
            className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm font-medium transition-all whitespace-nowrap flex-shrink-0 ${
              activeTab === t.id
                ? 'bg-white dark:bg-slate-700 text-slate-800 dark:text-white shadow-sm'
                : 'text-slate-500 hover:text-slate-700 dark:hover:text-slate-300'
            }`}
          >
            {t.icon}
            {t.label}
            {t.count !== undefined && (
              <span className={`text-[11px] px-1.5 py-0.5 rounded-full font-semibold ${
                activeTab === t.id ? 'bg-brand-100 dark:bg-brand-900/40 text-brand-600 dark:text-brand-300' : 'bg-slate-200 dark:bg-slate-700 text-slate-500'
              }`}>
                {t.count}
              </span>
            )}
          </button>
        ))}
      </div>

      {/* ── Tab content ───────────────────────────────────────── */}

      {/* Closet preview */}
      {activeTab === 'closet' && (
        <div className="animate-fade-in">
          {!profile?.closet_preview?.length ? (
            <div className="card p-10 text-center text-slate-400">
              <Shirt size={32} className="mx-auto mb-3 opacity-30" />
              <p className="font-semibold text-slate-500">No items in wardrobe yet</p>
              <button onClick={() => navigate('/upload')} className="btn-primary text-sm mt-4">
                Upload your first item
              </button>
            </div>
          ) : (
            <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
              {profile.closet_preview.map((item, i) => (
                <div key={item.id ?? i} className="card overflow-hidden group cursor-pointer" onClick={() => navigate('/closet')}>
                  <div className="aspect-square bg-cream-100 dark:bg-slate-800 relative overflow-hidden">
                    {item.image_url
                      ? <img src={item.image_url} alt={item.name} className="w-full h-full object-cover group-hover:scale-105 transition-transform duration-300" />
                      : <div className="w-full h-full flex items-center justify-center text-4xl">👕</div>
                    }
                  </div>
                  <div className="p-2">
                    <p className="text-xs font-semibold text-slate-700 dark:text-slate-200 truncate">{item.name}</p>
                    <p className="text-[11px] text-slate-400 capitalize">{item.category}</p>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* Followers / Following / Discover */}
      {(['followers', 'following', 'discover'] as Tab[]).includes(activeTab) && (
        <div className="space-y-3 animate-fade-in">
          {/* Discover search */}
          {activeTab === 'discover' && (
            <div className="relative">
              <Search size={16} className="absolute left-3.5 top-1/2 -translate-y-1/2 text-slate-400" />
              <input
                type="text"
                className="input w-full pl-9"
                placeholder="Search by name or username…"
                value={searchQuery}
                onChange={e => setSearchQuery(e.target.value)}
                autoFocus
              />
            </div>
          )}

          {/* Refresh */}
          <div className="flex items-center justify-between">
            <p className="text-sm text-slate-500 dark:text-slate-400">
              {listLoading ? 'Loading…'
                : activeTab === 'discover' && searchQuery ? `${searchResults.length} result${searchResults.length !== 1 ? 's' : ''}`
                : `${currentList.length} ${activeTab}`
              }
            </p>
            {activeTab !== 'discover' && (
              <button onClick={loadSocial} className="btn-ghost text-xs gap-1">
                <RefreshCw size={12} className={listLoading ? 'animate-spin' : ''} /> Refresh
              </button>
            )}
          </div>

          {listLoading ? (
            <div className="space-y-2">
              {[...Array(4)].map((_, i) => (
                <div key={i} className="card p-3 flex items-center gap-3 animate-pulse">
                  <div className="w-9 h-9 rounded-full bg-cream-200 dark:bg-slate-700 flex-shrink-0" />
                  <div className="flex-1 space-y-1.5">
                    <div className="h-3 bg-cream-200 dark:bg-slate-700 rounded w-2/5" />
                    <div className="h-2.5 bg-cream-100 dark:bg-slate-700/50 rounded w-1/4" />
                  </div>
                </div>
              ))}
            </div>
          ) : currentList.length === 0 ? (
            <div className="card p-10 text-center text-slate-400">
              <Users size={32} className="mx-auto mb-3 opacity-30" />
              <p className="font-semibold text-slate-500 mb-1">
                {activeTab === 'discover' && searchQuery ? 'No users found' :
                 activeTab === 'followers' ? 'No followers yet' :
                 activeTab === 'following' ? 'Not following anyone yet' :
                 'No users to discover'}
              </p>
              {activeTab === 'discover' && !searchQuery && (
                <p className="text-sm">Search for users to follow</p>
              )}
            </div>
          ) : (
            <div className="card divide-y divide-cream-200 dark:divide-slate-700/50">
              {currentList.map(u => (
                <UserCard
                  key={u.id}
                  user={u}
                  compact
                  onClick={() => navigate(`/profile?uid=${u.id}`)}
                  onFollowChange={(userId, isFollowing, count) => {
                    const update = (list: SocialUser[]) =>
                      list.map(item =>
                        item.id === userId
                          ? { ...item, is_following: isFollowing, follower_count: count }
                          : item,
                      )
                    setFollowers(update)
                    setFollowing(update)
                    setDiscover(update)
                    setSearchResults(update)
                    if (profile) setProfile(p => p ? { ...p, following_count: p.following_count + (isFollowing ? 1 : -1) } : p)
                  }}
                />
              ))}
            </div>
          )}
        </div>
      )}

      {/* Settings / Edit Profile */}
      {activeTab === 'settings' && (
        <div className="card p-6 space-y-5 animate-fade-in">
          <h3 className="font-display font-semibold text-base text-slate-800 dark:text-slate-100">Edit Profile</h3>
          <div className="space-y-4">
            <div className="space-y-1.5">
              <label className="label text-slate-700 dark:text-slate-300">Display name</label>
              <input
                type="text"
                className="input w-full"
                value={editName}
                onChange={e => setEditName(e.target.value)}
                placeholder="Your full name"
              />
            </div>
            <div className="space-y-1.5">
              <label className="label text-slate-700 dark:text-slate-300">Username</label>
              <input
                type="text"
                className="input w-full opacity-50 cursor-not-allowed"
                value={`@${currentUser?.username ?? ''}`}
                disabled
              />
              <p className="text-xs text-slate-400">Username cannot be changed after sign-up</p>
            </div>
            <div className="space-y-1.5">
              <label className="label text-slate-700 dark:text-slate-300">Bio</label>
              <textarea
                className="input w-full resize-none"
                rows={3}
                value={editBio}
                onChange={e => setEditBio(e.target.value)}
                placeholder="Tell the world about your style…"
              />
            </div>
            <button
              onClick={saveProfile}
              disabled={saveLoading || !editName.trim()}
              className="btn-primary w-full sm:w-auto"
            >
              {saveLoading ? <><Loader2 size={14} className="animate-spin" /> Saving…</> : 'Save changes'}
            </button>
          </div>
        </div>
      )}
    </div>
  )
}
