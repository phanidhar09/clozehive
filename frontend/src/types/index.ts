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
  /** Garment fit (slim/regular/relaxed/oversized/tailored) — drives outfit proportion matching. */
  fit?: string
  price?: number
  image_url?: string
  tags: string[]
  wear_count: number
  last_worn?: string
  season?: string[]
  occasion: string[]
  eco_score?: number
  is_favorite?: boolean
  notes?: string
  /** Physical availability — anything but 'available' is hidden from FANI styling. */
  availability?: AvailabilityStatus
  /** Physical wear state — a soft occasion-aware styling signal; 'damaged' is excluded from styling & packing. */
  condition?: ConditionGrade
  created_at: string
}

export type AvailabilityStatus = 'available' | 'in_laundry' | 'at_cleaners' | 'lent_out'

export const AVAILABILITY_LABELS: Record<AvailabilityStatus, string> = {
  available: 'Available',
  in_laundry: 'In laundry',
  at_cleaners: 'At the cleaners',
  lent_out: 'Lent out',
}

/** Ordinal wear state (best → worst). Mirrors backend app.constants.wardrobe.Condition. */
export type ConditionGrade = 'new' | 'excellent' | 'good' | 'fair' | 'worn' | 'damaged'

/** Best → worst; drives dropdown ordering. */
export const CONDITION_OPTIONS: ConditionGrade[] = ['new', 'excellent', 'good', 'fair', 'worn', 'damaged']

export const CONDITION_LABELS: Record<ConditionGrade, string> = {
  new: 'New',
  excellent: 'Excellent',
  good: 'Good',
  fair: 'Fair',
  worn: 'Worn',
  damaged: 'Damaged',
}

/** Canonical row from POST /closet/analyze-preview (aligned with backend ClosetPreviewItem). */
export interface VisionPreviewItem {
  slot_index: number
  temp_id: string
  /** Stable UUID assigned immediately after AI detection — use as React key and for confirm validation. */
  detected_item_id?: string | null
  name: string
  category: string
  subcategory?: string | null
  color?: string | null
  brand?: string | null
  material?: string | null
  pattern?: string | null
  /** Garment fit detected by the vision pipeline — pre-fills the review editor. */
  fit?: string | null
  season: string[]
  occasions: string[]
  description?: string | null
  confidence: number
  original_image_url: string
  preview_image_url: string
  processed_image_url?: string | null
  background_removed: boolean
  background_removal_status?: string | null
  style_tags: string[]
}

export type StyleGender = 'male' | 'female' | 'non_binary' | 'prefer_not_to_say' | 'custom'

export interface UserStyleProfile {
  id: string
  user_id: string
  gender: StyleGender | null
  custom_gender: string | null
  height_value: number | null
  height_unit: 'cm' | 'ft_in' | null
  weight_value: number | null
  weight_unit: 'kg' | 'lb' | null
  age_range: string | null
  skin_tone: string | null
  undertone: 'warm' | 'cool' | 'neutral' | null
  body_types: string[]
  custom_body_type: string | null
  fit_preferences: string[]
  custom_fit_notes: string | null
  size_profile: Record<string, string>
  custom_size_notes: string | null
  style_preferences: string[]
  favorite_colors: string[]
  avoided_colors: string[]
  neutral_color_preference: boolean | null
  bold_color_preference: boolean | null
  occasion_preferences: string[]
  climate_preferences: string[]
  onboarding_completed: boolean
  onboarding_skipped: boolean
  created_at?: string | null
  updated_at?: string | null
  // v2 onboarding fields
  styling_goals?: string[]
  avoidances?: string[]
  pattern_preferences?: string[]
  style_archetype?: string | null
  recommendation_rules?: Record<string, unknown> | null
  ai_stylist_context?: string | null
}

export interface OnboardingStatus {
  onboarding_completed: boolean
  onboarding_skipped: boolean
  has_profile_record: boolean
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

export interface PackingItemDetailed {
  item_id?: string | null
  name: string
  category: string
  reason?: string
  recommended_days?: string[]
}

export interface PackingItemNeeded {
  name: string
  category: string
  reason?: string
}

export interface DailyOutfitPlan {
  date: string
  day_label?: string
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
  item_ids?: string[]
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
  // Personalised sections
  take_from_your_closet?: PackingItemDetailed[]
  you_might_still_need?: PackingItemNeeded[]
  closet_hint?: string | null
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
  auth_provider?: 'local' | 'google'   // how the account was created
  follower_count?: number
  following_count?: number
  created_at?: string

  // ── Personalization (User Intelligence Hub) ────────────────────────────────
  body_profile?: BodyProfile | null
  style_profile?: StyleProfile | null
  preferences?: UserPreferences | null
  permissions?: UserPermissions | null
  avatar_config?: AvatarConfig | null
  onboarding_completed?: boolean
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

export type TripStyle = 'casual' | 'smart_casual' | 'chic' | 'business' | 'sporty' | 'beach' | 'boho' | 'streetwear'
export type BagSize = 'backpack' | 'carry_on' | 'medium_suitcase' | 'large_suitcase' | 'none'
export type TimeOfDay = 'morning' | 'afternoon' | 'evening' | 'night' | 'full_day'
export type ActivityFormality = 'casual' | 'smart_casual' | 'formal' | 'active' | 'beachwear' | 'business'

export interface TripActivity {
  name: string
  day_number?: number | null
  date?: string | null
  time_of_day?: TimeOfDay | null
  formality?: ActivityFormality | null
  is_fixed: boolean
  notes?: string | null
}

export interface Trip {
  id: string            // UUID
  user_id: string       // UUID
  destination: string
  start_date: string    // ISO date
  end_date: string      // ISO date
  purpose: string
  notes?: string | null
  trip_style?: TripStyle | null
  bag_size?: BagSize | null
  activities: TripActivity[]
  is_saved: boolean
  created_at: string
  updated_at: string
}

// ── Rich packing plan types ───────────────────────────────────────────────────

export interface RichOutfitItem {
  closet_item_id?: string | null
  item_name: string
  category: string
  image_url?: string | null
  source: 'from_closet' | 'missing_recommended' | 'optional' | 'essential'
}

export interface OutfitSlot {
  slot: TimeOfDay
  activity: string
  outfit_name: string
  items: RichOutfitItem[]
  styling_notes?: string
  comfort_notes?: string
  rewear_notes?: string
  /** Set once the user edits this outfit — the styling prose may describe items that are no longer in it. */
  notes_stale?: boolean
}

export interface RichDayPlan {
  day_number: number
  date: string
  weather_note?: string
  activities: string[]
  outfits: OutfitSlot[]
}

export interface PackingChecklistItem {
  item_name: string
  category: string
  closet_item_id?: string | null
  image_url?: string | null
  source: string
  quantity: number
  planned_days: string[]
  activities: string[]
  rewear_count: number
  is_packed: boolean
  priority?: string
  reason?: string
}

export interface RewearStrategyItem {
  item_name: string
  closet_item_id?: string | null
  worn_on_days: string[]
  worn_for?: string[]
  reason: string
}

export interface BagCapacitySummary {
  packing_status: 'fits' | 'tight' | 'overpacked'
  total_unique_items?: number
  optimization_notes: string[]
}

export interface MissingItemRich {
  item_name: string
  category: string
  needed_for?: string
  priority: 'essential' | 'recommended' | 'optional'
  reason?: string
}

export interface PackingPlan {
  id: string
  trip_id: string
  user_id: string
  // ── Legacy fields (backward compat) ──────────────────────────────────────
  take_from_your_closet: PackingItemDetailed[]
  you_might_still_need: PackingItemNeeded[]
  daily_plan: DailyOutfitPlan[]
  weather_summary?: PackingResult['weather_summary']
  packing_list: PackingItem[]
  missing_items: PackingItem[]
  summary?: string | null
  closet_hint?: string | null
  alerts: string[]
  // ── New rich fields ───────────────────────────────────────────────────────
  activities: TripActivity[]
  day_plans_rich: RichDayPlan[]
  rewear_strategy: RewearStrategyItem[]
  bag_capacity_summary?: BagCapacitySummary | null
  packing_checklist: PackingChecklistItem[]
  checklist_state: Record<string, boolean>
  trip_style_direction?: string | null
  climate_summary?: string | null
  location_etiquette?: string | null
  /** Days the user hand-edited. Preserved verbatim when the plan is regenerated. */
  pinned_days: number[]
  // ─────────────────────────────────────────────────────────────────────────
  is_saved: boolean
  created_at: string
  updated_at: string
}

/** An item the user already owns that would fill a gap in the current plan. */
export interface ClosetSuggestion {
  closet_item_id: string
  item_name?: string | null
  category: string
  image_url?: string | null
  reason: string
}

export type OutfitEditOperation = 'add' | 'remove' | 'swap'

export interface CreateTripResponse {
  trip: Trip
  packing_plan?: PackingPlan | null
  packing_error?: string | null
}

export interface SavePlannerResponse {
  message: string
  trip: Trip
  packing_plan: PackingPlan
}

export interface TripListResponse {
  trips: Trip[]
  total: number
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

export interface PurchaseGapInsight {
  gap_type: string
  missing_category: string
  reason: string
  priority_score: number
  suggested_attributes?: Record<string, string> | null
}

export interface CostPerWearItem {
  item_id: string
  name: string
  category: string
  price: number
  wear_count: number
  cost_per_wear: number
}

export interface ForgottenGem {
  item_id: string
  name: string
  category: string
  wear_count: number
  last_worn?: string | null
  days_since_worn?: number | null
}

export interface VersatilityItem {
  item_id: string
  name: string
  category: string
  outfit_count: number
}

export interface WardrobeValueInsights {
  items_priced: number
  total_value: number
  value_worn: number
  value_unworn: number
  utilization_rate: number
  active_rate_90d: number
  avg_cost_per_wear?: number | null
  best_value_items: CostPerWearItem[]
  worst_value_items: CostPerWearItem[]
  forgotten_gems: ForgottenGem[]
  most_versatile: VersatilityItem[]
}

export interface ClosetAnalytics {
  summary: ClosetSummary
  category_coverage: CategoryCoverageItem[]
  color_stats: ColorStats[]
  category_stats: CategoryStats[]
  outfit_readiness: OutfitReadiness
  usage_insights?: UsageInsights | null
  value_insights?: WardrobeValueInsights | null
  purchase_gap_insights?: PurchaseGapInsight[]
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
  fit_confidence?: number | null
  score_breakdown: ScoreBreakdown
  fit_notes?: string
  occasion_match?: 'High' | 'Medium' | 'Low' | null
  style_match?: 'High' | 'Medium' | 'Low' | null
  size_profile_match?: 'High' | 'Medium' | 'Low' | 'Unknown' | null
  body_profile_notes?: string
  recommendations: OutfitRecommendations
  reasoning: string
  why_it_works?: string
  what_to_improve?: string[]
}

export interface SuggestedPairingItem {
  id: string
  name: string
  category: string
  color?: string | null
  image_url?: string | null
  brand?: string | null
  reason: string
}

export interface OutfitAnalysis {
  outfit: ScoredOutfit
  missing_pieces: string[]
  style_tips: string[]
  suggested_pairings?: SuggestedPairingItem[]
  suggested_pairings_error?: boolean
}

// ── Vision pipeline ──────────────────────────────────────────────────────────

export interface VisionAnalyzeResponse {
  items: Array<{
    item_id: string
    name: string
    category: string
    color?: string
    brand?: string
    image_base64?: string
    [key: string]: unknown
  }>
  scan_id?: string
}

export interface SaveItemRequest {
  item_id: string
  name: string
  category: string
  color?: string
  brand?: string
  image_base64?: string
  [key: string]: unknown
}

export interface SaveAnalyzedItemsResponse {
  created: ClosetItem[]
  failed: string[]
}

// ── AI Stylist Chat ───────────────────────────────────────────────────────────

export interface AIChatItemRef {
  id: string
  name: string
  category: string
  color?: string | null
  image_url?: string | null
}

export interface AIChatOutfitScoreBreakdown {
  color: number
  occasion: number
  fit: number
  style: number
  weather: number
  preference: number
}

export interface RecommendedOutfit {
  title: string
  items: AIChatItemRef[]
  matching_score: number
  score_breakdown?: AIChatOutfitScoreBreakdown
  reasoning: string
  fashion_rules_used: string[]
  improvement_tips: string[]
  occasion_match?: string | null
}

export interface PurchaseGapHint {
  category: string
  reason: string
  /** Particular item to buy (preferred over bare category). */
  item?: string | null
  /** Outfit type this gap unlocks (e.g. work, formal dinner). */
  outfit_type?: string | null
}

export interface StylingHint {
  tip: string
  closet_item_name?: string | null
  closet_item_id?: string | null
  category: 'color' | 'layering' | 'accessories' | 'fit' | 'occasion' | 'general'
}

export interface AIChatStructuredResponse {
  reply: string
  recommended_outfits: RecommendedOutfit[]
  styling_suggestions: StylingHint[]
  purchase_gaps: PurchaseGapHint[]
  follow_up_questions: string[]
}

export interface AIChatMessage {
  id: string
  session_id: string
  role: 'user' | 'assistant' | 'system'
  message: string
  structured_response?: AIChatStructuredResponse | null
  created_at: string
}

export interface AIChatSession {
  id: string
  title: string
  created_at: string
  updated_at: string
}

export interface StylistChatMessage {
  id: string
  role: 'user' | 'assistant'
  content: string
  images?: string[]             // base64 data-URL strings attached by the user
  structured?: AIChatStructuredResponse | null
  timestamp: Date
}

export interface AIChatContext {
  occasion?: string
  mood?: string
  location?: string
  weather_required?: boolean
}

// ── Weekly outfit planner ─────────────────────────────────────────────────────

export interface PlannedDayItem {
  id: string
  name: string
  category: string
  color?: string | null
  brand?: string | null
  image_url?: string | null
}

export interface PlannedDay {
  plan_date: string             // YYYY-MM-DD
  occasion: string
  items: PlannedDayItem[]
  weather_condition?: string | null
  temp_high?: number | null
  temp_low?: number | null
  reasoning: string
  source: 'fani' | 'manual' | string
  is_worn: boolean
}

export interface PlannerWeekResponse {
  start_date: string
  days: PlannedDay[]
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
  | 'other'
