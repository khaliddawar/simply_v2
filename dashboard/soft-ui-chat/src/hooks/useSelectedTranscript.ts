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

export const useSelectedTranscript = create<SelectedTranscriptState>((set, get) => ({
  // Initial state
  selected: null,

  /**
   * Set the currently selected transcript (new API)
   * @param transcript - The transcript to select, or null to clear selection
   */
  setSelected: (transcript: Transcript | null) => {
    set({ selected: transcript });
  },

  /**
   * Clear the current selection
   */
  clearSelection: () => {
    set({ selected: null });
  },

  // ============================================
  // Backward Compatibility Aliases
  // ============================================

  /**
   * Alias for `selected` - for backward compatibility
   * @deprecated Use `selected` instead
   */
  get selectedTranscript() {
    return get().selected;
  },

  /**
   * Alias for `setSelected` - for backward compatibility
   * @deprecated Use `setSelected` instead
   * @param transcript - The transcript to select, or null to clear selection
   */
  setSelectedTranscript: (transcript: Transcript | null) => {
    set({ selected: transcript });
  },
}));

export default useSelectedTranscript;
