import { useState, useEffect, useCallback } from 'react'
import {
  Plus, Search, Users, Loader2, X, Globe, Lock,
  Crown, UserMinus, RefreshCw, AlertTriangle, Copy, Check, Compass
} from 'lucide-react'
import { useApp } from '@/store'
import { socialApi } from '@/lib/api'
import type { Group, GroupMember, SocialUser } from '@/types'
import GroupCard from '@/components/ui/GroupCard'
import { cn } from '@/lib/utils'

// ── Create Group Modal ─────────────────────────────────────
function CreateGroupModal({ onClose, onCreate }: {
  onClose: () => void
  onCreate: (g: Group) => void
}) {
  const [name, setName] = useState('')
  const [description, setDescription] = useState('')
  const [isPublic, setIsPublic] = useState(true)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  const submit = async () => {
    if (!name.trim()) return
    setLoading(true)
    setError('')
    try {
      const group = await socialApi.createGroup({ name: name.trim(), description: description.trim() || undefined, is_public: isPublic })
      onCreate(group)
      onClose()
    } catch (err: unknown) {
      const d = (err as { response?: { data?: { message?: string; error?: string } } })?.response?.data
      const msg = d?.message ?? d?.error ?? 'Failed to create group'
      setError(msg)
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/50 backdrop-blur-sm">
      <div className="bg-white dark:bg-slate-800 rounded-2xl shadow-2xl w-full max-w-md animate-slide-up">
        <div className="flex items-center justify-between p-5 border-b border-cream-200 dark:border-slate-700">
          <h2 className="font-display font-bold text-lg text-slate-800 dark:text-white">Create Group</h2>
          <button onClick={onClose} className="p-1.5 rounded-lg hover:bg-cream-100 dark:hover:bg-slate-700 transition-colors">
            <X size={18} className="text-slate-500" />
          </button>
        </div>
        <div className="p-5 space-y-4">
          {error && (
            <div className="flex items-center gap-2 p-3 rounded-xl bg-red-50 dark:bg-red-900/20 text-red-600 dark:text-red-300 text-sm">
              <AlertTriangle size={14} /> {error}
            </div>
          )}
          <div className="space-y-1.5">
            <label className="label text-slate-700 dark:text-slate-300">Group name *</label>
            <input type="text" className="input w-full" placeholder="e.g. Work Outfits" value={name} onChange={e => setName(e.target.value)} autoFocus />
          </div>
          <div className="space-y-1.5">
            <label className="label text-slate-700 dark:text-slate-300">Description</label>
            <textarea className="input w-full resize-none" rows={2} placeholder="What's this group about?" value={description} onChange={e => setDescription(e.target.value)} />
          </div>
          <div className="flex gap-3">
            <button
              onClick={() => setIsPublic(true)}
              className={cn('flex-1 flex items-center gap-2 p-3 rounded-xl border-2 transition-all text-sm font-medium',
                isPublic ? 'border-brand-500 bg-brand-50 dark:bg-brand-900/20 text-brand-700 dark:text-brand-300'
                         : 'border-cream-300 dark:border-slate-600 text-slate-500 hover:border-slate-400')}
            >
              <Globe size={16} /> Public
            </button>
            <button
              onClick={() => setIsPublic(false)}
              className={cn('flex-1 flex items-center gap-2 p-3 rounded-xl border-2 transition-all text-sm font-medium',
                !isPublic ? 'border-brand-500 bg-brand-50 dark:bg-brand-900/20 text-brand-700 dark:text-brand-300'
                          : 'border-cream-300 dark:border-slate-600 text-slate-500 hover:border-slate-400')}
            >
              <Lock size={16} /> Private
            </button>
          </div>
        </div>
        <div className="flex gap-3 p-5 border-t border-cream-200 dark:border-slate-700">
          <button onClick={onClose} className="btn-ghost flex-1">Cancel</button>
          <button onClick={submit} disabled={loading || !name.trim()} className="btn-primary flex-1">
            {loading ? <><Loader2 size={14} className="animate-spin" /> Creating…</> : 'Create Group'}
          </button>
        </div>
      </div>
    </div>
  )
}

// ── Join Group Modal ───────────────────────────────────────
function JoinGroupModal({ onClose, onJoin }: {
  onClose: () => void
  onJoin: (g: Group) => void
}) {
  const [code, setCode] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  const submit = async () => {
    if (!code.trim()) return
    setLoading(true)
    setError('')
    try {
      const group = await socialApi.joinGroup(code.trim().toUpperCase())
      onJoin(group)
      onClose()
    } catch (err: unknown) {
      const msg = (err as { response?: { data?: { error?: string } } })?.response?.data?.error ?? 'Invalid invite code'
      setError(msg)
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/50 backdrop-blur-sm">
      <div className="bg-white dark:bg-slate-800 rounded-2xl shadow-2xl w-full max-w-sm animate-slide-up">
        <div className="flex items-center justify-between p-5 border-b border-cream-200 dark:border-slate-700">
          <h2 className="font-display font-bold text-lg text-slate-800 dark:text-white">Join Group</h2>
          <button onClick={onClose} className="p-1.5 rounded-lg hover:bg-cream-100 dark:hover:bg-slate-700 transition-colors">
            <X size={18} className="text-slate-500" />
          </button>
        </div>
        <div className="p-5 space-y-4">
          {error && (
            <div className="flex items-center gap-2 p-3 rounded-xl bg-red-50 dark:bg-red-900/20 text-red-600 dark:text-red-300 text-sm">
              <AlertTriangle size={14} /> {error}
            </div>
          )}
          <div className="space-y-1.5">
            <label className="label text-slate-700 dark:text-slate-300">Invite code</label>
            <input
              type="text"
              className="input w-full font-mono text-center tracking-widest uppercase"
              placeholder="ABCD123456"
              value={code}
              onChange={e => setCode(e.target.value)}
              maxLength={10}
              autoFocus
            />
            <p className="text-xs text-slate-400">Ask a group admin for their 10-character invite code</p>
          </div>
        </div>
        <div className="flex gap-3 p-5 border-t border-cream-200 dark:border-slate-700">
          <button onClick={onClose} className="btn-ghost flex-1">Cancel</button>
          <button onClick={submit} disabled={loading || code.trim().length < 4} className="btn-primary flex-1">
            {loading ? <><Loader2 size={14} className="animate-spin" /> Joining…</> : 'Join Group'}
          </button>
        </div>
      </div>
    </div>
  )
}

// ── Group Detail Panel ─────────────────────────────────────
function GroupDetail({ group, onClose, onUpdate }: {
  group: Group
  onClose: () => void
  onUpdate: (g: Group) => void
}) {
  const { currentUser } = useApp()
  const [users, setUsers] = useState<SocialUser[]>([])
  const [userQuery, setUserQuery] = useState('')
  const [inviting, setInviting] = useState<string | null>(null)
  const [copied, setCopied] = useState(false)

  const members = group.members ?? []
  const isAdmin = group.role === 'admin' || group.role === 'owner'
  const isOwner = group.role === 'owner'

  useEffect(() => {
    if (!userQuery.trim()) { setUsers([]); return }
    const t = setTimeout(() => {
      socialApi.searchUsers(userQuery).then(setUsers).catch(() => {})
    }, 400)
    return () => clearTimeout(t)
  }, [userQuery])

  const invite = async (userId: string) => {
    setInviting(userId)
    try {
      // Copy invite code to clipboard as the invite mechanism
      await navigator.clipboard.writeText(group.invite_code)
      alert(`Share this invite code with the user: ${group.invite_code}`)
    } catch { /* ignore */ }
    finally { setInviting(null) }
  }

  const remove = async (userId: string) => {
    if (!confirm('Remove this member?')) return
    try {
      await socialApi.removeMember(group.id, userId)
      const updatedMembers = members.filter(m => m.id !== userId)
      onUpdate({ ...group, members: updatedMembers, member_count: group.member_count - 1 })
    } catch { /* ignore */ }
  }

  const toggleRole = async (member: GroupMember) => {
    const newRole: 'admin' | 'member' = member.role === 'admin' ? 'member' : 'admin'
    try {
      await socialApi.changeMemberRole(group.id, member.id, newRole)
      const updatedMembers = members.map(m => m.id === member.id ? { ...m, role: newRole } : m)
      onUpdate({ ...group, members: updatedMembers })
    } catch { /* ignore */ }
  }

  const copyCode = async () => {
    await navigator.clipboard.writeText(group.invite_code)
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }

  const handleLeave = async () => {
    if (!currentUser || !confirm('Leave this group?')) return
    try {
      await socialApi.leaveGroup(group.id)
      onClose()
    } catch { /* ignore */ }
  }

  const handleDelete = async () => {
    if (!confirm(`Delete "${group.name}"? This cannot be undone.`)) return
    try {
      await socialApi.deleteGroup(group.id)
      onClose()
    } catch { /* ignore */ }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/50 backdrop-blur-sm">
      <div className="bg-white dark:bg-slate-800 rounded-2xl shadow-2xl w-full max-w-lg max-h-[90vh] flex flex-col animate-slide-up">
        {/* Header */}
        <div className="flex items-center justify-between p-5 border-b border-cream-200 dark:border-slate-700 flex-shrink-0">
          <div>
            <h2 className="font-display font-bold text-lg text-slate-800 dark:text-white flex items-center gap-2">
              {group.name}
              {isAdmin && <Crown size={16} className="text-amber-500" />}
            </h2>
            <p className="text-xs text-slate-400 mt-0.5">{group.member_count} members · {group.is_public ? '🌍 Public' : '🔒 Private'}</p>
          </div>
          <button onClick={onClose} className="p-1.5 rounded-lg hover:bg-cream-100 dark:hover:bg-slate-700 transition-colors">
            <X size={18} className="text-slate-500" />
          </button>
        </div>

        <div className="flex-1 overflow-y-auto p-5 space-y-5">
          {/* Description */}
          {group.description && (
            <p className="text-sm text-slate-500 dark:text-slate-400">{group.description}</p>
          )}

          {/* Invite code */}
          <div className="flex items-center gap-3 p-3 rounded-xl bg-cream-50 dark:bg-slate-700/50 border border-cream-200 dark:border-slate-600">
            <div className="flex-1">
              <p className="text-[10px] text-slate-400 font-semibold uppercase tracking-wider mb-0.5">Invite code</p>
              <p className="font-mono font-bold text-slate-800 dark:text-white tracking-widest">{group.invite_code}</p>
            </div>
            <button onClick={copyCode} className="p-2 rounded-lg hover:bg-brand-100 dark:hover:bg-brand-900/30 text-slate-500 hover:text-brand-600 transition-colors">
              {copied ? <Check size={16} className="text-emerald-500" /> : <Copy size={16} />}
            </button>
          </div>

          {/* Members list */}
          {members.length > 0 && (
            <div>
              <p className="text-sm font-semibold text-slate-700 dark:text-slate-300 mb-3">Members</p>
              <div className="space-y-2">
                {members.map(member => {
                  const displayName = member.display_name || member.username || 'Unknown'
                  const initials = displayName.split(' ').map((n: string) => n[0]).join('').slice(0, 2).toUpperCase()
                  const isMe = member.id === currentUser?.id
                  const isCreator = member.role === 'owner'

                  return (
                    <div key={member.id} className="flex items-center gap-3 p-2.5 rounded-xl hover:bg-cream-50 dark:hover:bg-slate-700/50 transition-colors">
                      <div className="w-9 h-9 rounded-full bg-gradient-brand flex items-center justify-center text-sm font-bold text-white flex-shrink-0">
                        {member.avatar_url ? <img src={member.avatar_url} alt="" className="w-full h-full rounded-full object-cover" /> : initials}
                      </div>
                      <div className="flex-1 min-w-0">
                        <p className="text-sm font-semibold text-slate-800 dark:text-slate-100 truncate">
                          {displayName} {isMe && <span className="text-slate-400 font-normal">(you)</span>}
                        </p>
                        {member.username && <p className="text-[11px] text-slate-400">@{member.username}</p>}
                      </div>
                      <div className="flex items-center gap-2">
                        {/* Role badge */}
                        <span className={cn(
                          'text-[11px] px-2 py-0.5 rounded-full font-semibold',
                          member.role === 'owner'
                            ? 'bg-brand-100 dark:bg-brand-900/30 text-brand-700 dark:text-brand-300'
                            : member.role === 'admin'
                              ? 'bg-amber-100 dark:bg-amber-900/30 text-amber-700 dark:text-amber-300'
                              : 'bg-slate-100 dark:bg-slate-700 text-slate-500 dark:text-slate-400',
                        )}>
                          {member.role === 'owner' ? '👑 Owner' : member.role === 'admin' ? '⭐ Admin' : 'Member'}
                        </span>

                        {/* Admin actions */}
                        {isAdmin && !isMe && !isCreator && (
                          <div className="flex gap-1">
                            <button
                              onClick={() => toggleRole(member)}
                              className="p-1.5 rounded-lg hover:bg-amber-100 dark:hover:bg-amber-900/20 text-amber-600 transition-colors text-xs"
                              title={member.role === 'admin' ? 'Demote to member' : 'Promote to admin'}
                            >
                              <Crown size={13} />
                            </button>
                            <button
                              onClick={() => remove(member.id)}
                              className="p-1.5 rounded-lg hover:bg-red-100 dark:hover:bg-red-900/20 text-red-500 transition-colors"
                              title="Remove member"
                            >
                              <UserMinus size={13} />
                            </button>
                          </div>
                        )}
                      </div>
                    </div>
                  )
                })}
              </div>
            </div>
          )}

          {/* Invite member (admin only) */}
          {isAdmin && (
            <div className="space-y-2">
              <p className="text-sm font-semibold text-slate-700 dark:text-slate-300">Invite member</p>
              <div className="relative">
                <Search size={14} className="absolute left-3.5 top-1/2 -translate-y-1/2 text-slate-400" />
                <input
                  type="text"
                  className="input w-full pl-9"
                  placeholder="Search by name or username…"
                  value={userQuery}
                  onChange={e => setUserQuery(e.target.value)}
                />
              </div>
              {users.filter(u => !members.find(m => m.id === u.id)).map(u => {
                const displayName = u.display_name || u.username || 'Unknown'
                const initials = displayName.split(' ').map((n: string) => n[0]).join('').slice(0, 2).toUpperCase()
                return (
                  <div key={u.id} className="flex items-center gap-3 p-2.5 rounded-xl bg-cream-50 dark:bg-slate-700/50">
                    <div className="w-8 h-8 rounded-full bg-gradient-brand flex items-center justify-center text-xs font-bold text-white flex-shrink-0">
                      {u.avatar_url ? <img src={u.avatar_url} alt="" className="w-full h-full rounded-full object-cover" /> : initials}
                    </div>
                    <div className="flex-1 min-w-0">
                      <p className="text-sm font-medium text-slate-800 dark:text-slate-100 truncate">{displayName}</p>
                      {u.username && <p className="text-[11px] text-slate-400">@{u.username}</p>}
                    </div>
                    <button
                      onClick={() => invite(u.id)}
                      disabled={inviting === u.id}
                      className="btn-primary text-xs py-1.5 px-3"
                    >
                      {inviting === u.id ? <Loader2 size={12} className="animate-spin" /> : 'Share code'}
                    </button>
                  </div>
                )
              })}
            </div>
          )}
        </div>

        {/* Footer actions */}
        <div className="flex gap-3 p-5 border-t border-cream-200 dark:border-slate-700 flex-shrink-0">
          <button onClick={handleLeave} className="btn-ghost text-sm text-red-500 hover:text-red-600 hover:bg-red-50 dark:hover:bg-red-900/20 flex-1">
            Leave group
          </button>
          {isOwner && (
            <button onClick={handleDelete} className="btn-ghost text-sm text-red-600 hover:text-red-700 flex-1">
              Delete group
            </button>
          )}
        </div>
      </div>
    </div>
  )
}

// ── Main Groups Page ───────────────────────────────────────
export default function Groups() {
  const [myGroups, setMyGroups] = useState<Group[]>([])
  const [publicGroups, setPublicGroups] = useState<Group[]>([])
  const [loading, setLoading] = useState(true)
  const [activeTab, setActiveTab] = useState<'mine' | 'discover'>('mine')

  const [showCreate, setShowCreate] = useState(false)
  const [showJoin, setShowJoin] = useState(false)
  const [selectedGroup, setSelectedGroup] = useState<Group | null>(null)

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const mine = await socialApi.getMyGroups()
      setMyGroups(mine)
      // Discover: show public groups not already joined (client-side filter)
      const publicOnes = mine.filter(g => g.is_public)
      setPublicGroups(publicOnes)
    } catch (e) {
      console.error(e)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    load()
    const id = setInterval(load, 30_000)
    return () => clearInterval(id)
  }, [load])

  const handleCreate = (g: Group) => setMyGroups(prev => [g, ...prev])
  const handleJoin = (g: Group) => {
    setMyGroups(prev => [g, ...prev])
    setPublicGroups(prev => prev.filter(p => p.id !== g.id))
  }
  const handleUpdate = (g: Group) => {
    setMyGroups(prev => prev.map(p => p.id === g.id ? g : p))
    if (selectedGroup?.id === g.id) setSelectedGroup(g)
  }
  const handleDetailClose = () => {
    setSelectedGroup(null)
    load()
  }

  const displayGroups = activeTab === 'mine' ? myGroups : publicGroups

  return (
    <div className="max-w-5xl space-y-6 animate-slide-up">

      {/* ── Header ─────────────────────────────────────────── */}
      <div className="flex items-center justify-between">
        <div>
          <h2 className="font-display font-bold text-xl text-slate-800 dark:text-slate-100 flex items-center gap-2">
            <Users size={22} className="text-brand-500" /> Groups
          </h2>
          <p className="text-sm text-slate-400 mt-0.5">Share styles, plan outfits together, stay inspired</p>
        </div>
        <div className="flex gap-2">
          <button onClick={() => setShowJoin(true)} className="btn-ghost text-sm gap-1.5">
            <Search size={15} /> Join by code
          </button>
          <button onClick={() => setShowCreate(true)} className="btn-primary text-sm gap-1.5">
            <Plus size={15} /> Create group
          </button>
        </div>
      </div>

      {/* ── Tabs ───────────────────────────────────────────── */}
      <div className="flex items-center gap-3">
        <div className="flex gap-1 bg-cream-100 dark:bg-slate-800 p-1 rounded-xl">
          {[
            { id: 'mine' as const,     label: `My Groups (${myGroups.length})`,     icon: <Users size={14} /> },
            { id: 'discover' as const, label: `Public (${publicGroups.length})`,    icon: <Compass size={14} /> },
          ].map(t => (
            <button
              key={t.id}
              onClick={() => setActiveTab(t.id)}
              className={cn(
                'flex items-center gap-1.5 px-4 py-1.5 rounded-lg text-sm font-medium transition-all',
                activeTab === t.id
                  ? 'bg-white dark:bg-slate-700 text-slate-800 dark:text-white shadow-sm'
                  : 'text-slate-500 hover:text-slate-700 dark:hover:text-slate-300',
              )}
            >
              {t.icon} {t.label}
            </button>
          ))}
        </div>
        <button
          onClick={load}
          className="p-2 rounded-xl hover:bg-cream-100 dark:hover:bg-slate-800 text-slate-400 hover:text-slate-600 transition-colors"
          title="Refresh"
        >
          <RefreshCw size={15} className={loading ? 'animate-spin' : ''} />
        </button>
      </div>

      {/* ── Groups grid ────────────────────────────────────── */}
      {loading ? (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
          {[...Array(3)].map((_, i) => (
            <div key={i} className="card p-5 space-y-4 animate-pulse">
              <div className="flex items-center gap-3">
                <div className="w-12 h-12 rounded-2xl bg-cream-200 dark:bg-slate-700 flex-shrink-0" />
                <div className="flex-1 space-y-2">
                  <div className="h-4 bg-cream-200 dark:bg-slate-700 rounded w-3/4" />
                  <div className="h-3 bg-cream-100 dark:bg-slate-700/50 rounded w-1/2" />
                </div>
              </div>
              <div className="h-3 bg-cream-100 dark:bg-slate-700/50 rounded" />
            </div>
          ))}
        </div>
      ) : displayGroups.length === 0 ? (
        <div className="card p-12 text-center">
          <div className="w-16 h-16 mx-auto mb-4 rounded-2xl bg-brand-50 dark:bg-brand-900/20 flex items-center justify-center">
            <Users size={32} className="text-brand-400" />
          </div>
          <h3 className="font-display font-bold text-lg text-slate-800 dark:text-white mb-2">
            {activeTab === 'mine' ? 'No groups yet' : 'No public groups'}
          </h3>
          <p className="text-sm text-slate-400 mb-6">
            {activeTab === 'mine'
              ? 'Create a group to share outfits with friends, family, or colleagues.'
              : 'You have no public groups yet.'}
          </p>
          {activeTab === 'mine' && (
            <div className="flex gap-3 justify-center">
              <button onClick={() => setShowJoin(true)} className="btn-ghost">Join by code</button>
              <button onClick={() => setShowCreate(true)} className="btn-primary gap-1.5">
                <Plus size={15} /> Create first group
              </button>
            </div>
          )}
        </div>
      ) : (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
          {displayGroups.map(group => (
            <GroupCard
              key={group.id}
              group={group}
              showInviteCode={activeTab === 'mine'}
              onClick={() => setSelectedGroup(group)}
            />
          ))}
        </div>
      )}

      {/* ── Modals ─────────────────────────────────────────── */}
      {showCreate && (
        <CreateGroupModal onClose={() => setShowCreate(false)} onCreate={handleCreate} />
      )}
      {showJoin && (
        <JoinGroupModal onClose={() => setShowJoin(false)} onJoin={handleJoin} />
      )}
      {selectedGroup && (
        <GroupDetail group={selectedGroup} onClose={handleDetailClose} onUpdate={handleUpdate} />
      )}
    </div>
  )
}
