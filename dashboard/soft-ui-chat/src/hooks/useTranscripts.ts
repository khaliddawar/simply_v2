import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api";
import type {
  Video,
  VideoListResponse,
  VideoWithTranscript,
  MoveVideoRequest,
} from "@/types/api";

/**
 * Query key factory for transcripts
 */
export const transcriptKeys = {
  all: ["transcripts"] as const,
  lists: () => [...transcriptKeys.all, "list"] as const,
  list: (groupId?: string | null) => [...transcriptKeys.lists(), { groupId }] as const,
  details: () => [...transcriptKeys.all, "detail"] as const,
  detail: (id: string) => [...transcriptKeys.details(), id] as const,
};

/**
 * Hook to fetch list of transcripts, optionally filtered by group
 * @param groupId - Optional group ID to filter transcripts
 */
export function useTranscripts(groupId?: string | null) {
  return useQuery({
    queryKey: transcriptKeys.list(groupId),
    queryFn: async (): Promise<VideoListResponse> => {
      const params: Record<string, string> = {};
      if (groupId) params.group_id = groupId;
      const { data } = await api.get("/api/videos", { params });
      return data;
    },
  });
}

/**
 * Hook to fetch a single transcript with full transcript text
 * @param id - Video/transcript ID
 */
export function useTranscript(id: string) {
  return useQuery({
    queryKey: transcriptKeys.detail(id),
    queryFn: async (): Promise<VideoWithTranscript> => {
      const { data } = await api.get(`/api/videos/${id}`, {
        params: { include_transcript: true },
      });
      return data;
    },
    enabled: !!id,
  });
}

/**
 * Hook to delete a transcript
 * Invalidates transcript list queries on success
 */
export function useDeleteTranscript() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (id: string): Promise<void> => {
      await api.delete(`/api/videos/${id}`);
    },
    onSuccess: () => {
      // Invalidate all transcript list queries
      queryClient.invalidateQueries({ queryKey: transcriptKeys.lists() });
    },
  });
}

/**
 * Hook to move a transcript to a different group
 * Invalidates transcript list queries on success
 */
export function useMoveTranscript() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async ({
      id,
      groupId,
    }: {
      id: string;
      groupId: string | null;
    }): Promise<Video> => {
      const payload: MoveVideoRequest = { group_id: groupId };
      const { data } = await api.put(`/api/videos/${id}/group`, payload);
      return data;
    },
    onSuccess: () => {
      // Invalidate all transcript list queries since group membership changed
      queryClient.invalidateQueries({ queryKey: transcriptKeys.lists() });
    },
  });
}
