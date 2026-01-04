/**
 * Citation Card Component
 *
 * Displays a single citation/source from search results
 * with video thumbnail, relevance score, and snippet preview.
 */
import { useState } from 'react';
import { ChevronDown, ChevronUp, ExternalLink } from 'lucide-react';
import type { Citation } from '@/hooks/useChat';

interface CitationCardProps {
  citation: Citation;
  index: number;
  onSelect?: (videoId: string) => void;
}

/**
 * Format relevance score as percentage
 */
function formatScore(score?: number): string {
  if (score === undefined || score === null) return '';
  // Score is typically 0-1, convert to percentage
  const percentage = Math.round(score * 100);
  return `${percentage}%`;
}

/**
 * CitationCard - Individual source card with expandable snippet
 */
export function CitationCard({ citation, index, onSelect }: CitationCardProps) {
  const [isExpanded, setIsExpanded] = useState(false);

  const hasSnippet = citation.snippet && citation.snippet.length > 0;
  const scorePercentage = citation.score ? Math.round(citation.score * 100) : 0;

  const handleClick = () => {
    if (citation.video_id && onSelect) {
      onSelect(citation.video_id);
    }
  };

  return (
    <div
      className="bg-accent/30 rounded-lg border border-border/50 overflow-hidden
                 hover:border-primary/30 transition-all duration-200 animate-slide-in-left"
      style={{ animationDelay: `${index * 50}ms` }}
    >
      {/* Main Content */}
      <div
        className="p-3 cursor-pointer"
        onClick={handleClick}
        role="button"
        tabIndex={0}
        onKeyDown={(e) => e.key === 'Enter' && handleClick()}
      >
        {/* Title Row */}
        <div className="flex items-start gap-2">
          {/* Index Badge */}
          <span className="flex-shrink-0 w-5 h-5 rounded bg-primary/10 text-primary
                          text-xxs font-bold flex items-center justify-center">
            {index + 1}
          </span>

          <div className="flex-1 min-w-0">
            {/* Video Title */}
            <h4 className="text-xs font-medium text-foreground truncate pr-2">
              {citation.title || 'Untitled Video'}
            </h4>

            {/* Relevance Score Bar */}
            {citation.score !== undefined && (
              <div className="mt-2 flex items-center gap-2">
                <div className="flex-1 h-1.5 bg-accent rounded-full overflow-hidden">
                  <div
                    className="h-full bg-primary rounded-full transition-all duration-500"
                    style={{ width: `${scorePercentage}%` }}
                  />
                </div>
                <span className="text-xxs font-medium text-muted-foreground w-8 text-right">
                  {formatScore(citation.score)}
                </span>
              </div>
            )}
          </div>

          {/* Expand/Link Icon */}
          {hasSnippet ? (
            <button
              onClick={(e) => {
                e.stopPropagation();
                setIsExpanded(!isExpanded);
              }}
              className="p-1 hover:bg-accent rounded transition-colors"
              aria-label={isExpanded ? 'Collapse snippet' : 'Expand snippet'}
            >
              {isExpanded ? (
                <ChevronUp className="w-3.5 h-3.5 text-muted-foreground" />
              ) : (
                <ChevronDown className="w-3.5 h-3.5 text-muted-foreground" />
              )}
            </button>
          ) : (
            <ExternalLink className="w-3.5 h-3.5 text-muted-foreground" />
          )}
        </div>
      </div>

      {/* Expandable Snippet */}
      {hasSnippet && isExpanded && (
        <div className="px-3 pb-3 pt-0">
          <div className="pl-7">
            <p className="text-xxs text-muted-foreground leading-relaxed
                          bg-background/50 rounded p-2 border-l-2 border-primary/30">
              "{citation.snippet}"
            </p>
          </div>
        </div>
      )}
    </div>
  );
}

export default CitationCard;
