/**
 * HTTP client + API helpers for the FastAPI gateway (/api/v1).
 */

import axios, {
  AxiosHeaders,
  type AxiosError,
  type AxiosInstance,
  type InternalAxiosRequestConfig,
} from 'axios'
import type {
  AuthUser,
  ClosetAnalytics,
  ClosetItem,
  CreateTripResponse,
  Group,
  GroupMember,
  OnboardingStatus,
  OutfitAnalysis,
  OutfitSuggestion,
  PackingPlan,
  PlannedDay,
  PlannerWeekResponse,
  SavePlannerResponse,
  SocialUser,
  Trip,
  TripActivity,
  TripListResponse,
  UserStyleProfile,
  VisionPreviewItem,
} from '@/types'

import { skipRefreshOn401 } from './authUrlGuards'
import { apiOrigin, isLoopbackHostname, isNonPublicApiHostname, uploadsOrigin } from './apiOrigin'
import { refreshAccessToken } from './refreshAccessToken'
import { tokenStorage } from './tokenStorage'

export { apiOrigin } from './apiOrigin'
export { tokenStorage } from './tokenStorage'

// ── Base URL ───────────────────────────────────────────────────────────────

/**
 * Closet image URLs are `/uploads/...` (gateway static) or GCS HTTPS.
 * - Same-origin SPA (empty ``apiOrigin()``): force uploads through the page host so
 *   nginx/Vite can proxy ``/uploads`` (fixes JSON that still says ``http://localhost:8000/uploads/...``
 *   while the user only opens :3001 / :80).
 * - Tolerate ``uploads/...`` without a leading slash.
 */
export function resolveUploadUrl(url: string | undefined | null): string | undefined {
  if (url == null || typeof url !== 'string') return undefined
  let u = url.trim()
  if (!u) return undefined
  if (/^uploads\//i.test(u)) u = `/${u}`

  if (u.startsWith('data:') || u.startsWith('blob:')) {
    return u
  }
  if (u.startsWith('http://') || u.startsWith('https://')) {
    try {
      const parsed = new URL(u)
      const path = `${parsed.pathname}${parsed.search}`
      if (path.startsWith('/uploads/') && typeof window !== 'undefined') {
        if (isNonPublicApiHostname(parsed.hostname)) {
          return `${window.location.origin}${path}`
        }
        if (!apiOrigin() && isLoopbackHostname(parsed.hostname)) {
          return `${window.location.origin}${path}`
        }
      }
    } catch {
      return u
    }
    return u
  }
  if (u.startsWith('/uploads/')) {
    if (typeof window === 'undefined') {
      const o = apiOrigin()
      return o ? `${o}${u}` : u
    }
    const base = uploadsOrigin()
    const origin = base || window.location.origin
    return `${origin}${u}`
  }
  return u
}

function mapVisionPreviewItemUrls(items: VisionPreviewItem[] | undefined): VisionPreviewItem[] {
  return (items ?? []).map(it => ({
    ...it,
    original_image_url: resolveUploadUrl(it.original_image_url) ?? it.original_image_url,
    preview_image_url: resolveUploadUrl(it.preview_image_url) ?? it.preview_image_url,
    processed_image_url:
      it.processed_image_url != null
        ? (resolveUploadUrl(it.processed_image_url) ?? it.processed_image_url)
        : it.processed_image_url,
  }))
}

function normalizeOutfitSuggestion(outfit: OutfitSuggestion | null): OutfitSuggestion | null {
  if (!outfit) return null
  return {
    ...outfit,
    items: (outfit.items ?? []).map(it => ({
      ...it,
      image_url: resolveUploadUrl(it.image_url),
    })),
  }
}


const api: AxiosInstance = axios.create({
  baseURL: `${apiOrigin()}/api/v1`,
  timeout: 120_000,
  // Required so the browser sends the HttpOnly refresh-token cookie on
  // /auth/refresh and /auth/logout calls.  Safe for same-origin deploys.
  withCredentials: true,
})

api.interceptors.request.use(cfg => {
  const t = tokenStorage.getAccess()
  if (t) {
    cfg.headers.Authorization = `Bearer ${t}`
  }
  // FormData must use multipart boundary set by the browser. A global JSON Content-Type
  // (or manual multipart/form-data without boundary) breaks uploads and surfaces as "Network Error".
  if (typeof FormData !== 'undefined' && cfg.data instanceof FormData) {
    delete cfg.headers['Content-Type']
  } else if (
    cfg.data != null
    && typeof cfg.data === 'object'
    && !(cfg.data instanceof FormData)
    && !(cfg.data instanceof ArrayBuffer)
    && typeof cfg.data !== 'string'
    && cfg.headers['Content-Type'] == null
  ) {
    cfg.headers['Content-Type'] = 'application/json'
  }
  return cfg
})

function dispatchUnauthenticated(): void {
  tokenStorage.clear()
  window.dispatchEvent(new Event('ch:unauthenticated'))
}

type RequestConfigWithRetry = InternalAxiosRequestConfig & { _chRetry?: boolean }

api.interceptors.response.use(
  res => res,
  async (err: AxiosError) => {
    const original = err.config as RequestConfigWithRetry | undefined
    const status = err.response?.status

    if (status !== 401 || !original) {
      return Promise.reject(err)
    }

    if (skipRefreshOn401(original.url)) {
      dispatchUnauthenticated()
      return Promise.reject(err)
    }

    if (original._chRetry) {
      dispatchUnauthenticated()
      return Promise.reject(err)
    }
    original._chRetry = true

    // Refresh token lives in an HttpOnly cookie — we cannot read it from JS.
    // Just attempt the refresh; if the cookie is absent/expired the refresh
    // endpoint will return 401 and `_chRetry` prevents an infinite loop.

    try {
      const access = await refreshAccessToken()
      const hdr = original.headers
        ? AxiosHeaders.from(original.headers as Record<string, string>)
        : new AxiosHeaders()
      hdr.set('Authorization', `Bearer ${access}`)
      original.headers = hdr
      return api.request(original)
    } catch {
      dispatchUnauthenticated()
      return Promise.reject(err)
    }
  },
)

// ── Mappers ────────────────────────────────────────────────────────────────

function mapUserResponse(raw: Record<string, unknown>): AuthUser {
  // Runtime guard: if the backend sends a response without the expected shape
  // (e.g. after a schema migration), surface a clear error instead of silently
  // returning a half-populated object that breaks rendering.
  if (!raw.id || !raw.email) {
    console.error('[mapUserResponse] Unexpected user response shape:', Object.keys(raw))
  }
  return {
    id: String(raw.id),
    email: String(raw.email ?? ''),
    username: String(raw.username ?? ''),
    display_name: String(raw.name ?? raw.display_name ?? ''),
    bio: (raw.bio as string | null | undefined) ?? null,
    avatar_url: (raw.avatar_url as string | null | undefined) ?? null,
    role: (raw.role === 'admin' ? 'admin' : 'user') as 'user' | 'admin',
    auth_provider: (raw.auth_provider === 'google' ? 'google' : 'local') as 'local' | 'google',
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

function mapUserStyleProfile(raw: Record<string, unknown>): UserStyleProfile {
  const sp = raw.size_profile
  let size_profile: Record<string, string> = {}
  if (typeof sp === 'object' && sp !== null && !Array.isArray(sp)) {
    size_profile = Object.fromEntries(
      Object.entries(sp as Record<string, unknown>).map(([k, v]) => [String(k), String(v ?? '')]),
    )
  }
  const strList = (v: unknown) => (Array.isArray(v) ? v.map(x => String(x)) : [])

  return {
    id: String(raw.id ?? ''),
    user_id: String(raw.user_id ?? ''),
    gender: (raw.gender as UserStyleProfile['gender']) ?? null,
    custom_gender: (raw.custom_gender as string | null | undefined) ?? null,
    height_value: raw.height_value != null ? Number(raw.height_value) : null,
    height_unit: (raw.height_unit as UserStyleProfile['height_unit']) ?? null,
    weight_value: raw.weight_value != null ? Number(raw.weight_value) : null,
    weight_unit: (raw.weight_unit as UserStyleProfile['weight_unit']) ?? null,
    age_range: (raw.age_range as string | null | undefined) ?? null,
    skin_tone: (raw.skin_tone as string | null | undefined) ?? null,
    undertone: (raw.undertone as UserStyleProfile['undertone']) ?? null,
    body_types: strList(raw.body_types),
    custom_body_type: (raw.custom_body_type as string | null | undefined) ?? null,
    fit_preferences: strList(raw.fit_preferences),
    custom_fit_notes: (raw.custom_fit_notes as string | null | undefined) ?? null,
    size_profile,
    custom_size_notes: (raw.custom_size_notes as string | null | undefined) ?? null,
    style_preferences: strList(raw.style_preferences),
    favorite_colors: strList(raw.favorite_colors),
    avoided_colors: strList(raw.avoided_colors),
    neutral_color_preference:
      raw.neutral_color_preference === null || raw.neutral_color_preference === undefined
        ? null
        : Boolean(raw.neutral_color_preference),
    bold_color_preference:
      raw.bold_color_preference === null || raw.bold_color_preference === undefined
        ? null
        : Boolean(raw.bold_color_preference),
    occasion_preferences: strList(raw.occasion_preferences),
    climate_preferences: strList(raw.climate_preferences),
    onboarding_completed: Boolean(raw.onboarding_completed),
    onboarding_skipped: Boolean(raw.onboarding_skipped),
    created_at: raw.created_at != null ? String(raw.created_at) : null,
    updated_at: raw.updated_at != null ? String(raw.updated_at) : null,
  }
}

function mapClosetItem(raw: Record<string, unknown>): ClosetItem {
  const seasonRaw = raw.season
  // Backend always returns season as string[] — normalise legacy string responses too.
  const season: string[] | undefined = Array.isArray(seasonRaw)
    ? (seasonRaw as string[]).filter(Boolean)
    : typeof seasonRaw === 'string' && seasonRaw.trim()
      ? seasonRaw.split(',').map(s => s.trim()).filter(Boolean)
      : undefined

  const image_url =
    resolveUploadUrl(raw.image_url as string | undefined)
    ?? resolveUploadUrl(raw.processed_image_url as string | undefined)
    ?? resolveUploadUrl(raw.original_image_url as string | undefined)

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
    fit: raw.fit as string | undefined,
    price: raw.price != null ? Number(raw.price) : undefined,
    image_url,
    tags: Array.isArray(raw.tags) ? (raw.tags as string[]) : [],
    wear_count: Number(raw.wear_count ?? 0),
    last_worn: raw.last_worn != null ? String(raw.last_worn) : undefined,
    season,
    occasion: Array.isArray(raw.occasion) ? (raw.occasion as string[]) : [],
    eco_score: raw.eco_score != null ? Number(raw.eco_score) : undefined,
    is_favorite: Boolean(raw.is_favorite),
    notes: raw.notes as string | undefined,
    availability: (raw.availability as ClosetItem['availability']) ?? 'available',
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
    is_public: raw.is_private != null ? !raw.is_private : true,
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
    trip_style: (raw.trip_style as Trip['trip_style']) ?? null,
    bag_size: (raw.bag_size as Trip['bag_size']) ?? null,
    activities: (raw.activities as TripActivity[]) ?? [],
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
  /** Present when today is a festival at the user's location. */
  festival: { name: string; emoji: string; dress: string } | null
  style_tips: string[]
}

// ── Auth ────────────────────────────────────────────────────────────────────

export const authApi = {
  async login(body: { identifier: string; password: string }): Promise<{
    user: AuthUser
    access_token: string
    // refresh_token intentionally absent — delivered via HttpOnly cookie
  }> {
    const { data } = await api.post('/auth/login', body)
    return {
      user: mapUserResponse(data.user as Record<string, unknown>),
      access_token: String(data.access_token),
    }
  },

  async signup(body: {
    name: string
    email: string
    username: string
    password: string
    gdpr_consent: boolean
  }): Promise<{ user: AuthUser; access_token: string }> {
    const { data } = await api.post('/auth/signup', body)
    return {
      user: mapUserResponse(data.user as Record<string, unknown>),
      access_token: String(data.access_token),
    }
  },

  async getMe(): Promise<AuthUser> {
    const { data } = await api.get('/auth/me')
    return mapUserResponse(data as Record<string, unknown>)
  },

  async logout(): Promise<void> {
    try {
      // withCredentials ensures the HttpOnly cookie is sent to the server for revocation.
      await api.post('/auth/logout')
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

  async deleteAccount(): Promise<void> {
    await api.delete('/auth/me')
  },

  async exportMyData(): Promise<void> {
    const { data } = await api.get('/auth/me/export')
    const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = 'clozehive_data_export.json'
    a.click()
    URL.revokeObjectURL(url)
  },

  async oauthExchange(code: string): Promise<{ access_token: string }> {
    // withCredentials ensures the server's Set-Cookie header is honoured —
    // the refresh token is delivered as an HttpOnly cookie, not in the body.
    const { data } = await api.post('/auth/oauth/exchange', { code })
    return {
      access_token: String(data.access_token),
    }
  },

  /**
   * Request a password-reset email.  The server always returns 202 regardless
   * of whether the email is registered (prevents account enumeration).
   */
  async forgotPassword(email: string): Promise<void> {
    await api.post('/auth/forgot-password', { email })
  },

  /**
   * Consume a one-time password-reset token and set a new password.
   * @throws AxiosError with response.data.detail on invalid/expired token.
   */
  async resetPassword(token: string, new_password: string): Promise<void> {
    await api.post('/auth/reset-password', { token, new_password })
  },
}

export const profileApi = {
  async getOnboardingStatus(): Promise<OnboardingStatus> {
    const { data } = await api.get<OnboardingStatus>('/profile/onboarding-status')
    return data
  },

  async getStyleProfile(): Promise<UserStyleProfile | null> {
    try {
      const { data } = await api.get<Record<string, unknown>>('/profile/style')
      return mapUserStyleProfile(data)
    } catch (e: unknown) {
      const s = (e as { response?: { status?: number } })?.response?.status
      if (s === 404) return null
      throw e
    }
  },

  async patchStyleProfile(
    patch: Partial<UserStyleProfile> & Record<string, unknown>,
  ): Promise<UserStyleProfile> {
    const { data } = await api.patch<Record<string, unknown>>('/profile/style', patch)
    return mapUserStyleProfile(data)
  },

  async completeOnboarding(skipped: boolean): Promise<UserStyleProfile> {
    const { data } = await api.post<Record<string, unknown>>('/profile/style/complete', { skipped })
    return mapUserStyleProfile(data)
  },

  async submitOnboarding(payload: Record<string, unknown>): Promise<UserStyleProfile> {
    const { data } = await api.post<Record<string, unknown>>('/profile/onboarding/submit', payload)
    return mapUserStyleProfile(data)
  },
}

export type ClosetPreviewItem = VisionPreviewItem

export type ClosetAnalyzePreviewResponse = {
  preview_session_id: string
  items: VisionPreviewItem[]
  scan_id?: string | null
  pipeline_cached?: boolean
}

export type ClosetConfirmItemPayload = {
  slot_index: number
  /** Stable UUID from detection — backend validates this matches the slot to prevent image↔metadata mismatch. */
  detected_item_id?: string
  selected: boolean
  name: string
  category: string
  color?: string
  fabric?: string
  material?: string
  pattern?: string
  season?: string[]
  occasion?: string[]
  notes?: string
  brand?: string
  size?: string
  fit?: string
  price?: number
  tags?: string[]
  eco_score?: number
}

export type ClosetConfirmRequest = {
  preview_session_id: string
  items: ClosetConfirmItemPayload[]
}

export type BulkAnalyzePreviewFileResult = {
  filename: string
  preview: ClosetAnalyzePreviewResponse
}

export type BulkAnalyzePreviewResponse = {
  results: BulkAnalyzePreviewFileResult[]
  failed: { filename: string; error: string }[]
}

// ── Closet ──────────────────────────────────────────────────────────────────

export const closetApi = {
  async list(page = 1, perPage = 500): Promise<{ items: ClosetItem[]; total: number; hasMore: boolean }> {
    const { data } = await api.get<{ items: Record<string, unknown>[]; total: number }>('/closet/', {
      params: { page, per_page: perPage },
    })
    const items = (data.items ?? []).map(mapClosetItem)
    const total = data.total ?? items.length
    const loadedSoFar = ((page - 1) * perPage) + items.length
    return { items, total, hasMore: total > loadedSoFar }
  },

  async delete(id: string): Promise<void> {
    await api.delete(`/closet/${id}`)
  },

  async analyzePreview(file: File): Promise<ClosetAnalyzePreviewResponse> {
    const fd = new FormData()
    fd.append('file', file)
    const { data } = await api.post<ClosetAnalyzePreviewResponse>('/closet/analyze-preview', fd)
    return {
      ...(data ?? {}),
      items: mapVisionPreviewItemUrls(data?.items),
    }
  },

  async bulkAnalyzePreview(files: File[]): Promise<BulkAnalyzePreviewResponse> {
    const form = new FormData()
    for (const f of files) form.append('files', f)
    const { data } = await api.post<BulkAnalyzePreviewResponse>('/closet/bulk-analyze-preview', form)
    return {
      results: (data.results ?? []).map(r => ({
        ...r,
        preview: r.preview
          ? { ...r.preview, items: mapVisionPreviewItemUrls(r.preview.items) }
          : r.preview,
      })),
      failed: data.failed ?? [],
    }
  },

  async confirmPreview(body: ClosetConfirmRequest): Promise<{ saved: ClosetItem[]; total_saved: number }> {
    const { data } = await api.post<{ saved: Record<string, unknown>[]; total_saved: number }>(
      '/closet/confirm',
      body,
    )
    return {
      saved: (data.saved ?? []).map(mapClosetItem),
      total_saved: data.total_saved ?? 0,
    }
  },

  async bulkUpload(files: File[]): Promise<{ created: ClosetItem[]; failed: { filename: string; error: string }[] }> {
    const form = new FormData()
    for (const f of files) form.append('files', f)
    const { data } = await api.post<{ created: Record<string, unknown>[]; failed: { filename: string; error: string }[] }>(
      '/closet/bulk-upload',
      form,
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
    )
    return { item: mapClosetItem(data.item), vision_analysis: data.vision_analysis ?? {} }
  },

  async update(id: string, patch: Partial<ClosetItem>): Promise<ClosetItem> {
    const { data } = await api.patch<Record<string, unknown>>(`/closet/${id}`, patch)
    return mapClosetItem(data)
  },

  async reEmbed(force = false): Promise<{ status: string; items_queued: number; message: string }> {
    const { data } = await api.post('/closet/re-embed', null, { params: { force } })
    return data as { status: string; items_queued: number; message: string }
  },
}

// ── Outfits / AI ───────────────────────────────────────────────────────────

export const outfitsApi = {
  async getOutfitOfDay(): Promise<OutfitOfDayResponse> {
    const { data } = await api.get<OutfitOfDayResponse>('/ai/outfit-of-day')
    return {
      ...data,
      outfit: normalizeOutfitSuggestion(data.outfit),
    }
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
    const { data } = await api.post<OutfitAnalysis>('/outfits/analyze', body)
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
  const parsed = data as { outfits?: OutfitSuggestion[]; style_tips?: string[] }
  return {
    ...parsed,
    outfits: parsed.outfits?.map(o => normalizeOutfitSuggestion(o)!),
  }
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
    trip_style?: string | null
    bag_size?: string | null
    activities?: TripActivity[]
  }): Promise<CreateTripResponse> {
    const { data } = await api.post<CreateTripResponse>('/trips/', body, { timeout: 120_000 })
    return {
      trip: mapTrip(data.trip as unknown as Record<string, unknown>),
      packing_plan: (data.packing_plan ?? null) as CreateTripResponse['packing_plan'],
      packing_error: data.packing_error ?? null,
    }
  },

  async addActivities(tripId: string, activities: TripActivity[], replace = false): Promise<Trip> {
    const { data } = await api.post(`/trips/${tripId}/activities`, { activities, replace })
    return mapTrip(data as Record<string, unknown>)
  },

  async regeneratePacking(tripId: string): Promise<PackingPlan> {
    const { data } = await api.post<PackingPlan>(`/trips/${tripId}/regenerate-packing`, {}, { timeout: 120_000 })
    return data
  },

  async updateChecklistItem(tripId: string, itemKey: string, isPacked: boolean): Promise<void> {
    await api.patch(`/trips/${tripId}/planner/checklist`, { item_key: itemKey, is_packed: isPacked })
  },

  async getPackingList(tripId: string): Promise<unknown> {
    const { data } = await api.get(`/trips/${tripId}/packing-list`, { timeout: 90_000 })
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

export interface DigestItem {
  item_id: string
  name: string
  category: string
  detail: string
}

export interface WeeklyDigest {
  week_start: string
  week_end: string
  wears_logged: number
  items_worn: number
  new_items: number
  utilization_rate: number
  most_worn?: DigestItem | null
  best_value?: DigestItem | null
  forgotten_gem?: DigestItem | null
  headline: string
}

export const analyticsApi = {
  async getClosetAnalytics(): Promise<ClosetAnalytics> {
    const { data } = await api.get<ClosetAnalytics>('/analytics/closet')
    return data
  },
  async getWeeklyDigest(): Promise<WeeklyDigest> {
    const { data } = await api.get<WeeklyDigest>('/analytics/weekly-digest')
    return data
  },
}

// ── Daily FANI nudges ─────────────────────────────────────────────────────────

export interface DailyNudge {
  id: string
  nudge_date: string
  message: string
  nudge_type: string
  payload: Record<string, unknown>
  dismissed: boolean
  created_at: string
}

export const nudgeApi = {
  async getToday(): Promise<DailyNudge | null> {
    const { data } = await api.get<{ nudge: DailyNudge | null }>('/ai-chat/nudges/today')
    return data.nudge
  },
  async dismiss(id: string): Promise<void> {
    await api.post(`/ai-chat/nudges/${id}/dismiss`)
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

  async getFollowers(
    userId: string,
    opts: { limit?: number; offset?: number } = {},
  ): Promise<{ users: SocialUser[]; hasMore: boolean }> {
    const limit = opts.limit ?? 50
    const { data } = await api.get<Record<string, unknown>[]>(`/social/followers/${userId}`, {
      params: { limit, offset: opts.offset ?? 0 },
    })
    const users = (data ?? []).map(mapSocialUser)
    return { users, hasMore: users.length === limit }
  },

  async getFollowing(
    userId: string,
    opts: { limit?: number; offset?: number } = {},
  ): Promise<{ users: SocialUser[]; hasMore: boolean }> {
    const limit = opts.limit ?? 50
    const { data } = await api.get<Record<string, unknown>[]>(`/social/following/${userId}`, {
      params: { limit, offset: opts.offset ?? 0 },
    })
    const users = (data ?? []).map(mapSocialUser)
    return { users, hasMore: users.length === limit }
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

// ── RAG: Fashion Knowledge ────────────────────────────────────────────────────

export const fashionKnowledgeApi = {
  async search(query: string, limit = 5, category?: string): Promise<{
    query: string
    count: number
    results: Array<{
      id: string
      title: string
      content: string
      category: string
      season: string | null
      occasion: string | null
      relevance_score: number
    }>
  }> {
    const params: Record<string, unknown> = { query, limit }
    if (category) params.category = category
    const { data } = await api.get('/fashion-knowledge/search', { params })
    return data as ReturnType<typeof fashionKnowledgeApi.search> extends Promise<infer T> ? T : never
  },
}

// ── RAG: Outfit History ───────────────────────────────────────────────────────

export type OutfitHistoryRecord = {
  id: string
  occasion: string | null
  weather_context: { weather: string } | null
  selected_item_ids: string[]
  matching_score: number | null
  recommendation_text: string | null
  improvement_tips: string[]
  was_saved: boolean
  was_worn: boolean
  user_feedback: string | null
  similarity_score?: number
  created_at: string | null
}

export const outfitHistoryApi = {
  async list(limit = 20, offset = 0): Promise<{ count: number; results: OutfitHistoryRecord[] }> {
    const { data } = await api.get('/outfits/history/', { params: { limit, offset } })
    return data as { count: number; results: OutfitHistoryRecord[] }
  },

  async getSimilar(occasion: string, weather = '', limit = 5): Promise<{
    count: number
    results: OutfitHistoryRecord[]
  }> {
    const { data } = await api.get('/outfits/history/similar', { params: { occasion, weather, limit } })
    return data as { count: number; results: OutfitHistoryRecord[] }
  },

  async submitFeedback(historyId: string, body: {
    feedback?: string
    was_worn?: boolean
    was_saved?: boolean
  }): Promise<{ id: string; user_feedback: string | null; was_worn: boolean; was_saved: boolean }> {
    const { data } = await api.post(`/outfits/history/${historyId}/feedback`, body)
    return data as ReturnType<typeof outfitHistoryApi.submitFeedback> extends Promise<infer T> ? T : never
  },

  async delete(historyId: string): Promise<void> {
    await api.delete(`/outfits/history/${historyId}`)
  },
}

// ── RAG: Packing Memory ────────────────────────────────────────────────────────

export const packingMemoryApi = {
  async getForTrip(tripId: string): Promise<{
    id: string
    destination: string
    purpose: string | null
    packed_item_ids: string[]
    missing_items: Array<{ name: string; category: string; reason: string }>
    user_feedback: string | null
    created_at: string | null
  } | null> {
    try {
      const { data } = await api.get(`/trips/${tripId}/packing-memory`)
      return data as ReturnType<typeof packingMemoryApi.getForTrip> extends Promise<infer T> ? T : never
    } catch {
      return null
    }
  },

  async submitFeedback(tripId: string, feedback: string): Promise<{ id: string; user_feedback: string }> {
    const { data } = await api.post(`/trips/${tripId}/packing-memory/feedback`, { feedback })
    return data as { id: string; user_feedback: string }
  },
}

// ── RAG: Purchase Gaps ────────────────────────────────────────────────────────

export type PurchaseGap = {
  id: string
  gap_type: 'outfit' | 'trip_packing' | 'seasonal' | 'occasion' | 'structural' | 'proportion'
  missing_category: string
  missing_color: string | null
  missing_season: string | null
  missing_occasion: string | null
  reason: string
  priority_score: number
  source_context: Record<string, unknown> | null
  suggested_attributes: Record<string, unknown> | null
  resolved: boolean
  created_at: string | null
}

export const purchaseGapsApi = {
  async list(resolved = false, limit = 30): Promise<{ count: number; gaps: PurchaseGap[] }> {
    const { data } = await api.get('/purchase-gaps/', { params: { resolved, limit } })
    return data as { count: number; gaps: PurchaseGap[] }
  },

  async resolve(gapId: string): Promise<{ id: string; resolved: true }> {
    const { data } = await api.patch(`/purchase-gaps/${gapId}/resolve`)
    return data as { id: string; resolved: true }
  },

  async delete(gapId: string): Promise<void> {
    await api.delete(`/purchase-gaps/${gapId}`)
  },
}

// ── RAG: Closet Similarity ────────────────────────────────────────────────────

/** Rich similar-item result returned by the new check-similar and items/{id}/similar endpoints. */
export type SimilarClosetItem = {
  id: string
  item_id: string
  name: string
  category: string
  color: string
  colors: string[]
  brand: string
  image_url: string
  /** 0–100 integer */
  similarity_score: number
  /** "Possible duplicate" | "Very similar" | "Related item" */
  similarity_label: string
  /** Why they are similar */
  similarity_reason: string
  /** Key differences between the two items */
  difference_summary: string
  /** Legacy field kept for backward compat */
  reason?: string
}

export interface CheckSimilarPayload {
  name?: string
  category: string
  subcategory?: string
  color?: string
  colors?: string[]
  pattern?: string
  material?: string
  style_tags?: string[]
  occasion_tags?: string[]
  season_tags?: string[]
  limit?: number
}

export const closetSimilarityApi = {
  /**
   * Check if a NEW (not-yet-saved) item is similar to existing closet items.
   * Call before saving to warn the user of potential duplicates.
   */
  async checkSimilarClosetItems(payload: CheckSimilarPayload): Promise<SimilarClosetItem[]> {
    try {
      const { data } = await api.post<{ similar_items: SimilarClosetItem[] }>(
        '/closet/check-similar',
        payload,
      )
      return data.similar_items ?? []
    } catch {
      return []
    }
  },

  /** Get similar items for an EXISTING closet item (detail view). */
  async getSimilarForItem(itemId: string, limit = 6): Promise<SimilarClosetItem[]> {
    try {
      const { data } = await api.get<{ similar_items: SimilarClosetItem[] }>(
        `/closet/items/${itemId}/similar`,
        { params: { limit } },
      )
      return data.similar_items ?? []
    } catch {
      return []
    }
  },

  // ── Legacy endpoints kept for backward compat ──────────────────────────────
  async findSimilar(params: {
    closet_item_id?: string
    query?: string
    image_url?: string
    limit?: number
  }): Promise<{ query_type: string; count: number; results: SimilarClosetItem[] }> {
    const { data } = await api.post('/closet/similar', null, { params: { ...params, limit: params.limit ?? 5 } })
    return data as { query_type: string; count: number; results: SimilarClosetItem[] }
  },

  async getSimilarToItem(itemId: string, limit = 5): Promise<{ count: number; results: SimilarClosetItem[] }> {
    const { data } = await api.get(`/closet/similar/${itemId}`, { params: { limit } })
    return data as { count: number; results: SimilarClosetItem[] }
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
  let accessToken = tokenStorage.getAccess()
  if (!accessToken) {
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

  const openStream = (bearer: string) =>
    fetch(`${apiOrigin()}/api/v1/ai/chat/stream`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Authorization: `Bearer ${bearer}`,
      },
      body: JSON.stringify({ message, history: [], include_closet: true }),
    })

  try {
    let res = await openStream(accessToken)

    if (res.status === 401) {
      // Refresh token is in an HttpOnly cookie — attempt refresh unconditionally.
      try {
        accessToken = await refreshAccessToken()
        res = await openStream(accessToken)
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

// ── Shopping Check API ────────────────────────────────────────────────────────

export interface ShoppingMatchedItem {
  id: string
  name: string
  category: string
  color: string
  image_url: string | null
  similarity_score: number
  is_duplicate: boolean
}

export interface ShoppingCheckResult {
  check_id: string
  item_analysis: Record<string, unknown>
  matched_items: ShoppingMatchedItem[]
  buy_score: number
  /** Headline verdict on a 0–10 scale (buy_score / 10). Shown to the user. */
  rating: number
  /** Verdict colour band: green (strong), amber (middling), red (weak). */
  rating_color: 'green' | 'amber' | 'red'
  /** Same 0–10 value as `rating`; kept as an alias. */
  buy_score_10?: number
  /** Internal analytics band only — do NOT surface (it's a buy/skip word). */
  buy_recommendation: 'buy' | 'consider' | 'skip'
  /** Personal-fit sub-signal (coloring/fit/taste), 0–1; null when no profile. */
  style_match?: number | null
  closet_boost_pct: number
  /** Per-factor % contributions to buy_score (weights sum to 100). */
  score_breakdown?: Record<string, number>
  /** Max % each factor can contribute — denominators for the breakdown bars. */
  score_weights?: Record<string, number>
  reasoning: string
  /** RAG-grounded natural-language verdict; null when knowledge was unavailable. */
  fani_take?: { take: string; cited_titles: string[]; grounded: boolean } | null
  /** Persisted image URL of the analysed item (set for URL/screenshot checks). */
  image_url?: string | null
  /** How the item was sourced: photo upload, product-URL image, or page screenshot. */
  input_type?: 'photo' | 'url' | 'screenshot'
  /** Pasted product URL (URL checks only). */
  source_url?: string | null
  source_title?: string | null
  source_brand?: string | null
  source_price?: string | null
  source_site?: string | null
  /** How many near-duplicates of this item the closet already holds. */
  dupe_count?: number
  /** How many owned items this would pair into outfits with. */
  completes_outfits?: number
  /** Running count of product links this user has checked (repeat-paste signal). */
  url_check_count?: number
}

export interface ShoppingHistoryEntry extends ShoppingCheckResult {
  image_url: string | null
  purchase_decision: boolean | null
  decision_at: string | null
  created_at: string
}

export interface ClosetMatchSuggestion {
  category: string
  role?: string
  reason: string
  colors: string[]
  occasions: string[]
  priority: 'high' | 'medium' | 'low'
  price_range?: string
}

/** An item the user already owns that completes the look. */
export interface ClosetPairing {
  id: string
  name: string
  category: string
  image_url: string | null
  role: string
  reason: string
}

export interface ClosetMatchResult {
  closet_item: {
    id: string
    name: string
    category: string
    color: string
    image_url: string | null
    occasion: string[]
    season: string[]
  }
  /** Owned items that complete the look — shown first. */
  closet_pairings: ClosetPairing[]
  outfit_potential: 'high' | 'medium' | 'low'
  styling_tip: string
  /** Items to buy — only for slots the closet cannot fill. */
  suggestions: ClosetMatchSuggestion[]
  /** True when the styling advice was grounded in retrieved fashion knowledge (RAG). */
  grounded_in_knowledge?: boolean
}

export interface BuiltOutfitItem {
  id: string
  name: string
  category: string
  color: string
  image_url: string | null
  role: string
  wear_count: number
}

export interface BuiltOutfit {
  score: number
  tier: 'Perfect' | 'Great' | 'Solid' | 'Wearable' | 'Risky'
  items: BuiltOutfitItem[]
  missing_roles: string[]
  forgotten_item_ids: string[]
  note: string
}

export interface GapSuggestion {
  role: string
  shop_for: string
  suggested_colors: string[]
  formality: string
  completes_outfits: number
  reason: string
}

export interface BuiltOutfitsResult {
  anchor: { name: string; category: string; color: string; image_url: string | null }
  outfits: BuiltOutfit[]
  missing_roles: string[]
  completes_outfits: number
  gap_suggestions: GapSuggestion[]
}

export const shoppingCheckApi = {
  async checkItem(file: File): Promise<ShoppingCheckResult> {
    const form = new FormData()
    form.append('file', file)
    const { data } = await api.post<ShoppingCheckResult>('/shopping/check', form, {
      headers: { 'Content-Type': 'multipart/form-data' },
    })
    return data
  },

  async checkUrl(url: string): Promise<ShoppingCheckResult> {
    const { data } = await api.post<ShoppingCheckResult>('/shopping/check-url', { url })
    return data
  },

  async buildOutfits(checkId: string): Promise<BuiltOutfitsResult> {
    const { data } = await api.post<BuiltOutfitsResult>(`/shopping/${checkId}/outfits`)
    return data
  },

  async recordDecision(checkId: string, bought: boolean): Promise<void> {
    await api.patch(`/shopping/${checkId}/decision`, { bought })
  },

  /** Fire-and-forget Shop with FANI funnel event (instrumentation). */
  logEvent(checkId: string, eventType: string, metadata?: Record<string, unknown>): void {
    void api.post(`/shopping/${checkId}/event`, { event_type: eventType, metadata }).catch(() => {})
  },

  async getHistory(limit = 30): Promise<ShoppingHistoryEntry[]> {
    const { data } = await api.get<{ checks: ShoppingHistoryEntry[] }>('/shopping/history', {
      params: { limit },
    })
    return data.checks ?? []
  },

  async deleteCheck(checkId: string): Promise<void> {
    await api.delete(`/shopping/${checkId}`)
  },

  async addToCloset(checkId: string): Promise<{ closet_item: Record<string, unknown> }> {
    const { data } = await api.post(`/shopping/${checkId}/add-to-closet`)
    return data
  },

  async getClosetMatchSuggestions(closetItemId: string): Promise<ClosetMatchResult> {
    const { data } = await api.post<ClosetMatchResult>('/shopping/closet-match', {
      closet_item_id: closetItemId,
    })
    return data
  },
}

// ── Weekly outfit planner ────────────────────────────────────────────────────

function mapPlannedDay(day: PlannedDay): PlannedDay {
  return {
    ...day,
    items: (day.items ?? []).map(it => ({ ...it, image_url: resolveUploadUrl(it.image_url) ?? it.image_url })),
  }
}

export interface PlannerForecastDay {
  date: string                 // YYYY-MM-DD
  condition: string
  temp_high?: number | null
  temp_low?: number | null
  occasion?: string | null
}

export const plannerApi = {
  async getWeek(start?: string): Promise<PlannerWeekResponse> {
    const { data } = await api.get<PlannerWeekResponse>('/planner/week', {
      params: start ? { start } : undefined,
    })
    return { ...data, days: (data.days ?? []).map(mapPlannedDay) }
  },

  async generate(body: {
    start_date?: string
    days?: PlannerForecastDay[]
    location?: string
  }): Promise<PlannerWeekResponse> {
    const { data } = await api.post<PlannerWeekResponse>('/planner/generate', body)
    return { ...data, days: (data.days ?? []).map(mapPlannedDay) }
  },

  async setDay(planDate: string, body: { item_ids: string[]; occasion?: string; notes?: string }): Promise<PlannedDay> {
    const { data } = await api.put<PlannedDay>(`/planner/${planDate}`, body)
    return mapPlannedDay(data)
  },

  async clearDay(planDate: string): Promise<void> {
    await api.delete(`/planner/${planDate}`)
  },

  async markWorn(planDate: string): Promise<PlannedDay> {
    const { data } = await api.post<PlannedDay>(`/planner/${planDate}/worn`)
    return mapPlannedDay(data)
  },
}

// ── WebSocket auth ────────────────────────────────────────────────────────────

export const wsApi = {
  /** Exchange the bearer token for a short-lived single-use WS connect ticket. */
  async ticket(): Promise<string> {
    const { data } = await api.post<{ ticket: string }>('/ws/ticket')
    return data.ticket
  },
}
