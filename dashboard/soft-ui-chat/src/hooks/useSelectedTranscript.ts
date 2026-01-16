/**
 * Selected Transcript Store
 *
 * Zustand store for managing the currently selected transcript
 * in the dashboard. Used for displaying transcript details in the
 * main content area.
 *
 * Now uses the unified Transcript type to support all source types
 * (YouTube videos, meetings, file uploads, etc.)
 */
import { create } from 'zustand';
import type { Transcript } from '@/types/api';

// ============================================
// Store Types
// ============================================

interface SelectedTranscriptState {
  // Primary state (new naming convention)
  selected: Transcript | null;

  // Primary actions (new naming convention)
  setSelected: (transcript: Transcript | null) => void;
  clearSelection: () => void;

  // Aliases for backward compatibility with old code
  selectedTranscript: Transcript | null;
  setSelectedTranscript: (transcript: Transcript | null) => void;
}

// ============================================
// Selected Transcript Store Implementation
// ============================================

export const useSelectedTranscript = create<SelectedTranscriptState>((set) => ({
  // Initial state - both properties kept in sync
  selected: null,
  selectedTranscript: null,  // Actual state property, not a getter

  /**
   * Set the currently selected transcript (new API)
   * @param transcript - The transcript to select, or null to clear selection
   */
  setSelected: (transcript: Transcript | null) => {
    set({ selected: transcript, selectedTranscript: transcript });
  },

  /**
   * Clear the current selection
   */
  clearSelection: () => {
    set({ selected: null, selectedTranscript: null });
  },

  /**
   * Alias for `setSelected` - for backward compatibility
   * @deprecated Use `setSelected` instead
   * @param transcript - The transcript to select, or null to clear selection
   */
  setSelectedTranscript: (transcript: Transcript | null) => {
    set({ selected: transcript, selectedTranscript: transcript });
  },
}));

export default useSelectedTranscript;
