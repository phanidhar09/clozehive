import { Sparkles } from 'lucide-react'
import type { ChatMessage as ChatMsg } from '@/types'
import OutfitCard from '@/components/outfit/OutfitCard'
import { cn } from '@/lib/utils'

interface Props { message: ChatMsg; streaming?: boolean }

export default function ChatMessage({ message, streaming = false }: Props) {
  const isUser = message.role === 'user'

  return (
    <div className={cn('flex gap-3 animate-slide-up', isUser && 'flex-row-reverse')}>
      {/* Avatar */}
      <div className={cn(
        'w-8 h-8 rounded-full flex-shrink-0 flex items-center justify-center text-xs font-bold shadow-sm mt-0.5',
        isUser
          ? 'bg-gradient-brand text-white'
          : 'bg-slate-900 dark:bg-slate-700 text-white',
      )}>
        {isUser ? 'A' : <Sparkles size={14} />}
      </div>

      {/* Content */}
      <div className={cn('flex flex-col gap-2 max-w-[75%]', isUser && 'items-end')}>
        <div className={cn(
          'px-4 py-3 rounded-2xl text-sm leading-relaxed',
          isUser
            ? 'bg-gradient-brand text-white rounded-tr-sm'
            : 'bg-white dark:bg-slate-800 text-slate-700 dark:text-slate-200 shadow-card rounded-tl-sm border border-cream-300 dark:border-slate-700',
        )}>
          {/* Render text with whitespace preserved */}
          <span style={{ whiteSpace: 'pre-wrap' }}>{message.content}</span>
          {/* Blinking cursor while streaming */}
          {streaming && (
            <span className="inline-block w-0.5 h-4 bg-brand-500 ml-0.5 animate-pulse align-middle" />
          )}
        </div>

        {/* Inline outfit cards */}
        {message.outfits && message.outfits.length > 0 && (
          <div className="w-full space-y-2 mt-1">
            {message.outfits.map((outfit, i) => (
              <OutfitCard key={outfit.name + i} outfit={outfit} rank={i} compact />
            ))}
          </div>
        )}

        <span className="text-[10px] text-slate-400 px-1">
          {message.timestamp.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
        </span>
      </div>
    </div>
  )
}
