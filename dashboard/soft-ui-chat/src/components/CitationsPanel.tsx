/**
 * Citations Panel Component
 *
 * Displays search result sources after a query.
 * Shows when the last assistant message contains citations.
 * Also includes video actions when a specific video is selected.
 */
import { useState } from 'react';
import { BookOpen, Search, Filter, Sparkles, Mail, Loader2, ExternalLink } from 'lucide-react';
import { useChat, type Citation } from '@/hooks/useChat';
import { useLibraryStats } from '@/hooks/useLibraryStats';
import { useGroups } from '@/hooks/useGroups';
import { useSelectedTranscript } from '@/hooks/useSelectedTranscript';
import { useGenerateSummary, useEmailSummary } from '@/hooks/useTranscripts';
import { CitationCard } from './CitationCard';
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
 * CitationsPanel - Shows sources from the last search query
 */
export function CitationsPanel() {
  const { messages, groupFilter, videoFilter } = useChat();
  const { totalVideos } = useLibraryStats();
  const { data: groups } = useGroups();
  const { selectedTranscript, setSelectedTranscript } = useSelectedTranscript();
  const generateSummary = useGenerateSummary();
  const emailSummary = useEmailSummary();

  // State for dialogs
  const [showSummaryDialog, setShowSummaryDialog] = useState(false);
  const [showEmailDialog, setShowEmailDialog] = useState(false);
  const [summary, setSummary] = useState<VideoSummaryResponse | null>(null);
  const [emailAddress, setEmailAddress] = useState('');

  // Get citations from the last assistant message
  const lastAssistantMessage = [...messages]
    .reverse()
    .find((m) => m.role === 'assistant');

  const citations: Citation[] = lastAssistantMessage?.citations ?? [];

  // Find the current group name for display
  const currentGroup = groupFilter
    ? groups?.find((g) => g.id === groupFilter)
    : null;

  const handleSelectVideo = (videoId: string) => {
    console.log('Select video:', videoId);
  };

  const handleGenerateSummary = async () => {
    if (!selectedTranscript) return;
    try {
      const result = await generateSummary.mutateAsync({
        videoId: selectedTranscript.id,
        forceRegenerate: false,
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

  const handleEmailSummary = () => {
    if (!summary) {
      toast.info('Please generate a summary first');
      return;
    }
    setShowEmailDialog(true);
  };

  const handleSendEmail = async () => {
    if (!emailAddress || !summary || !selectedTranscript) return;

    const summaryHtml = formatSummaryHtml(summary);
    try {
      const result = await emailSummary.mutateAsync({
        videoId: selectedTranscript.id,
        request: {
          recipient_email: emailAddress,
          summary_html: summaryHtml,
          video_title: selectedTranscript.title,
          channel_name: selectedTranscript.channel_name || undefined,
          duration_seconds: selectedTranscript.duration_seconds || undefined,
          transcript_length: selectedTranscript.transcript_length || undefined,
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

  function formatSummaryHtml(s: VideoSummaryResponse): string {
    let html = `<h2>Overview</h2><p>${s.executive_summary}</p>`;
    if (s.key_takeaways.length > 0) {
      html += '<h3>Key Takeaways</h3><ul>';
      s.key_takeaways.forEach((t) => { html += `<li>${t}</li>`; });
      html += '</ul>';
    }
    if (s.target_audience) {
      html += `<p><strong>Who this is for:</strong> ${s.target_audience}</p>`;
    }
    return html;
  }

  const handleOpenYouTube = () => {
    if (selectedTranscript?.youtube_id) {
      window.open(`https://www.youtube.com/watch?v=${selectedTranscript.youtube_id}`, '_blank', 'noopener,noreferrer');
    }
  };

  return (
    <div className="flex flex-col h-full">
      {/* Header */}
      <div className="p-4 border-b border-border/50">
        <div className="flex items-center gap-2">
          <div className="w-8 h-8 rounded-lg bg-primary/10 flex items-center justify-center">
            <BookOpen className="w-4 h-4 text-primary" />
          </div>
          <div className="flex-1">
            <h2 className="font-semibold text-sm text-foreground">
              Sources
              {citations.length > 0 && (
                <span className="ml-1.5 text-muted-foreground font-normal">
                  ({citations.length})
                </span>
              )}
            </h2>
            <p className="text-xxs text-muted-foreground">
              References from your search
            </p>
          </div>
        </div>
      </div>

      {/* Search Context */}
      <div className="px-4 py-3 border-b border-border/50 bg-accent/20">
        <div className="flex items-center gap-2 text-xxs">
          <Search className="w-3 h-3 text-muted-foreground" />
          <span className="text-muted-foreground">Searching in:</span>
          {videoFilter && selectedTranscript ? (
            <span className="font-medium text-foreground truncate max-w-[140px]" title={selectedTranscript.title}>
              {selectedTranscript.title}
            </span>
          ) : currentGroup ? (
            <span className="flex items-center gap-1">
              <span
                className="w-2 h-2 rounded-full"
                style={{ backgroundColor: currentGroup.color }}
              />
              <span className="font-medium text-foreground">
                {currentGroup.name}
              </span>
            </span>
          ) : (
            <span className="font-medium text-foreground">All videos</span>
          )}
        </div>
        <div className="flex items-center gap-2 text-xxs mt-1">
          <Filter className="w-3 h-3 text-muted-foreground" />
          <span className="text-muted-foreground">
            {videoFilter ? '1 video' : `${totalVideos} video${totalVideos !== 1 ? 's' : ''}`} indexed
          </span>
        </div>
      </div>

      {/* Video Actions - shown when a video is selected */}
      {videoFilter && selectedTranscript && (
        <div className="px-4 py-3 border-b border-border/50 space-y-2">
          <div className="flex gap-2">
            <button
              onClick={handleGenerateSummary}
              disabled={generateSummary.isPending}
              className="flex-1 flex items-center justify-center gap-1.5 px-3 py-2
                         bg-primary text-primary-foreground rounded-lg font-medium text-xs
                         hover:bg-primary/90 transition-colors disabled:opacity-50"
            >
              {generateSummary.isPending ? (
                <Loader2 className="w-3.5 h-3.5 animate-spin" />
              ) : (
                <Sparkles className="w-3.5 h-3.5" />
              )}
              {summary ? 'View Summary' : 'Generate Summary'}
            </button>
            <button
              onClick={handleEmailSummary}
              disabled={!summary || emailSummary.isPending}
              className="flex items-center justify-center gap-1.5 px-3 py-2
                         border border-border/50 rounded-lg text-xs
                         hover:bg-accent transition-colors disabled:opacity-50"
            >
              <Mail className="w-3.5 h-3.5" />
            </button>
            <button
              onClick={handleOpenYouTube}
              className="flex items-center justify-center gap-1.5 px-3 py-2
                         border border-border/50 rounded-lg text-xs
                         hover:bg-accent transition-colors"
            >
              <ExternalLink className="w-3.5 h-3.5" />
            </button>
          </div>
        </div>
      )}

      {/* Citations List */}
      <div className="flex-1 overflow-y-auto p-4 space-y-3">
        {citations.length > 0 ? (
          citations.map((citation, index) => (
            <CitationCard
              key={citation.video_id || index}
              citation={citation}
              index={index}
              onSelect={handleSelectVideo}
            />
          ))
        ) : (
          <div className="text-center py-8">
            <BookOpen className="w-8 h-8 text-muted-foreground/50 mx-auto mb-2" />
            <p className="text-xs text-muted-foreground">
              No sources found for this query
            </p>
          </div>
        )}
      </div>

      {/* Footer hint */}
      {citations.length > 0 && (
        <div className="p-3 border-t border-border/50 bg-accent/10">
          <p className="text-xxs text-muted-foreground text-center">
            Click a source to view the full video
          </p>
        </div>
      )}

      {/* Summary Dialog */}
      <Dialog open={showSummaryDialog} onOpenChange={setShowSummaryDialog}>
        <DialogContent className="max-w-2xl max-h-[80vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <Sparkles className="w-5 h-5 text-primary" />
              Video Summary
            </DialogTitle>
            <DialogDescription>{selectedTranscript?.title}</DialogDescription>
          </DialogHeader>

          {summary && (
            <div className="space-y-4 py-4">
              <div>
                <h3 className="text-sm font-semibold text-foreground mb-2">Overview</h3>
                <p className="text-sm text-muted-foreground leading-relaxed">
                  {summary.executive_summary}
                </p>
              </div>

              {summary.key_takeaways.length > 0 && (
                <div>
                  <h3 className="text-sm font-semibold text-foreground mb-2">Key Takeaways</h3>
                  <ul className="space-y-1.5">
                    {summary.key_takeaways.map((takeaway, i) => (
                      <li key={i} className="text-sm text-muted-foreground flex items-start gap-2">
                        <span className="text-primary mt-0.5">•</span>
                        {takeaway}
                      </li>
                    ))}
                  </ul>
                </div>
              )}

              {summary.target_audience && (
                <div className="p-3 bg-accent/50 rounded-lg">
                  <span className="text-xs font-medium text-foreground">Who this is for: </span>
                  <span className="text-sm text-muted-foreground">{summary.target_audience}</span>
                </div>
              )}
            </div>
          )}

          <DialogFooter className="flex gap-2">
            <Button variant="outline" onClick={() => setShowSummaryDialog(false)}>
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
            <label htmlFor="email" className="text-sm font-medium text-foreground mb-2 block">
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
              onClick={() => { setShowEmailDialog(false); setEmailAddress(''); }}
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

export default CitationsPanel;
