/**
 * Unified Library Hook
 *
 * React Query hooks for fetching, filtering, and managing transcripts
 * from the unified /api/transcripts endpoint. Replaces separate
 * useTranscripts and usePodcasts hooks with a single, flexible interface.
 *
 * @see docs/UNIFIED_LIBRARY_PLAN.md for architecture details
 */
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api";
import type {
  Transcript,
  TranscriptListResponse,
  SourceType,
  VideoSummaryResponse,
  EmailSummaryRequest,
  EmailSummaryResponse,
} from "@/types/api";

// ============================================
// Query Key Factory
// ============================================

/**
 * Query key factory for unified library queries.
 * Provides structured, hierarchical keys for react-query caching.
 */
export const libraryKeys = {
  /** Root key for all library queries */
  all: ["library"] as const,

  /** Key for list queries (with filters) */
  lists: () => [...libraryKeys.all, "list"] as const,

  /** Key for a specific filtered list */
  list: (filters: UseLibraryOptions) => [...libraryKeys.lists(), filters] as const,

  /** Key for detail queries */
  details: () => [...libraryKeys.all, "detail"] as const,

  /** Key for a specific transcript detail */
  detail: (id: string) => [...libraryKeys.details(), id] as const,

  /** Key for summary queries */
  summaries: () => [...libraryKeys.all, "summary"] as const,

  /** Key for a specific transcript summary */
  summary: (id: string) => [...libraryKeys.summaries(), id] as const,
};

// ============================================
// Types
// ============================================

/**
 * Options for filtering and sorting library transcripts
 */
export interface UseLibraryOptions {
  /** Filter by group ID (null for ungrouped, undefined for all) */
  groupId?: string | null;

  /** Filter by source type (youtube, fireflies, zoom, etc.) */
  sourceType?: SourceType | null;

  /** If true, only fetch ungrouped transcripts (for "Recent" section) */
  ungroupedOnly?: boolean;

  /** Field to sort by */
  sortBy?: "created_at" | "title" | "source_type";

  /** Sort direction */
  sortOrder?: "asc" | "desc";

  /** Maximum number of transcripts to fetch */
  limit?: number;

  /** Offset for pagination */
  offset?: number;
}

/**
 * Request payload for moving a transcript to a group
 */
export interface MoveTranscriptRequest {
  group_id: string | null;
}

/**
 * Transcript with full transcript text content
 */
export interface TranscriptWithText extends Transcript {
  transcript_text?: string | null;
}

// ============================================
// Library List Hook
// ============================================

/**
 * Hook to fetch library transcripts with filtering and sorting.
 *
 * Replaces useTranscripts and usePodcasts with unified interface.
 *
 * @param options - Filtering and sorting options
 * @returns React Query result with transcripts array
 *
 * @example
 * // Fetch all transcripts
 * const { data } = useLibrary();
 *
 * @example
 * // Fetch ungrouped transcripts (Recent section)
 * const { data } = useLibrary({ ungroupedOnly: true });
 *
 * @example
 * // Fetch YouTube videos only, sorted by title
 * const { data } = useLibrary({
 *   sourceType: 'youtube',
 *   sortBy: 'title',
 *   sortOrder: 'asc'
 * });
 *
 * @example
 * // Fetch transcripts in a specific group
 * const { data } = useLibrary({ groupId: 'group-uuid' });
 */
export function useLibrary(options: UseLibraryOptions = {}) {
  const {
    groupId,
    sourceType,
    ungroupedOnly = false,
    sortBy = "created_at",
    sortOrder = "desc",
    limit,
    offset,
  } = options;

  return useQuery({
    queryKey: libraryKeys.list(options),
    queryFn: async (): Promise<TranscriptListResponse> => {
      // Build query parameters
      const params: Record<string, string> = {};

      if (groupId) {
        params.group_id = groupId;
      }
      if (sourceType) {
        params.source_type = sourceType;
      }
      if (ungroupedOnly) {
        params.ungrouped = "true";
      }
      if (sortBy) {
        params.sort_by = sortBy;
      }
      if (sortOrder) {
        params.sort_order = sortOrder;
      }
      if (limit !== undefined) {
        params.limit = String(limit);
      }
      if (offset !== undefined) {
        params.offset = String(offset);
      }

      const { data } = await api.get<TranscriptListResponse>("/api/transcripts", { params });
      return data;
    },
  });
}

// ============================================
// Single Transcript Hook
// ============================================

/**
 * Hook to fetch a single transcript with full text content.
 *
 * @param id - Transcript UUID
 * @returns React Query result with transcript details
 */
export function useTranscriptDetail(id: string) {
  return useQuery({
    queryKey: libraryKeys.detail(id),
    queryFn: async (): Promise<TranscriptWithText> => {
      const { data } = await api.get<TranscriptWithText>(`/api/transcripts/${id}`, {
        params: { include_transcript: true },
      });
      return data;
    },
    enabled: !!id,
  });
}

// ============================================
// Move Transcript Mutation
// ============================================

/**
 * Hook to move a transcript to a different group.
 *
 * Invalidates both 'library' and 'groups' queries on success
 * to refresh counts and list membership.
 *
 * @returns Mutation function and state
 *
 * @example
 * const moveTranscript = useMoveTranscript();
 *
 * // Move to a group
 * moveTranscript.mutate({ transcriptId: 'uuid', groupId: 'group-uuid' });
 *
 * // Move to Recent (ungrouped)
 * moveTranscript.mutate({ transcriptId: 'uuid', groupId: null });
 */
export function useMoveTranscript() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async ({
      transcriptId,
      groupId,
    }: {
      transcriptId: string;
      groupId: string | null;
    }): Promise<Transcript> => {
      const payload: MoveTranscriptRequest = { group_id: groupId };
      const { data } = await api.patch<Transcript>(
        `/api/transcripts/${transcriptId}/group`,
        payload
      );
      return data;
    },
    onSuccess: () => {
      // Invalidate all library list queries since group membership changed
      queryClient.invalidateQueries({ queryKey: libraryKeys.lists() });
      // Invalidate groups queries to update transcript counts
      queryClient.invalidateQueries({ queryKey: ["groups"] });
    },
  });
}

// ============================================
// Delete Transcript Mutation
// ============================================

/**
 * Hook to delete a transcript from the library.
 *
 * Removes the transcript from both PostgreSQL and Pinecone.
 * Invalidates both 'library' and 'groups' queries on success.
 *
 * @returns Mutation function and state
 *
 * @example
 * const deleteTranscript = useDeleteTranscript();
 * deleteTranscript.mutate('transcript-uuid');
 */
export function useDeleteTranscript() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (transcriptId: string): Promise<void> => {
      await api.delete(`/api/transcripts/${transcriptId}`);
    },
    onSuccess: () => {
      // Invalidate all library list queries
      queryClient.invalidateQueries({ queryKey: libraryKeys.lists() });
      // Invalidate groups queries to update transcript counts
      queryClient.invalidateQueries({ queryKey: ["groups"] });
    },
  });
}

// ============================================
// Transcript Summary Hook
// ============================================

/**
 * Options for fetching transcript summary
 */
export interface UseTranscriptSummaryOptions {
  /** If true, force regeneration even if cached summary exists */
  forceRegenerate?: boolean;

  /** If false, disable the query (useful for conditional fetching) */
  enabled?: boolean;
}

/**
 * Hook to fetch or generate a summary for a transcript.
 *
 * Uses cached summary if available, otherwise generates a new one
 * using the Chain of Density summarization pipeline.
 *
 * @param transcriptId - UUID of the transcript
 * @param options - Configuration options
 * @returns React Query result with summary data
 *
 * @example
 * // Fetch summary (use cache if available)
 * const { data, isLoading } = useTranscriptSummary('transcript-uuid');
 *
 * @example
 * // Force regeneration of summary
 * const { data } = useTranscriptSummary('transcript-uuid', {
 *   forceRegenerate: true
 * });
 *
 * @example
 * // Conditionally fetch summary
 * const { data } = useTranscriptSummary(transcriptId, {
 *   enabled: !!transcriptId && showSummary
 * });
 */
export function useTranscriptSummary(
  transcriptId: string,
  options: UseTranscriptSummaryOptions = {}
) {
  const { forceRegenerate = false, enabled = true } = options;

  return useQuery({
    queryKey: [...libraryKeys.summary(transcriptId), { forceRegenerate }],
    queryFn: async (): Promise<VideoSummaryResponse> => {
      const { data } = await api.get<VideoSummaryResponse>(
        `/api/transcripts/${transcriptId}/summary`,
        {
          params: { force_regenerate: forceRegenerate },
        }
      );
      return data;
    },
    enabled: enabled && !!transcriptId,
    // Summary generation can take a while, so don't auto-refetch
    staleTime: 5 * 60 * 1000, // 5 minutes
    gcTime: 30 * 60 * 1000, // 30 minutes (formerly cacheTime)
  });
}

// ============================================
// Generate Summary Mutation
// ============================================

/**
 * Hook to generate a summary for a transcript on demand.
 *
 * Use this mutation variant when you need explicit control over
 * when summary generation occurs (e.g., button click).
 *
 * @returns Mutation function and state
 *
 * @example
 * const generateSummary = useGenerateTranscriptSummary();
 *
 * const handleClick = () => {
 *   generateSummary.mutate({
 *     transcriptId: 'uuid',
 *     forceRegenerate: false
 *   });
 * };
 */
export function useGenerateTranscriptSummary() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async ({
      transcriptId,
      forceRegenerate = false,
    }: {
      transcriptId: string;
      forceRegenerate?: boolean;
    }): Promise<VideoSummaryResponse> => {
      const { data } = await api.get<VideoSummaryResponse>(
        `/api/transcripts/${transcriptId}/summary`,
        {
          params: { force_regenerate: forceRegenerate },
        }
      );
      return data;
    },
    onSuccess: (_data, variables) => {
      // Invalidate the summary query to reflect new data
      queryClient.invalidateQueries({
        queryKey: libraryKeys.summary(variables.transcriptId),
      });
      // Also invalidate the transcript detail as has_summary may have changed
      queryClient.invalidateQueries({
        queryKey: libraryKeys.detail(variables.transcriptId),
      });
    },
  });
}

// ============================================
// Email Summary Mutation
// ============================================

/**
 * Hook to email a transcript summary to a recipient.
 *
 * @returns Mutation function and state
 *
 * @example
 * const emailSummary = useEmailTranscriptSummary();
 *
 * emailSummary.mutate({
 *   transcriptId: 'uuid',
 *   request: {
 *     recipient_email: 'user@example.com',
 *     summary_html: '<h1>Summary</h1>...'
 *   }
 * });
 */
export function useEmailTranscriptSummary() {
  return useMutation({
    mutationFn: async ({
      transcriptId,
      request,
    }: {
      transcriptId: string;
      request: EmailSummaryRequest;
    }): Promise<EmailSummaryResponse> => {
      const { data } = await api.post<EmailSummaryResponse>(
        `/api/transcripts/${transcriptId}/email-summary`,
        request
      );
      return data;
    },
  });
}

// ============================================
// Sync to Pinecone Mutation
// ============================================

/**
 * Response from the sync-pinecone endpoint
 */
interface SyncPineconeResponse {
  success: boolean;
  message: string;
  pinecone_file_id: string;
  video_id_in_pinecone: string;
}

/**
 * Hook to sync a transcript to Pinecone for RAG search.
 *
 * Use this to fix transcripts that weren't properly uploaded
 * to Pinecone during creation.
 *
 * @returns Mutation function and state
 *
 * @example
 * const syncToPinecone = useSyncTranscriptToPinecone();
 * syncToPinecone.mutate('transcript-uuid');
 */
export function useSyncTranscriptToPinecone() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (transcriptId: string): Promise<SyncPineconeResponse> => {
      const { data } = await api.post<SyncPineconeResponse>(
        `/api/transcripts/${transcriptId}/sync-pinecone`
      );
      return data;
    },
    onSuccess: (_data, transcriptId) => {
      // Invalidate the specific transcript detail to refresh pinecone_file_id
      queryClient.invalidateQueries({ queryKey: libraryKeys.detail(transcriptId) });
      // Invalidate list queries as pinecone status may be displayed
      queryClient.invalidateQueries({ queryKey: libraryKeys.lists() });
    },
  });
}

// ============================================
// Utility Exports
// ============================================

/**
 * Default export for convenient importing
 */
export default useLibrary;
