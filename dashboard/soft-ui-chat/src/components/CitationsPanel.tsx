/**
 * Citations Panel Component
 *
 * Displays search result sources after a query.
 * Shows when the last assistant message contains citations.
 */
import { BookOpen, Search, Filter } from 'lucide-react';
import { useChat, type Citation } from '@/hooks/useChat';
import { useLibraryStats } from '@/hooks/useLibraryStats';
import { useGroups } from '@/hooks/useGroups';
import { useSelectedTranscript } from '@/hooks/useSelectedTranscript';
import { CitationCard } from './CitationCard';

/**
 * CitationsPanel - Shows sources from the last search query
 */
export function CitationsPanel() {
  const { messages, groupFilter } = useChat();
  const { totalVideos } = useLibraryStats();
  const { data: groups } = useGroups();
  const { setSelectedTranscript } = useSelectedTranscript();

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
    // This would ideally fetch the video and select it
    // For now, we just log the action
    console.log('Select video:', videoId);
    // TODO: Implement video selection when video data is available
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
          {currentGroup ? (
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
            {totalVideos} video{totalVideos !== 1 ? 's' : ''} indexed
          </span>
        </div>
      </div>

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
    </div>
  );
}

export default CitationsPanel;
