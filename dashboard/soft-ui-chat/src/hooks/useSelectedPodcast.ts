/**
 * Selected Podcast Store
 *
 * Zustand store for managing the currently selected podcast
 * in the dashboard. Used for displaying podcast details in the
 * right panel.
 */
import { create } from 'zustand';
import type { Podcast } from '@/types/api';

// ============================================
// Store Types
// ============================================

interface SelectedPodcastState {
  // State
  selectedPodcast: Podcast | null;

  // Actions
  setSelectedPodcast: (podcast: Podcast | null) => void;
  clearSelection: () => void;
}

// ============================================
// Selected Podcast Store Implementation
// ============================================

export const useSelectedPodcast = create<SelectedPodcastState>((set) => ({
  // Initial state
  selectedPodcast: null,

  /**
   * Set the currently selected podcast
   * @param podcast - The podcast to select, or null to clear selection
   */
  setSelectedPodcast: (podcast: Podcast | null) => {
    set({ selectedPodcast: podcast });
  },

  /**
   * Clear the current selection
   */
  clearSelection: () => {
    set({ selectedPodcast: null });
  },
}));

export default useSelectedPodcast;
