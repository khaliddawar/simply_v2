/**
 * Video Details Panel Component
 *
 * Displays selected video information with thumbnail,
 * metadata, and quick actions.
 */
import { useState } from 'react';
import {
  Play,
  FolderOpen,
  Calendar,
  Clock,
  FileText,
  Mail,
  Trash2,
  Sparkles,
  ExternalLink,
  Loader2,
} from 'lucide-react';
import { useSelectedTranscript } from '@/hooks/useSelectedTranscript';
import { useDeleteTranscript } from '@/hooks/useTranscripts';
import { toast } from 'sonner';

/**
 * Format duration from seconds to MM:SS or HH:MM:SS
 */
function formatDuration(seconds?: number | null): string {
  if (!seconds) return '--:--';

  const hours = Math.floor(seconds / 3600);
  const minutes = Math.floor((seconds % 3600) / 60);
  const secs = seconds % 60;

  if (hours > 0) {
    return `${hours}:${minutes.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}`;
  }
  return `${minutes}:${secs.toString().padStart(2, '0')}`;
}

/**
 * Format date to readable string
 */
function formatDate(dateString: string): string {
  const date = new Date(dateString);
  return date.toLocaleDateString('en-US', {
    month: 'short',
    day: 'numeric',
    year: 'numeric',
  });
}

/**
 * VideoDetailsPanel - Shows selected video info and actions
 */
export function VideoDetailsPanel() {
  const { selectedTranscript, clearSelection } = useSelectedTranscript();
  const deleteTranscript = useDeleteTranscript();
  const [isDeleting, setIsDeleting] = useState(false);

  if (!selectedTranscript) {
    return null;
  }

  const {
    id,
    youtube_id,
    title,
    channel_name,
    duration_seconds,
    thumbnail_url,
    group_name,
    created_at,
    transcript_length,
  } = selectedTranscript;

  const youtubeUrl = `https://www.youtube.com/watch?v=${youtube_id}`;

  const handleOpenYouTube = () => {
    window.open(youtubeUrl, '_blank', 'noopener,noreferrer');
  };

  const handleGenerateSummary = () => {
    // TODO: Implement summary generation
    toast.info('Summary generation coming soon!');
  };

  const handleEmailSummary = () => {
    // TODO: Implement email summary
    toast.info('Email summary coming soon!');
  };

  const handleDelete = async () => {
    if (!confirm('Are you sure you want to delete this video from your library?')) {
      return;
    }

    setIsDeleting(true);
    try {
      await deleteTranscript.mutateAsync(id);
      toast.success('Video deleted successfully');
      clearSelection();
    } catch {
      toast.error('Failed to delete video');
    } finally {
      setIsDeleting(false);
    }
  };

  return (
    <div className="flex flex-col h-full">
      {/* Thumbnail */}
      <div className="relative aspect-video bg-accent">
        {thumbnail_url ? (
          <img
            src={thumbnail_url}
            alt={title}
            className="w-full h-full object-cover"
          />
        ) : (
          <div className="w-full h-full flex items-center justify-center">
            <Play className="w-12 h-12 text-muted-foreground/30" />
          </div>
        )}
        {/* Duration Badge */}
        <div className="absolute bottom-2 right-2 px-1.5 py-0.5 bg-black/80 rounded text-xxs text-white font-medium">
          {formatDuration(duration_seconds)}
        </div>
        {/* Play Overlay */}
        <button
          onClick={handleOpenYouTube}
          className="absolute inset-0 flex items-center justify-center bg-black/0 hover:bg-black/30 transition-colors group"
          aria-label="Open on YouTube"
        >
          <div className="w-12 h-12 rounded-full bg-white/90 flex items-center justify-center opacity-0 group-hover:opacity-100 transition-opacity">
            <Play className="w-5 h-5 text-black ml-0.5" />
          </div>
        </button>
      </div>

      {/* Video Info */}
      <div className="p-4 border-b border-border/50">
        <h2 className="font-semibold text-sm text-foreground leading-tight mb-1 line-clamp-2">
          {title}
        </h2>
        {channel_name && (
          <p className="text-xs text-muted-foreground">{channel_name}</p>
        )}
      </div>

      {/* Metadata */}
      <div className="p-4 border-b border-border/50 space-y-2">
        {/* Group */}
        <div className="flex items-center gap-2 text-xs">
          <FolderOpen className="w-3.5 h-3.5 text-muted-foreground" />
          <span className="text-muted-foreground">Group:</span>
          <span className="font-medium text-foreground">
            {group_name || 'Ungrouped'}
          </span>
        </div>

        {/* Added Date */}
        <div className="flex items-center gap-2 text-xs">
          <Calendar className="w-3.5 h-3.5 text-muted-foreground" />
          <span className="text-muted-foreground">Added:</span>
          <span className="font-medium text-foreground">
            {formatDate(created_at)}
          </span>
        </div>

        {/* Duration */}
        <div className="flex items-center gap-2 text-xs">
          <Clock className="w-3.5 h-3.5 text-muted-foreground" />
          <span className="text-muted-foreground">Duration:</span>
          <span className="font-medium text-foreground">
            {formatDuration(duration_seconds)}
          </span>
        </div>

        {/* Transcript Length */}
        {transcript_length && (
          <div className="flex items-center gap-2 text-xs">
            <FileText className="w-3.5 h-3.5 text-muted-foreground" />
            <span className="text-muted-foreground">Transcript:</span>
            <span className="font-medium text-foreground">
              {transcript_length.toLocaleString()} chars
            </span>
          </div>
        )}
      </div>

      {/* Generate Summary Button */}
      <div className="p-4 border-b border-border/50">
        <button
          onClick={handleGenerateSummary}
          className="w-full flex items-center justify-center gap-2 px-4 py-2.5
                     bg-primary text-primary-foreground rounded-lg font-medium text-sm
                     hover:bg-primary/90 transition-colors"
        >
          <Sparkles className="w-4 h-4" />
          Generate Summary
        </button>
      </div>

      {/* Quick Actions */}
      <div className="p-4 flex-1">
        <h3 className="text-xs font-semibold text-foreground mb-3">Quick Actions</h3>
        <div className="space-y-2">
          {/* Open on YouTube */}
          <button
            onClick={handleOpenYouTube}
            className="w-full flex items-center gap-2 px-3 py-2 rounded-lg border border-border/50
                       text-xs text-foreground hover:bg-accent transition-colors"
          >
            <ExternalLink className="w-3.5 h-3.5 text-muted-foreground" />
            Open on YouTube
          </button>

          {/* Email Summary */}
          <button
            onClick={handleEmailSummary}
            className="w-full flex items-center gap-2 px-3 py-2 rounded-lg border border-border/50
                       text-xs text-foreground hover:bg-accent transition-colors"
          >
            <Mail className="w-3.5 h-3.5 text-muted-foreground" />
            Email Summary
          </button>

          {/* Delete */}
          <button
            onClick={handleDelete}
            disabled={isDeleting}
            className="w-full flex items-center gap-2 px-3 py-2 rounded-lg border border-destructive/30
                       text-xs text-destructive hover:bg-destructive/10 transition-colors
                       disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {isDeleting ? (
              <Loader2 className="w-3.5 h-3.5 animate-spin" />
            ) : (
              <Trash2 className="w-3.5 h-3.5" />
            )}
            {isDeleting ? 'Deleting...' : 'Delete Video'}
          </button>
        </div>
      </div>
    </div>
  );
}

export default VideoDetailsPanel;
