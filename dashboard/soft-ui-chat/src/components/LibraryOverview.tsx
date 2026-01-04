/**
 * Library Overview Component
 *
 * Default state for the right panel when no video is selected
 * and no search is active. Shows library statistics and suggested queries.
 */
import { Library, FolderOpen, Clock, Lightbulb, TrendingUp } from 'lucide-react';
import { useLibraryStats } from '@/hooks/useLibraryStats';
import { useChat } from '@/hooks/useChat';

/**
 * Suggested search queries to help users get started
 */
const SUGGESTED_QUERIES = [
  'What are the main themes across my videos?',
  'Summarize what I learned this week',
  'What advice was given about productivity?',
  'Compare different perspectives on AI',
];

/**
 * LibraryOverview - Shows library stats and suggestions when idle
 */
export function LibraryOverview() {
  const stats = useLibraryStats();
  const { sendMessage } = useChat();

  const handleSuggestionClick = (query: string) => {
    sendMessage(query);
  };

  return (
    <div className="flex flex-col h-full">
      {/* Header */}
      <div className="p-4 border-b border-border/50">
        <div className="flex items-center gap-2">
          <div className="w-8 h-8 rounded-lg bg-accent flex items-center justify-center">
            <Library className="w-4 h-4 text-primary" />
          </div>
          <div>
            <h2 className="font-semibold text-sm text-foreground">Your Library</h2>
            <p className="text-xxs text-muted-foreground">Overview and insights</p>
          </div>
        </div>
      </div>

      {/* Stats Grid */}
      <div className="p-4 border-b border-border/50">
        <div className="grid grid-cols-2 gap-3">
          {/* Videos Count */}
          <div className="bg-accent/50 rounded-lg p-3">
            <div className="flex items-center gap-1.5 text-muted-foreground mb-1">
              <Library className="w-3.5 h-3.5" />
              <span className="text-xxs font-medium">Videos</span>
            </div>
            {stats.isLoading ? (
              <div className="h-6 w-12 bg-accent animate-pulse rounded" />
            ) : (
              <p className="text-lg font-bold text-foreground">{stats.totalVideos}</p>
            )}
          </div>

          {/* Groups Count */}
          <div className="bg-accent/50 rounded-lg p-3">
            <div className="flex items-center gap-1.5 text-muted-foreground mb-1">
              <FolderOpen className="w-3.5 h-3.5" />
              <span className="text-xxs font-medium">Groups</span>
            </div>
            {stats.isLoading ? (
              <div className="h-6 w-8 bg-accent animate-pulse rounded" />
            ) : (
              <p className="text-lg font-bold text-foreground">{stats.totalGroups}</p>
            )}
          </div>

          {/* Total Duration */}
          <div className="bg-accent/50 rounded-lg p-3 col-span-2">
            <div className="flex items-center gap-1.5 text-muted-foreground mb-1">
              <Clock className="w-3.5 h-3.5" />
              <span className="text-xxs font-medium">Total Content</span>
            </div>
            {stats.isLoading ? (
              <div className="h-6 w-16 bg-accent animate-pulse rounded" />
            ) : (
              <p className="text-lg font-bold text-foreground">
                {stats.totalDurationFormatted}
              </p>
            )}
          </div>
        </div>
      </div>

      {/* Getting Started / Activity */}
      <div className="p-4 border-b border-border/50">
        <div className="flex items-center gap-1.5 mb-3">
          <TrendingUp className="w-3.5 h-3.5 text-primary" />
          <h3 className="font-semibold text-xs text-foreground">Getting Started</h3>
        </div>
        <div className="space-y-2">
          {stats.totalVideos === 0 ? (
            <p className="text-xs text-muted-foreground leading-relaxed">
              Add videos to your library using the Chrome extension, then search
              your knowledge base here.
            </p>
          ) : (
            <p className="text-xs text-muted-foreground leading-relaxed">
              Ask questions about your {stats.totalVideos} video{stats.totalVideos !== 1 ? 's' : ''}
              {' '}to discover insights and connections.
            </p>
          )}
        </div>
      </div>

      {/* Suggested Queries */}
      <div className="p-4 flex-1 overflow-y-auto">
        <div className="flex items-center gap-1.5 mb-3">
          <Lightbulb className="w-3.5 h-3.5 text-amber-500" />
          <h3 className="font-semibold text-xs text-foreground">Try asking</h3>
        </div>
        <div className="space-y-2">
          {SUGGESTED_QUERIES.map((query, index) => (
            <button
              key={index}
              onClick={() => handleSuggestionClick(query)}
              disabled={stats.totalVideos === 0}
              className="w-full text-left px-3 py-2 rounded-lg border border-border/50
                         text-xs text-muted-foreground hover:bg-accent hover:text-foreground
                         hover:border-primary/30 transition-all duration-200
                         disabled:opacity-50 disabled:cursor-not-allowed disabled:hover:bg-transparent
                         disabled:hover:text-muted-foreground disabled:hover:border-border/50"
            >
              "{query}"
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}

export default LibraryOverview;
