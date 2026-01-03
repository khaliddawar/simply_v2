/**
 * API Client Configuration
 *
 * Axios-based HTTP client with authentication interceptors
 * for communicating with the TubeVibe FastAPI backend.
 */
import axios from 'axios';

// Base URL from environment variable, falling back to localhost for development
const API_BASE = import.meta.env.VITE_API_URL || 'http://localhost:8000';

/**
 * Configured Axios instance for API requests
 *
 * Features:
 * - Automatic JSON content type
 * - Bearer token injection from localStorage
 * - 401 response handling with redirect to login
 */
export const api = axios.create({
  baseURL: API_BASE,
  headers: { 'Content-Type': 'application/json' }
});

// Request interceptor - add auth token to all requests
api.interceptors.request.use((config) => {
  const token = localStorage.getItem('access_token');
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

// Response interceptor - handle authentication errors
api.interceptors.response.use(
  (response) => response,
  async (error) => {
    if (error.response?.status === 401) {
      // Clear stored token on authentication failure
      localStorage.removeItem('access_token');
      // Redirect to home/login page
      window.location.href = '/';
    }
    return Promise.reject(error);
  }
);

export default api;
