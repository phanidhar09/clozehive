import { useState, useRef, useEffect, useCallback } from 'react'
import { AnimatePresence, motion, useMotionValue } from 'framer-motion'
import { Sparkles, X, Maximize2, Send, Square, AlertTriangle } from 'lucide-react'
import { Link } from 'react-router-dom'
import { cn } from '@/lib/utils'
import { generateId } from '@/lib/utils'
import { sendMessage } from '@/services/aiChatApi'
import OutfitRecommendationCard from './OutfitRecommendationCard'
import type { StylistChatMessage, AIChatContext } from '@/types'

const STORAGE_KEY = 'ch:ai-btn-pos'

const WELCOME: StylistChatMessage = {
  id: 'welcome',
  role: 'assistant',
  content: "Hey! 👋 I'm FANI — your Fashion AI Nurturing Individuality. Ask me what to wear and I'll build outfits from your actual closet.",
  timestamp: new Date(),
}

const QUICK = [
  'What should I wear today?',
  'Build me a smart casual outfit',
  'Outfit for dinner tonight',
  'I feel like looking bold',
]

// ── Message bubble ────────────────────────────────────────────────────────────

interface BubbleProps { msg: StylistChatMessage; streaming?: boolean; sessionId?: string }

function Bubble({ msg, streaming = false, sessionId }: BubbleProps) {
  const isUser = msg.role === 'user'
  const outfits = msg.structured?.recommended_outfits ?? []
  const gaps = msg.structured?.purchase_gaps ?? []
  const followUps = msg.structured?.follow_up_questions ?? []

  return (
    <div className={cn('flex gap-2 animate-slide-up', isUser && 'flex-row-reverse')}>
      <div className={cn(
        'w-7 h-7 rounded-full flex-shrink-0 flex items-center justify-center text-[10px] font-bold shadow-sm mt-0.5',
        isUser ? 'bg-gradient-brand text-white' : 'bg-slate-900 dark:bg-slate-700 text-white',
      )}>
        {isUser ? 'You' : <Sparkles size={12} />}
      </div>

      <div className={cn('flex flex-col gap-2 max-w-[80%]', isUser && 'items-end')}>
        {msg.content && (
          <div className={cn(
            'px-3 py-2 rounded-2xl text-xs leading-relaxed',
            isUser
              ? 'bg-gradient-brand text-white rounded-tr-sm'
              : 'bg-white dark:bg-slate-800 text-slate-700 dark:text-slate-200 shadow-sm rounded-tl-sm border border-cream-200 dark:border-slate-700',
          )}>
            <span style={{ whiteSpace: 'pre-wrap' }}>{msg.content}</span>
            {streaming && <span className="inline-block w-0.5 h-3.5 bg-brand-500 ml-0.5 animate-pulse align-middle" />}
          </div>
        )}

        {outfits.length > 0 && (
          <div className="w-full space-y-2">
            {outfits.map((outfit, i) => (
              <OutfitRecommendationCard key={outfit.title + i} outfit={outfit} rank={i} sessionId={sessionId} />
            ))}
          </div>
        )}

        {gaps.length > 0 && (
          <div className="w-full p-2.5 rounded-xl bg-amber-50 dark:bg-amber-900/20 border border-amber-200 dark:border-amber-800 text-xs space-y-1">
            <p className="font-semibold text-amber-700 dark:text-amber-400">Missing from your closet:</p>
            {gaps.map((g, i) => (
              <p key={i} className="text-amber-600 dark:text-amber-300 flex gap-1">
                <span>•</span>
                <span><strong className="capitalize">{g.category}</strong> — {g.reason}</span>
              </p>
            ))}
          </div>
        )}

        {followUps.length > 0 && (
          <div className="flex flex-wrap gap-1">
            {followUps.map((q, i) => (
              <span key={i} className="text-[10px] px-2 py-1 rounded-full bg-slate-100 dark:bg-slate-700 text-slate-500 dark:text-slate-400 border border-slate-200 dark:border-slate-600 cursor-default">
                {q}
              </span>
            ))}
          </div>
        )}

        <span className="text-[9px] text-slate-400 px-1">
          {msg.timestamp.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
        </span>
      </div>
    </div>
  )
}

// ── Draggable floating button + chat popup ────────────────────────────────────

export default function FloatingAIChat() {
  const [open, setOpen] = useState(false)
  const [messages, setMessages] = useState<StylistChatMessage[]>([WELCOME])
  const [input, setInput] = useState('')
  const [streaming, setStreaming] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [sessionId, setSessionId] = useState<string | null>(null)
  const bottomRef = useRef<HTMLDivElement>(null)
  const cancelRef = useRef(false)
  const inputRef = useRef<HTMLInputElement>(null)
  const isDragging = useRef(false)

  // ── Persisted drag position ───────────────────────────────────────────────
  const dragX = useMotionValue(0)
  const dragY = useMotionValue(0)

  useEffect(() => {
    try {
      const saved = localStorage.getItem(STORAGE_KEY)
      if (saved) {
        const { x, y } = JSON.parse(saved) as { x: number; y: number }
        // Clamp to viewport so a saved position on a different screen size doesn't go off-screen
        const maxX = window.innerWidth - 80
        const maxY = window.innerHeight - 80
        dragX.set(Math.max(-maxX, Math.min(0, x)))
        dragY.set(Math.max(-maxY, Math.min(0, y)))
      }
    } catch { /* ignore bad storage */ }
  }, [])

  const savePosition = () => {
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify({ x: dragX.get(), y: dragY.get() }))
    } catch { /* ignore */ }
  }

  // ── Listen for navbar open event ──────────────────────────────────────────
  useEffect(() => {
    const handler = () => {
      setOpen(true)
      try { localStorage.setItem('ch_ai_chat_tried', '1') } catch { /* ignore */ }
    }
    window.addEventListener('ch:open-ai-chat', handler)
    return () => window.removeEventListener('ch:open-ai-chat', handler)
  }, [])

  // ── Auto-scroll ───────────────────────────────────────────────────────────
  useEffect(() => {
    if (open) {
      bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
      setTimeout(() => inputRef.current?.focus(), 100)
    }
  }, [messages, open])

  // ── Send message ──────────────────────────────────────────────────────────
  const send = useCallback(async (text: string, ctx?: AIChatContext) => {
    const trimmed = text.trim()
    if (!trimmed || streaming) return
    cancelRef.current = false

    const userMsg: StylistChatMessage = { id: generateId(), role: 'user', content: trimmed, timestamp: new Date() }
    setMessages(m => [...m, userMsg])
    setInput('')
    setStreaming(true)
    setError(null)

    const aiMsgId = generateId()
    setMessages(m => [...m, { id: aiMsgId, role: 'assistant', content: '', timestamp: new Date() }])

    try {
      const history = messages
        .filter(m => m.role !== 'assistant' || m.id !== 'welcome')
        .map(m => ({ role: m.role, content: m.content }))

      const res = await sendMessage({ message: trimmed, sessionId, context: ctx, history })
      if (cancelRef.current) return

      setSessionId(res.session_id)
      setMessages(m => m.map(msg =>
        msg.id === aiMsgId
          ? { ...msg, content: res.reply, structured: { reply: res.reply, recommended_outfits: res.recommended_outfits, purchase_gaps: res.purchase_gaps, follow_up_questions: res.follow_up_questions } }
          : msg,
      ))
    } catch (e) {
      if (cancelRef.current) return
      setError(e instanceof Error ? e.message : 'Network error')
      setMessages(m => m.map(msg2 => msg2.id === aiMsgId ? { ...msg2, content: 'Something went wrong. Please try again.' } : msg2))
    } finally {
      setStreaming(false)
    }
  }, [streaming, messages, sessionId])

  const stopStreaming = () => { cancelRef.current = true; setStreaming(false) }
  const newChat = () => { cancelRef.current = true; setStreaming(false); setMessages([WELCOME]); setSessionId(null); setError(null) }

  return (
    <>
      {/* ── Draggable trigger button ─────────────────────────────────────── */}
      <AnimatePresence>
        {!open && (
          <motion.button
            drag
            dragMomentum={false}
            dragElastic={0}
            style={{ x: dragX, y: dragY }}
            onDragStart={() => { isDragging.current = true }}
            onDragEnd={() => {
              savePosition()
              // small delay so click doesn't fire right after drag end
              setTimeout(() => { isDragging.current = false }, 100)
            }}
            onClick={() => {
              if (!isDragging.current) {
                setOpen(true)
                try { localStorage.setItem('ch_ai_chat_tried', '1') } catch { /* ignore */ }
              }
            }}
            initial={{ scale: 0, opacity: 0 }}
            animate={{ scale: 1, opacity: 1 }}
            exit={{ scale: 0, opacity: 0 }}
            transition={{ type: 'spring', stiffness: 400, damping: 25 }}
            className="fixed bottom-6 right-6 z-50 w-14 h-14 rounded-full bg-gradient-brand shadow-lg hover:shadow-xl hover:opacity-90 flex items-center justify-center cursor-grab active:cursor-grabbing select-none"
            aria-label="Open FANI"
            title="Drag to reposition · Click to open"
          >
            <Sparkles size={22} className="text-white pointer-events-none" />
          </motion.button>
        )}
      </AnimatePresence>

      {/* ── Chat popup — anchored at same drag position ──────────────────── */}
      <AnimatePresence>
        {open && (
          <motion.div
            drag
            dragMomentum={false}
            dragElastic={0}
            dragHandle=".drag-handle"
            style={{ x: dragX, y: dragY }}
            onDragEnd={savePosition}
            initial={{ opacity: 0, y: 24, scale: 0.95 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: 24, scale: 0.95 }}
            transition={{ type: 'spring', stiffness: 380, damping: 28 }}
            className="fixed bottom-6 right-6 z-50 w-[360px] max-w-[calc(100vw-24px)] rounded-2xl shadow-2xl bg-white dark:bg-slate-900 border border-cream-200 dark:border-slate-700 flex flex-col"
            style={{ maxHeight: 'min(620px, calc(100vh - 48px))' }}
          >
            {/* Header — drag handle */}
            <div className="drag-handle flex items-center justify-between px-4 py-3 border-b border-cream-200 dark:border-slate-700 bg-slate-900 dark:bg-slate-800 rounded-t-2xl flex-shrink-0 cursor-grab active:cursor-grabbing select-none">
              <div className="flex items-center gap-2">
                <div className="w-7 h-7 rounded-lg bg-gradient-brand flex items-center justify-center flex-shrink-0">
                  <Sparkles size={14} className="text-white" />
                </div>
                <div>
                  <p className="text-sm font-semibold text-white">FANI</p>
                  <p className="text-[10px] text-slate-400">Fashion AI Nurturing Individuality</p>
                </div>
              </div>
              <div className="flex gap-1">
                <Link
                  to="/ai-stylist"
                  className="p-1.5 rounded-lg hover:bg-slate-700 text-slate-400 hover:text-white transition-colors"
                  title="Open full screen"
                  onClick={() => setOpen(false)}
                >
                  <Maximize2 size={14} />
                </Link>
                <button
                  onClick={() => setOpen(false)}
                  className="p-1.5 rounded-lg hover:bg-slate-700 text-slate-400 hover:text-white transition-colors"
                >
                  <X size={14} />
                </button>
              </div>
            </div>

            {/* Messages */}
            <div className="flex-1 overflow-y-auto p-3 space-y-3 chat-scroll min-h-0">
              {messages.map(msg => (
                <Bubble
                  key={msg.id}
                  msg={msg}
                  streaming={streaming && msg === messages[messages.length - 1] && msg.role === 'assistant'}
                  sessionId={sessionId ?? undefined}
                />
              ))}

              {streaming && messages[messages.length - 1]?.content === '' && (
                <div className="flex gap-2">
                  <div className="w-7 h-7 rounded-full bg-slate-900 dark:bg-slate-700 flex items-center justify-center flex-shrink-0">
                    <Sparkles size={12} className="text-white" />
                  </div>
                  <div className="px-3 py-2 bg-white dark:bg-slate-800 border border-cream-200 dark:border-slate-700 rounded-2xl rounded-tl-sm shadow-sm flex gap-1 items-center">
                    {[0, 1, 2].map(i => (
                      <div key={i} className="w-1.5 h-1.5 rounded-full bg-brand-400 animate-pulse-soft" style={{ animationDelay: `${i * 0.2}s` }} />
                    ))}
                  </div>
                </div>
              )}

              {error && (
                <div className="flex items-center gap-2 text-xs text-red-500 px-2">
                  <AlertTriangle size={12} /> {error}
                </div>
              )}
              <div ref={bottomRef} />
            </div>

            {/* Quick prompts */}
            {messages.length <= 1 && (
              <div className="px-3 pb-2 flex gap-1.5 flex-wrap flex-shrink-0">
                {QUICK.map(q => (
                  <button
                    key={q}
                    onClick={() => send(q)}
                    disabled={streaming}
                    className="text-[10px] px-2 py-1 rounded-full bg-brand-50 dark:bg-brand-900/30 text-brand-700 dark:text-brand-300 border border-brand-200 dark:border-brand-800 hover:bg-brand-100 transition-colors disabled:opacity-40"
                  >
                    {q}
                  </button>
                ))}
              </div>
            )}

            {/* Input */}
            <div className="px-3 pb-3 flex-shrink-0 border-t border-cream-100 dark:border-slate-700 pt-2">
              <div className="flex gap-2 items-end">
                <input
                  ref={inputRef}
                  value={input}
                  onChange={e => setInput(e.target.value)}
                  onKeyDown={e => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send(input) } }}
                  placeholder="Ask about outfits…"
                  disabled={streaming}
                  className="flex-1 bg-slate-50 dark:bg-slate-800 border border-cream-200 dark:border-slate-600 rounded-xl px-3 py-2 text-xs text-slate-800 dark:text-slate-100 placeholder-slate-400 focus:outline-none focus:ring-1 focus:ring-brand-400 disabled:opacity-50"
                />
                {streaming ? (
                  <button onClick={stopStreaming} className="w-9 h-9 rounded-xl bg-red-500 hover:bg-red-600 flex items-center justify-center flex-shrink-0">
                    <Square size={12} className="text-white fill-white" />
                  </button>
                ) : (
                  <button onClick={() => send(input)} disabled={!input.trim()} className="w-9 h-9 rounded-xl bg-gradient-brand flex items-center justify-center flex-shrink-0 hover:opacity-90 active:scale-95 transition-all disabled:opacity-40">
                    <Send size={13} className="text-white" />
                  </button>
                )}
              </div>
              <button onClick={newChat} className="mt-1.5 text-[10px] text-slate-400 hover:text-slate-600 dark:hover:text-slate-300 transition-colors">
                + New chat
              </button>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </>
  )
}
