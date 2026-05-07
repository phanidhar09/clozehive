/**
 * HTTP client + API helpers for the FastAPI gateway (/api/v1).
 */

import axios, { type AxiosInstance } from 'axios'
import type {
  AuthUser,
  ClosetAnalytics,
  ClosetItem,
  CreateTripResponse,
  Group,
  GroupMember,
  OutfitAnalysis,
  OutfitSuggestion,
  PackingPlan,
  SavePlannerResponse,
  SocialUser,
  Trip,
  TripListResponse,
} from '@/types'

// ── Base URL ───────────────────────────────────────────────────────────────

function apiOrigin(): string {
  const raw = import.meta.env.VITE_API_URL as string | undefined
  return (raw?.replace(/\/$/, '') || 'http://localhost:8000')
}

// ── Tokens ──────────────────────────────────────────────────────────────────

const ACCESS_KEY = 'ch_access_token'
const REFRESH_KEY = 'ch_refresh_token'

export const tokenStorage = {
  getAccess(): string | null {
    try {
      return localStorage.getItem(ACCESS_KEY)
    } catch {
      return null
    }
  },
  getRefresh(): string | null {
    try {
      return localStorage.getItem(REFRESH_KEY)
    } catch {
      return null
    }
  },
  set(access: string, refresh: string): void {
    try {
      localStorage.setItem(ACCESS_KEY, access)
      localStorage.setItem(REFRESH_KEY, refresh)
    } catch {
      /* ignore */
    }
  },
  clear(): void {
    try {
      localStorage.removeItem(ACCESS_KEY)
      localStorage.removeItem(REFRESH_KEY)
    } catch {
      /* ignore */
    }
  },
}

// ── Axios ─────────────────────────────────────────────────────────────────

const api: AxiosInstance = axios.create({
  baseURL: `${apiOrigin()}/api/v1`,
  headers: { 'Content-Type': 'application/json' },
  timeout: 120_000,
})

api.interceptors.request.use(cfg => {
  const t = tokenStorage.getAccess()
  if (t) {
    cfg.headers.Authorization = `Bearer ${t}`
  }
  return cfg
})

api.interceptors.response.use(
  res => res,
  err => {
    if (err.response?.status === 401) {
      window.dispatchEvent(new Event('ch:unauthenticated'))
    }
    return Promise.reject(err)
  },
)

// ── Mappers ────────────────────────────────────────────────────────────────

function mapUserResponse(raw: Record<string, unknown>): AuthUser {
  return {
    id: String(raw.id),
    email: String(raw.email ?? ''),
    username: String(raw.username ?? ''),
    display_name: String(raw.name ?? raw.display_name ?? ''),
    bio: (raw.bio as string | null | undefined) ?? null,
    avatar_url: (raw.avatar_url as string | null | undefined) ?? null,
    role: (raw.role === 'admin' ? 'admin' : 'user') as 'user' | 'admin',
    follower_count: raw.follower_count != null ? Number(raw.follower_count) : undefined,
    following_count: raw.following_count != null ? Number(raw.following_count) : undefined,
    created_at: raw.created_at != null ? String(raw.created_at) : undefined,
    body_profile: (raw.body_profile as AuthUser['body_profile']) ?? null,
    style_profile: (raw.style_profile as AuthUser['style_profile']) ?? null,
    preferences: (raw.preferences as AuthUser['preferences']) ?? null,
    permissions: (raw.permissions as AuthUser['permissions']) ?? null,
    avatar_config: (raw.avatar_config as AuthUser['avatar_config']) ?? null,
    onboarding_completed: raw.onboarding_completed != null ? Boolean(raw.onboarding_completed) : undefined,
  }
}

function mapClosetItem(raw: Record<string, unknown>): ClosetItem {
  const seasonRaw = raw.season
  let season: string | undefined
  if (Array.isArray(seasonRaw)) season = seasonRaw.join(', ')
  else if (typeof seasonRaw === 'string') season = seasonRaw

  return {
    id: String(raw.id),
    user_id: String(raw.user_id ?? ''),
    name: String(raw.name ?? ''),
    category: String(raw.category ?? 'tops'),
    color: raw.color as string | undefined,
    fabric: raw.fabric as string | undefined,
    pattern: raw.pattern as string | undefined,
    brand: raw.brand as string | undefined,
    size: raw.size as string | undefined,
    price: raw.price != null ? Number(raw.price) : undefined,
    image_url: raw.image_url as string | undefined,
    tags: Array.isArray(raw.tags) ? (raw.tags as string[]) : [],
    wear_count: Number(raw.wear_count ?? 0),
    last_worn: raw.last_worn != null ? String(raw.last_worn) : undefined,
    season,
    occasion: Array.isArray(raw.occasion) ? (raw.occasion as string[]) : [],
    eco_score: raw.eco_score != null ? Number(raw.eco_score) : undefined,
    is_favorite: Boolean(raw.is_favorite),
    notes: raw.notes as string | undefined,
    created_at: String(raw.created_at ?? ''),
  }
}

function mapSocialUser(raw: Record<string, unknown>): SocialUser {
  return {
    id: String(raw.id),
    username: String(raw.username ?? ''),
    display_name: String(raw.name ?? raw.display_name ?? ''),
    bio: (raw.bio as string | null | undefined) ?? null,
    avatar_url: (raw.avatar_url as string | undefined) ?? null,
    follower_count: Number(raw.follower_count ?? 0),
    following_count: Number(raw.following_count ?? 0),
    is_following: raw.is_following != null ? Boolean(raw.is_following) : undefined,
    item_count: raw.item_count != null ? Number(raw.item_count) : undefined,
  }
}

function mapGroupMember(raw: Record<string, unknown>, ownerId: string): GroupMember {
  const uid = String(raw.user_id ?? raw.id ?? '')
  const roleRaw = String(raw.role ?? 'member')
  const role: GroupMember['role'] =
    uid === ownerId ? 'owner' : roleRaw === 'admin' ? 'admin' : 'member'
  return {
    id: uid,
    display_name: String(raw.name ?? raw.display_name ?? ''),
    username: String(raw.username ?? ''),
    avatar_url: (raw.avatar_url as string | undefined) ?? null,
    role,
    joined_at: String(raw.joined_at ?? new Date().toISOString()),
  }
}

function mapGroup(raw: Record<string, unknown>): Group {
  const ownerId = String(raw.owner_id ?? '')
  const membersRaw = Array.isArray(raw.members) ? raw.members as Record<string, unknown>[] : []
  const members = membersRaw.map(m => mapGroupMember(m, ownerId))
  return {
    id: String(raw.id),
    name: String(raw.name ?? ''),
    description: (raw.description as string | undefined) ?? null,
    is_public: raw.is_private != null ? !Boolean(raw.is_private) : true,
    invite_code: String(raw.invite_code ?? ''),
    member_count: Number(raw.member_count ?? members.length),
    members,
    role: (raw.my_role as Group['role']) ?? undefined,
    created_at: String(raw.created_at ?? ''),
    updated_at: raw.updated_at != null ? String(raw.updated_at) : undefined,
  }
}

function mapTrip(raw: Record<string, unknown>): Trip {
  return {
    id: String(raw.id),
    user_id: String(raw.user_id ?? ''),
    destination: String(raw.destination ?? ''),
    start_date: String(raw.start_date ?? ''),
    end_date: String(raw.end_date ?? ''),
    purpose: String(raw.purpose ?? ''),
    notes: (raw.notes as string | null | undefined) ?? null,
    is_saved: Boolean(raw.is_saved),
    created_at: String(raw.created_at ?? ''),
    updated_at: String(raw.updated_at ?? ''),
  }
}

// ── Exported types used by pages ───────────────────────────────────────────

export interface OutfitOfDayResponse {
  outfit: OutfitSuggestion | null
  weather: { condition?: string; temp_c?: number; location_label?: string } | null
  occasion: string
  style_tips: string[]
}

// ── Auth ────────────────────────────────────────────────────────────────────

export const authApi = {
  async login(body: { identifier: string; password: string }): Promise<{
    user: AuthUser
    access_token: string
    refresh_token: string
  }> {
    const { data } = await api.post('/auth/login', body)
    return {
      user: mapUserResponse(data.user as Record<string, unknown>),
      access_token: String(data.access_token),
      refresh_token: String(data.refresh_token),
    }
  },

  async signup(body: {
    name: string
    email: string
    username: string
    password: string
  }): Promise<{ user: AuthUser; access_token: string; refresh_token: string }> {
    const { data } = await api.post('/auth/signup', body)
    return {
      user: mapUserResponse(data.user as Record<string, unknown>),
      access_token: String(data.access_token),
      refresh_token: String(data.refresh_token),
    }
  },

  async getMe(): Promise<AuthUser> {
    const { data } = await api.get('/auth/me')
    return mapUserResponse(data as Record<string, unknown>)
  },

  async logout(): Promise<void> {
    const refresh = tokenStorage.getRefresh()
    if (!refresh) return
    try {
      await api.post('/auth/logout', { refresh_token: refresh })
    } catch {
      /* best-effort */
    }
  },

  async updateProfile(
    patch: Partial<AuthUser> & Record<string, unknown>,
  ): Promise<AuthUser> {
    const body: Record<string, unknown> = { ...patch }
    if ('display_name' in body && body.display_name !== undefined) {
      body.name = body.display_name
      delete body.display_name
    }
    const { data } = await api.patch('/auth/me', body)
    return mapUserResponse(data as Record<string, unknown>)
  },
}

// ── Closet ──────────────────────────────────────────────────────────────────

export const closetApi = {
  async list(): Promise<ClosetItem[]> {
    const { data } = await api.get<{ items: Record<string, unknown>[] }>('/closet/', {
      params: { page: 1, per_page: 200 },
    })
    return (data.items ?? []).map(mapClosetItem)
  },

  async delete(id: string): Promise<void> {
    await api.delete(`/closet/${id}`)
  },

  async bulkUpload(files: File[]): Promise<{ created: ClosetItem[]; failed: { filename: string; error: string }[] }> {
    const form = new FormData()
    for (const f of files) form.append('files', f)
    const { data } = await api.post<{ created: Record<string, unknown>[]; failed: { filename: string; error: string }[] }>(
      '/closet/bulk-upload',
      form,
      { headers: { 'Content-Type': 'multipart/form-data' } },
    )
    return {
      created: (data.created ?? []).map(mapClosetItem),
      failed: data.failed ?? [],
    }
  },

  async upload(form: FormData): Promise<{ item: ClosetItem; vision_analysis: Record<string, unknown> }> {
    const { data } = await api.post<{ item: Record<string, unknown>; vision_analysis: Record<string, unknown> }>(
      '/closet/upload',
      form,
      { headers: { 'Content-Type': 'multipart/form-data' } },
    )
    return { item: mapClosetItem(data.item), vision_analysis: data.vision_analysis ?? {} }
  },

  async update(id: string, patch: Partial<ClosetItem>): Promise<ClosetItem> {
    const { data } = await api.patch<Record<string, unknown>>(`/closet/${id}`, patch)
    return mapClosetItem(data)
  },
}

// ── Outfits / AI ───────────────────────────────────────────────────────────

export const outfitsApi = {
  async getOutfitOfDay(): Promise<OutfitOfDayResponse> {
    const { data } = await api.get<OutfitOfDayResponse>('/ai/outfit-of-day')
    return data
  },

  async create(body: {
    name: string
    item_ids: string[]
    occasion: string
    notes?: string
  }): Promise<Record<string, unknown>> {
    const { data } = await api.post('/outfits/', body)
    return data as Record<string, unknown>
  },

  async analyze(body: {
    item_ids: string[]
    occasion: string
    weather?: string
    temperature?: number
    user_profile?: unknown
    date?: string
    location?: string
  }): Promise<OutfitAnalysis> {
    const { data } = await api.post<OutfitAnalysis>('/outfits/generate', body)
    return data
  },
}

export async function generateOutfitOnce(body: {
  occasion: string
  weather: string
  temperature: number
  user_profile: {
    body_profile?: unknown
    style_profile?: unknown
    preferences?: unknown
  } | null
}): Promise<{ outfits?: OutfitSuggestion[]; style_tips?: string[] }> {
  const { data } = await api.post('/ai/outfit', body)
  return data as { outfits?: OutfitSuggestion[]; style_tips?: string[] }
}

// ── Trips ───────────────────────────────────────────────────────────────────

export const tripsApi = {
  async list(): Promise<Trip[]> {
    const { data } = await api.get<TripListResponse>('/trips/')
    return (data.trips ?? []).map(t => mapTrip(t as unknown as Record<string, unknown>))
  },

  async listSaved(): Promise<Trip[]> {
    const { data } = await api.get<TripListResponse>('/trips/saved')
    return (data.trips ?? []).map(t => mapTrip(t as unknown as Record<string, unknown>))
  },

  async create(body: {
    destination: string
    start_date: string
    end_date: string
    purpose: string
    notes?: string
  }): Promise<CreateTripResponse> {
    const { data } = await api.post<CreateTripResponse>('/trips/', body)
    return {
      trip: mapTrip(data.trip as unknown as Record<string, unknown>),
      packing_plan: (data.packing_plan ?? null) as CreateTripResponse['packing_plan'],
      packing_error: data.packing_error ?? null,
    }
  },

  async getPackingList(tripId: string): Promise<unknown> {
    const { data } = await api.get(`/trips/${tripId}/packing-list`)
    return data
  },

  async getPackingPlan(tripId: string): Promise<PackingPlan> {
    const { data } = await api.get<PackingPlan>(`/trips/${tripId}/packing-plan`)
    return data
  },

  async savePlanner(tripId: string): Promise<SavePlannerResponse> {
    const { data } = await api.post<SavePlannerResponse>(`/trips/${tripId}/save-planner`)
    return {
      message: String((data as SavePlannerResponse).message ?? 'Saved'),
      trip: mapTrip((data as SavePlannerResponse).trip as unknown as Record<string, unknown>),
      packing_plan: (data as SavePlannerResponse).packing_plan,
    }
  },

  async delete(tripId: string): Promise<void> {
    await api.delete(`/trips/${tripId}`)
  },
}

// ── Analytics ───────────────────────────────────────────────────────────────

export const analyticsApi = {
  async getClosetAnalytics(): Promise<ClosetAnalytics> {
    const { data } = await api.get<ClosetAnalytics>('/analytics/closet')
    return data
  },
}

// ── Social ──────────────────────────────────────────────────────────────────

export const socialApi = {
  async getProfile(userId: string): Promise<SocialUser> {
    const { data } = await api.get(`/social/users/${userId}`)
    return mapSocialUser(data as Record<string, unknown>)
  },

  async searchUsers(query?: string, limit = 30): Promise<SocialUser[]> {
    const { data } = await api.get<Record<string, unknown>[]>('/social/users', {
      params: { q: query ?? '', limit },
    })
    return (data ?? []).map(mapSocialUser)
  },

  async follow(targetId: string): Promise<{ following: boolean; follower_count: number }> {
    const { data } = await api.post<{ following: boolean; follower_count: number }>(`/social/follow/${targetId}`)
    return data
  },

  async unfollow(targetId: string): Promise<{ following: boolean; follower_count: number }> {
    const { data } = await api.delete<{ following: boolean; follower_count: number }>(`/social/follow/${targetId}`)
    return data
  },

  async getFollowers(userId: string): Promise<SocialUser[]> {
    const { data } = await api.get<Record<string, unknown>[]>(`/social/followers/${userId}`)
    return (data ?? []).map(mapSocialUser)
  },

  async getFollowing(userId: string): Promise<SocialUser[]> {
    const { data } = await api.get<Record<string, unknown>[]>(`/social/following/${userId}`)
    return (data ?? []).map(mapSocialUser)
  },

  async getMyGroups(): Promise<Group[]> {
    const { data } = await api.get<Record<string, unknown>[]>('/social/groups')
    return (data ?? []).map(mapGroup)
  },

  async createGroup(body: {
    name: string
    description?: string
    is_public: boolean
  }): Promise<Group> {
    const { data } = await api.post<Record<string, unknown>>('/social/groups', {
      name: body.name,
      description: body.description,
      is_private: !body.is_public,
    })
    return mapGroup(data)
  },

  async joinGroup(inviteCode: string): Promise<Group> {
    const { data } = await api.post<Record<string, unknown>>('/social/groups/join', {
      invite_code: inviteCode,
    })
    return mapGroup(data)
  },

  async removeMember(groupId: string, targetUserId: string): Promise<void> {
    await api.delete(`/social/groups/${groupId}/members/${targetUserId}`)
  },

  async changeMemberRole(
    groupId: string,
    targetUserId: string,
    role: 'admin' | 'member',
  ): Promise<void> {
    await api.patch(`/social/groups/${groupId}/members/${targetUserId}/role`, { role })
  },

  async leaveGroup(groupId: string): Promise<void> {
    await api.delete(`/social/groups/${groupId}/members/me`)
  },

  async deleteGroup(groupId: string): Promise<void> {
    await api.delete(`/social/groups/${groupId}`)
  },
}

// ── Streaming chat (SSE) ───────────────────────────────────────────────────

export async function streamChat(
  message: string,
  handlers: {
    onToken: (token: string) => void
    onDone: () => void
    onError: (message: string) => void
  },
): Promise<void> {
  const token = tokenStorage.getAccess()
  if (!token) {
    handlers.onError('Not authenticated')
    handlers.onDone()
    return
  }

  let finished = false
  const finish = () => {
    if (!finished) {
      finished = true
      handlers.onDone()
    }
  }

  try {
    const res = await fetch(`${apiOrigin()}/api/v1/ai/chat/stream`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Authorization: `Bearer ${token}`,
      },
      body: JSON.stringify({ message, history: [], include_closet: true }),
    })

    if (!res.ok || !res.body) {
      handlers.onError(`Request failed (${res.status})`)
      finish()
      return
    }

    const reader = res.body.getReader()
    const decoder = new TextDecoder()
    let buffer = ''

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
          const evt = JSON.parse(line) as { type?: string; content?: string; message?: string }
          if (evt.type === 'token' && evt.content) handlers.onToken(evt.content)
          if (evt.type === 'error') handlers.onError(String(evt.message ?? 'Stream error'))
          if (evt.type === 'done') finish()
        } catch {
          /* malformed chunk */
        }
      }
    }
  } catch (e) {
    handlers.onError(e instanceof Error ? e.message : 'Network error')
  } finally {
    finish()
  }
}
