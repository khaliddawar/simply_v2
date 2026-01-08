import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api";
import type {
  Podcast,
  PodcastListResponse,
  PodcastWithTranscript,
  MovePodcastRequest,
  PodcastSummaryResponse,
} from "@/types/api";

/**
 * Query key factory for podcasts
 */
export const podcastKeys = {
  all: ["podcasts"] as const,
  lists: () => [...podcastKeys.all, "list"] as const,
  list: (groupId?: string | null) => [...podcastKeys.lists(), { groupId }] as const,
  details: () => [...podcastKeys.all, "detail"] as const,
  detail: (id: string) => [...podcastKeys.details(), id] as const,
};

/**
 * Hook to fetch list of podcasts, optionally filtered by group
 * @param groupId - Optional group ID to filter podcasts
 */
export function usePodcasts(groupId?: string | null) {
  return useQuery({
    queryKey: podcastKeys.list(groupId),
    queryFn: async (): Promise<PodcastListResponse> => {
      const params: Record<string, string> = {};
      if (groupId) params.group_id = groupId;
      const { data } = await api.get("/api/podcasts", { params });
      return data;
    },
  });
}

/**
 * Hook to fetch a single podcast with full transcript text
 * @param id - Podcast ID
 */
export function usePodcast(id: string) {
  return useQuery({
    queryKey: podcastKeys.detail(id),
    queryFn: async (): Promise<PodcastWithTranscript> => {
      const { data } = await api.get(`/api/podcasts/${id}`, {
        params: { include_transcript: true },
      });
      return data;
    },
    enabled: !!id,
  });
}

/**
 * Hook to delete a podcast
 * Invalidates podcast list queries on success
 */
export function useDeletePodcast() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (id: string): Promise<void> => {
      await api.delete(`/api/podcasts/${id}`);
    },
    onSuccess: () => {
      // Invalidate all podcast list queries
      queryClient.invalidateQueries({ queryKey: podcastKeys.lists() });
    },
  });
}

/**
 * Hook to move a podcast to a different group
 * Invalidates podcast list queries on success
 */
export function useMovePodcast() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async ({
      id,
      groupId,
    }: {
      id: string;
      groupId: string | null;
    }): Promise<Podcast> => {
      const payload: MovePodcastRequest = { group_id: groupId };
      const { data } = await api.patch(`/api/podcasts/${id}/group`, payload);
      return data;
    },
    onSuccess: () => {
      // Invalidate all podcast list queries since group membership changed
      queryClient.invalidateQueries({ queryKey: podcastKeys.lists() });
    },
  });
}

/**
 * Hook to generate a summary for a podcast
 * Calls the backend summarization service
 *
 * @param forceRegenerate - If true, regenerates summary even if cached version exists
 */
export function useGeneratePodcastSummary() {
  return useMutation({
    mutationFn: async ({
      podcastId,
      forceRegenerate = false,
    }: {
      podcastId: string;
      forceRegenerate?: boolean;
    }): Promise<PodcastSummaryResponse> => {
      const { data } = await api.get(`/api/podcasts/${podcastId}/summary`, {
        params: { force_regenerate: forceRegenerate },
      });
      return data;
    },
  });
}
