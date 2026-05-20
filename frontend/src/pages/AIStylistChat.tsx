import { useState, useRef, useEffect, useCallback } from 'react'
import {
  Sparkles, RefreshCw, AlertTriangle, MessageSquare, History,
} from 'lucide-react'
import { useApp } from '@/store'
import { generateId } from '@/lib/utils'
import { sendMessage, getChatHistory } from '@/services/aiChatApi'
import ChatInput from '@/components/ai-chat/ChatInput'
import OutfitRecommendationCard from '@/components/ai-chat/OutfitRecommendationCard'
import type { StylistChatMessage, AIChatContext } from '@/types'

// ── Message bubble ────────────────────────────────────────────────────────────

const WELCOME: StylistChatMessage = {
  id: 'welcome',
  role: 'assistant',
  content:
    "Hey! I'm FANI — your Fashion AI Nurturing Individuality. I can build outfits from your actual wardrobe, factor in weather and occasion, and explain exactly why an outfit works. What do you need today?",
  timestamp: new Date(),
}

const QUICK_PROMPTS = [
  { label: '👕 Outfit today', text: 'What should I wear today?' },
  { label: '🍽️ Dinner look', text: 'Build me an outfit for dinner tonight' },
  { label: '💼 Office ready', text: 'Create a smart casual office outfit' },
  { label: '✈️ Packing help', text: 'What should I pack for a weekend trip?' },
  { label: '🔥 Bold outfit', text: 'I want to look bold and confident today' },
  { label: '🧳 Travel look', text: 'Suggest a comfortable travel outfit' },
]

function UserBubble({ content }: { content: string }) {
  return (
    <div className="flex justify-end gap-3 animate-slide-up">
      <div className="max-w-[75%]">
        <div className="px-4 py-3 rounded-2xl rounded-tr-sm text-sm leading-relaxed bg-gradient-brand text-white shadow-sm">
          <span style={{ whiteSpace: 'pre-wrap' }}>{content}</span>
        </div>
      </div>
      <div className="w-8 h-8 rounded-full bg-gradient-brand flex-shrink-0 flex items-center justify-center text-white text-xs font-bold shadow-sm mt-0.5">
        You
      </div>
    </div>
  )
}

function AssistantBubble({
  msg,
  streaming,
  sessionId,
}: {
  msg: StylistChatMessage
  streaming: boolean
  sessionId?: string
}) {
  const outfits = msg.structured?.recommended_outfits ?? []
  const gaps = msg.structured?.purchase_gaps ?? []
  const followUps = msg.structured?.follow_up_questions ?? []

  return (
    <div className="flex gap-3 animate-slide-up">
      <div className="w-8 h-8 rounded-full bg-slate-900 dark:bg-slate-700 flex-shrink-0 flex items-center justify-center shadow-sm mt-0.5">
        <Sparkles size={14} className="text-white" />
      </div>

      <div className="flex flex-col gap-3 max-w-[80%] min-w-0">
        {/* Text reply */}
        {msg.content && (
          <div className="px-4 py-3 rounded-2xl rounded-tl-sm text-sm leading-relaxed bg-white dark:bg-slate-800 text-slate-700 dark:text-slate-200 shadow-card border border-cream-300 dark:border-slate-700">
            <span style={{ whiteSpace: 'pre-wrap' }}>{msg.content}</span>
            {streaming && (
              <span className="inline-block w-0.5 h-4 bg-brand-500 ml-0.5 animate-pulse align-middle" />
            )}
          </div>
        )}

        {/* Outfit recommendation cards */}
        {outfits.length > 0 && (
          <div className="space-y-2 w-full">
            {outfits.map((outfit, i) => (
              <OutfitRecommendationCard
                key={outfit.title + i}
                outfit={outfit}
                rank={i}
                sessionId={sessionId}
              />
            ))}
          </div>
        )}

        {/* Purchase gaps */}
        {gaps.length > 0 && (
          <div className="p-3 rounded-2xl bg-amber-50 dark:bg-amber-900/20 border border-amber-200 dark:border-amber-800 text-sm space-y-1.5">
            <p className="font-semibold text-amber-700 dark:text-amber-400 text-xs flex items-center gap-1.5">
              <AlertTriangle size={12} /> Missing from your closet
            </p>
            {gaps.map((g, i) => (
              <p key={i} className="text-xs text-amber-700 dark:text-amber-300 flex gap-2">
                <span>•</span>
                <span><strong className="capitalize">{g.category}</strong> — {g.reason}</span>
              </p>
            ))}
          </div>
        )}

        {/* Follow-up suggestions */}
        {followUps.length > 0 && (
          <div className="flex flex-wrap gap-1.5">
            {followUps.map((q, i) => (
              <span
                key={i}
                className="text-xs px-2.5 py-1 rounded-full bg-slate-100 dark:bg-slate-700 text-slate-500 dark:text-slate-400 border border-slate-200 dark:border-slate-600"
              >
                {q}
              </span>
            ))}
          </div>
        )}

        <span className="text-[10px] text-slate-400 px-1">
          {msg.timestamp.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
        </span>
      </div>
    </div>
  )
}

function ThinkingBubble() {
  return (
    <div className="flex gap-3 animate-slide-up">
      <div className="w-8 h-8 rounded-full bg-slate-900 dark:bg-slate-700 flex-shrink-0 flex items-center justify-center shadow-sm">
        <Sparkles size={14} className="text-white" />
      </div>
      <div className="px-4 py-3 rounded-2xl rounded-tl-sm bg-white dark:bg-slate-800 border border-cream-300 dark:border-slate-700 shadow-card">
        <div className="flex gap-1 items-center">
          {[0, 1, 2].map(i => (
            <div
              key={i}
              className="w-2 h-2 rounded-full bg-brand-400 animate-pulse-soft"
              style={{ animationDelay: `${i * 0.2}s` }}
            />
          ))}
        </div>
      </div>
    </div>
  )
}

// ── Main page ─────────────────────────────────────────────────────────────────

export default function AIStylistChat() {
  const { closetItems } = useApp()
  const [messages, setMessages] = useState<StylistChatMessage[]>([WELCOME])
  const [streaming, setStreaming] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [sessionId, setSessionId] = useState<string | null>(null)
  const [showHistory, setShowHistory] = useState(false)
  const bottomRef = useRef<HTMLDivElement>(null)
  const cancelRef = useRef(false)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  const send = useCallback(async (text: string, ctx?: AIChatContext) => {
    const trimmed = text.trim()
    if (!trimmed || streaming) return
    cancelRef.current = false

    const userMsg: StylistChatMessage = {
      id: generateId(),
      role: 'user',
      content: trimmed,
      timestamp: new Date(),
    }
    setMessages(m => [...m, userMsg])
    setStreaming(true)
    setError(null)

    const aiMsgId = generateId()
    setMessages(m => [...m, { id: aiMsgId, role: 'assistant', content: '', timestamp: new Date() }])

    try {
      const history = messages
        .filter(m => m.id !== 'welcome')
        .slice(-10)
        .map(m => ({ role: m.role, content: m.content }))

      const res = await sendMessage({
        message: trimmed,
        sessionId,
        context: ctx,
        history,
      })

      if (cancelRef.current) return
      setSessionId(res.session_id)
      setMessages(m => m.map(msg =>
        msg.id === aiMsgId
          ? {
              ...msg,
              content: res.reply,
              structured: {
                reply: res.reply,
                recommended_outfits: res.recommended_outfits,
                purchase_gaps: res.purchase_gaps,
                follow_up_questions: res.follow_up_questions,
              },
            }
          : msg,
      ))
    } catch (e) {
      if (cancelRef.current) return
      const errMsg = e instanceof Error ? e.message : 'Network error'
      setError(errMsg)
      setMessages(m => m.map(msg =>
        msg.id === aiMsgId
          ? { ...msg, content: `I'm having trouble connecting right now. (${errMsg})` }
          : msg,
      ))
    } finally {
      if (!cancelRef.current) setStreaming(false)
    }
  }, [streaming, messages, sessionId])

  const stopStreaming = () => {
    cancelRef.current = true
    setStreaming(false)
  }

  const newChat = () => {
    cancelRef.current = true
    setStreaming(false)
    setMessages([WELCOME])
    setSessionId(null)
    setError(null)
  }

  return (
    <div className="flex flex-col h-[calc(100vh-130px)] max-w-3xl mx-auto animate-fade-in">

      {/* Header */}
      <div className="flex items-center justify-between mb-4 flex-shrink-0">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-2xl bg-gradient-brand flex items-center justify-center shadow-md">
            <Sparkles size={18} className="text-white" />
          </div>
          <div>
            <h2 className="font-display font-bold text-xl text-slate-800 dark:text-slate-100">
              FANI
            </h2>
            <p className="text-xs text-slate-400">
              {closetItems.length > 0
                ? `${closetItems.length} wardrobe items · Fashion AI Nurturing Individuality`
                : 'Add items to your closet for personalised suggestions'}
            </p>
          </div>
        </div>

        <div className="flex gap-2">
          <button
            onClick={() => setShowHistory(v => !v)}
            className="btn-ghost text-xs gap-1.5"
            title="Chat history"
          >
            <History size={13} />
            <span className="hidden sm:inline">History</span>
          </button>
          <button onClick={newChat} className="btn-ghost text-xs gap-1.5">
            <RefreshCw size={13} />
            <span className="hidden sm:inline">New chat</span>
          </button>
        </div>
      </div>

      {/* Warnings */}
      {closetItems.length === 0 && (
        <div className="card p-3 mb-3 bg-amber-50 dark:bg-amber-900/20 border-amber-200 dark:border-amber-800 text-amber-700 dark:text-amber-300 text-xs flex items-center gap-2 flex-shrink-0">
          <AlertTriangle size={13} />
          Your wardrobe is empty — upload items first for the best outfit suggestions.
        </div>
      )}

      {error && (
        <div className="card p-2 mb-3 bg-red-50 dark:bg-red-900/20 border-red-200 dark:border-red-800 text-red-600 dark:text-red-300 text-xs flex items-center gap-2 flex-shrink-0">
          <AlertTriangle size={12} />
          {error}
        </div>
      )}

      {/* Message area */}
      <div className="flex-1 overflow-y-auto chat-scroll space-y-4 pb-4 min-h-0">
        {messages.map(msg =>
          msg.role === 'user' ? (
            <UserBubble key={msg.id} content={msg.content} />
          ) : (
            <AssistantBubble
              key={msg.id}
              msg={msg}
              streaming={streaming && msg === messages[messages.length - 1] && msg.role === 'assistant' && msg.content === ''}
              sessionId={sessionId ?? undefined}
            />
          ),
        )}

        {/* Thinking indicator when the last assistant message is still empty */}
        {streaming && messages[messages.length - 1]?.role === 'assistant' && messages[messages.length - 1]?.content === '' && (
          <ThinkingBubble />
        )}

        <div ref={bottomRef} />
      </div>

      {/* Quick prompts — only when at start */}
      {messages.length <= 1 && (
        <div className="grid grid-cols-2 sm:grid-cols-3 gap-2 mb-4 flex-shrink-0">
          {QUICK_PROMPTS.map(p => (
            <button
              key={p.text}
              onClick={() => send(p.text)}
              disabled={streaming}
              className="text-left text-xs px-3 py-2.5 rounded-xl bg-white dark:bg-slate-800 border border-cream-200 dark:border-slate-700 text-slate-600 dark:text-slate-300 hover:border-brand-300 dark:hover:border-brand-700 hover:bg-brand-50 dark:hover:bg-brand-900/20 transition-colors disabled:opacity-40 shadow-sm"
            >
              {p.label}
            </button>
          ))}
        </div>
      )}

      {/* Input */}
      <div className="flex-shrink-0">
        <ChatInput
          onSend={send}
          streaming={streaming}
          onStop={stopStreaming}
          disabled={false}
        />
      </div>
    </div>
  )
}
