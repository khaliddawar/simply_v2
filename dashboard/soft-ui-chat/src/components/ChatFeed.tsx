import { useRef, useEffect, useCallback } from "react";
import { MessageSquare, Trash2, Filter } from "lucide-react";
import { useChat, type Message } from "@/hooks/useChat";
import { useGroups } from "@/hooks/useGroups";
import { useSelectedTranscript } from "@/hooks/useSelectedTranscript";
import { ChatMessage } from "./ChatMessage";
import { ChatInput } from "./ChatInput";
import { TranscriptHeader } from "./TranscriptHeader";
import { ThinkingIndicator } from "./ThinkingIndicator";
import { UserProfileDropdown } from "./UserProfileDropdown";
import { Button } from "@/components/ui/button";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { toast } from "sonner";

/**
 * Empty state component when no messages exist
 */
function EmptyState() {
  return (
    <div className="flex-1 flex flex-col items-center justify-center px-4 text-center">
      <div className="w-16 h-16 rounded-full bg-accent-purple/10 flex items-center justify-center mb-4">
        <MessageSquare className="w-8 h-8 text-accent-purple" />
      </div>
      <h3 className="text-lg font-semibold text-foreground mb-2">
        Ask about your videos
      </h3>
      <p className="text-sm text-muted-foreground max-w-sm">
        Search through your video transcripts using natural language. Ask questions
        and get answers with citations from your library.
      </p>
      <div className="mt-6 space-y-2">
        <p className="text-xs text-muted-foreground">Try asking:</p>
        <div className="flex flex-wrap gap-2 justify-center">
          {[
            "What videos mention AI?",
            "Summarize my recent videos",
            "Find videos about productivity",
          ].map((suggestion) => (
            <span
              key={suggestion}
              className="px-3 py-1.5 bg-secondary rounded-full text-xs text-secondary-foreground"
            >
              {suggestion}
            </span>
          ))}
        </div>
      </div>
    </div>
  );
}

/**
 * Main chat feed component - RAG-powered chat interface
 *
 * Features:
 * - Real-time chat with video transcript search
 * - Citations from matched videos
 * - Group filtering to scope searches
 * - Auto-scroll to latest messages
 * - Clear chat functionality
 */
export function ChatFeed() {
  const messagesEndRef = useRef<HTMLDivElement>(null);

  // Chat state from Zustand store
  const { messages, isLoading, isStreaming, error, groupFilter, videoFilter, sendMessage, setGroupFilter, setStreaming, clearChat } = useChat();

  // Groups for filter dropdown
  const { data: groups = [] } = useGroups();

  // Selected transcript state
  const { selectedTranscript } = useSelectedTranscript();

  // Handle streaming completion
  const handleStreamingComplete = useCallback(() => {
    setStreaming(false);
  }, [setStreaming]);

  // Auto-scroll to bottom when new messages arrive
  useEffect(() => {
    if (messagesEndRef.current) {
      messagesEndRef.current.scrollIntoView({ behavior: "smooth" });
    }
  }, [messages, isLoading]);

  // Show error toast
  useEffect(() => {
    if (error) {
      toast.error(error);
    }
  }, [error]);

  const handleSend = (message: string) => {
    sendMessage(message);
  };

  const handleClearChat = () => {
    clearChat();
    toast.success("Chat cleared");
  };

  const handleGroupFilterChange = (value: string) => {
    setGroupFilter(value === "all" ? null : value);
  };

  return (
    <div className="flex-1 h-full flex flex-col bg-background">
      {/* Header */}
      <header className="h-14 border-b border-border/50 flex items-center justify-between px-4 bg-card/50 backdrop-blur-sm shrink-0">
        <div className="flex items-center gap-3">
          <MessageSquare className="w-5 h-5 text-accent-purple" />
          <h2 className="text-sm font-semibold text-foreground">Knowledge Search</h2>
        </div>

        <div className="flex items-center gap-2">
          {/* Filter indicator - shows video or group context */}
          <div className="flex items-center gap-2">
            <Filter className="w-4 h-4 text-muted-foreground" />
            {videoFilter && selectedTranscript ? (
              // Video selected - show video indicator
              <div className="h-8 px-3 flex items-center gap-2 bg-accent-purple/10 rounded-md border border-accent-purple/30">
                <span className="text-xs font-medium text-accent-purple truncate max-w-[120px]">
                  {selectedTranscript.title}
                </span>
              </div>
            ) : (
              // No video selected - show group filter
              <Select
                value={groupFilter || "all"}
                onValueChange={handleGroupFilterChange}
              >
                <SelectTrigger className="w-[140px] h-8 text-xs">
                  <SelectValue placeholder="All videos" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">All videos</SelectItem>
                  {groups.map((group) => (
                    <SelectItem key={group.id} value={group.id}>
                      <div className="flex items-center gap-2">
                        <div
                          className="w-2 h-2 rounded-full"
                          style={{ backgroundColor: group.color }}
                        />
                        {group.name}
                      </div>
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            )}
          </div>

          {/* Clear chat button */}
          {messages.length > 0 && (
            <Button
              variant="ghost"
              size="sm"
              onClick={handleClearChat}
              className="h-8 px-2 text-muted-foreground hover:text-foreground"
            >
              <Trash2 className="w-4 h-4" />
            </Button>
          )}

          {/* Separator */}
          <div className="h-6 w-px bg-border/50 mx-1" />

          {/* User profile dropdown */}
          <UserProfileDropdown />
        </div>
      </header>

      {/* Transcript header - shown when a transcript is selected */}
      {selectedTranscript && <TranscriptHeader />}

      {/* Messages area */}
      <div className="flex-1 overflow-y-auto px-4 py-4 scrollbar-hide">
        {messages.length === 0 && !isLoading ? (
          <EmptyState />
        ) : (
          <div className="space-y-4 max-w-3xl mx-auto">
            {messages.map((message: Message, index: number) => {
              // Check if this is the last assistant message and streaming is active
              const isLastMessage = index === messages.length - 1;
              const isAssistant = message.role === 'assistant';
              const shouldStream = isLastMessage && isAssistant && isStreaming;

              return (
                <ChatMessage
                  key={message.id}
                  message={message}
                  isStreaming={shouldStream}
                  onStreamingComplete={shouldStream ? handleStreamingComplete : undefined}
                />
              );
            })}

            {/* Loading indicator - shown while waiting for response */}
            {isLoading && <ThinkingIndicator />}

            {/* Scroll anchor */}
            <div ref={messagesEndRef} />
          </div>
        )}
      </div>

      {/* Chat input */}
      <ChatInput
        onSend={handleSend}
        isLoading={isLoading}
        placeholder={
          videoFilter && selectedTranscript
            ? `Ask about "${selectedTranscript.title.slice(0, 30)}${selectedTranscript.title.length > 30 ? '...' : ''}"...`
            : groupFilter
            ? `Ask about videos in ${groups.find((g) => g.id === groupFilter)?.name || "this group"}...`
            : "Ask a question about your videos..."
        }
      />
    </div>
  );
}
