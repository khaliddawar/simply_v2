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
  X,
  CheckCircle,
  Users,
} from 'lucide-react';
import { useSelectedTranscript } from '@/hooks/useSelectedTranscript';
import { useDeleteTranscript, useGenerateSummary, useEmailSummary } from '@/hooks/useTranscripts';
import { toast } from 'sonner';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
} from '@/components/ui/dialog';
import { Input } from '@/components/ui/input';
import { Button } from '@/components/ui/button';
import type { VideoSummaryResponse } from '@/types/api';

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
  const generateSummary = useGenerateSummary();
  const emailSummary = useEmailSummary();

  const [isDeleting, setIsDeleting] = useState(false);
  const [showSummaryDialog, setShowSummaryDialog] = useState(false);
  const [showEmailDialog, setShowEmailDialog] = useState(false);
  const [summary, setSummary] = useState<VideoSummaryResponse | null>(null);
  const [emailAddress, setEmailAddress] = useState('');

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

  const handleGenerateSummary = async () => {
    try {
      const result = await generateSummary.mutateAsync(id);
      if (result.success) {
        setSummary(result);
        setShowSummaryDialog(true);
      } else {
        toast.error(result.error || 'Failed to generate summary');
      }
    } catch {
      toast.error('Failed to generate summary. Please try again.');
    }
  };

  const handleEmailSummary = () => {
    if (!summary) {
      toast.info('Please generate a summary first');
      return;
    }
    setShowEmailDialog(true);
  };

  const handleSendEmail = async () => {
    if (!emailAddress || !summary) return;

    const summaryHtml = formatSummaryHtml(summary);
    try {
      const result = await emailSummary.mutateAsync({
        videoId: id,
        request: {
          recipient_email: emailAddress,
          summary_html: summaryHtml,
          video_title: title,
          channel_name: channel_name || undefined,
          duration_seconds: duration_seconds || undefined,
          transcript_length: transcript_length || undefined,
        },
      });

      if (result.success) {
        toast.success(`Summary sent to ${emailAddress}`);
        setShowEmailDialog(false);
        setEmailAddress('');
      } else {
        toast.error(result.error || 'Failed to send email');
      }
    } catch {
      toast.error('Failed to send email. Please try again.');
    }
  };

  /**
   * Format summary as HTML for email
   */
  function formatSummaryHtml(s: VideoSummaryResponse): string {
    let html = `<h2>Overview</h2><p>${s.executive_summary}</p>`;

    if (s.key_takeaways.length > 0) {
      html += '<h3>Key Takeaways</h3><ul>';
      s.key_takeaways.forEach((t) => {
        html += `<li>${t}</li>`;
      });
      html += '</ul>';
    }

    if (s.target_audience) {
      html += `<p><strong>Who this is for:</strong> ${s.target_audience}</p>`;
    }

    if (s.sections.length > 0) {
      html += '<h3>Detailed Breakdown</h3>';
      s.sections.forEach((section) => {
        html += `<h4>${section.title} (${section.timestamp})</h4>`;
        html += `<p>${section.summary}</p>`;
        if (section.key_points.length > 0) {
          html += '<ul>';
          section.key_points.forEach((p) => {
            html += `<li>${p}</li>`;
          });
          html += '</ul>';
        }
      });
    }

    return html;
  }

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
          <button
            onClick={() => setShowSummaryDialog(true)}
            className="w-full mt-2 text-xs text-primary hover:underline"
          >
            Click to view generated summary
          </button>
        )}
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
            disabled={!summary || emailSummary.isPending}
            className="w-full flex items-center gap-2 px-3 py-2 rounded-lg border border-border/50
                       text-xs text-foreground hover:bg-accent transition-colors
                       disabled:opacity-50 disabled:cursor-not-allowed"
          >
            <Mail className="w-3.5 h-3.5 text-muted-foreground" />
            {summary ? 'Email Summary' : 'Email Summary (generate first)'}
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

      {/* Summary Dialog */}
      <Dialog open={showSummaryDialog} onOpenChange={setShowSummaryDialog}>
        <DialogContent className="max-w-2xl max-h-[80vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <Sparkles className="w-5 h-5 text-primary" />
              Video Summary
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
                  <h3 className="text-sm font-semibold text-foreground mb-2">
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

              {/* Target Audience */}
              {summary.target_audience && (
                <div className="flex items-start gap-2 p-3 bg-accent/50 rounded-lg">
                  <Users className="w-4 h-4 text-muted-foreground mt-0.5" />
                  <div>
                    <span className="text-xs font-medium text-foreground">
                      Who this is for:
                    </span>
                    <p className="text-sm text-muted-foreground">
                      {summary.target_audience}
                    </p>
                  </div>
                </div>
              )}

              {/* Sections */}
              {summary.sections.length > 0 && (
                <div>
                  <h3 className="text-sm font-semibold text-foreground mb-3">
                    Detailed Breakdown ({summary.total_sections} sections)
                  </h3>
                  <div className="space-y-4">
                    {summary.sections.map((section, i) => (
                      <div
                        key={i}
                        className="border border-border/50 rounded-lg p-3"
                      >
                        <div className="flex items-center justify-between mb-2">
                          <h4 className="text-sm font-medium text-foreground">
                            {section.title}
                          </h4>
                          <span className="text-xs text-muted-foreground bg-accent px-2 py-0.5 rounded">
                            {section.timestamp}
                          </span>
                        </div>
                        <p className="text-sm text-muted-foreground mb-2">
                          {section.summary}
                        </p>
                        {section.key_points.length > 0 && (
                          <ul className="space-y-1">
                            {section.key_points.map((point, j) => (
                              <li
                                key={j}
                                className="text-xs text-muted-foreground flex items-start gap-1.5"
                              >
                                <span className="text-primary">–</span>
                                {point}
                              </li>
                            ))}
                          </ul>
                        )}
                      </div>
                    ))}
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
            <Button onClick={handleEmailSummary} disabled={emailSummary.isPending}>
              <Mail className="w-4 h-4 mr-2" />
              Email Summary
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Email Dialog */}
      <Dialog open={showEmailDialog} onOpenChange={setShowEmailDialog}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <Mail className="w-5 h-5 text-primary" />
              Email Summary
            </DialogTitle>
            <DialogDescription>
              Send the video summary to an email address.
            </DialogDescription>
          </DialogHeader>

          <div className="py-4">
            <label
              htmlFor="email"
              className="text-sm font-medium text-foreground mb-2 block"
            >
              Email address
            </label>
            <Input
              id="email"
              type="email"
              placeholder="Enter email address"
              value={emailAddress}
              onChange={(e) => setEmailAddress(e.target.value)}
              className="w-full"
            />
          </div>

          <DialogFooter className="flex gap-2">
            <Button
              variant="outline"
              onClick={() => {
                setShowEmailDialog(false);
                setEmailAddress('');
              }}
            >
              Cancel
            </Button>
            <Button
              onClick={handleSendEmail}
              disabled={!emailAddress || emailSummary.isPending}
            >
              {emailSummary.isPending ? (
                <>
                  <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                  Sending...
                </>
              ) : (
                <>
                  <Mail className="w-4 h-4 mr-2" />
                  Send Email
                </>
              )}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}

export default VideoDetailsPanel;
