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
