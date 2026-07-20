/**
 * AIStylistChat — full-page version of FANI (v2 redesign).
 *
 * Layout: a single centered card that holds everything.
 *  - Card header: FANI badge, Chat / History segmented toggle, New button
 *  - Chat tab: centered welcome + quick prompts at the start, message stream,
 *    bottom input row
 *  - History tab: past sessions (load / delete), replacing the old slide-out sidebar
 *
 * Data wiring is unchanged from the previous version:
 *  - Session handoff from the floating chat (sessionStorage key: ch:ai-chat-handoff)
 *  - Streamed replies with grounding-gate corrections + structured payloads
 *  - Clickable follow-up chips, styling suggestions, purchase gaps, image upload
 */

import { useState, useRef, useEffect, useCallback } from 'react'
import {
  AlertTriangle,
  ChevronRight,
  Clock,
  Lightbulb,
  MessageSquare,
  Plus,
  Sparkles,
  Trash2,
} from 'lucide-react'
import { useApp } from '@/store'
import { generateId } from '@/lib/utils'
import { streamMessage, aiChatSessionsApi } from '@/services/aiChatApi'
import { cn } from '@/lib/utils'
import ChatInput from '@/components/ai-chat/ChatInput'
import FormattedMessage from '@/components/ai-chat/FormattedMessage'
import OutfitRecommendationCard from '@/components/ai-chat/OutfitRecommendationCard'
import { FaniLoader } from '@/components/system/FaniLoader'
import type { StylistChatMessage, AIChatContext, StylingHint, AIChatSession } from '@/types'

// ── Constants ─────────────────────────────────────────────────────────────────

const WELCOME: StylistChatMessage = {
  id: 'welcome',
  role: 'assistant',
  content:
    "Hey! I'm FANI — your Fashion Analysis and Nurturing Intelligence. I can build outfits from your actual wardrobe, answer styling questions, and help you look your best. What's on your mind?",
  timestamp: new Date(),
}
const AI_CHAT_TRIED_KEY = 'ch_ai_chat_tried'

// Auto-resume the latest session only while it still feels like "today's
// conversation" — anything older starts fresh (History keeps the rest).
const RESUME_WINDOW_MS = 12 * 60 * 60 * 1000

const QUICK_PROMPTS = [
  { label: '👕 What should I wear today?', text: 'What should I wear today?' },
  { label: '🍽️ Build a dinner look',       text: 'Build me an outfit for dinner tonight' },
  { label: '💼 Office ready',              text: 'Create a smart casual office outfit' },
  { label: '✨ Improve my style',          text: 'How can I improve my style with what I own?' },
  { label: '🔍 What am I missing?',        text: 'What key items am I missing from my wardrobe?' },
  { label: '🔥 Something bold',            text: 'I want to look bold and confident today' },
]

// ── Styling hint colour map ────────────────────────────────────────────────────

const HINT_STYLE: Record<string, string> = {
  color:       'bg-pink-50 dark:bg-pink-900/20 border-pink-200 dark:border-pink-800 text-pink-700 dark:text-pink-300',
  layering:    'bg-sky-50 dark:bg-sky-900/20 border-sky-200 dark:border-sky-800 text-sky-700 dark:text-sky-300',
  accessories: 'bg-brand-50 dark:bg-brand-900/20 border-brand-200 dark:border-brand-800 text-brand-700 dark:text-brand-300',
  fit:         'bg-emerald-50 dark:bg-emerald-900/20 border-emerald-200 dark:border-emerald-800 text-emerald-700 dark:text-emerald-300',
  occasion:    'bg-amber-50 dark:bg-amber-900/20 border-amber-200 dark:border-amber-800 text-amber-700 dark:text-amber-300',
  general:     'bg-slate-50 dark:bg-slate-800 border-slate-200 dark:border-slate-700 text-slate-600 dark:text-slate-300',
}

const HINT_EMOJI: Record<string, string> = {
  color: '🎨', layering: '🧥', accessories: '💍', fit: '✂️', occasion: '📅', general: '💡',
}

// ── Message mappers ───────────────────────────────────────────────────────────

function apiMsgToStylist(m: {
  id: string; role: string; message: string
  structured_response?: unknown; created_at: string
}): StylistChatMessage | null {
  if (m.role !== 'user' && m.role !== 'assistant') return null
  return {
    id: m.id,
    role: m.role as 'user' | 'assistant',
    content: m.message,
    structured: (m.structured_response as StylistChatMessage['structured']) ?? null,
    timestamp: new Date(m.created_at),
  }
}

// ── Bubble sub-components ─────────────────────────────────────────────────────

function UserBubble({ content, images }: { content: string; images?: string[] }) {
  return (
    <div className="flex justify-end animate-slide-up">
      <div className="max-w-[75%] flex flex-col items-end gap-2">
        {images && images.length > 0 && (
          <div className="flex gap-2 flex-wrap justify-end">
            {images.map((src, i) => (
              <img
                key={i}
                src={src}
                alt="uploaded"
                className="w-28 h-28 object-cover rounded-2xl rounded-br-sm shadow-sm border border-white/20"
              />
            ))}
          </div>
        )}
        {content && content !== '(see attached image)' && (
          <div className="px-4 py-3 rounded-2xl rounded-br-sm text-sm leading-relaxed bg-gradient-brand text-white shadow-sm">
            <span style={{ whiteSpace: 'pre-wrap' }}>{content}</span>
          </div>
        )}
      </div>
    </div>
  )
}

function AssistantBubble({
  msg,
  streaming,
  sessionId,
  onFollowUp,
}: {
  msg: StylistChatMessage
  streaming: boolean
  sessionId?: string
  onFollowUp?: (q: string) => void
}) {
  const outfits = msg.structured?.recommended_outfits ?? []
  const hints: StylingHint[] = msg.structured?.styling_suggestions ?? []
  const gaps  = msg.structured?.purchase_gaps ?? []
  const followUps = msg.structured?.follow_up_questions ?? []

  return (
    <div className="flex gap-3 animate-slide-up">
      <div className="w-[30px] h-[30px] rounded-[10px] bg-slate-900 dark:bg-slate-700 flex-shrink-0 flex items-center justify-center shadow-sm mt-0.5">
        <Sparkles size={13} className="text-white" />
      </div>

      <div className="flex flex-col gap-3 max-w-[80%] min-w-0 flex-1 items-start">
        {/* Text reply — rendered as lightweight markdown for a polished output */}
        {msg.content && (
          <div className="px-4 py-3 rounded-2xl rounded-tl-sm bg-white dark:bg-slate-800 text-slate-700 dark:text-slate-200 shadow-card border border-cream-200 dark:border-slate-700">
            <FormattedMessage content={msg.content} />
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
                onAskFollowUp={onFollowUp}
              />
            ))}
          </div>
        )}

        {/* Styling suggestions */}
        {hints.length > 0 && (
          <div className="space-y-2 w-full">
            <p className="text-xs font-semibold uppercase tracking-widest text-slate-400 flex items-center gap-1.5">
              <Lightbulb size={11} /> Styling Tips
            </p>
            {hints.map((hint, i) => (
              <div
                key={i}
                className={`flex items-start gap-2.5 p-3 rounded-xl border text-sm ${HINT_STYLE[hint.category] ?? HINT_STYLE.general}`}
              >
                <span className="flex-shrink-0 mt-0.5 text-base">
                  {HINT_EMOJI[hint.category] ?? '💡'}
                </span>
                <div className="flex-1 min-w-0">
                  <p className="leading-snug">{hint.tip}</p>
                  {hint.closet_item_name && (
                    <p className="mt-1 text-xs font-semibold opacity-80">→ {hint.closet_item_name}</p>
                  )}
                </div>
              </div>
            ))}
          </div>
        )}

        {/* Purchase gaps */}
        {gaps.length > 0 && (
          <div className="p-3 rounded-2xl bg-amber-50 dark:bg-amber-900/20 border border-amber-200 dark:border-amber-800 text-sm space-y-1.5 w-full">
            <p className="font-semibold text-amber-700 dark:text-amber-400 text-xs flex items-center gap-1.5">
              <AlertTriangle size={12} /> Missing from your closet
            </p>
            {gaps.map((g, i) => (
              <p key={i} className="text-xs text-amber-700 dark:text-amber-300 flex gap-2">
                <span>•</span>
                <span>
                  <strong className="capitalize">{g.item || g.category}</strong>
                  {g.outfit_type ? (
                    <span className="opacity-80"> for {g.outfit_type} outfits</span>
                  ) : null}
                  {' — '}{g.reason}
                </span>
              </p>
            ))}
          </div>
        )}

        {/* Follow-up suggestions — clickable */}
        {followUps.length > 0 && (
          <div className="flex flex-wrap gap-1.5">
            {followUps.map((q, i) => (
              <button
                key={i}
                type="button"
                onClick={() => onFollowUp?.(q)}
                disabled={!onFollowUp}
                className="text-xs px-3 py-1.5 rounded-full bg-brand-50 dark:bg-brand-900/30 text-brand-700 dark:text-brand-300 border border-brand-200 dark:border-brand-700 hover:bg-brand-100 dark:hover:bg-brand-900/50 transition-colors disabled:cursor-default"
              >
                {q}
              </button>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}

function ThinkingBubble() {
  return (
    <div className="flex gap-3 animate-slide-up">
      <div className="w-[30px] h-[30px] rounded-[10px] bg-slate-900 dark:bg-slate-700 flex-shrink-0 flex items-center justify-center shadow-sm">
        <Sparkles size={13} className="text-white" />
      </div>
      <div className="px-4 py-3.5 rounded-2xl rounded-tl-sm bg-white dark:bg-slate-800 border border-cream-200 dark:border-slate-700 shadow-card">
        <div className="flex gap-1 items-center">
          {[0, 1, 2].map(i => (
            <div key={i} className="w-[7px] h-[7px] rounded-full bg-brand-400 animate-pulse-soft" style={{ animationDelay: `${i * 0.2}s` }} />
          ))}
        </div>
      </div>
    </div>
  )
}

// ── History tab ───────────────────────────────────────────────────────────────

function HistoryPanel({
  active,
  onLoadSession,
  onDeleteSession,
  currentSessionId,
}: {
  active: boolean
  onLoadSession: (sessionId: string, title: string) => void
  onDeleteSession: (sessionId: string) => void
  currentSessionId: string | null
}) {
  const [sessions, setSessions] = useState<AIChatSession[]>([])
  const [loading, setLoading] = useState(false)
  const [deletingId, setDeletingId] = useState<string | null>(null)
  const [deleteInProgress, setDeleteInProgress] = useState<string | null>(null)

  useEffect(() => {
    if (!active) return
    setLoading(true)
    aiChatSessionsApi.list()
      .then(s => setSessions(s))
      .catch(() => {/* silent */})
      .finally(() => setLoading(false))
  }, [active])

  const handleDeleteConfirm = async (sessionId: string) => {
    setDeleteInProgress(sessionId)
    try {
      await aiChatSessionsApi.deleteSession(sessionId)
      setSessions(prev => prev.filter(s => s.id !== sessionId))
      onDeleteSession(sessionId)
    } catch {
      // silent — session list still shows; user can retry
    } finally {
      setDeleteInProgress(null)
      setDeletingId(null)
    }
  }

  function relTime(iso: string) {
    const diff = Date.now() - new Date(iso).getTime()
    const m = Math.floor(diff / 60000)
    if (m < 2) return 'just now'
    if (m < 60) return `${m}m ago`
    const h = Math.floor(m / 60)
    if (h < 24) return `${h}h ago`
    return `${Math.floor(h / 24)}d ago`
  }

  if (loading) {
    return (
      <div className="flex-1 min-h-0 flex items-center justify-center bg-cream-50 dark:bg-slate-950/40">
        <div className="h-5 w-5 rounded-full border-2 border-brand-400 border-t-transparent animate-spin" />
      </div>
    )
  }

  if (sessions.length === 0) {
    return (
      <div className="flex-1 min-h-0 flex flex-col items-center justify-center gap-2 px-6 text-center bg-cream-50 dark:bg-slate-950/40">
        <MessageSquare size={26} className="text-slate-300 dark:text-slate-600" />
        <p className="text-sm text-slate-400">No conversations yet</p>
        <p className="text-xs text-slate-300 dark:text-slate-600">Start chatting and your sessions will appear here</p>
      </div>
    )
  }

  return (
    <div className="flex-1 min-h-0 overflow-y-auto chat-scroll p-6 bg-cream-50 dark:bg-slate-950/40 flex flex-col gap-2 w-full max-w-[860px] mx-auto">
      {sessions.map(session => {
        const isActive = currentSessionId === session.id
        const isConfirming = deletingId === session.id
        const isDeleting = deleteInProgress === session.id

        return (
          <div
            key={session.id}
            className={cn(
              'group rounded-2xl border bg-white dark:bg-slate-800 shadow-sm transition-colors overflow-hidden',
              isActive
                ? 'border-brand-200 dark:border-brand-800/60 ring-1 ring-brand-100 dark:ring-brand-900/40'
                : 'border-cream-200 dark:border-slate-700 hover:border-brand-200 dark:hover:border-brand-800/60 hover:bg-brand-50/60 dark:hover:bg-brand-900/10',
            )}
          >
            <div className="flex items-center">
              <button
                type="button"
                onClick={() => onLoadSession(session.id, session.title)}
                disabled={isDeleting}
                className="flex-1 flex items-center gap-3 px-4 py-3.5 text-left min-w-0"
              >
                <div className={cn(
                  'w-8 h-8 rounded-[10px] flex-shrink-0 flex items-center justify-center',
                  isActive ? 'bg-brand-100 dark:bg-brand-500/20' : 'bg-brand-50 dark:bg-slate-700',
                )}>
                  <MessageSquare size={14} className="text-brand-500" />
                </div>
                <div className="min-w-0 flex-1">
                  <p className={cn(
                    'text-sm font-semibold truncate leading-snug',
                    isActive ? 'text-brand-700 dark:text-brand-300' : 'text-slate-900 dark:text-slate-100',
                  )}>
                    {session.title}
                  </p>
                  <p className="text-[11px] text-slate-400 flex items-center gap-1 mt-0.5">
                    <Clock size={9} />
                    {relTime(session.updated_at)}
                  </p>
                </div>
                <ChevronRight size={14} className="text-slate-300 dark:text-slate-600 flex-shrink-0" />
              </button>

              {/* Delete trigger — appears on row hover */}
              <button
                type="button"
                onClick={e => { e.stopPropagation(); setDeletingId(isConfirming ? null : session.id) }}
                disabled={isDeleting}
                title="Delete this chat"
                className={cn(
                  'flex-shrink-0 p-2 mr-2 rounded-lg transition-all',
                  isConfirming
                    ? 'opacity-100 text-red-500 bg-red-50 dark:bg-red-900/20'
                    : 'opacity-0 group-hover:opacity-100 text-slate-400 hover:text-red-500 hover:bg-red-50 dark:hover:bg-red-900/20',
                )}
              >
                {isDeleting ? (
                  <div className="h-3.5 w-3.5 rounded-full border-2 border-red-400 border-t-transparent animate-spin" />
                ) : (
                  <Trash2 size={13} />
                )}
              </button>
            </div>

            {/* Inline delete confirmation */}
            {isConfirming && (
              <div className="flex items-center justify-between gap-2 px-4 py-2.5 bg-red-50 dark:bg-red-900/20 border-t border-red-100 dark:border-red-800/40">
                <p className="text-xs text-red-700 dark:text-red-400 font-medium">Delete this chat?</p>
                <div className="flex items-center gap-2">
                  <button
                    type="button"
                    onClick={() => setDeletingId(null)}
                    className="text-[11px] font-medium text-slate-500 dark:text-slate-400 hover:text-slate-700 dark:hover:text-slate-200 transition-colors"
                  >
                    Cancel
                  </button>
                  <button
                    type="button"
                    onClick={() => handleDeleteConfirm(session.id)}
                    disabled={isDeleting}
                    className="text-[11px] font-bold text-white bg-red-500 hover:bg-red-600 px-2.5 py-1 rounded-lg transition-colors disabled:opacity-50"
                  >
                    Delete
                  </button>
                </div>
              </div>
            )}
          </div>
        )
      })}
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
  const [tab, setTab] = useState<'chat' | 'history'>('chat')
  const [loadingHistory, setLoadingHistory] = useState(false)
  const scrollRef = useRef<HTMLDivElement>(null)
  const bottomRef = useRef<HTMLDivElement>(null)
  const cancelRef = useRef(false)
  const hasRestored = useRef(false)
  // Set as soon as the user acts (send / pick a session / new chat) so the
  // async resume below can never clobber an in-flight conversation.
  const interactedRef = useRef(false)

  // ── Restore handoff from floating chat, else resume the latest session ──────
  useEffect(() => {
    if (hasRestored.current) return
    hasRestored.current = true

    // 1) A handoff from the floating chat widget always wins.
    let handedOff = false
    try {
      const raw = sessionStorage.getItem('ch:ai-chat-handoff')
      if (raw) {
        sessionStorage.removeItem('ch:ai-chat-handoff')
        const { sessionId: sid, messages: msgs } = JSON.parse(raw) as {
          sessionId: string | null
          messages: Array<{
            id: string; role: string; content: string
            structured: StylistChatMessage['structured'] | null
            timestamp: string
          }>
        }
        const restored: StylistChatMessage[] = msgs
          .filter(m => m.role === 'user' || m.role === 'assistant')
          .map(m => ({
            id: m.id,
            role: m.role as 'user' | 'assistant',
            content: m.content,
            structured: m.structured,
            timestamp: new Date(m.timestamp),
          }))
        if (restored.length > 0) {
          handedOff = true
          setMessages(restored)
          if (sid) setSessionId(sid)
        }
      }
    } catch { /* ignore bad storage */ }
    if (handedOff) return

    // 2) Otherwise pick up where the user left off: resume the most recent
    //    session if it's fresh. Older ones stay a tap away in History.
    //    No unmount-cancel flag: StrictMode's dev double-mount would cancel
    //    the fetch permanently (hasRestored blocks the re-run), and a
    //    post-unmount setState is a harmless no-op. interactedRef keeps a
    //    late response from clobbering anything the user started meanwhile.
    ;(async () => {
      try {
        const sessions = await aiChatSessionsApi.list() // newest first
        const latest = sessions[0]
        if (!latest) return
        if (Date.now() - new Date(latest.updated_at).getTime() > RESUME_WINDOW_MS) return
        const msgs = await aiChatSessionsApi.getMessages(latest.id)
        const converted: StylistChatMessage[] = msgs
          .map(apiMsgToStylist)
          .filter((m): m is StylistChatMessage => m !== null)
        if (interactedRef.current || converted.length === 0) return
        setMessages(converted)
        setSessionId(latest.id)
      } catch { /* welcome screen is a fine fallback */ }
    })()
  }, [])

  // ── Auto-scroll ──────────────────────────────────────────────────────────────
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  // ── Load a past session from history ────────────────────────────────────────
  const loadSession = useCallback(async (sid: string, _title: string) => {
    interactedRef.current = true
    setLoadingHistory(true)
    setTab('chat')
    setError(null)
    cancelRef.current = true
    setStreaming(false)
    try {
      const msgs = await aiChatSessionsApi.getMessages(sid)
      const converted: StylistChatMessage[] = msgs
        .map(apiMsgToStylist)
        .filter((m): m is StylistChatMessage => m !== null)
      setMessages(converted.length > 0 ? converted : [WELCOME])
      setSessionId(sid)
    } catch {
      setError('Could not load session. Please try again.')
    } finally {
      setLoadingHistory(false)
    }
  }, [])

  // ── Send message ─────────────────────────────────────────────────────────────
  const send = useCallback(async (text: string, ctx?: AIChatContext, images?: string[]) => {
    const trimmed = text.trim()
    if (!trimmed && (!images || images.length === 0)) return
    if (streaming) return
    interactedRef.current = true
    cancelRef.current = false
    setTab('chat')

    const userMsg: StylistChatMessage = {
      id: generateId(),
      role: 'user',
      content: trimmed || '(see attached image)',
      images,
      timestamp: new Date(),
    }
    setMessages(m => [...m, userMsg])
    try { localStorage.setItem(AI_CHAT_TRIED_KEY, '1') } catch { /* ignore */ }
    setStreaming(true)
    setError(null)

    const aiMsgId = generateId()
    setMessages(m => [...m, { id: aiMsgId, role: 'assistant', content: '', timestamp: new Date() }])

    try {
      const history = messages
        .filter(m => m.id !== 'welcome' && m.content)
        .slice(-12)
        .map(m => ({ role: m.role, content: m.content }))

      await streamMessage(
        { message: trimmed || '(see attached image)', sessionId, context: ctx, history, images },
        {
          onSession: (sid) => { if (!cancelRef.current) setSessionId(sid) },
          onToken: (content) => {
            if (cancelRef.current) return
            setMessages(m => m.map(msg =>
              msg.id === aiMsgId ? { ...msg, content: msg.content + content } : msg,
            ))
          },
          onCorrection: ({ reply, note }) => {
            if (cancelRef.current) return
            // Grounding gate flagged the streamed text — replace it with the
            // grounded reply, or append the soft note.
            setMessages(m => m.map(msg =>
              msg.id === aiMsgId
                ? { ...msg, content: reply ?? (note ? `${msg.content}\n\n_${note}_` : msg.content) }
                : msg,
            ))
          },
          onStructured: (payload) => {
            if (cancelRef.current) return
            setMessages(m => m.map(msg =>
              msg.id === aiMsgId
                ? {
                    ...msg,
                    // The structured event carries the authoritative grounded reply.
                    content: payload.reply || msg.content,
                    structured: {
                      reply: payload.reply,
                      recommended_outfits: payload.recommended_outfits,
                      styling_suggestions: payload.styling_suggestions ?? [],
                      purchase_gaps: payload.purchase_gaps,
                      follow_up_questions: payload.follow_up_questions,
                    },
                  }
                : msg,
            ))
          },
          onDone: () => { /* streaming flag cleared in finally */ },
          onError: (errMsg) => {
            if (cancelRef.current) return
            setError(errMsg)
            setMessages(m => m.map(msg =>
              msg.id === aiMsgId
                ? { ...msg, content: msg.content || `I'm having trouble connecting right now. (${errMsg})` }
                : msg,
            ))
          },
        },
      )
    } catch (e) {
      if (cancelRef.current) return
      const errMsg = e instanceof Error ? e.message : 'Network error'
      setError(errMsg)
      setMessages(m => m.map(msg =>
        msg.id === aiMsgId
          ? { ...msg, content: msg.content || `I'm having trouble connecting right now. (${errMsg})` }
          : msg,
      ))
    } finally {
      if (!cancelRef.current) setStreaming(false)
    }
  }, [streaming, messages, sessionId])

  const stopStreaming = () => { cancelRef.current = true; setStreaming(false) }

  const newChat = useCallback(() => {
    interactedRef.current = true
    cancelRef.current = true
    setStreaming(false)
    setMessages([WELCOME])
    setSessionId(null)
    setTab('chat')
    setError(null)
  }, [])

  // If the user deletes the currently-active session, start a fresh chat
  const handleDeleteSession = useCallback((deletedId: string) => {
    if (deletedId === sessionId) {
      newChat()
    }
  }, [sessionId, newChat])

  const isAtStart = messages.length === 1 && messages[0].id === 'welcome'
  const visibleMessages = messages.filter(m => m.id !== 'welcome')
  const lastMsg = messages[messages.length - 1]
  const showThinking =
    streaming && lastMsg?.role === 'assistant' && lastMsg?.content === ''

  const tabBtn = (t: 'chat' | 'history', label: string) => (
    <button
      onClick={() => setTab(t)}
      className={cn(
        'px-4 py-1.5 rounded-[10px] text-xs transition-colors',
        tab === t
          ? 'bg-white dark:bg-slate-700 text-slate-900 dark:text-white shadow-sm font-semibold'
          : 'text-slate-500 dark:text-slate-400 font-medium hover:text-slate-800 dark:hover:text-slate-200',
      )}
    >
      {label}
    </button>
  )

  return (
    <div className="animate-fade-in">
      {/* Mobile: 176px = 64 header + 16 main top pad + 96 main bottom pad (clears
          the fixed bottom nav), so the composer is never hidden behind it.
          dvh tracks the collapsing mobile URL bar. */}
      <div className="relative w-full h-[calc(100dvh-176px)] md:h-[calc(100vh-112px)] bg-white dark:bg-slate-900 rounded-[20px] border border-cream-200 dark:border-slate-700/70 shadow-card flex flex-col overflow-hidden">

        {/* ── Card header ─────────────────────────────────────────────────────── */}
        <div className="flex-shrink-0 flex items-center justify-between gap-3 px-4 sm:px-5 py-3 border-b border-cream-200 dark:border-slate-700/70">
          <div className="flex items-center gap-2.5 min-w-0">
            <div className="w-9 h-9 rounded-xl bg-gradient-brand flex items-center justify-center shadow-sm flex-shrink-0">
              <Sparkles size={16} className="text-white" />
            </div>
            <div className="min-w-0">
              <div className="font-display font-bold text-[15px] leading-tight text-slate-900 dark:text-white">FANI</div>
              <div className="text-[10px] text-slate-400 truncate">
                {closetItems.length > 0 ? `${closetItems.length} wardrobe items` : 'Add items to your closet'}
              </div>
            </div>
          </div>

          <div className="flex bg-slate-100 dark:bg-slate-800 rounded-xl p-[3px] flex-shrink-0">
            {tabBtn('chat', 'Chat')}
            {tabBtn('history', 'History')}
          </div>

          <button
            onClick={newChat}
            className="inline-flex items-center gap-1.5 px-3 sm:px-3.5 py-2 rounded-xl text-xs font-medium text-slate-500 dark:text-slate-400 bg-transparent border border-cream-200 dark:border-slate-700 hover:bg-slate-100 dark:hover:bg-slate-800 hover:text-slate-700 dark:hover:text-slate-200 transition-colors flex-shrink-0"
            title="New chat"
          >
            <Plus size={13} />
            <span className="hidden sm:inline">New</span>
          </button>
        </div>

        {/* ── Chat tab ────────────────────────────────────────────────────────── */}
        {tab === 'chat' && (
          <>
            <div ref={scrollRef} className="flex-1 min-h-0 overflow-y-auto chat-scroll bg-cream-50 dark:bg-slate-950/40">
              {loadingHistory ? (
                <div className="h-full flex items-center justify-center">
                  <FaniLoader size="md" messages={['Loading your chat…']} />
                </div>
              ) : isAtStart ? (
                /* Welcome / empty state */
                <div className="h-full flex flex-col items-center justify-center gap-5 px-6 py-8 text-center">
                  <div className="w-14 h-14 rounded-[18px] bg-gradient-brand flex items-center justify-center shadow-[0_0_24px_rgba(13,148,136,0.45)]">
                    <Sparkles size={26} className="text-white" />
                  </div>
                  <div>
                    <h1 className="font-display font-bold text-[26px] leading-tight text-slate-900 dark:text-white">
                      What should we style today?
                    </h1>
                    <p className="mt-1.5 text-sm text-slate-500 dark:text-slate-400">
                      I'll build outfits from your actual wardrobe — just ask.
                    </p>
                  </div>
                  <div className="flex flex-wrap gap-2 justify-center max-w-lg">
                    {QUICK_PROMPTS.map(p => (
                      <button
                        key={p.text}
                        onClick={() => send(p.text)}
                        disabled={streaming}
                        className="text-xs px-3.5 py-2.5 rounded-full bg-white dark:bg-slate-800 border border-cream-200 dark:border-slate-700 text-slate-600 dark:text-slate-300 shadow-sm hover:border-brand-300 hover:bg-brand-50 hover:text-brand-700 dark:hover:bg-brand-900/20 dark:hover:text-brand-300 transition-colors disabled:opacity-40"
                      >
                        {p.label}
                      </button>
                    ))}
                  </div>
                </div>
              ) : (
                /* Message stream */
                <div className="p-5 sm:p-6 flex flex-col gap-4 w-full max-w-[860px] mx-auto">
                  {visibleMessages.map(msg =>
                    msg.role === 'user' ? (
                      <UserBubble key={msg.id} content={msg.content} images={msg.images} />
                    ) : (
                      <AssistantBubble
                        key={msg.id}
                        msg={msg}
                        streaming={
                          streaming &&
                          msg === lastMsg &&
                          msg.role === 'assistant' &&
                          msg.content === ''
                        }
                        sessionId={sessionId ?? undefined}
                        onFollowUp={streaming ? undefined : (q) => send(q)}
                      />
                    ),
                  )}
                  {showThinking && <ThinkingBubble />}
                  <div ref={bottomRef} />
                </div>
              )}
            </div>

            {/* Warnings */}
            {(error || closetItems.length === 0) && !loadingHistory && (
              <div className="flex-shrink-0 px-5 pt-3 space-y-2 w-full max-w-[860px] mx-auto">
                {closetItems.length === 0 && (
                  <div className="rounded-xl px-3 py-2 bg-amber-50 dark:bg-amber-900/20 border border-amber-200 dark:border-amber-800 text-amber-700 dark:text-amber-300 text-xs flex items-center gap-2">
                    <AlertTriangle size={13} className="flex-shrink-0" />
                    Your wardrobe is empty — upload items first for the best outfit suggestions.
                  </div>
                )}
                {error && (
                  <div className="rounded-xl px-3 py-2 bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 text-red-600 dark:text-red-300 text-xs flex items-center gap-2">
                    <AlertTriangle size={12} className="flex-shrink-0" />
                    {error}
                  </div>
                )}
              </div>
            )}

            {/* Input */}
            <div className="flex-shrink-0 px-4 sm:px-5 py-3 border-t border-cream-200 dark:border-slate-700/70 bg-white dark:bg-slate-900">
              <div className="w-full max-w-[860px] mx-auto">
                <ChatInput
                  onSend={send}
                  streaming={streaming}
                  onStop={stopStreaming}
                  disabled={loadingHistory}
                />
              </div>
            </div>
          </>
        )}

        {/* ── History tab ─────────────────────────────────────────────────────── */}
        {tab === 'history' && (
          <HistoryPanel
            active={tab === 'history'}
            onLoadSession={loadSession}
            onDeleteSession={handleDeleteSession}
            currentSessionId={sessionId}
          />
        )}
      </div>
    </div>
  )
}
