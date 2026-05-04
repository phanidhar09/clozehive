// ─────────────────────────────────────────────────────────────────────────────
//  Domain types — aligned with production backend (UUID PKs throughout)
// ─────────────────────────────────────────────────────────────────────────────

export interface ClosetItem {
  id: string            // UUID
  user_id: string       // UUID
  name: string
  category: string
  color?: string
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
  item_ids?: string[]
  items: Partial<ClosetItem>[]
  explanation?: string
  style_notes?: string
  style_score?: number
  occasion_fit?: string
  weather_fit?: string
  weather_suitability?: string
}

export interface PackingItem {
  name: string
  category: string
  quantity: number
  reason?: string
  available_in_closet: boolean
  closet_item_id?: string
  packed?: boolean
  from_closet?: boolean
  item_id?: string
}

export interface DailyOutfitPlan {
  date: string
  weather?: {
    date: string
    condition: string
    temp_high: number
    temp_low: number
    description: string
  }
  outfit_suggestion?: string
  outfit_name?: string
  items?: string[]
  items_needed?: string[]
}

export interface PackingResult {
  destination: string
  start_date: string
  end_date: string
  duration_days?: number
  purpose?: string
  trip_type?: string
  weather_summary?: {
    dominant_condition: string
    avg_high: number
    avg_low: number
    rainy_days: number
    total_days: number
    recommendation: string
  }
  packing_list?: PackingItem[]
  items?: PackingItem[]
  missing_items?: PackingItem[]
  daily_plan?: DailyOutfitPlan[]
  daily_plans?: DailyOutfitPlan[]
  alerts: string[]
  summary?: string
}

export interface ChatMessage {
  id: string
  role: 'user' | 'assistant'
  content: string
  outfits?: OutfitSuggestion[]
  timestamp: Date
}

// ── Auth ──────────────────────────────────────────────────────────────────────

export interface AuthUser {
  id: string            // UUID
  email: string
  username: string
  display_name: string
  bio?: string | null
  avatar_url?: string | null
  role: 'user' | 'admin'
  follower_count?: number
  following_count?: number
  created_at?: string

  // ── Personalization (User Intelligence Hub) ────────────────────────────────
  body_profile?: BodyProfile | null
  style_profile?: StyleProfile | null
  preferences?: UserPreferences | null
  permissions?: UserPermissions | null
  avatar_config?: AvatarConfig | null
}

// ── Personalization sub-types — mirror api-gateway/app/schemas/auth.py ───────

export type BodyType = 'slim' | 'athletic' | 'average' | 'broad' | 'curvy' | 'plus'
export type PreferredFit = 'slim' | 'regular' | 'oversized'
export type StyleTag =
  | 'casual' | 'formal' | 'streetwear' | 'sporty' | 'minimal'
  | 'business' | 'boho' | 'vintage' | 'preppy' | 'elegant'

export interface BodyProfile {
  height_cm?: number | null
  weight_kg?: number | null
  body_type?: BodyType | null
  preferred_fit?: PreferredFit | null
  shirt_size?: string | null
  pant_size?: string | null
  shoe_size?: string | null
}

export interface StyleProfile {
  selected_styles: StyleTag[]
  learned_style?: string | null
  learned_at?: string | null
  favorite_colors: string[]
  avoid_colors: string[]
}

export interface UserPreferences {
  occasion_focus: string[]
  avoid_categories: string[]
  notes?: string | null
}

export interface UserPermissions {
  location: boolean
  calendar: boolean
  location_coords?: { lat: number; lon: number } | null
  location_label?: string | null
  timezone?: string | null
}

export interface AvatarConfig {
  skin_tone?: string | null
  hair_color?: string | null
  hair_style?: string | null
  body_type?: string | null
  outfit?: string | null
}

// ── Trips ────────────────────────────────────────────────────────────────────

export interface Trip {
  id: string            // UUID
  user_id: string       // UUID
  destination: string
  start_date: string    // ISO date
  end_date: string      // ISO date
  purpose: string
  notes?: string | null
  created_at: string
  updated_at: string
}

// ── Analytics ────────────────────────────────────────────────────────────────

export interface CategoryCoverageItem {
  category: string
  count: number
  recommended_minimum: number
  status: 'good' | 'low' | 'missing'
}

export interface ColorStats {
  color: string
  count: number
  percentage: number
}

export interface CategoryStats {
  category: string
  count: number
  percentage: number
}

export interface OutfitReadiness {
  estimated_outfits: number
  best_covered_occasions: string[]
  weakest_covered_occasions: string[]
}

export interface UsageInsights {
  most_worn_items: Array<{ name: string; wear_count: number }>
  least_worn_items: Array<{ name: string; wear_count: number }>
  not_worn_recently: Array<{ name: string; last_worn?: string }>
}

export interface ClosetSummary {
  total_items: number
  strongest_category?: string | null
  most_common_color?: string | null
  best_covered_occasion?: string | null
}

export interface ClosetAnalytics {
  summary: ClosetSummary
  category_coverage: CategoryCoverageItem[]
  color_stats: ColorStats[]
  category_stats: CategoryStats[]
  outfit_readiness: OutfitReadiness
  usage_insights?: UsageInsights | null
}

// ── Social ────────────────────────────────────────────────────────────────────

export interface SocialUser {
  id: string            // UUID
  username: string
  display_name: string
  bio?: string | null
  avatar_url?: string | null
  follower_count: number
  following_count: number
  is_following?: boolean
  item_count?: number
  closet_preview?: Partial<ClosetItem>[]
}

// ── Groups ────────────────────────────────────────────────────────────────────

export interface GroupMember {
  id: string            // UUID
  display_name: string
  username: string
  avatar_url?: string | null
  role: 'owner' | 'admin' | 'member'
  joined_at: string
}

export interface Group {
  id: string            // UUID
  name: string
  description?: string | null
  is_public: boolean
  invite_code: string
  member_count: number
  members?: GroupMember[]
  role?: 'owner' | 'admin' | 'member'
  created_at: string
  updated_at?: string
}

// ── Smart bulk ingestion ──────────────────────────────────────────────────────

export type IngestJobStatus = 'processing' | 'completed' | 'failed'
export type ReviewItemStatus = 'pending_review' | 'approved' | 'rejected'

export interface IngestJob {
  job_id: string
  status: IngestJobStatus
  total_images: number
  processed_images: number
  items_detected: number
  failed_images: number
  created_at: string
  updated_at: string
  error?: string | null
}

export interface ReviewItem {
  temp_item_id: string
  job_id: string
  source_image_id: string
  original_crop_url: string
  processed_image_url: string
  name: string
  category: string
  subcategory: string
  description: string
  primary_color: string
  secondary_colors: string[]
  pattern: string
  material: string
  occasion_tags: string[]
  season_tags: string[]
  style_tags: string[]
  fit: string
  eco_score?: number | null
  brand: string
  confidence_score: number
  status: ReviewItemStatus
  needs_review: boolean
  warnings: string[]
}

export interface IngestResults {
  job_id: string
  status: string
  summary: {
    total_images: number
    items_detected: number
    items_ready_for_review: number
    low_confidence_items: number
    failed_images: number
  }
  items: ReviewItem[]
  errors: string[]
}

export interface ApproveResponse {
  approved: number
  failed: number
  closet_item_ids: string[]
}

// ── Outfit AI analysis ────────────────────────────────────────────────────────

export interface OutfitItemRef {
  id: string
  name: string
  category: string
  color?: string | null
}

export interface OutfitItemSlots {
  top?: OutfitItemRef | null
  bottom?: OutfitItemRef | null
  footwear?: OutfitItemRef | null
  outerwear?: OutfitItemRef | null
  accessories?: OutfitItemRef[]
}

export interface ScoreBreakdown {
  color: number       // max 25
  occasion: number    // max 25
  fit: number         // max 20
  style: number       // max 15
  weather: number     // max 10
  preference: number  // max 5
}

export interface OutfitRecommendations {
  improvements: string[]
  issues: string[]
  styling_tips: string[]
}

export interface ScoredOutfit {
  items: OutfitItemSlots
  matching_score: number
  confidence: number
  score_breakdown: ScoreBreakdown
  recommendations: OutfitRecommendations
  reasoning: string
}

export interface OutfitAnalysis {
  outfit: ScoredOutfit
  missing_pieces: string[]
  style_tips: string[]
}

// ── UI helpers ────────────────────────────────────────────────────────────────

export type ColorScheme = 'light' | 'dark'
export type Category =
  | 'all'
  | 'tops'
  | 'bottoms'
  | 'shoes'
  | 'outerwear'
  | 'dresses'
  | 'accessories'
