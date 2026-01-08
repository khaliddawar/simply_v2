/**
 * Podcast Details Panel Component
 *
 * Displays selected podcast information with metadata
 * and quick actions.
 */
import { useState } from 'react';
import {
  Mic,
  FolderOpen,
  Calendar,
  Clock,
  FileText,
  Trash2,
  Sparkles,
  Loader2,
  Users,
  RefreshCw,
  CheckCircle,
  ListTodo,
  MessageSquare,
  Lightbulb,
} from 'lucide-react';
import { useSelectedPodcast } from '@/hooks/useSelectedPodcast';
import { useDeletePodcast, useGeneratePodcastSummary } from '@/hooks/usePodcasts';
import { toast } from 'sonner';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
} from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import type { PodcastSummaryResponse } from '@/types/api';

/**
 * Format duration from minutes to human-readable format
 */
function formatDuration(minutes?: number | null): string {
  if (!minutes) return '--:--';

  const hours = Math.floor(minutes / 60);
  const mins = minutes % 60;

  if (hours > 0) {
    return `${hours}h ${mins}m`;
  }
  return `${mins}m`;
}

/**
 * Format date to readable string
 */
function formatDate(dateString?: string | null): string {
  if (!dateString) return 'Unknown';
  const date = new Date(dateString);
  return date.toLocaleDateString('en-US', {
    month: 'short',
    day: 'numeric',
    year: 'numeric',
  });
}

/**
 * Get source display name
 */
function getSourceLabel(source: string): string {
  switch (source) {
    case 'fireflies':
      return 'Fireflies.ai';
    case 'zoom':
      return 'Zoom';
    case 'manual':
      return 'Manual Upload';
    default:
      return source;
  }
}

/**
 * PodcastDetailsPanel - Shows selected podcast info and actions
 */
export function PodcastDetailsPanel() {
  const { selectedPodcast, clearSelection } = useSelectedPodcast();
  const deletePodcast = useDeletePodcast();
  const generateSummary = useGeneratePodcastSummary();

  const [isDeleting, setIsDeleting] = useState(false);
  const [showSummaryDialog, setShowSummaryDialog] = useState(false);
  const [summary, setSummary] = useState<PodcastSummaryResponse | null>(null);

  if (!selectedPodcast) {
    return null;
  }

  const {
    id,
    title,
    subject,
    source,
    podcast_date,
    duration_minutes,
    participants,
    group_name,
    created_at,
    transcript_length,
  } = selectedPodcast;

  const handleGenerateSummary = async (forceRegenerate = false) => {
    try {
      const result = await generateSummary.mutateAsync({
        podcastId: id,
        forceRegenerate,
      });
      if (result.success) {
        setSummary(result);
        setShowSummaryDialog(true);
        if (result.cached) {
          toast.success('Loaded cached summary');
        } else {
          toast.success('Summary generated successfully');
        }
      } else {
        toast.error(result.error || 'Failed to generate summary');
      }
    } catch {
      toast.error('Failed to generate summary. Please try again.');
    }
  };

  const handleDelete = async () => {
    if (!confirm('Are you sure you want to delete this podcast from your library?')) {
      return;
    }

    setIsDeleting(true);
    try {
      await deletePodcast.mutateAsync(id);
      toast.success('Podcast deleted successfully');
      clearSelection();
    } catch {
      toast.error('Failed to delete podcast');
    } finally {
      setIsDeleting(false);
    }
  };

  return (
    <div className="flex flex-col h-full">
      {/* Header */}
      <div className="relative aspect-video bg-gradient-to-br from-purple-500/20 to-indigo-500/20 flex items-center justify-center">
        <Mic className="w-16 h-16 text-purple-500/50" />
        {/* Source Badge */}
        <div className="absolute bottom-2 right-2 px-2 py-0.5 bg-black/80 rounded text-xxs text-white font-medium">
          {getSourceLabel(source)}
        </div>
      </div>

      {/* Podcast Info */}
      <div className="p-4 border-b border-border/50">
        <h2 className="font-semibold text-sm text-foreground leading-tight mb-1 line-clamp-2">
          {title}
        </h2>
        {subject && (
          <p className="text-xs text-muted-foreground">{subject}</p>
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

        {/* Podcast Date */}
        {podcast_date && (
          <div className="flex items-center gap-2 text-xs">
            <Calendar className="w-3.5 h-3.5 text-muted-foreground" />
            <span className="text-muted-foreground">Date:</span>
            <span className="font-medium text-foreground">
              {formatDate(podcast_date)}
            </span>
          </div>
        )}

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
            {formatDuration(duration_minutes)}
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

        {/* Participants */}
        {participants && participants.length > 0 && (
          <div className="flex items-start gap-2 text-xs">
            <Users className="w-3.5 h-3.5 text-muted-foreground mt-0.5" />
            <span className="text-muted-foreground">Participants:</span>
            <span className="font-medium text-foreground flex-1">
              {participants.slice(0, 3).join(', ')}
              {participants.length > 3 && ` +${participants.length - 3} more`}
            </span>
          </div>
        )}
      </div>

      {/* Generate Summary Button */}
      <div className="p-4 border-b border-border/50">
        <button
          onClick={() => handleGenerateSummary(false)}
          disabled={generateSummary.isPending}
          className="w-full flex items-center justify-center gap-2 px-4 py-2.5
                     bg-primary text-primary-foreground rounded-lg font-medium text-sm
                     hover:bg-primary/90 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
        >
          {generateSummary.isPending ? (
            <>
              <Loader2 className="w-4 h-4 animate-spin" />
              Generating...
            </>
          ) : (
            <>
              <Sparkles className="w-4 h-4" />
              {summary ? 'View Summary' : 'Generate Summary'}
            </>
          )}
        </button>
        {summary && !generateSummary.isPending && (
          <div className="mt-2 flex flex-col gap-1">
            <button
              onClick={() => setShowSummaryDialog(true)}
              className="w-full text-xs text-primary hover:underline"
            >
              Click to view generated summary
            </button>
            {summary.cached && (
              <span className="text-xs text-muted-foreground text-center">
                Cached • <button
                  onClick={() => handleGenerateSummary(true)}
                  className="text-primary hover:underline"
                >
                  Regenerate
                </button>
              </span>
            )}
          </div>
        )}
      </div>

      {/* Quick Actions */}
      <div className="p-4 flex-1">
        <h3 className="text-xs font-semibold text-foreground mb-3">Quick Actions</h3>
        <div className="space-y-2">
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
            {isDeleting ? 'Deleting...' : 'Delete Podcast'}
          </button>
        </div>
      </div>

      {/* Summary Dialog */}
      <Dialog open={showSummaryDialog} onOpenChange={setShowSummaryDialog}>
        <DialogContent className="max-w-2xl max-h-[80vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <Sparkles className="w-5 h-5 text-primary" />
              Podcast Summary
              {summary?.cached && (
                <span className="ml-2 text-xs font-normal bg-accent text-muted-foreground px-2 py-0.5 rounded">
                  Cached
                </span>
              )}
            </DialogTitle>
            <DialogDescription>{title}</DialogDescription>
          </DialogHeader>

          {summary && (
            <div className="space-y-6 py-4">
              {/* Executive Summary */}
              <div>
                <h3 className="text-sm font-semibold text-foreground mb-2 flex items-center gap-2">
                  <CheckCircle className="w-4 h-4 text-green-500" />
                  Overview
                </h3>
                <p className="text-sm text-muted-foreground leading-relaxed">
                  {summary.executive_summary}
                </p>
              </div>

              {/* Key Takeaways */}
              {summary.key_takeaways.length > 0 && (
                <div>
                  <h3 className="text-sm font-semibold text-foreground mb-2 flex items-center gap-2">
                    <Lightbulb className="w-4 h-4 text-yellow-500" />
                    Key Takeaways
                  </h3>
                  <ul className="space-y-1.5">
                    {summary.key_takeaways.map((takeaway, i) => (
                      <li
                        key={i}
                        className="text-sm text-muted-foreground flex items-start gap-2"
                      >
                        <span className="text-primary mt-0.5">•</span>
                        {takeaway}
                      </li>
                    ))}
                  </ul>
                </div>
              )}

              {/* Action Items */}
              {summary.action_items.length > 0 && (
                <div>
                  <h3 className="text-sm font-semibold text-foreground mb-2 flex items-center gap-2">
                    <ListTodo className="w-4 h-4 text-blue-500" />
                    Action Items
                  </h3>
                  <ul className="space-y-1.5">
                    {summary.action_items.map((item, i) => (
                      <li
                        key={i}
                        className="text-sm text-muted-foreground flex items-start gap-2"
                      >
                        <span className="text-blue-500 mt-0.5">□</span>
                        {item}
                      </li>
                    ))}
                  </ul>
                </div>
              )}

              {/* Decisions Made */}
              {summary.decisions_made.length > 0 && (
                <div>
                  <h3 className="text-sm font-semibold text-foreground mb-2 flex items-center gap-2">
                    <CheckCircle className="w-4 h-4 text-green-500" />
                    Decisions Made
                  </h3>
                  <ul className="space-y-1.5">
                    {summary.decisions_made.map((decision, i) => (
                      <li
                        key={i}
                        className="text-sm text-muted-foreground flex items-start gap-2"
                      >
                        <span className="text-green-500 mt-0.5">✓</span>
                        {decision}
                      </li>
                    ))}
                  </ul>
                </div>
              )}

              {/* Topics Discussed */}
              {summary.topics_discussed.length > 0 && (
                <div>
                  <h3 className="text-sm font-semibold text-foreground mb-2 flex items-center gap-2">
                    <MessageSquare className="w-4 h-4 text-purple-500" />
                    Topics Discussed
                  </h3>
                  <div className="flex flex-wrap gap-2">
                    {summary.topics_discussed.map((topic, i) => (
                      <span
                        key={i}
                        className="text-xs bg-accent text-muted-foreground px-2 py-1 rounded"
                      >
                        {topic}
                      </span>
                    ))}
                  </div>
                </div>
              )}

              {/* Participants */}
              {summary.participants && summary.participants.length > 0 && (
                <div className="flex items-start gap-2 p-3 bg-accent/50 rounded-lg">
                  <Users className="w-4 h-4 text-muted-foreground mt-0.5" />
                  <div>
                    <span className="text-xs font-medium text-foreground">
                      Participants:
                    </span>
                    <p className="text-sm text-muted-foreground">
                      {summary.participants.join(', ')}
                    </p>
                  </div>
                </div>
              )}
            </div>
          )}

          <DialogFooter className="flex gap-2">
            <Button
              variant="outline"
              onClick={() => setShowSummaryDialog(false)}
            >
              Close
            </Button>
            <Button
              variant="outline"
              onClick={() => {
                setShowSummaryDialog(false);
                handleGenerateSummary(true);
              }}
              disabled={generateSummary.isPending}
            >
              <RefreshCw className="w-4 h-4 mr-2" />
              Regenerate
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}

export default PodcastDetailsPanel;
