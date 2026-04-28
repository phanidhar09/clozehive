import { useState } from 'react'
import { UserPlus, UserMinus, Loader2 } from 'lucide-react'
import type { SocialUser } from '@/types'
import { followUser, unfollowUser } from '@/lib/api'
import { cn } from '@/lib/utils'

interface Props {
  user: SocialUser
  onClick?: () => void
  onFollowChange?: (userId: number, following: boolean, count: number) => void
  compact?: boolean
}

export default function UserCard({ user, onClick, onFollowChange, compact = false }: Props) {
  const [following, setFollowing] = useState(user.is_following)
  const [followerCount, setFollowerCount] = useState(user.follower_count)
  const [loading, setLoading] = useState(false)

  const initials = user.name
    ? user.name.split(' ').map(n => n[0]).join('').slice(0, 2).toUpperCase()
    : '?'

  const toggleFollow = async (e: React.MouseEvent) => {
    e.stopPropagation()
    setLoading(true)
    try {
      const res = following
        ? await unfollowUser(user.id)
        : await followUser(user.id)
      setFollowing(res.following)
      setFollowerCount(res.follower_count)
      onFollowChange?.(user.id, res.following, res.follower_count)
    } catch (err) {
      console.error('Follow toggle failed:', err)
    } finally {
      setLoading(false)
    }
  }

  if (compact) {
    return (
      <div
        onClick={onClick}
        className={cn('flex items-center gap-3 p-3 rounded-xl hover:bg-cream-50 dark:hover:bg-slate-800 transition-colors', onClick && 'cursor-pointer')}
      >
        <div className="w-9 h-9 rounded-full bg-gradient-brand flex items-center justify-center text-sm font-bold text-white flex-shrink-0">
          {user.avatar_url ? <img src={user.avatar_url} alt="" className="w-full h-full rounded-full object-cover" /> : initials}
        </div>
        <div className="flex-1 min-w-0">
          <p className="text-sm font-semibold text-slate-800 dark:text-slate-100 truncate">{user.name}</p>
          {user.username && <p className="text-xs text-slate-400 truncate">@{user.username}</p>}
        </div>
        <button
          onClick={toggleFollow}
          disabled={loading}
          className={cn(
            'flex items-center gap-1 px-3 py-1.5 rounded-xl text-xs font-semibold transition-all flex-shrink-0',
            following
              ? 'bg-cream-100 dark:bg-slate-700 text-slate-600 dark:text-slate-300 hover:bg-red-50 dark:hover:bg-red-900/20 hover:text-red-500'
              : 'bg-brand-600 text-white hover:bg-brand-700',
          )}
        >
          {loading ? <Loader2 size={12} className="animate-spin" />
            : following ? <><UserMinus size={12} /> Unfollow</>
            : <><UserPlus size={12} /> Follow</>
          }
        </button>
      </div>
    )
  }

  return (
    <div
      onClick={onClick}
      className={cn('card p-4 space-y-3', onClick && 'cursor-pointer card-hover')}
    >
      {/* Avatar + name */}
      <div className="flex items-center gap-3">
        <div className="w-12 h-12 rounded-full bg-gradient-brand flex items-center justify-center text-base font-bold text-white flex-shrink-0 ring-2 ring-brand-200 dark:ring-brand-800">
          {user.avatar_url ? <img src={user.avatar_url} alt="" className="w-full h-full rounded-full object-cover" /> : initials}
        </div>
        <div className="flex-1 min-w-0">
          <p className="font-semibold text-slate-800 dark:text-slate-100 truncate">{user.name}</p>
          {user.username && (
            <p className="text-sm text-slate-400 truncate">@{user.username}</p>
          )}
        </div>
      </div>

      {/* Bio */}
      {user.bio && (
        <p className="text-sm text-slate-500 dark:text-slate-400 line-clamp-2">{user.bio}</p>
      )}

      {/* Stats */}
      <div className="flex gap-4 text-sm">
        <div className="text-center">
          <div className="font-bold text-slate-800 dark:text-slate-100">{followerCount}</div>
          <div className="text-[11px] text-slate-400">Followers</div>
        </div>
        <div className="text-center">
          <div className="font-bold text-slate-800 dark:text-slate-100">{user.following_count}</div>
          <div className="text-[11px] text-slate-400">Following</div>
        </div>
        {user.item_count !== undefined && (
          <div className="text-center">
            <div className="font-bold text-slate-800 dark:text-slate-100">{user.item_count}</div>
            <div className="text-[11px] text-slate-400">Items</div>
          </div>
        )}
      </div>

      {/* Follow button */}
      <button
        onClick={toggleFollow}
        disabled={loading}
        className={cn(
          'w-full h-9 rounded-xl text-sm font-semibold flex items-center justify-center gap-1.5 transition-all',
          following
            ? 'bg-cream-100 dark:bg-slate-700 text-slate-600 dark:text-slate-300 hover:bg-red-50 dark:hover:bg-red-900/20 hover:text-red-500 border border-cream-300 dark:border-slate-600'
            : 'bg-gradient-brand text-white shadow-sm hover:opacity-90',
        )}
      >
        {loading ? <Loader2 size={14} className="animate-spin" />
          : following ? <><UserMinus size={14} /> Following</>
          : <><UserPlus size={14} /> Follow</>
        }
      </button>
    </div>
  )
}
