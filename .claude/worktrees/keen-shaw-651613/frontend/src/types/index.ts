export interface ClosetItem {
  id: string
  user_id: number
  name: string
  category: string
  color: string
  color_hex?: string
  fabric?: string
  pattern?: string
  brand?: string
  size?: string
  price?: number
  image_url?: string
  tags: string[]
  wear_count: number
  last_worn?: string
  season?: string
  occasion: string[]
  eco_score?: number
  is_favorite?: boolean
  notes?: string
  created_at: string
}

export interface Outfit {
  id: string
  name: string
  item_ids: string[]
  items?: ClosetItem[]
  occasion: string
  weather_condition?: string
  temperature?: number
  ai_explanation: string
  style_score?: number
  is_saved?: boolean
}

export interface OutfitSuggestion {
  name: string
  item_ids: string[]
  items: Partial<ClosetItem>[]
  explanation: string
  style_score: number
  occasion_fit: string
  weather_fit: string
}

export interface PackingItem {
  name: string
  category: string
  quantity: number
  reason: string
  available_in_closet: boolean
  closet_item_id?: string
}

export interface DailyOutfitPlan {
  date: string
  weather: {
    date: string
    condition: string
    temp_high: number
    temp_low: number
    description: string
  }
  outfit_suggestion: string
  items_needed: string[]
}

export interface PackingResult {
  destination: string
  start_date: string
  end_date: string
  duration_days: number
  trip_type: string
  weather_summary: {
    dominant_condition: string
    avg_high: number
    avg_low: number
    rainy_days: number
    total_days: number
    recommendation: string
  }
  packing_list: PackingItem[]
  missing_items: PackingItem[]
  daily_plan: DailyOutfitPlan[]
  alerts: string[]
}

export interface ChatMessage {
  id: string
  role: 'user' | 'assistant'
  content: string
  outfits?: OutfitSuggestion[]
  timestamp: Date
}

export interface User {
  id: number
  name: string
  email: string
  style_preferences?: string
  body_type?: string
}

// ── Auth ─────────────────────────────────────────────────────
export interface AuthUser {
  /** Numeric user ID (returned as string from the API normaliser) */
  id: string
  email: string
  username: string
  /** Display name (maps to `name` on the backend) */
  display_name: string
  bio?: string | null
  avatar_url?: string | null
  role?: 'user' | 'admin'
  follower_count?: number
  following_count?: number
  created_at?: string
}

// ── Social ───────────────────────────────────────────────────
export interface SocialUser {
  id: number
  name: string
  email: string
  username: string | null
  bio: string | null
  avatar_url: string | null
  follower_count: number
  following_count: number
  is_following: boolean
  item_count?: number
  closet_preview?: Partial<ClosetItem>[]
}

// ── Groups ───────────────────────────────────────────────────
export interface GroupMember {
  id: number
  name: string
  username: string | null
  avatar_url: string | null
  role: 'admin' | 'member'
  joined_at: string
}

export interface Group {
  id: string
  name: string
  description: string | null
  creator_id: number
  invite_code: string
  is_public: number
  created_at: string
  updated_at: string
  member_count: number
  members: GroupMember[]
  my_role: 'admin' | 'member' | null
  is_member: boolean
}

export type ColorScheme = 'light' | 'dark'
export type Category = 'all' | 'tops' | 'bottoms' | 'shoes' | 'outerwear' | 'dresses' | 'accessories'
