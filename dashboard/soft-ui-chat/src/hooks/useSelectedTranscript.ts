/**
 * Selected Transcript Store
 *
 * Zustand store for managing the currently selected transcript
 * in the dashboard. Used for displaying transcript details in the
 * main content area.
 */
import { create } from 'zustand';
import type { Video } from '@/types/api';

// ============================================
// Store Types
// ============================================

interface SelectedTranscriptState {
  // State
  selectedTranscript: Video | null;

  // Actions
  setSelectedTranscript: (transcript: Video | null) => void;
  clearSelection: () => void;
}

// ============================================
// Selected Transcript Store Implementation
// ============================================

export const useSelectedTranscript = create<SelectedTranscriptState>((set) => ({
  // Initial state
  selectedTranscript: null,

  /**
   * Set the currently selected transcript
   * @param transcript - The video/transcript to select, or null to clear selection
   */
  setSelectedTranscript: (transcript: Video | null) => {
    set({ selectedTranscript: transcript });
  },

  /**
   * Clear the current selection
   */
  clearSelection: () => {
    set({ selectedTranscript: null });
  },
}));

export default useSelectedTranscript;
