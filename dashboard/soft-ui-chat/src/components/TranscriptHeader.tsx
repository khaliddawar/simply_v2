/**
 * TranscriptHeader Component
 *
 * Displays the currently selected transcript information as a compact banner
 * at the top of the chat area. Shows video thumbnail, title, channel name,
 * and duration with a clear selection button.
 */
import { X, Video as VideoIcon } from "lucide-react";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { useSelectedTranscript } from "@/hooks/useSelectedTranscript";
import type { Video } from "@/types/api";

/**
 * Format duration in seconds to human-readable string (e.g., "15 min" or "1 hr 30 min")
 */
function formatDuration(seconds: number | null | undefined): string {
  if (!seconds) return "";

  const hours = Math.floor(seconds / 3600);
  const minutes = Math.floor((seconds % 3600) / 60);

  if (hours > 0) {
    return minutes > 0 ? `${hours} hr ${minutes} min` : `${hours} hr`;
  }
  return `${minutes} min`;
}

/**
 * Props for TranscriptHeader component
 */
interface TranscriptHeaderProps {
  /** Optional className for additional styling */
  className?: string;
}

/**
 * TranscriptHeader displays the currently selected transcript as a compact banner.
 *
 * Features:
 * - Shows video thumbnail (if available) or placeholder icon
 * - Displays video title with truncation for long titles
 * - Shows channel name and duration
 * - Provides a clear selection button to deselect the transcript
 */
export function TranscriptHeader({ className }: TranscriptHeaderProps) {
  const { selectedTranscript, clearSelection } = useSelectedTranscript();

  // Don't render if no transcript is selected
  if (!selectedTranscript) {
    return null;
  }

  const { title, channel_name, duration_seconds, thumbnail_url } = selectedTranscript;

  return (
    <Card className={`mx-4 mt-4 mb-2 overflow-hidden ${className || ""}`}>
      <div className="flex items-center gap-3 p-3">
        {/* Thumbnail or placeholder */}
        <div className="flex-shrink-0 w-16 h-10 rounded-md overflow-hidden bg-muted flex items-center justify-center">
          {thumbnail_url ? (
            <img
              src={thumbnail_url}
              alt={title}
              className="w-full h-full object-cover"
            />
          ) : (
            <VideoIcon className="w-5 h-5 text-muted-foreground" />
          )}
        </div>

        {/* Video info */}
        <div className="flex-1 min-w-0">
          <h3 className="text-sm font-medium text-foreground truncate" title={title}>
            {title}
          </h3>
          <p className="text-xs text-muted-foreground truncate">
            {channel_name || "Unknown channel"}
            {duration_seconds ? ` \u2022 ${formatDuration(duration_seconds)}` : ""}
          </p>
        </div>

        {/* Clear selection button */}
        <Button
          variant="ghost"
          size="sm"
          onClick={clearSelection}
          className="flex-shrink-0 h-8 w-8 p-0 text-muted-foreground hover:text-foreground"
          title="Clear selection"
        >
          <X className="w-4 h-4" />
          <span className="sr-only">Clear selection</span>
        </Button>
      </div>
    </Card>
  );
}

export default TranscriptHeader;
