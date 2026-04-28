import { useState, useRef, useEffect, useCallback } from 'react'
import { Send, Sparkles, RefreshCw, AlertTriangle, Square } from 'lucide-react'
import { useApp } from '@/store'
import { streamChat } from '@/lib/api'
import ChatMessage from '@/components/chat/ChatMessage'
import type { ChatMessage as ChatMsg } from '@/types'
import { generateId } from '@/lib/utils'

const QUICK_PROMPTS = [
  'What should I wear today?',
  'Suggest a formal outfit for a meeting',
  'Best outfit for a rainy day?',
  'What goes with my navy chinos?',
]

const WELCOME_MSG: ChatMsg = {
  id: 'welcome',
  role: 'assistant',
  content: "Hey! 👋 I'm your AI stylist. Tell me what you need and I'll suggest outfits from your wardrobe.",
  timestamp: new Date(),
}

export default function AIStylist() {
  const { closetItems } = useApp()
  const [messages, setMessages] = useState<ChatMsg[]>([WELCOME_MSG])
  const [input, setInput] = useState('')
  const [streaming, setStreaming] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const bottomRef = useRef<HTMLDivElement>(null)
  // Ref to abort streaming by marking it cancelled
  const cancelledRef = useRef(false)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  const send = useCallback(async (text: string) => {
    if (!text.trim() || streaming) return
    cancelledRef.current = false

    const userMsg: ChatMsg = {
      id: generateId(),
      role: 'user',
      content: text,
      timestamp: new Date(),
    }
    setMessages(m => [...m, userMsg])
    setInput('')
    setStreaming(true)
    setError(null)

    // Add an empty AI message that we'll fill token-by-token
    const aiMsgId = generateId()
    setMessages(m => [
      ...m,
      { id: aiMsgId, role: 'assistant', content: '', timestamp: new Date() },
    ])

    await streamChat(text, {
      onToken: (token: string) => {
        if (cancelledRef.current) return
        setMessages(m =>
          m.map(msg =>
            msg.id === aiMsgId ? { ...msg, content: msg.content + token } : msg,
          ),
        )
      },
      onDone: () => {
        setStreaming(false)
      },
      onError: (err: string) => {
        if (cancelledRef.current) return
        setError(err)
        setMessages(m =>
          m.map(msg =>
            msg.id === aiMsgId
              ? {
                  ...msg,
                  content:
                    `I'm having trouble connecting right now. Make sure the backend and AI service are running. (${err})`,
                }
              : msg,
          ),
        )
        setStreaming(false)
      },
    })
  }, [streaming])

  const stopStreaming = () => {
    cancelledRef.current = true
    setStreaming(false)
  }

  const newChat = () => {
    cancelledRef.current = true
    setStreaming(false)
    setMessages([WELCOME_MSG])
    setError(null)
  }

  return (
    <div className="flex flex-col h-[calc(100vh-130px)] max-w-3xl animate-fade-in">
      {/* Header */}
      <div className="flex items-center justify-between mb-4">
        <div>
          <h2 className="font-display font-bold text-xl text-slate-800 dark:text-slate-100 flex items-center gap-2">
            <div className="w-8 h-8 rounded-xl bg-gradient-brand flex items-center justify-center shadow-md">
              <Sparkles size={15} className="text-white" />
            </div>
            AI Stylist
          </h2>
          <p className="text-sm text-slate-400 mt-0.5 ml-10">
            {closetItems.length > 0
              ? `Using ${closetItems.length} items from your wardrobe`
              : 'Add items to your closet for personalised suggestions'}
          </p>
        </div>
        <button onClick={newChat} className="btn-ghost text-xs gap-1.5">
          <RefreshCw size={13} /> New chat
        </button>
      </div>

      {/* Closet empty warning */}
      {closetItems.length === 0 && (
        <div className="card p-3 mb-3 bg-amber-50 dark:bg-amber-900/20 border-amber-200 dark:border-amber-800 text-amber-700 dark:text-amber-300 text-xs flex items-center gap-2">
          <AlertTriangle size={13} />
          Your wardrobe is empty — add items first for the best outfit suggestions.
        </div>
      )}

      {/* Error banner */}
      {error && (
        <div className="card p-2 mb-3 bg-red-50 dark:bg-red-900/20 border-red-200 dark:border-red-800 text-red-600 dark:text-red-300 text-xs flex items-center gap-2">
          <AlertTriangle size={12} />
          {error}
        </div>
      )}

      {/* Chat area */}
      <div className="flex-1 overflow-y-auto chat-scroll space-y-4 pb-4">
        {messages.map(msg => (
          <ChatMessage key={msg.id} message={msg} streaming={streaming && msg === messages[messages.length - 1] && msg.role === 'assistant'} />
        ))}

        {/* Blinking cursor while streaming the last message */}
        {streaming && messages[messages.length - 1]?.role === 'assistant' && messages[messages.length - 1]?.content === '' && (
          <div className="flex items-center gap-3">
            <div className="w-8 h-8 rounded-full bg-slate-900 dark:bg-slate-700 flex items-center justify-center flex-shrink-0">
              <Sparkles size={14} className="text-white" />
            </div>
            <div className="bg-white dark:bg-slate-800 border border-cream-300 dark:border-slate-700 rounded-2xl rounded-tl-sm px-4 py-3 shadow-card">
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
        )}

        <div ref={bottomRef} />
      </div>

      {/* Quick prompts */}
      <div className="flex gap-2 flex-wrap mb-3">
        {QUICK_PROMPTS.map(p => (
          <button
            key={p}
            onClick={() => send(p)}
            disabled={streaming}
            className="text-xs px-3 py-1.5 rounded-full bg-brand-50 dark:bg-brand-900/30 text-brand-700 dark:text-brand-300 border border-brand-200 dark:border-brand-800 hover:bg-brand-100 dark:hover:bg-brand-900/50 transition-colors disabled:opacity-40"
          >
            {p}
          </button>
        ))}
      </div>

      {/* Input */}
      <div className="flex gap-3 items-end">
        <div className="flex-1 relative">
          <textarea
            rows={1}
            className="input resize-none pr-12 leading-relaxed"
            placeholder="Ask about outfits, style tips, what to wear…"
            value={input}
            onChange={e => setInput(e.target.value)}
            onKeyDown={e => {
              if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault()
                send(input)
              }
            }}
          />
        </div>

        {streaming ? (
          <button
            onClick={stopStreaming}
            title="Stop generating"
            className="w-11 h-11 rounded-xl bg-red-500 hover:bg-red-600 flex items-center justify-center shadow-md active:scale-95 transition-all flex-shrink-0"
          >
            <Square size={14} className="text-white fill-white" />
          </button>
        ) : (
          <button
            onClick={() => send(input)}
            disabled={!input.trim()}
            className="w-11 h-11 rounded-xl bg-gradient-brand flex items-center justify-center shadow-md hover:opacity-90 active:scale-95 transition-all disabled:opacity-40 flex-shrink-0"
          >
            <Send size={16} className="text-white" />
          </button>
        )}
      </div>
    </div>
  )
}
