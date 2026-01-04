import { Bot } from 'lucide-react';
import { cn } from '@/lib/utils';

/**
 * Props for the ThinkingIndicator component
 */
interface ThinkingIndicatorProps {
  /** Custom message to display while thinking */
  message?: string;
  /** Additional CSS classes */
  className?: string;
}

/**
 * Animated thinking indicator displayed while the AI is processing
 *
 * Features:
 * - Three bouncing dots animation with staggered delays
 * - Customizable status message
 * - Matches the chat message styling for visual consistency
 */
export function ThinkingIndicator({
  message = 'Searching your transcripts...',
  className,
}: ThinkingIndicatorProps) {
  return (
    <div className={cn('flex gap-3 animate-fade-in', className)}>
      {/* Avatar with animated dots */}
      <div className="flex-shrink-0 w-8 h-8 rounded-full bg-accent-purple/20 flex items-center justify-center">
        <Bot className="h-4 w-4 text-accent-purple" />
      </div>

      {/* Message bubble */}
      <div className="flex flex-col items-start">
        <div className="rounded-2xl rounded-bl-sm bg-card border border-border/50 px-4 py-3">
          <div className="flex items-center gap-2">
            {/* Bouncing dots */}
            <div className="flex gap-1">
              <span
                className="w-2 h-2 bg-accent-purple rounded-full animate-bounce"
                style={{ animationDelay: '0ms', animationDuration: '600ms' }}
              />
              <span
                className="w-2 h-2 bg-accent-purple rounded-full animate-bounce"
                style={{ animationDelay: '150ms', animationDuration: '600ms' }}
              />
              <span
                className="w-2 h-2 bg-accent-purple rounded-full animate-bounce"
                style={{ animationDelay: '300ms', animationDuration: '600ms' }}
              />
            </div>
            {/* Status message */}
            <p className="text-sm text-muted-foreground">{message}</p>
          </div>
        </div>
      </div>
    </div>
  );
}

export default ThinkingIndicator;
