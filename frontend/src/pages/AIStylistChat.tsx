/**
 * AIStylistChat — full-page version of FANI.
 *
 * Features:
 * - Session handoff from the floating chat (sessionStorage key: ch:ai-chat-handoff)
 * - Sidebar history: lists past sessions, click to load messages
 * - Clickable follow-up question chips
 * - Styling suggestions panel (same as FloatingAIChat)
 * - General question support
 */

import { useState, useRef, useEffect, useCallback } from 'react'
import { AnimatePresence, motion } from 'framer-motion'
import BackButton from '@/components/ui/BackButton'
import {
  AlertTriangle,
  ChevronLeft,
  Clock,
  History,
  Lightbulb,
  MessageSquare,
  RefreshCw,
  Sparkles,
  Trash2,
  X,
} from 'lucide-react'
import { useApp } from '@/store'
import { generateId } from '@/lib/utils'
import { sendMessage, aiChatSessionsApi } from '@/services/aiChatApi'
import { cn } from '@/lib/utils'
import ChatInput from '@/components/ai-chat/ChatInput'
import OutfitRecommendationCard from '@/components/ai-chat/OutfitRecommendationCard'
import type { StylistChatMessage, AIChatContext, StylingHint, AIChatSession } from '@/types'

// ── Constants ─────────────────────────────────────────────────────────────────

const WELCOME: StylistChatMessage = {
  id: 'welcome',
  role: 'assistant',
  content:
    "Hey! I'm FANI — your Fashion Analysis and Nurturing Intelligence. I can build outfits from your actual wardrobe, answer styling questions, and help you look your best. What's on your mind?",
  timestamp: new Date(),
}

const QUICK_PROMPTS = [
  { label: '👕 Outfit today',     text: 'What should I wear today?' },
  { label: '🍽️ Dinner look',      text: 'Build me an outfit for dinner tonight' },
  { label: '💼 Office ready',     text: 'Create a smart casual office outfit' },
  { label: '✨ Improve my style', text: 'How can I improve my style with what I own?' },
  { label: '🔍 What am I missing', text: 'What key items am I missing from my wardrobe?' },
  { label: '🔥 Bold outfit',      text: 'I want to look bold and confident today' },
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
    <div className="flex justify-end gap-3 animate-slide-up">
      <div className="max-w-[75%] flex flex-col items-end gap-2">
        {images && images.length > 0 && (
          <div className="flex gap-2 flex-wrap justify-end">
            {images.map((src, i) => (
              <img
                key={i}
                src={src}
                alt="uploaded"
                className="w-28 h-28 object-cover rounded-2xl rounded-tr-sm shadow-sm border border-white/20"
              />
            ))}
          </div>
        )}
        {content && content !== '(see attached image)' && (
          <div className="px-4 py-3 rounded-2xl rounded-tr-sm text-sm leading-relaxed bg-gradient-brand text-white shadow-sm">
            <span style={{ whiteSpace: 'pre-wrap' }}>{content}</span>
          </div>
        )}
      </div>
      <div className="w-8 h-8 rounded-full bg-gradient-brand flex-shrink-0 flex items-center justify-center text-white text-xs font-bold shadow-sm mt-0.5 select-none">
        You
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
      <div className="w-8 h-8 rounded-full bg-slate-900 dark:bg-slate-700 flex-shrink-0 flex items-center justify-center shadow-sm mt-0.5">
        <Sparkles size={14} className="text-white" />
      </div>

      <div className="flex flex-col gap-3 max-w-[80%] min-w-0 flex-1">
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
                onAskFollowUp={onFollowUp}
              />
            ))}
          </div>
        )}

        {/* Styling suggestions */}
        {hints.length > 0 && (
          <div className="space-y-2">
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
            <div key={i} className="w-2 h-2 rounded-full bg-brand-400 animate-pulse-soft" style={{ animationDelay: `${i * 0.2}s` }} />
          ))}
        </div>
      </div>
    </div>
  )
}

// ── History Sidebar ───────────────────────────────────────────────────────────

function HistorySidebar({
  open,
  onClose,
  onLoadSession,
  onDeleteSession,
  currentSessionId,
}: {
  open: boolean
  onClose: () => void
  onLoadSession: (sessionId: string, title: string) => void
  onDeleteSession: (sessionId: string) => void
  currentSessionId: string | null
}) {
  const [sessions, setSessions] = useState<AIChatSession[]>([])
  const [loading, setLoading] = useState(false)
  const [loadingSession, setLoadingSession] = useState<string | null>(null)
  const [deletingId, setDeletingId] = useState<string | null>(null)
  const [deleteInProgress, setDeleteInProgress] = useState<string | null>(null)

  useEffect(() => {
    if (!open) return
    setLoading(true)
    aiChatSessionsApi.list()
      .then(s => setSessions(s))
      .catch(() => {/* silent */})
      .finally(() => setLoading(false))
  }, [open])

  const handleClick = async (session: AIChatSession) => {
    if (loadingSession === session.id || deletingId === session.id) return
    setDeletingId(null)
    setLoadingSession(session.id)
    try {
      onLoadSession(session.id, session.title)
    } finally {
      setLoadingSession(null)
    }
  }

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

  return (
    <AnimatePresence>
      {open && (
        <>
          {/* Backdrop (mobile) */}
          <motion.div
            initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
            className="fixed inset-0 z-30 bg-black/30 lg:hidden"
            onClick={onClose}
          />
          <motion.aside
            initial={{ x: -280, opacity: 0 }}
            animate={{ x: 0, opacity: 1 }}
            exit={{ x: -280, opacity: 0 }}
            transition={{ type: 'spring', stiffness: 360, damping: 32 }}
            className="fixed left-0 top-0 bottom-0 z-40 w-72 bg-white dark:bg-slate-900 border-r border-cream-200 dark:border-slate-700 flex flex-col shadow-2xl lg:static lg:shadow-none lg:z-auto"
          >
            {/* Sidebar header */}
            <div className="flex items-center justify-between px-4 py-4 border-b border-cream-200 dark:border-slate-700 flex-shrink-0">
              <div className="flex items-center gap-2">
                <History size={15} className="text-brand-500" />
                <span className="font-semibold text-sm text-slate-800 dark:text-white">Chat History</span>
              </div>
              <button
                onClick={onClose}
                className="p-1.5 rounded-lg hover:bg-slate-100 dark:hover:bg-slate-800 text-slate-400 hover:text-slate-600 dark:hover:text-slate-300 transition-colors"
              >
                <X size={14} />
              </button>
            </div>

            {/* Session list */}
            <div className="flex-1 overflow-y-auto py-2">
              {loading ? (
                <div className="flex items-center justify-center py-8">
                  <div className="h-5 w-5 rounded-full border-2 border-brand-400 border-t-transparent animate-spin" />
                </div>
              ) : sessions.length === 0 ? (
                <div className="flex flex-col items-center gap-2 py-10 px-4 text-center">
                  <MessageSquare size={24} className="text-slate-300 dark:text-slate-600" />
                  <p className="text-sm text-slate-400">No conversations yet</p>
                  <p className="text-xs text-slate-300 dark:text-slate-600">Start chatting and your sessions will appear here</p>
                </div>
              ) : (
                <div className="space-y-0.5 px-1">
                  {sessions.map(session => {
                    const isActive = currentSessionId === session.id
                    const isConfirming = deletingId === session.id
                    const isDeleting = deleteInProgress === session.id
                    const isLoadingThis = loadingSession === session.id

                    return (
                      <div
                        key={session.id}
                        className={cn(
                          'rounded-xl overflow-hidden transition-colors',
                          isActive && !isConfirming
                            ? 'bg-brand-50 dark:bg-brand-900/20 ring-1 ring-brand-200 dark:ring-brand-800/50'
                            : 'hover:bg-slate-50 dark:hover:bg-slate-800/60',
                        )}
                      >
                        {/* Row */}
                        <div className="flex items-center group">
                          <button
                            type="button"
                            onClick={() => handleClick(session)}
                            disabled={isLoadingThis || isDeleting}
                            className="flex-1 text-left px-3 py-2.5 flex items-start gap-2.5 min-w-0"
                          >
                            <div className={cn(
                              'w-6 h-6 rounded-lg flex-shrink-0 flex items-center justify-center mt-0.5',
                              isActive ? 'bg-brand-100 dark:bg-brand-500/20' : 'bg-slate-100 dark:bg-slate-800',
                            )}>
                              {isLoadingThis ? (
                                <div className="h-3 w-3 rounded-full border-2 border-brand-400 border-t-transparent animate-spin" />
                              ) : (
                                <MessageSquare size={11} className={isActive ? 'text-brand-500' : 'text-slate-400'} />
                              )}
                            </div>
                            <div className="min-w-0 flex-1">
                              <p className={cn(
                                'text-sm font-medium truncate leading-snug',
                                isActive ? 'text-brand-700 dark:text-brand-300' : 'text-slate-700 dark:text-slate-200',
                              )}>
                                {session.title}
                              </p>
                              <p className="text-[10px] text-slate-400 flex items-center gap-1 mt-0.5">
                                <Clock size={9} />
                                {relTime(session.updated_at)}
                              </p>
                            </div>
                          </button>

                          {/* Delete trigger — appears on row hover */}
                          <button
                            type="button"
                            onClick={e => { e.stopPropagation(); setDeletingId(isConfirming ? null : session.id) }}
                            disabled={isDeleting}
                            title="Delete this chat"
                            className={cn(
                              'flex-shrink-0 p-2 mr-1 rounded-lg transition-all',
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
                          <div className="flex items-center justify-between gap-2 px-3 py-2 bg-red-50 dark:bg-red-900/20 border-t border-red-100 dark:border-red-800/40">
                            <p className="text-xs text-red-700 dark:text-red-400 font-medium">
                              Delete this chat?
                            </p>
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
              )}
            </div>
          </motion.aside>
        </>
      )}
    </AnimatePresence>
  )
}

// ── Main page ─────────────────────────────────────────────────────────────────

export default function AIStylistChat() {
  const { closetItems } = useApp()
  const [messages, setMessages] = useState<StylistChatMessage[]>([WELCOME])
  const [streaming, setStreaming] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [sessionId, setSessionId] = useState<string | null>(null)
  const [sessionTitle, setSessionTitle] = useState<string>('FANI — AI Stylist')
  const [showHistory, setShowHistory] = useState(false)
  const [loadingHistory, setLoadingHistory] = useState(false)
  const bottomRef = useRef<HTMLDivElement>(null)
  const cancelRef = useRef(false)
  const hasRestored = useRef(false)

  // ── Restore handoff from floating chat ──────────────────────────────────────
  useEffect(() => {
    if (hasRestored.current) return
    hasRestored.current = true
    try {
      const raw = sessionStorage.getItem('ch:ai-chat-handoff')
      if (!raw) return
      sessionStorage.removeItem('ch:ai-chat-handoff')
      const { sessionId: sid, messages: msgs } = JSON.parse(raw) as {
        sessionId: string | null
        messages: Array<{
          id: string; role: string; content: string
          structured: StylistChatMessage['structured'] | null
          timestamp: string
        }>
      }
      if (msgs.length === 0) return
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
        setMessages(restored)
        if (sid) setSessionId(sid)
      }
    } catch { /* ignore bad storage */ }
  }, [])

  // ── Auto-scroll ──────────────────────────────────────────────────────────────
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  // ── Load a past session from history ────────────────────────────────────────
  const loadSession = useCallback(async (sid: string, title: string) => {
    setLoadingHistory(true)
    setShowHistory(false)
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
      setSessionTitle(title)
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
    cancelRef.current = false

    const userMsg: StylistChatMessage = {
      id: generateId(),
      role: 'user',
      content: trimmed || '(see attached image)',
      images,
      timestamp: new Date(),
    }
    setMessages(m => [...m, userMsg])
    setStreaming(true)
    setError(null)

    const aiMsgId = generateId()
    setMessages(m => [...m, { id: aiMsgId, role: 'assistant', content: '', timestamp: new Date() }])

    try {
      const history = messages
        .filter(m => m.id !== 'welcome' && m.content)
        .slice(-12)
        .map(m => ({ role: m.role, content: m.content }))

      const res = await sendMessage({ message: trimmed || '(see attached image)', sessionId, context: ctx, history, images })
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
                styling_suggestions: res.styling_suggestions ?? [],
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

  const stopStreaming = () => { cancelRef.current = true; setStreaming(false) }

  const newChat = useCallback(() => {
    cancelRef.current = true
    setStreaming(false)
    setMessages([WELCOME])
    setSessionId(null)
    setSessionTitle('FANI — AI Stylist')
    setError(null)
  }, [])

  // If the user deletes the currently-active session, start a fresh chat
  const handleDeleteSession = useCallback((deletedId: string) => {
    if (deletedId === sessionId) {
      newChat()
    }
  }, [sessionId, newChat])

  const isAtStart = messages.length === 1 && messages[0].id === 'welcome'

  return (
    <div className="flex flex-col h-[calc(100vh-130px)] gap-0 animate-fade-in relative">
      <BackButton fallback="/dashboard" label="Back" className="mb-2 self-start" />

      {/* ── Content row ──────────────────────────────────────────────────────── */}
      <div className="flex flex-1 min-h-0 gap-0">

      {/* ── History sidebar ─────────────────────────────────────────────────── */}
      <HistorySidebar
        open={showHistory}
        onClose={() => setShowHistory(false)}
        onLoadSession={loadSession}
        onDeleteSession={handleDeleteSession}
        currentSessionId={sessionId}
      />

      {/* ── Main chat column ────────────────────────────────────────────────── */}
      <div className="flex flex-col flex-1 min-w-0">

        {/* Header */}
        <div className="flex items-center justify-between mb-4 flex-shrink-0">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-2xl bg-gradient-brand flex items-center justify-center shadow-md flex-shrink-0">
              <Sparkles size={18} className="text-white" />
            </div>
            <div className="min-w-0">
              <h2 className="font-display font-bold text-xl text-slate-800 dark:text-slate-100 truncate">
                {sessionTitle}
              </h2>
              <p className="text-xs text-slate-400">
                {closetItems.length > 0
                  ? `${closetItems.length} wardrobe items · Fashion Analysis and Nurturing Intelligence`
                  : 'Add items to your closet for personalised suggestions'}
              </p>
            </div>
          </div>

          <div className="flex gap-2 flex-shrink-0">
            <button
              onClick={() => setShowHistory(v => !v)}
              className={`btn-ghost text-xs gap-1.5 ${showHistory ? 'bg-brand-50 dark:bg-brand-900/30 text-brand-600 dark:text-brand-400' : ''}`}
              title="Chat history"
            >
              <History size={13} />
              <span className="hidden sm:inline">History</span>
            </button>
            <button onClick={newChat} className="btn-ghost text-xs gap-1.5" title="New chat">
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

        {/* Loading history indicator */}
        {loadingHistory && (
          <div className="flex items-center justify-center py-8">
            <div className="h-6 w-6 rounded-full border-2 border-brand-400 border-t-transparent animate-spin" />
          </div>
        )}

        {/* Message area */}
        {!loadingHistory && (
          <div className="flex-1 overflow-y-auto chat-scroll space-y-4 pb-4 min-h-0">
            {messages.map(msg =>
              msg.role === 'user' ? (
                <UserBubble key={msg.id} content={msg.content} images={msg.images} />
              ) : (
                <AssistantBubble
                  key={msg.id}
                  msg={msg}
                  streaming={
                    streaming &&
                    msg === messages[messages.length - 1] &&
                    msg.role === 'assistant' &&
                    msg.content === ''
                  }
                  sessionId={sessionId ?? undefined}
                  onFollowUp={streaming ? undefined : (q) => send(q)}
                />
              ),
            )}

            {streaming &&
              messages[messages.length - 1]?.role === 'assistant' &&
              messages[messages.length - 1]?.content === '' && (
                <ThinkingBubble />
              )}

            <div ref={bottomRef} />
          </div>
        )}

        {/* Quick prompts — only at start */}
        {isAtStart && !loadingHistory && (
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
            disabled={loadingHistory}
          />
        </div>
      </div>
      </div>{/* end content row */}
    </div>
  )
}
