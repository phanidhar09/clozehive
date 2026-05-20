/**
 * FANI (Fashion AI Nurturing Individuality) Chat API client.
 * Wraps /api/v1/ai-chat/* endpoints.
 */

import axios from 'axios'
import { apiOrigin } from '@/lib/api'
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
}

// ── Messaging ─────────────────────────────────────────────────────────────────

export interface SendMessageOptions {
  message: string
  sessionId?: string | null
  context?: AIChatContext
  history?: Array<{ role: string; content: string }>
}

export interface SendMessageResponse {
  session_id: string
  message_id: string
  reply: string
  recommended_outfits: AIChatStructuredResponse['recommended_outfits']
  purchase_gaps: AIChatStructuredResponse['purchase_gaps']
  follow_up_questions: string[]
}

export async function sendMessage(opts: SendMessageOptions): Promise<SendMessageResponse> {
  const { data } = await api.post<SendMessageResponse>('/ai-chat/message', {
    message: opts.message,
    session_id: opts.sessionId ?? null,
    context: opts.context ?? {},
    history: opts.history ?? [],
  })
  return data
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
