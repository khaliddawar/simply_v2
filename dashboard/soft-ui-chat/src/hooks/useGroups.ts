import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api";
import type {
  Group,
  GroupListResponse,
  GroupCreateRequest,
  GroupUpdateRequest,
} from "@/types/api";
import { transcriptKeys } from "@/hooks/useTranscripts";

/**
 * Query key factory for groups
 */
export const groupKeys = {
  all: ["groups"] as const,
  lists: () => [...groupKeys.all, "list"] as const,
  list: () => [...groupKeys.lists()] as const,
  details: () => [...groupKeys.all, "detail"] as const,
  detail: (id: string) => [...groupKeys.details(), id] as const,
};

/**
 * Hook to fetch all groups for the current user
 */
export function useGroups() {
  return useQuery({
    queryKey: groupKeys.list(),
    queryFn: async (): Promise<Group[]> => {
      const { data } = await api.get<GroupListResponse>("/api/groups");
      return data.groups;
    },
  });
}

/**
 * Hook to create a new group
 * Invalidates group list queries on success
 */
export function useCreateGroup() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (payload: GroupCreateRequest): Promise<Group> => {
      const { data } = await api.post("/api/groups", payload);
      return data;
    },
    onSuccess: () => {
      // Invalidate group list to refetch with new group
      queryClient.invalidateQueries({ queryKey: groupKeys.lists() });
    },
  });
}

/**
 * Hook to update an existing group
 * Invalidates group list and transcript list queries on success
 */
export function useUpdateGroup() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async ({
      id,
      ...payload
    }: GroupUpdateRequest & { id: string }): Promise<Group> => {
      const { data } = await api.put(`/api/groups/${id}`, payload);
      return data;
    },
    onSuccess: () => {
      // Invalidate group list to reflect changes
      queryClient.invalidateQueries({ queryKey: groupKeys.lists() });
      // Invalidate transcript lists since group name/color might be displayed there
      queryClient.invalidateQueries({ queryKey: transcriptKeys.lists() });
    },
  });
}

/**
 * Hook to delete a group
 * Invalidates group list and transcript list queries on success
 */
export function useDeleteGroup() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (id: string): Promise<void> => {
      await api.delete(`/api/groups/${id}`);
    },
    onSuccess: () => {
      // Invalidate group list to remove deleted group
      queryClient.invalidateQueries({ queryKey: groupKeys.lists() });
      // Invalidate transcript lists since videos in deleted group become ungrouped
      queryClient.invalidateQueries({ queryKey: transcriptKeys.lists() });
    },
  });
}
