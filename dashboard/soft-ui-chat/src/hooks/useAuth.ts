/**
 * Authentication Store
 *
 * Zustand store with persist middleware for managing
 * user authentication state across the dashboard.
 */
import { create } from 'zustand';
import { persist } from 'zustand/middleware';
import { api } from '@/lib/api';
import type { User, TokenResponse, LoginRequest, RegisterRequest } from '@/types/api';

// ============================================
// Store Types
// ============================================

interface AuthState {
  // State
  user: User | null;
  token: string | null;
  isAuthenticated: boolean;
  isLoading: boolean;
  error: string | null;

  // Actions
  login: (email: string, password: string) => Promise<void>;
  register: (email: string, password: string, first_name?: string, last_name?: string) => Promise<void>;
  googleLogin: () => void;
  handleOAuthCallback: () => Promise<boolean>;
  logout: () => void;
  fetchUser: () => Promise<void>;
  clearError: () => void;
  setLoading: (loading: boolean) => void;
}

// ============================================
// Auth Store Implementation
// ============================================

export const useAuth = create<AuthState>()(
  persist(
    (set, get) => ({
      // Initial state
      user: null,
      token: null,
      isAuthenticated: false,
      isLoading: false,
      error: null,

      /**
       * Login with email and password
       * Stores token in localStorage and updates state
       */
      login: async (email: string, password: string) => {
        set({ isLoading: true, error: null });

        try {
          const payload: LoginRequest = { email, password };
          const response = await api.post<TokenResponse>('/api/auth/login', payload);
          const { access_token, user } = response.data;

          // Store token in localStorage for axios interceptor
          localStorage.setItem('access_token', access_token);

          set({
            user,
            token: access_token,
            isAuthenticated: true,
            isLoading: false,
            error: null,
          });
        } catch (error: unknown) {
          const errorMessage = extractErrorMessage(error, 'Login failed. Please check your credentials.');
          set({
            isLoading: false,
            error: errorMessage,
            isAuthenticated: false,
            user: null,
            token: null,
          });
          throw new Error(errorMessage);
        }
      },

      /**
       * Register a new user account
       * Automatically logs in on successful registration
       */
      register: async (email: string, password: string, first_name?: string, last_name?: string) => {
        set({ isLoading: true, error: null });

        try {
          const payload: RegisterRequest = {
            email,
            password,
            ...(first_name && { first_name }),
            ...(last_name && { last_name }),
          };
          const response = await api.post<TokenResponse>('/api/auth/register', payload);
          const { access_token, user } = response.data;

          // Store token in localStorage for axios interceptor
          localStorage.setItem('access_token', access_token);

          set({
            user,
            token: access_token,
            isAuthenticated: true,
            isLoading: false,
            error: null,
          });
        } catch (error: unknown) {
          const errorMessage = extractErrorMessage(error, 'Registration failed. Please try again.');
          set({
            isLoading: false,
            error: errorMessage,
            isAuthenticated: false,
            user: null,
            token: null,
          });
          throw new Error(errorMessage);
        }
      },

      /**
       * Initiate Google OAuth login flow
       * Redirects to backend which redirects to Google
       */
      googleLogin: () => {
        // Get the current URL to redirect back after OAuth
        const currentUrl = window.location.origin + window.location.pathname;
        const apiBase = import.meta.env.VITE_API_URL || '';
        const googleLoginUrl = `${apiBase}/api/auth/google/login?redirect_uri=${encodeURIComponent(currentUrl)}`;
        window.location.href = googleLoginUrl;
      },

      /**
       * Handle OAuth callback - check for access_token in URL
       * Returns true if OAuth callback was handled, false otherwise
       */
      handleOAuthCallback: async () => {
        const params = new URLSearchParams(window.location.search);
        const accessToken = params.get('access_token');

        if (!accessToken) {
          return false;
        }

        // Store token
        localStorage.setItem('access_token', accessToken);
        set({ token: accessToken, isLoading: true });

        // Clean URL (remove token from address bar for security)
        window.history.replaceState({}, '', window.location.pathname);

        // Fetch user info
        try {
          const response = await api.get<User>('/api/auth/me');
          set({
            user: response.data,
            isAuthenticated: true,
            isLoading: false,
            error: null,
          });
          return true;
        } catch {
          localStorage.removeItem('access_token');
          set({
            user: null,
            token: null,
            isAuthenticated: false,
            isLoading: false,
            error: 'OAuth login failed. Please try again.',
          });
          return true; // Still return true to indicate we handled the callback
        }
      },

      /**
       * Logout user and clear all auth state
       */
      logout: () => {
        // Clear token from localStorage
        localStorage.removeItem('access_token');

        set({
          user: null,
          token: null,
          isAuthenticated: false,
          isLoading: false,
          error: null,
        });
      },

      /**
       * Fetch current user profile from API
       * Used to validate stored token and refresh user data
       */
      fetchUser: async () => {
        const { token } = get();

        if (!token) {
          set({ isAuthenticated: false, user: null });
          return;
        }

        set({ isLoading: true, error: null });

        try {
          const response = await api.get<User>('/api/auth/me');

          set({
            user: response.data,
            isAuthenticated: true,
            isLoading: false,
            error: null,
          });
        } catch (error: unknown) {
          // Token is invalid, clear auth state
          localStorage.removeItem('access_token');

          set({
            user: null,
            token: null,
            isAuthenticated: false,
            isLoading: false,
            error: null, // Don't show error for invalid token
          });
        }
      },

      /**
       * Clear any error messages
       */
      clearError: () => {
        set({ error: null });
      },

      /**
       * Set loading state manually
       */
      setLoading: (loading: boolean) => {
        set({ isLoading: loading });
      },
    }),
    {
      name: 'tubevibe-auth', // localStorage key
      partialize: (state) => ({
        // Only persist token, user data will be fetched on app load
        token: state.token,
      }),
      onRehydrate: () => {
        // After rehydration, sync token to localStorage for axios interceptor
        return (state) => {
          if (state?.token) {
            localStorage.setItem('access_token', state.token);
          }
        };
      },
    }
  )
);

// ============================================
// Helper Functions
// ============================================

/**
 * Extract error message from axios error response
 */
function extractErrorMessage(error: unknown, defaultMessage: string): string {
  if (error && typeof error === 'object' && 'response' in error) {
    const response = (error as { response?: { data?: { detail?: string } } }).response;
    if (response?.data?.detail) {
      return response.data.detail;
    }
  }
  if (error && typeof error === 'object' && 'message' in error) {
    return (error as { message: string }).message;
  }
  return defaultMessage;
}

export default useAuth;
