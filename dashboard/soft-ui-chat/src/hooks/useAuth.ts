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
// Google OAuth Configuration
// ============================================

// Same Google Client ID used by the extension
const GOOGLE_CLIENT_ID = '1049678014825-r2sgcffbksmm2jb8ikkdvdpfv23j8v7a.apps.googleusercontent.com';

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
       * Uses direct Google OAuth (same flow as Chrome extension)
       * Redirects to Google, which redirects back with access_token in URL fragment
       */
      googleLogin: () => {
        // Build the redirect URI - current page to return to after OAuth
        const redirectUri = window.location.origin + window.location.pathname;

        // Build Google OAuth URL with implicit grant flow
        const authUrl = new URL('https://accounts.google.com/o/oauth2/v2/auth');
        authUrl.searchParams.set('client_id', GOOGLE_CLIENT_ID);
        authUrl.searchParams.set('response_type', 'token');
        authUrl.searchParams.set('redirect_uri', redirectUri);
        authUrl.searchParams.set('scope', 'openid email profile');

        // Redirect to Google OAuth
        window.location.href = authUrl.toString();
      },

      /**
       * Handle OAuth callback - check for access_token in URL fragment
       * Uses same flow as Chrome extension:
       * 1. Extract Google access_token from URL fragment
       * 2. Get user info from Google
       * 3. Send to backend /api/auth/google/extension endpoint
       * Returns true if OAuth callback was handled, false otherwise
       */
      handleOAuthCallback: async () => {
        // Google OAuth returns token in URL fragment (hash), not query params
        const hashParams = new URLSearchParams(window.location.hash.substring(1));
        const googleAccessToken = hashParams.get('access_token');

        if (!googleAccessToken) {
          return false;
        }

        set({ isLoading: true });

        // Clean URL immediately (remove token from address bar for security)
        window.history.replaceState({}, '', window.location.pathname);

        try {
          // Step 1: Get user info from Google using the access token
          const googleUserResponse = await fetch('https://www.googleapis.com/oauth2/v2/userinfo', {
            headers: {
              'Authorization': `Bearer ${googleAccessToken}`
            }
          });

          if (!googleUserResponse.ok) {
            throw new Error('Failed to get user info from Google');
          }

          const googleUser = await googleUserResponse.json();

          // Step 2: Send to backend to create/get user (same endpoint as extension)
          const apiBase = import.meta.env.VITE_API_URL || '';
          const backendResponse = await fetch(`${apiBase}/api/auth/google/extension`, {
            method: 'POST',
            headers: {
              'Content-Type': 'application/json',
            },
            body: JSON.stringify({
              google_id: googleUser.id,
              email: googleUser.email,
              name: googleUser.name,
              given_name: googleUser.given_name,
              family_name: googleUser.family_name,
              picture: googleUser.picture
            }),
          });

          if (!backendResponse.ok) {
            const errorData = await backendResponse.json().catch(() => ({}));
            throw new Error(errorData.detail || 'Failed to authenticate with backend');
          }

          const backendData = await backendResponse.json();

          // Store the JWT token from our backend
          localStorage.setItem('access_token', backendData.access_token);

          set({
            user: backendData.user,
            token: backendData.access_token,
            isAuthenticated: true,
            isLoading: false,
            error: null,
          });
          return true;
        } catch (error) {
          const errorMessage = error instanceof Error ? error.message : 'OAuth login failed. Please try again.';
          localStorage.removeItem('access_token');
          set({
            user: null,
            token: null,
            isAuthenticated: false,
            isLoading: false,
            error: errorMessage,
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
