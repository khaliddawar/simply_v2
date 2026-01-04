import * as React from 'react';
import { Bot, User, ChevronDown, ChevronUp, FileText } from 'lucide-react';
import ReactMarkdown from 'react-markdown';
import { cn } from '@/lib/utils';
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from '@/components/ui/collapsible';
import { StreamingMessage } from '@/components/StreamingMessage';
import type { Message, Citation } from '@/hooks/useChat';

/**
 * Props for the ChatMessage component
 */
interface ChatMessageProps {
  /** The message to display */
  message: Message;
  /** Whether the message is currently being streamed/typed */
  isStreaming?: boolean;
  /** Callback when streaming animation completes */
  onStreamingComplete?: () => void;
  /** Additional CSS classes */
  className?: string;
}

/**
 * Format a timestamp for display
 */
function formatTimestamp(date: Date): string {
  return date.toLocaleTimeString([], {
    hour: 'numeric',
    minute: '2-digit',
    hour12: true,
  });
}

/**
 * Citation item component
 */
function CitationItem({ citation, index }: { citation: Citation; index: number }) {
  return (
    <div
      className={cn(
        'p-3 rounded-lg bg-background/50 border border-border/50',
        'hover:bg-background/80 transition-colors'
      )}
    >
      <div className="flex items-start gap-2">
        <div className="flex-shrink-0 mt-0.5">
          <FileText className="h-4 w-4 text-muted-foreground" />
        </div>
        <div className="flex-1 min-w-0">
          {citation.title && (
            <p className="text-sm font-medium text-foreground truncate">
              {citation.title}
            </p>
          )}
          {citation.snippet && (
            <p className="text-xs text-muted-foreground mt-1 line-clamp-2">
              "{citation.snippet}"
            </p>
          )}
          <div className="flex items-center gap-2 mt-1.5">
            <span className="text-xxs text-muted-foreground">
              Source {index + 1}
            </span>
            {citation.score !== undefined && (
              <>
                <span className="text-muted-foreground">&#183;</span>
                <span className="text-xxs text-muted-foreground">
                  {Math.round(citation.score * 100)}% relevant
                </span>
              </>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

/**
 * Citations section component with expandable content
 */
function CitationsSection({ citations }: { citations: Citation[] }) {
  const [isOpen, setIsOpen] = React.useState(false);

  if (!citations || citations.length === 0) return null;

  return (
    <Collapsible open={isOpen} onOpenChange={setIsOpen} className="mt-3">
      <CollapsibleTrigger
        className={cn(
          'flex items-center gap-1.5 text-xs text-muted-foreground',
          'hover:text-foreground transition-colors',
          'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring rounded'
        )}
      >
        <span>{citations.length} source{citations.length !== 1 ? 's' : ''}</span>
        {isOpen ? (
          <ChevronUp className="h-3 w-3" />
        ) : (
          <ChevronDown className="h-3 w-3" />
        )}
      </CollapsibleTrigger>
      <CollapsibleContent className="mt-2 space-y-2 animate-accordion-down">
        {citations.map((citation, index) => (
          <CitationItem
            key={citation.video_id || `citation-${index}`}
            citation={citation}
            index={index}
          />
        ))}
      </CollapsibleContent>
    </Collapsible>
  );
}

/**
 * Chat message bubble component
 *
 * Features:
 * - Different styles for user vs assistant messages
 * - User messages: right-aligned with primary color
 * - Assistant messages: left-aligned with AI icon and expandable citations
 * - Timestamp display
 * - Smooth fade-in animation
 * - Streaming/typing animation for assistant responses
 */
export function ChatMessage({
  message,
  isStreaming = false,
  onStreamingComplete,
  className,
}: ChatMessageProps) {
  const isUser = message.role === 'user';
  const shouldStream = !isUser && isStreaming;

  return (
    <div
      className={cn(
        'flex gap-3 animate-fade-in',
        isUser ? 'flex-row-reverse' : 'flex-row',
        className
      )}
    >
      {/* Avatar */}
      <div
        className={cn(
          'flex-shrink-0 w-8 h-8 rounded-full flex items-center justify-center',
          isUser
            ? 'bg-accent-blue text-primary-foreground'
            : 'bg-accent-purple/20 text-accent-purple'
        )}
      >
        {isUser ? (
          <User className="h-4 w-4" />
        ) : (
          <Bot className="h-4 w-4" />
        )}
      </div>

      {/* Message content */}
      <div
        className={cn(
          'flex flex-col max-w-[80%]',
          isUser ? 'items-end' : 'items-start'
        )}
      >
        {/* Message bubble */}
        <div
          className={cn(
            'rounded-2xl px-4 py-3',
            isUser
              ? 'bg-accent-blue text-primary-foreground rounded-br-sm'
              : 'bg-card border border-border/50 text-foreground rounded-bl-sm'
          )}
        >
          <div className="text-sm leading-relaxed">
            {shouldStream ? (
              <StreamingMessage
                content={message.content}
                onComplete={onStreamingComplete}
                typingSpeed={12}
              />
            ) : isUser ? (
              <span className="whitespace-pre-wrap break-words">
                {message.content}
              </span>
            ) : (
              <div className="prose prose-sm prose-invert max-w-none prose-p:my-1 prose-p:text-foreground prose-ul:my-1 prose-ol:my-1 prose-li:my-0.5 prose-li:text-foreground prose-headings:my-2 prose-strong:text-foreground prose-a:text-accent-blue">
                <ReactMarkdown>{message.content}</ReactMarkdown>
              </div>
            )}
          </div>
        </div>

        {/* Citations (assistant only) */}
        {!isUser && message.citations && message.citations.length > 0 && (
          <div className="w-full mt-1">
            <CitationsSection citations={message.citations} />
          </div>
        )}

        {/* Timestamp */}
        <span className="text-xxs text-muted-foreground mt-1.5 px-1">
          {formatTimestamp(message.timestamp)}
        </span>
      </div>
    </div>
  );
}

export default ChatMessage;
