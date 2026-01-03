import { useRef, useEffect } from "react";
import { MessageSquare, Trash2, Filter } from "lucide-react";
import { useChat, type Message } from "@/hooks/useChat";
import { useGroups } from "@/hooks/useGroups";
import { ChatMessage } from "./ChatMessage";
import { ChatInput } from "./ChatInput";
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
 * Loading indicator for when assistant is thinking
 */
function ThinkingIndicator() {
  return (
    <div className="flex gap-3 animate-fade-in">
      <div className="flex-shrink-0 w-8 h-8 rounded-full bg-accent-purple/20 flex items-center justify-center">
        <div className="flex gap-1">
          <span className="w-1.5 h-1.5 bg-accent-purple rounded-full animate-bounce" style={{ animationDelay: "0ms" }} />
          <span className="w-1.5 h-1.5 bg-accent-purple rounded-full animate-bounce" style={{ animationDelay: "150ms" }} />
          <span className="w-1.5 h-1.5 bg-accent-purple rounded-full animate-bounce" style={{ animationDelay: "300ms" }} />
        </div>
      </div>
      <div className="flex flex-col items-start">
        <div className="rounded-2xl rounded-bl-sm bg-card border border-border/50 px-4 py-3">
          <p className="text-sm text-muted-foreground">Searching your videos...</p>
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
  const { messages, isLoading, error, groupFilter, sendMessage, setGroupFilter, clearChat } = useChat();

  // Groups for filter dropdown
  const { data: groups = [] } = useGroups();

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
          {/* Group filter */}
          <div className="flex items-center gap-2">
            <Filter className="w-4 h-4 text-muted-foreground" />
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
        </div>
      </header>

      {/* Messages area */}
      <div className="flex-1 overflow-y-auto px-4 py-4 scrollbar-hide">
        {messages.length === 0 && !isLoading ? (
          <EmptyState />
        ) : (
          <div className="space-y-4 max-w-3xl mx-auto">
            {messages.map((message: Message) => (
              <ChatMessage key={message.id} message={message} />
            ))}

            {/* Loading indicator */}
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
          groupFilter
            ? `Ask about videos in ${groups.find((g) => g.id === groupFilter)?.name || "this group"}...`
            : "Ask a question about your videos..."
        }
      />
    </div>
  );
}
