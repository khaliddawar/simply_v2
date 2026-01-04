/**
 * Library Statistics Hook
 *
 * Computes aggregate statistics from the user's video library
 * for display in the right panel overview.
 */
import { useMemo } from 'react';
import { useTranscripts } from './useTranscripts';
import { useGroups } from './useGroups';

/**
 * Computed library statistics
 */
export interface LibraryStats {
  totalVideos: number;
  totalGroups: number;
  totalDurationSeconds: number;
  totalDurationFormatted: string;
  totalTranscriptLength: number;
  isLoading: boolean;
}

/**
 * Format duration in seconds to a readable string
 * @param seconds - Total seconds
 * @returns Formatted string like "4.2 hrs" or "45 min"
 */
function formatDuration(seconds: number): string {
  if (seconds < 60) {
    return `${seconds} sec`;
  }

  const hours = seconds / 3600;
  if (hours >= 1) {
    return `${hours.toFixed(1)} hrs`;
  }

  const minutes = Math.round(seconds / 60);
  return `${minutes} min`;
}

/**
 * Hook to compute library statistics from videos and groups
 *
 * Uses useTranscripts and useGroups to aggregate:
 * - Total video count
 * - Total group count
 * - Total content duration
 * - Total transcript length
 */
export function useLibraryStats(): LibraryStats {
  const { data: transcriptsData, isLoading: transcriptsLoading } = useTranscripts();
  const { data: groups, isLoading: groupsLoading } = useGroups();

  const stats = useMemo(() => {
    const videos = transcriptsData?.videos ?? [];

    // Calculate total duration
    const totalDurationSeconds = videos.reduce(
      (sum, video) => sum + (video.duration_seconds ?? 0),
      0
    );

    // Calculate total transcript length
    const totalTranscriptLength = videos.reduce(
      (sum, video) => sum + (video.transcript_length ?? 0),
      0
    );

    return {
      totalVideos: transcriptsData?.total ?? 0,
      totalGroups: groups?.length ?? 0,
      totalDurationSeconds,
      totalDurationFormatted: formatDuration(totalDurationSeconds),
      totalTranscriptLength,
      isLoading: transcriptsLoading || groupsLoading,
    };
  }, [transcriptsData, groups, transcriptsLoading, groupsLoading]);

  return stats;
}

export default useLibraryStats;
