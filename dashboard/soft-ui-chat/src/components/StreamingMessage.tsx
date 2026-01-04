import { useEffect, useState, useRef } from 'react';
import ReactMarkdown from 'react-markdown';
import { cn } from '@/lib/utils';

/**
 * Props for the StreamingMessage component
 */
interface StreamingMessageProps {
  /** The full content to stream/type out */
  content: string;
  /** Speed of typing in milliseconds per character */
  typingSpeed?: number;
  /** Whether to show the blinking cursor */
  showCursor?: boolean;
  /** Callback when streaming is complete */
  onComplete?: () => void;
  /** Additional CSS classes */
  className?: string;
}

/**
 * Component that displays text with a typing/streaming animation
 *
 * Features:
 * - Character-by-character text reveal
 * - Blinking cursor at the end while typing
 * - Smooth animation using requestAnimationFrame
 * - Configurable typing speed
 * - Completion callback
 */
export function StreamingMessage({
  content,
  typingSpeed = 15,
  showCursor = true,
  onComplete,
  className,
}: StreamingMessageProps) {
  const [displayedContent, setDisplayedContent] = useState('');
  const [isTyping, setIsTyping] = useState(true);
  const contentRef = useRef(content);
  const indexRef = useRef(0);
  const lastTimeRef = useRef(0);
  const animationFrameRef = useRef<number | null>(null);

  useEffect(() => {
    // Reset if content changes
    if (content !== contentRef.current) {
      contentRef.current = content;
      indexRef.current = 0;
      setDisplayedContent('');
      setIsTyping(true);
    }

    const animate = (timestamp: number) => {
      if (!lastTimeRef.current) {
        lastTimeRef.current = timestamp;
      }

      const elapsed = timestamp - lastTimeRef.current;

      // Add characters based on elapsed time
      if (elapsed >= typingSpeed) {
        const charsToAdd = Math.floor(elapsed / typingSpeed);
        const newIndex = Math.min(indexRef.current + charsToAdd, content.length);

        if (newIndex > indexRef.current) {
          indexRef.current = newIndex;
          setDisplayedContent(content.slice(0, newIndex));
        }

        lastTimeRef.current = timestamp;
      }

      // Continue animation or complete
      if (indexRef.current < content.length) {
        animationFrameRef.current = requestAnimationFrame(animate);
      } else {
        setIsTyping(false);
        onComplete?.();
      }
    };

    // Start animation
    animationFrameRef.current = requestAnimationFrame(animate);

    // Cleanup
    return () => {
      if (animationFrameRef.current) {
        cancelAnimationFrame(animationFrameRef.current);
      }
    };
  }, [content, typingSpeed, onComplete]);

  return (
    <div className={cn('relative', className)}>
      <div className="prose prose-sm prose-invert max-w-none prose-p:my-1 prose-p:text-foreground prose-ul:my-1 prose-ol:my-1 prose-li:my-0.5 prose-li:text-foreground prose-headings:my-2 prose-strong:text-foreground prose-a:text-accent-blue">
        <ReactMarkdown>{displayedContent}</ReactMarkdown>
      </div>
      {/* Blinking cursor */}
      {showCursor && isTyping && (
        <span className="inline-block w-0.5 h-4 ml-0.5 bg-foreground animate-pulse align-middle" />
      )}
    </div>
  );
}

export default StreamingMessage;
