/**
 * Right Panel Component
 *
 * Context-aware adaptive panel that switches between four states:
 * 1. Library Overview - Default state when idle
 * 2. Citations Panel - After search, when citations are available
 * 3. Video Details - When a video is selected from the sidebar
 * 4. Podcast Details - When a podcast is selected from the sidebar
 *
 * State priority: Citations > Video Selected > Podcast Selected > Overview
 */
import { useChat } from '@/hooks/useChat';
import { useSelectedTranscript } from '@/hooks/useSelectedTranscript';
import { useSelectedPodcast } from '@/hooks/useSelectedPodcast';
import { LibraryOverview } from './LibraryOverview';
import { CitationsPanel } from './CitationsPanel';
import { VideoDetailsPanel } from './VideoDetailsPanel';
import { PodcastDetailsPanel } from './PodcastDetailsPanel';

/**
 * Panel state type for conditional rendering
 */
type PanelState = 'citations' | 'video' | 'podcast' | 'overview';

/**
 * Determine which panel state to show based on current context
 */
function usePanelState(): PanelState {
  const { messages } = useChat();
  const { selectedTranscript } = useSelectedTranscript();
  const { selectedPodcast } = useSelectedPodcast();

  // Find the last assistant message
  const lastAssistantMessage = [...messages]
    .reverse()
    .find((m) => m.role === 'assistant');

  // Check if it has citations
  const hasCitations =
    lastAssistantMessage?.citations &&
    lastAssistantMessage.citations.length > 0;

  // Priority: Citations > Video Selected > Podcast Selected > Overview
  if (hasCitations) {
    return 'citations';
  }

  if (selectedTranscript) {
    return 'video';
  }

  if (selectedPodcast) {
    return 'podcast';
  }

  return 'overview';
}

/**
 * RightPanel - Adaptive context-aware panel
 */
export function RightPanel() {
  const panelState = usePanelState();

  return (
    <aside className="w-72 h-full bg-card border-l border-border/50 flex flex-col overflow-hidden rounded-r-2xl">
      {panelState === 'citations' && <CitationsPanel />}
      {panelState === 'video' && <VideoDetailsPanel />}
      {panelState === 'podcast' && <PodcastDetailsPanel />}
      {panelState === 'overview' && <LibraryOverview />}
    </aside>
  );
}

export default RightPanel;
