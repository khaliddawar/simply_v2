import * as React from 'react';
import { Send } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { cn } from '@/lib/utils';

/**
 * Props for the ChatInput component
 */
interface ChatInputProps {
  /** Callback fired when user sends a message */
  onSend: (message: string) => void;
  /** Whether the chat is currently processing a message */
  isLoading?: boolean;
  /** Placeholder text for the input */
  placeholder?: string;
  /** Additional CSS classes */
  className?: string;
}

/**
 * Chat input component with textarea and send button
 *
 * Features:
 * - Enter to send message
 * - Shift+Enter for newline
 * - Auto-resizing textarea
 * - Disabled state during loading
 * - Send button with loading state
 */
export function ChatInput({
  onSend,
  isLoading = false,
  placeholder = 'Ask a question about your videos...',
  className,
}: ChatInputProps) {
  const [value, setValue] = React.useState('');
  const textareaRef = React.useRef<HTMLTextAreaElement>(null);

  /**
   * Handle form submission
   */
  const handleSubmit = (e?: React.FormEvent) => {
    e?.preventDefault();

    const trimmedValue = value.trim();
    if (!trimmedValue || isLoading) return;

    onSend(trimmedValue);
    setValue('');

    // Reset textarea height
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto';
    }
  };

  /**
   * Handle keyboard events for Enter to send
   */
  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    // Enter without Shift sends the message
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSubmit();
    }
  };

  /**
   * Auto-resize textarea based on content
   */
  const handleInput = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
    const textarea = e.target;
    setValue(textarea.value);

    // Reset height to auto to get the correct scrollHeight
    textarea.style.height = 'auto';
    // Set height to scrollHeight, with a max height
    const maxHeight = 200; // Maximum height in pixels
    const newHeight = Math.min(textarea.scrollHeight, maxHeight);
    textarea.style.height = `${newHeight}px`;
  };

  const canSend = value.trim().length > 0 && !isLoading;

  return (
    <form
      onSubmit={handleSubmit}
      className={cn(
        'flex items-end gap-2 p-4 border-t border-border/50 bg-card/30 backdrop-blur-sm',
        className
      )}
    >
      <div className="flex-1 relative">
        <textarea
          ref={textareaRef}
          value={value}
          onChange={handleInput}
          onKeyDown={handleKeyDown}
          placeholder={placeholder}
          disabled={isLoading}
          rows={1}
          className={cn(
            'w-full resize-none rounded-lg border border-input bg-background px-4 py-3',
            'text-sm text-foreground placeholder:text-muted-foreground',
            'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2',
            'disabled:cursor-not-allowed disabled:opacity-50',
            'min-h-[48px] max-h-[200px] overflow-y-auto',
            'scrollbar-hide'
          )}
          aria-label="Chat message input"
        />
      </div>

      <Button
        type="submit"
        size="icon"
        disabled={!canSend}
        className={cn(
          'h-12 w-12 rounded-lg shrink-0',
          'transition-all duration-200',
          canSend && 'bg-accent-blue hover:bg-accent-blue/90'
        )}
        aria-label={isLoading ? 'Sending message...' : 'Send message'}
      >
        {isLoading ? (
          <div className="h-4 w-4 animate-spin rounded-full border-2 border-current border-t-transparent" />
        ) : (
          <Send className="h-4 w-4" />
        )}
      </Button>
    </form>
  );
}

export default ChatInput;
