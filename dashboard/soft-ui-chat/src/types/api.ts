/**
 * API Type Definitions
 *
 * TypeScript interfaces matching backend Pydantic models
 * for type-safe API communication.
 */

// ============================================
// User Types
// ============================================

/**
 * User plan types matching backend PlanType enum
 */
export type PlanType = 'free' | 'premium' | 'enterprise';

/**
 * Plan limits configuration object
 */
export interface PlanLimits {
  max_videos?: number;
  max_groups?: number;
  max_searches_per_day?: number;
  [key: string]: unknown;
}

/**
 * User profile information
 * Matches backend UserResponse model
 */
export interface User {
  id: string;
  email: string;
  first_name?: string | null;
  last_name?: string | null;
  plan_type: PlanType;
  plan_limits: PlanLimits;
  pinecone_namespace?: string | null;
  created_at?: string | null;
  updated_at?: string | null;
}

// ============================================
// Authentication Types
// ============================================

/**
 * Authentication token response
 * Matches backend TokenResponse model
 */
export interface TokenResponse {
  access_token: string;
  refresh_token?: string | null;
  token_type: string;
  expires_in: number;
  user: User;
}

/**
 * Login request payload
 */
export interface LoginRequest {
  email: string;
  password: string;
}

/**
 * Registration request payload
 */
export interface RegisterRequest {
  email: string;
  password: string;
  first_name?: string;
  last_name?: string;
}

// ============================================
// Video Types
// ============================================

/**
 * Video record from the library
 * Matches backend VideoResponse model
 */
export interface Video {
  id: string;
  youtube_id: string;
  title: string;
  channel_name?: string | null;
  duration_seconds?: number | null;
  thumbnail_url?: string | null;
  pinecone_file_id?: string | null;
  transcript_length?: number | null;
  group_id?: string | null;
  group_name?: string | null;
  // Summary cache status
  has_summary?: boolean;
  summary_generated_at?: string | null;
  created_at: string;
  updated_at: string;
}

/**
 * Video with full transcript content
 */
export interface VideoWithTranscript extends Video {
  transcript?: string | null;
}

/**
 * Paginated video list response
 * Matches backend VideoListResponse model
 */
export interface VideoListResponse {
  videos: Video[];
  total: number;
  page: number;
  per_page: number;
  has_more: boolean;
}

/**
 * Request payload for creating a new video
 */
export interface VideoCreateRequest {
  youtube_id: string;
  title: string;
  channel_name?: string;
  duration_seconds?: number;
  thumbnail_url?: string;
  transcript: string;
  group_id?: string;
}

/**
 * Request payload for moving a video to a different group
 */
export interface MoveVideoRequest {
  group_id?: string | null;
}

// ============================================
// Group Types
// ============================================

/**
 * Video group/folder for organization
 * Matches backend GroupResponse model
 */
export interface Group {
  id: string;
  name: string;
  description?: string | null;
  color: string;
  video_count: number;
  created_at: string;
  updated_at: string;
}

/**
 * Group list response
 * Matches backend GroupListResponse model
 */
export interface GroupListResponse {
  groups: Group[];
  total: number;
}

/**
 * Request payload for creating a new group
 */
export interface GroupCreateRequest {
  name: string;
  description?: string;
  color?: string;
}

/**
 * Request payload for updating a group
 */
export interface GroupUpdateRequest {
  name?: string;
  description?: string;
  color?: string;
}

// Type aliases for alternative naming conventions
export type CreateGroupRequest = GroupCreateRequest;
export type UpdateGroupRequest = GroupUpdateRequest;

// ============================================
// Search Types
// ============================================

/**
 * Citation reference in search results
 */
export interface Citation {
  video_id?: string;
  video_title?: string;
  text?: string;
  timestamp?: string;
  [key: string]: unknown;
}

/**
 * Search response from knowledge base
 * Matches backend SearchResponse model
 */
export interface SearchResponse {
  answer: string;
  citations: Citation[];
}

/**
 * Search request payload
 */
export interface SearchRequest {
  query: string;
  group_id?: string;
}

/**
 * Chat request with conversation history
 */
export interface ChatRequest {
  query: string;
  group_id?: string;
  history?: ChatMessage[];
}

/**
 * Chat message for conversation history
 */
export interface ChatMessage {
  role: 'user' | 'assistant';
  content: string;
  citations?: Citation[];
}

// ============================================
// Summary Types
// ============================================

/**
 * Individual section summary from Chain of Density
 */
export interface SectionSummary {
  title: string;
  timestamp: string;
  description: string;
  summary: string;
  key_points: string[];
  entities: string[];
}

/**
 * Metadata about the summarization process
 */
export interface SummaryMetadata {
  model: string;
  method: string;
  transcript_length: number;
}

/**
 * Full structured video summary response
 */
export interface VideoSummaryResponse {
  success: boolean;
  video_id?: string | null;
  video_title: string;
  executive_summary: string;
  key_takeaways: string[];
  target_audience: string;
  sections: SectionSummary[];
  total_sections: number;
  metadata?: SummaryMetadata | null;
  error?: string | null;
  // Cache metadata
  cached?: boolean;  // True if returned from cache
  cached_at?: string | null;  // ISO timestamp when summary was cached
}

/**
 * Simple summary response (from search/summary endpoint)
 */
export interface SummaryResponse {
  summary: string;
  key_points: string[];
  video_id: string;
}

// ============================================
// Email Types
// ============================================

/**
 * Request to email a video summary
 */
export interface EmailSummaryRequest {
  recipient_email: string;
  summary_html: string;
  video_title?: string;
  channel_name?: string;
  duration_seconds?: number;
  transcript_length?: number;
}

/**
 * Response from email summary endpoint
 */
export interface EmailSummaryResponse {
  success: boolean;
  message?: string | null;
  recipient?: string | null;
  error?: string | null;
}

// ============================================
// Podcast Types
// ============================================

/**
 * Podcast source type (where the transcript came from)
 */
export type PodcastSource = 'fireflies' | 'zoom' | 'manual';

/**
 * Podcast record from the library
 * Matches backend PodcastResponse model
 */
export interface Podcast {
  id: string;
  external_id?: string | null;
  source: PodcastSource;
  title: string;
  subject?: string | null;
  organizer_email?: string | null;
  podcast_date?: string | null;
  duration_minutes?: number | null;
  participants?: string[] | null;
  transcript_length?: number | null;
  pinecone_file_id?: string | null;
  group_id?: string | null;
  group_name?: string | null;
  // Summary cache status
  has_summary?: boolean;
  summary_generated_at?: string | null;
  // Source-specific metadata
  source_metadata?: Record<string, unknown> | null;
  created_at: string;
  updated_at: string;
}

/**
 * Podcast with full transcript content
 */
export interface PodcastWithTranscript extends Podcast {
  transcript?: string | null;
}

/**
 * Paginated podcast list response
 * Matches backend PodcastListResponse model
 */
export interface PodcastListResponse {
  podcasts: Podcast[];
  total: number;
  page: number;
  per_page: number;
  has_more: boolean;
}

/**
 * Request payload for moving a podcast to a different group
 */
export interface MovePodcastRequest {
  group_id?: string | null;
}

/**
 * Podcast summary response
 */
export interface PodcastSummaryResponse {
  success: boolean;
  podcast_id?: string | null;
  podcast_title: string;
  podcast_subject?: string | null;
  podcast_date?: string | null;
  participants?: string[] | null;
  executive_summary: string;
  key_takeaways: string[];
  action_items: string[];
  decisions_made: string[];
  topics_discussed: string[];
  metadata?: Record<string, unknown> | null;
  error?: string | null;
  cached?: boolean;
  cached_at?: string | null;
}

// ============================================
// API Error Types
// ============================================

/**
 * Standard API error response
 */
export interface ApiError {
  detail: string;
  status_code?: number;
}
