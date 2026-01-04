import { create } from 'zustand';
import { api } from '@/lib/api';

/**
 * Citation from a video transcript returned by the RAG search
 */
export interface Citation {
  video_id?: string;
  title?: string;
  snippet?: string;
  score?: number;
}

/**
 * Chat message in the conversation
 */
export interface Message {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  citations?: Citation[];
  timestamp: Date;
}

/**
 * Message payload for API requests (simplified format)
 */
interface MessagePayload {
  role: 'user' | 'assistant';
  content: string;
}

/**
 * Chat store state and actions
 */
interface ChatState {
  // State
  messages: Message[];
  isLoading: boolean;
  isStreaming: boolean;
  error: string | null;
  groupFilter: string | null;
  videoFilter: string | null;  // Filter to specific video for RAG

  // Actions
  sendMessage: (query: string) => Promise<void>;
  setGroupFilter: (groupId: string | null) => void;
  setVideoFilter: (videoId: string | null) => void;  // Set video context for chat
  setStreaming: (streaming: boolean) => void;
  clearChat: () => void;
}

/**
 * Generate a unique ID for messages
 */
const generateId = (): string => {
  return `msg_${Date.now()}_${Math.random().toString(36).substring(2, 9)}`;
};

/**
 * Convert messages to API payload format (last 10 messages)
 */
const messagesToPayload = (messages: Message[]): MessagePayload[] => {
  return messages.slice(-10).map((msg) => ({
    role: msg.role,
    content: msg.content,
  }));
};

/**
 * Zustand store for managing chat state and interactions
 *
 * Features:
 * - Send messages to POST /api/search/chat
 * - Maintains conversation history (sends last 10 messages for context)
 * - Supports group filtering for scoped searches
 * - Tracks loading and error states
 */
export const useChatStore = create<ChatState>((set, get) => ({
  // Initial state
  messages: [],
  isLoading: false,
  isStreaming: false,
  error: null,
  groupFilter: null,
  videoFilter: null,

  /**
   * Send a message to the chat endpoint
   * Adds user message immediately, then fetches assistant response
   */
  sendMessage: async (query: string) => {
    const trimmedQuery = query.trim();
    if (!trimmedQuery) return;

    // Create user message
    const userMessage: Message = {
      id: generateId(),
      role: 'user',
      content: trimmedQuery,
      timestamp: new Date(),
    };

    // Add user message and set loading state
    set((state) => ({
      messages: [...state.messages, userMessage],
      isLoading: true,
      error: null,
    }));

    try {
      const { messages, groupFilter, videoFilter } = get();

      // Prepare history payload (excluding the just-added user message for context)
      // We include all previous messages as context
      const history = messagesToPayload(messages.slice(0, -1));

      // Build request payload
      const payload: {
        query: string;
        history?: MessagePayload[];
        group_id?: string;
        video_id?: string;
      } = {
        query: trimmedQuery,
        history,
      };

      // Add filters - video filter takes priority for more specific context
      if (videoFilter) {
        payload.video_id = videoFilter;
      } else if (groupFilter) {
        payload.group_id = groupFilter;
      }

      // Make API request
      const response = await api.post('/api/search/chat', payload);
      const data = response.data;

      // Create assistant message with response and citations
      const assistantMessage: Message = {
        id: generateId(),
        role: 'assistant',
        content: data.response || data.message || '',
        citations: data.citations || [],
        timestamp: new Date(),
      };

      // Add assistant message and start streaming animation
      set((state) => ({
        messages: [...state.messages, assistantMessage],
        isLoading: false,
        isStreaming: true,
      }));
    } catch (error) {
      // Handle error
      const errorMessage =
        error instanceof Error
          ? error.message
          : 'Failed to send message. Please try again.';

      set({
        isLoading: false,
        error: errorMessage,
      });

      console.error('Chat error:', error);
    }
  },

  /**
   * Set the group filter for scoped searches
   * Pass null to search across all videos
   */
  setGroupFilter: (groupId: string | null) => {
    set({ groupFilter: groupId, videoFilter: null });  // Clear video filter when setting group
  },

  /**
   * Set the video filter for scoped searches to a specific video
   * Pass null to search across all videos (or current group if set)
   */
  setVideoFilter: (videoId: string | null) => {
    set({ videoFilter: videoId });
  },

  /**
   * Set the streaming state
   * Used to track when message content is being animated
   */
  setStreaming: (streaming: boolean) => {
    set({ isStreaming: streaming });
  },

  /**
   * Clear all messages and reset chat state
   */
  clearChat: () => {
    set({
      messages: [],
      error: null,
      isLoading: false,
      isStreaming: false,
    });
  },
}));

// Export hook alias for convenience
export const useChat = useChatStore;

export default useChatStore;
