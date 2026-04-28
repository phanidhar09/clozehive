import { Users, Crown, Lock, Globe, Copy, Check } from 'lucide-react'
import { useState } from 'react'
import type { Group } from '@/types'
import { cn } from '@/lib/utils'

interface Props {
  group: Group
  onClick?: () => void
  showInviteCode?: boolean
}

const GROUP_GRADIENTS = [
  'from-violet-500 to-purple-600',
  'from-sky-500 to-blue-600',
  'from-emerald-500 to-teal-600',
  'from-rose-500 to-pink-600',
  'from-amber-500 to-orange-600',
  'from-cyan-500 to-blue-500',
]

function hashGradient(id: string) {
  const sum = id.split('').reduce((a, c) => a + c.charCodeAt(0), 0)
  return GROUP_GRADIENTS[sum % GROUP_GRADIENTS.length]
}

export default function GroupCard({ group, onClick, showInviteCode = false }: Props) {
  const [copied, setCopied] = useState(false)
  const gradient = hashGradient(group.id)

  const copyCode = async (e: React.MouseEvent) => {
    e.stopPropagation()
    await navigator.clipboard.writeText(group.invite_code)
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }

  const members = group.members ?? []
  const visibleMembers = members.slice(0, 5)
  const extra = group.member_count - visibleMembers.length

  return (
    <div
      onClick={onClick}
      className={cn('card p-5 space-y-4 transition-all', onClick && 'card-hover cursor-pointer')}
    >
      {/* Header */}
      <div className="flex items-start gap-3">
        <div className={cn('w-12 h-12 rounded-2xl bg-gradient-to-br flex items-center justify-center flex-shrink-0 shadow-md', gradient)}>
          <Users size={22} className="text-white" />
        </div>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-1.5 mb-0.5">
            <h3 className="font-semibold text-slate-800 dark:text-slate-100 truncate">{group.name}</h3>
            {(group.role === 'admin' || group.role === 'owner') && (
              <span title="You are admin"><Crown size={13} className="text-amber-500 flex-shrink-0" /></span>
            )}
          </div>
          <div className="flex items-center gap-1.5 text-xs text-slate-400">
            {group.is_public ? <Globe size={11} /> : <Lock size={11} />}
            <span>{group.is_public ? 'Public' : 'Private'}</span>
            <span>·</span>
            <span>{group.member_count} {group.member_count === 1 ? 'member' : 'members'}</span>
          </div>
        </div>
      </div>

      {/* Description */}
      {group.description && (
        <p className="text-sm text-slate-500 dark:text-slate-400 line-clamp-2">{group.description}</p>
      )}

      {/* Members stack */}
      <div className="flex items-center justify-between">
        <div className="flex -space-x-2">
          {visibleMembers.map((member, i) => {
            const displayName = member.display_name || member.username || '?'
            const initials = displayName.split(' ').map((n: string) => n[0]).join('').slice(0, 2).toUpperCase()
            return (
              <div
                key={member.id}
                aria-label={`${displayName}${member.role === 'admin' ? ' (Admin)' : ''}`}
                className={cn(
                  'w-8 h-8 rounded-full border-2 border-white dark:border-slate-800 flex items-center justify-center text-xs font-bold text-white flex-shrink-0 bg-gradient-to-br',
                  GROUP_GRADIENTS[i % GROUP_GRADIENTS.length],
                )}
              >
                {member.avatar_url
                  ? <img src={member.avatar_url} alt={displayName} className="w-full h-full rounded-full object-cover" />
                  : initials}
              </div>
            )
          })}
          {extra > 0 && (
            <div className="w-8 h-8 rounded-full border-2 border-white dark:border-slate-800 bg-slate-200 dark:bg-slate-600 flex items-center justify-center text-[11px] font-bold text-slate-600 dark:text-slate-200">
              +{extra}
            </div>
          )}
        </div>

        {/* Role badge */}
        {group.role && (
          <span className={cn(
            'text-[11px] px-2 py-0.5 rounded-full font-semibold',
            group.role === 'owner'
              ? 'bg-brand-100 dark:bg-brand-900/30 text-brand-700 dark:text-brand-300'
              : group.role === 'admin'
                ? 'bg-amber-100 dark:bg-amber-900/30 text-amber-700 dark:text-amber-300'
                : 'bg-slate-100 dark:bg-slate-700 text-slate-500 dark:text-slate-400',
          )}>
            {group.role === 'owner' ? '👑 Owner' : group.role === 'admin' ? '⭐ Admin' : '● Member'}
          </span>
        )}
      </div>

      {/* Invite code */}
      {showInviteCode && group.role && (
        <div className="flex items-center gap-2 p-2.5 rounded-xl bg-cream-50 dark:bg-slate-800 border border-cream-200 dark:border-slate-700">
          <div className="flex-1 min-w-0">
            <p className="text-[10px] text-slate-400 font-medium uppercase tracking-wide">Invite code</p>
            <p className="font-mono text-sm font-bold text-slate-700 dark:text-slate-200 tracking-widest">{group.invite_code}</p>
          </div>
          <button
            onClick={copyCode}
            className="p-2 rounded-lg hover:bg-brand-100 dark:hover:bg-brand-900/30 text-slate-500 hover:text-brand-600 transition-colors flex-shrink-0"
            title="Copy code"
          >
            {copied ? <Check size={15} className="text-emerald-500" /> : <Copy size={15} />}
          </button>
        </div>
      )}
    </div>
  )
}
