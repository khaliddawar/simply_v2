/**
 * Right Panel Component
 *
 * Context-aware adaptive panel that switches between three states:
 * 1. Library Overview - Default state when idle
 * 2. Citations Panel - After search, when citations are available
 * 3. Video Details - When a video is selected from the sidebar
 *
 * State priority: Citations > Video Selected > Overview
 */
import { useChat } from '@/hooks/useChat';
import { useSelectedTranscript } from '@/hooks/useSelectedTranscript';
import { LibraryOverview } from './LibraryOverview';
import { CitationsPanel } from './CitationsPanel';
import { VideoDetailsPanel } from './VideoDetailsPanel';

/**
 * Panel state type for conditional rendering
 */
type PanelState = 'citations' | 'video' | 'overview';

/**
 * Determine which panel state to show based on current context
 */
function usePanelState(): PanelState {
  const { messages } = useChat();
  const { selectedTranscript } = useSelectedTranscript();

  // Find the last assistant message
  const lastAssistantMessage = [...messages]
    .reverse()
    .find((m) => m.role === 'assistant');

  // Check if it has citations
  const hasCitations =
    lastAssistantMessage?.citations &&
    lastAssistantMessage.citations.length > 0;

  // Priority: Citations > Video Selected > Overview
  if (hasCitations) {
    return 'citations';
  }

  if (selectedTranscript) {
    return 'video';
  }

  return 'overview';
}

/**
 * RightPanel - Adaptive context-aware panel
 */
export function RightPanel() {
  const panelState = usePanelState();

  return (
    <aside className="w-72 h-screen bg-card border-l border-border/50 flex flex-col overflow-hidden">
      {panelState === 'citations' && <CitationsPanel />}
      {panelState === 'video' && <VideoDetailsPanel />}
      {panelState === 'overview' && <LibraryOverview />}
    </aside>
  );
}

export default RightPanel;
