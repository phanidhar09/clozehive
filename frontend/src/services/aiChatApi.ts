/**
 * FANI (Fashion Analysis and Nurturing Intelligence) Chat API client.
 * Wraps /api/v1/ai-chat/* endpoints.
 */

import axios from 'axios'
import { apiOrigin } from '@/lib/api'
import { refreshAccessToken } from '@/lib/refreshAccessToken'
import { tokenStorage } from '@/lib/tokenStorage'
import type {
  AIChatSession,
  AIChatMessage,
  AIChatStructuredResponse,
  AIChatContext,
} from '@/types'

// Re-use the same axios instance configuration as the main api client
const api = axios.create({
  baseURL: `${apiOrigin()}/api/v1`,
  timeout: 60_000,
})

api.interceptors.request.use(cfg => {
  const t = tokenStorage.getAccess()
  if (t) cfg.headers.Authorization = `Bearer ${t}`
  return cfg
})

// ── Sessions ──────────────────────────────────────────────────────────────────

export const aiChatSessionsApi = {
  async list(): Promise<AIChatSession[]> {
    const { data } = await api.get<{ sessions: AIChatSession[] }>('/ai-chat/sessions')
    return data.sessions ?? []
  },

  async create(): Promise<AIChatSession> {
    const { data } = await api.post<AIChatSession>('/ai-chat/sessions')
    return data
  },

  async getMessages(sessionId: string): Promise<AIChatMessage[]> {
    const { data } = await api.get<{ messages: AIChatMessage[] }>(
      `/ai-chat/sessions/${sessionId}/messages`,
    )
    return data.messages ?? []
  },

  async deleteSession(sessionId: string): Promise<void> {
    await api.delete(`/ai-chat/sessions/${sessionId}`)
  },
}

// ── Messaging ─────────────────────────────────────────────────────────────────

export interface SendMessageOptions {
  message: string
  sessionId?: string | null
  context?: AIChatContext
  history?: Array<{ role: string; content: string }>
  images?: string[]  // base64 data-URL strings (compressed client-side)
}

export interface SendMessageResponse {
  session_id: string
  message_id: string
  reply: string
  recommended_outfits: AIChatStructuredResponse['recommended_outfits']
  styling_suggestions: AIChatStructuredResponse['styling_suggestions']
  purchase_gaps: AIChatStructuredResponse['purchase_gaps']
  follow_up_questions: string[]
}

export async function sendMessage(opts: SendMessageOptions): Promise<SendMessageResponse> {
  const { data } = await api.post<SendMessageResponse>('/ai-chat/message', {
    message: opts.message,
    session_id: opts.sessionId ?? null,
    context: opts.context ?? {},
    history: opts.history ?? [],
    images: opts.images ?? [],
  })
  return data
}

// ── Streaming messaging (SSE) ───────────────────────────────────────────────
//
// Consumes POST /ai-chat/stream — the advanced FANI path (model router, RAG,
// grounding gate, cost telemetry). Emits the reply token-by-token and delivers
// the full structured payload (outfits, suggestions, gaps) once complete.

export interface StreamStructuredPayload {
  reply: string
  recommended_outfits: AIChatStructuredResponse['recommended_outfits']
  styling_suggestions: AIChatStructuredResponse['styling_suggestions']
  purchase_gaps: AIChatStructuredResponse['purchase_gaps']
  follow_up_questions: string[]
  corrected?: boolean
}

export interface StreamMessageHandlers {
  onSession?: (sessionId: string) => void
  onToken: (content: string) => void
  // Server grounding gate flagged the streamed reply: `reply` (when present)
  // replaces the shown text; `note` is a soft annotation to append.
  onCorrection?: (correction: { reason: string; reply?: string; note?: string }) => void
  onStructured: (payload: StreamStructuredPayload) => void
  onDone: (info: { messageId?: string; sessionId?: string }) => void
  onError: (message: string) => void
}

export async function streamMessage(
  opts: SendMessageOptions,
  handlers: StreamMessageHandlers,
): Promise<void> {
  let accessToken = tokenStorage.getAccess()
  if (!accessToken) {
    handlers.onError('Not authenticated')
    handlers.onDone({})
    return
  }

  let finished = false
  const finish = (info: { messageId?: string; sessionId?: string } = {}) => {
    if (!finished) {
      finished = true
      handlers.onDone(info)
    }
  }

  const payload = JSON.stringify({
    message: opts.message,
    session_id: opts.sessionId ?? null,
    context: opts.context ?? {},
    history: opts.history ?? [],
    images: opts.images ?? [],
  })

  const open = (bearer: string) =>
    fetch(`${apiOrigin()}/api/v1/ai-chat/stream`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${bearer}` },
      body: payload,
    })

  try {
    let res = await open(accessToken)
    if (res.status === 401) {
      // Refresh token lives in an HttpOnly cookie — attempt refresh unconditionally.
      try {
        accessToken = await refreshAccessToken()
        res = await open(accessToken)
      } catch {
        tokenStorage.clear()
        window.dispatchEvent(new Event('ch:unauthenticated'))
        handlers.onError('Session expired — please sign in again')
        finish()
        return
      }
    }

    if (!res.ok || !res.body) {
      handlers.onError(`Request failed (${res.status})`)
      finish()
      return
    }

    const reader = res.body.getReader()
    const decoder = new TextDecoder()
    let buffer = ''
    let doneInfo: { messageId?: string; sessionId?: string } = {}

    while (true) {
      const { done, value } = await reader.read()
      if (done) break
      buffer += decoder.decode(value, { stream: true })
      const blocks = buffer.split('\n\n')
      buffer = blocks.pop() ?? ''

      for (const block of blocks) {
        const line = block
          .split('\n')
          .find(l => l.startsWith('data:'))
          ?.replace(/^data:\s*/, '')
          .trim()
        if (!line) continue
        try {
          const evt = JSON.parse(line) as Record<string, unknown>
          switch (evt.type) {
            case 'session':
              if (typeof evt.session_id === 'string') handlers.onSession?.(evt.session_id)
              break
            case 'token':
              if (typeof evt.content === 'string') handlers.onToken(evt.content)
              break
            case 'correction':
              handlers.onCorrection?.({
                reason: String(evt.reason ?? ''),
                reply: typeof evt.reply === 'string' ? evt.reply : undefined,
                note: typeof evt.note === 'string' ? evt.note : undefined,
              })
              break
            case 'structured':
              handlers.onStructured(evt as unknown as StreamStructuredPayload)
              break
            case 'done':
              doneInfo = {
                messageId: typeof evt.message_id === 'string' ? evt.message_id : undefined,
                sessionId: typeof evt.session_id === 'string' ? evt.session_id : undefined,
              }
              break
            case 'error':
              handlers.onError(String(evt.detail ?? 'Stream error'))
              break
          }
        } catch {
          /* malformed frame — skip */
        }
      }
    }
    finish(doneInfo)
  } catch (e) {
    handlers.onError(e instanceof Error ? e.message : 'Network error')
  } finally {
    finish()
  }
}

// ── History ───────────────────────────────────────────────────────────────────

export async function getChatHistory(limit = 20, offset = 0): Promise<{
  count: number
  messages: AIChatMessage[]
}> {
  const { data } = await api.get('/ai-chat/history', { params: { limit, offset } })
  return data as { count: number; messages: AIChatMessage[] }
}

// ── Feedback ──────────────────────────────────────────────────────────────────

export interface OutfitFeedbackPayload {
  closet_item_ids?: string[]
  outfit_id?: string | null
  rating?: number | null
  feedback_text?: string | null
  occasion?: string | null
  mood?: string | null
  was_worn?: boolean
}

export async function submitOutfitFeedback(payload: OutfitFeedbackPayload): Promise<{
  id: string
  message: string
}> {
  const { data } = await api.post('/ai-chat/feedback', payload)
  return data as { id: string; message: string }
}

// ── Save Outfit ───────────────────────────────────────────────────────────────

export interface SaveOutfitPayload {
  name: string
  item_ids: string[]
  occasion?: string
  explanation?: string
  style_score?: number
  session_id?: string | null
}

export async function saveRecommendedOutfit(payload: SaveOutfitPayload): Promise<{
  id: string
  name: string
  message: string
}> {
  const { data } = await api.post('/ai-chat/save-outfit', payload)
  return data as { id: string; name: string; message: string }
}

// ── Wear logging ──────────────────────────────────────────────────────────────

/**
 * Increment the wear counter for every item in an outfit.
 * Fires all requests in parallel; individual failures are silently ignored
 * so a single bad item ID doesn't break the whole interaction.
 */
export async function logOutfitWorn(itemIds: string[]): Promise<void> {
  const today = new Date().toISOString().slice(0, 10) // YYYY-MM-DD
  await Promise.allSettled(
    itemIds.map(id =>
      api.post(`/closet/${id}/wear`, { worn_date: today }),
    ),
  )
}

// ── Outfit Shuffle ────────────────────────────────────────────────────────────

export interface ShuffleOutfitPayload {
  item_ids: string[]
  occasion?: string
  seed_category?: string | null
  location?: string | null
}

export interface ShuffleAlternative {
  title: string
  items: Array<{
    id: string
    name: string
    category: string
    color?: string
    image_url?: string | null
  }>
  matching_score: number
  score_breakdown?: {
    color: number; occasion: number; fit: number
    style: number; weather: number; preference: number
  }
  reasoning: string
  improvement_tips: string[]
  fashion_rules_used?: string[]
}

export async function shuffleOutfit(payload: ShuffleOutfitPayload): Promise<ShuffleAlternative[]> {
  const { data } = await api.post<{ alternatives: ShuffleAlternative[] }>('/outfits/shuffle', payload)
  return data.alternatives ?? []
}
