// TubeVibe Background Script
// Note: Service workers in Manifest V3 don't support dynamic imports
// Security utilities should be loaded directly if needed

// ============================================================================
// TEST MODE - Set to true to bypass authentication for testing
// ============================================================================
const TEST_MODE = false;
const TEST_USER_ID = '00000000-0000-0000-0000-000000000001';
const API_BASE_URL = 'https://simply-backend-production.up.railway.app';

// Import enhanced token manager
importScripts('utils/tokenManager.js');

// Import Authorizer client for authentication
importScripts('utils/authorizerClient.js');

// ============================================================================
// AUTHENTICATION PROVIDER TOGGLE
// Set to true to use Authorizer for authentication (including Google OAuth)
// The extension calls Authorizer directly, then exchanges tokens with TubeVibe backend
// ============================================================================
const USE_AUTHORIZER = true;

// Handle extension installation
chrome.runtime.onInstalled.addListener(() => {
});
// Handle messages from content scripts
chrome.runtime.onMessage.addListener((request, sender, sendResponse) => {
  if (request.type === 'PING') {
    // Health check - just return success
    sendResponse({success: true, message: 'pong'});
    return true;
  } else if (request.type === 'PROCESS_TRANSCRIPT') {
    // Handle transcript processing
    handleTranscriptProcessing(request.data)
      .then(response => {
        sendResponse(response);
      })
      .catch(error => {
        console.error('Transcript processing error:', error);
        sendResponse({ success: false, error: error.message });
      });
    return true; // Keep message channel open for async response
  }
  if (request.type === 'USER_LOGIN') {
    // Handle user login
    handleUserLogin(request.data)
      .then(response => {
        sendResponse(response);
      })
      .catch(error => {
        sendResponse({ success: false, error: error.message });
      });
    return true; // Keep message channel open for async response
  }
  if (request.type === 'USER_SIGNUP') {
    // Handle user signup
    handleUserSignup(request.data)
      .then(response => sendResponse(response))
      .catch(error => sendResponse({ success: false, error: error.message }));
    return true; // Keep message channel open for async response
  }
  if (request.type === 'USER_LOGOUT') {
    // Handle user logout
    handleUserLogout()
      .then(response => {
        sendResponse(response);
      })
      .catch(error => {
        sendResponse({ success: false, error: error.message });
      });
    return true; // Keep message channel open for async response
  }
  if (request.type === 'GOOGLE_AUTH') {
    // Handle Google OAuth authentication
    handleGoogleAuth()
      .then(response => {
        sendResponse(response);
      })
      .catch(error => {
        sendResponse({ success: false, error: error.message });
      });
    return true; // Keep message channel open for async response
  }
  if (request.type === 'REQUEST_MAGIC_LINK') {
    // Handle magic link request (Authorizer only)
    handleMagicLinkRequest(request.data)
      .then(response => {
        sendResponse(response);
      })
      .catch(error => {
        sendResponse({ success: false, error: error.message });
      });
    return true; // Keep message channel open for async response
  }
  if (request.type === 'FORGOT_PASSWORD') {
    // Handle forgot password request (Authorizer only)
    handleForgotPassword(request.data)
      .then(response => {
        sendResponse(response);
      })
      .catch(error => {
        sendResponse({ success: false, error: error.message });
      });
    return true; // Keep message channel open for async response
  }
  if (request.type === 'INITIATE_UPGRADE') {
    // Handle subscription upgrade
    handleUpgradeInitiation(request.data)
      .then(response => {
        sendResponse(response);
      })
      .catch(error => {
        sendResponse({ success: false, error: error.message });
      });
    return true; // Keep message channel open for async response
  }
  if (request.type === 'GET_SUBSCRIPTION_STATUS') {
    // Handle subscription status check
    handleGetSubscriptionStatus()
      .then(response => {
        sendResponse(response);
      })
      .catch(error => {
        console.error('Subscription status error:', error);
        sendResponse({ success: false, error: error.message });
      });
    return true; // Keep message channel open for async response
  }
  if (request.type === 'REFRESH_TOKEN') {
    // Handle token refresh
    handleTokenRefresh()
      .then(response => {
        sendResponse(response);
      })
      .catch(error => {
        sendResponse({ success: false, error: error.message });
      });
    return true; // Keep message channel open for async response
  }
  // ============================================================================
  // NEW: Save to Library handler - saves transcript to TubeVibe Library (Pinecone)
  // ============================================================================
  if (request.type === 'SAVE_TO_LIBRARY') {
    handleSaveToLibrary(request.data)
      .then(response => {
        sendResponse(response);
      })
      .catch(error => {
        console.error('Save to library error:', error);
        sendResponse({ success: false, error: error.message });
      });
    return true;
  }
  // ============================================================================
  // NEW: Chat with video handler - uses Pinecone Assistant for Q&A
  // ============================================================================
  if (request.type === 'CHAT_WITH_VIDEO') {
    handleChatWithVideo(request.data)
      .then(response => {
        sendResponse(response);
      })
      .catch(error => {
        console.error('Chat with video error:', error);
        sendResponse({ success: false, error: error.message });
      });
    return true;
  }
  // ============================================================================
  // NEW: Check if video is saved in library
  // ============================================================================
  if (request.type === 'CHECK_VIDEO_SAVED') {
    handleCheckVideoSaved(request.data)
      .then(response => sendResponse(response))
      .catch(error => sendResponse({ success: false, error: error.message }));
    return true;
  }
  // ============================================================================
  // NEW: Generate video summary using TubeVibe Library (Topic Detection + CoD)
  // ============================================================================
  if (request.type === 'GENERATE_VIDEO_SUMMARY') {
    handleGenerateVideoSummary(request.data)
      .then(response => {
        sendResponse(response);
      })
      .catch(error => {
        console.error('Generate video summary error:', error);
        sendResponse({ success: false, error: error.message });
      });
    return true;
  }
  // ============================================================================
  // NEW: Email video summary to user
  // ============================================================================
  if (request.type === 'EMAIL_VIDEO_SUMMARY') {
    handleEmailVideoSummary(request.data)
      .then(response => {
        sendResponse(response);
      })
      .catch(error => {
        console.error('Email video summary error:', error);
        sendResponse({ success: false, error: error.message });
      });
    return true;
  }
  // ============================================================================
  // NEW: Get user's videos for history display
  // ============================================================================
  if (request.type === 'GET_USER_VIDEOS') {
    handleGetUserVideos(request.data)
      .then(response => {
        sendResponse(response);
      })
      .catch(error => {
        console.error('Get user videos error:', error);
        sendResponse({ success: false, error: error.message });
      });
    return true;
  }
  // ============================================================================
  // NEW: Get auth status (with TEST_MODE support)
  // ============================================================================
  if (request.type === 'GET_AUTH_STATUS') {
    handleGetAuthStatus()
      .then(response => sendResponse(response))
      .catch(error => sendResponse({ success: false, error: error.message }));
    return true;
  }
  return true; // Keep message channel open
});
// Handle user login
async function handleUserLogin(credentials) {
  try {
    // ========================================================================
    // AUTHORIZER AUTHENTICATION PATH
    // ========================================================================
    if (USE_AUTHORIZER) {
      const result = await AuthorizerClient.login(
        credentials.email,
        credentials.password
      );

      if (!result.success) {
        throw new Error(result.error || 'Login failed');
      }

      // Store tokens with auth_provider marker
      const storageData = {
        'access_token': result.access_token,
        'refresh_token': result.refresh_token,
        'user_info': result.user,
        'token_expires_at': Date.now() + (result.expires_in * 1000),
        'auth_provider': 'authorizer'
      };
      await chrome.storage.local.set(storageData);

      return {
        success: true,
        user: result.user,
        session: {
          access_token: result.access_token,
          refresh_token: result.refresh_token
        }
      };
    }

    // ========================================================================
    // LEGACY AUTHENTICATION PATH (fallback when USE_AUTHORIZER is false)
    // ========================================================================
    const response = await fetch(`${API_BASE_URL}/api/auth/login`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(credentials),
    });
    if (!response.ok) {
      const error = await response.json();
      throw new Error(error.message || error.detail || 'Login failed');
    }
    const data = await response.json();
    // Fetch user information using the access token
    let userInfo = null;
    try {
      const userResponse = await fetch(`${API_BASE_URL}/api/auth/me`, {
        headers: {
          'Authorization': `Bearer ${data.access_token}`
        }
      });
      if (userResponse.ok) {
        userInfo = await userResponse.json();
      }
    } catch (error) {
      // User info fetch failed, continue with login
    }
    // Store tokens in Chrome storage (backend returns tokens directly)
    const storageData = {
      'access_token': data.access_token,
      'refresh_token': data.refresh_token,
      'user_info': userInfo || { email: 'unknown' },
      'token_expires_at': Date.now() + (data.expires_in || 3600) * 1000, // Store expiration time
      'auth_provider': 'legacy'
    };
    await chrome.storage.local.set(storageData);
    return {
      success: true,
      user: userInfo || { email: 'unknown' },
      session: { access_token: data.access_token, refresh_token: data.refresh_token }
    };
  } catch (error) {
    console.error('Login error:', error);
    throw error;
  }
}
// Token management using TokenManager utility
async function refreshAccessToken() {
  const tokenData = await TokenManager.refreshTokenWithRetry();
  return tokenData ? tokenData.access_token : null;
}

// Get valid access token with auth_provider aware refresh
async function getValidAccessToken() {
  try {
    // Get token data and auth_provider from storage
    const storage = await chrome.storage.local.get([
      'access_token',
      'refresh_token',
      'token_expires_at',
      'auth_provider',
      'user_info'
    ]);

    if (!storage.access_token) {
      return null;
    }

    // Check if token is expired (with 10-minute buffer)
    const now = Date.now();
    const bufferTime = 10 * 60 * 1000; // 10 minutes
    const isExpired = storage.token_expires_at && now >= (storage.token_expires_at - bufferTime);

    if (!isExpired) {
      return storage.access_token;
    }

    // Refresh token using the correct method based on auth_provider
    if (storage.auth_provider === 'authorizer' && USE_AUTHORIZER) {
      if (!storage.refresh_token) {
        return null;
      }

      const result = await AuthorizerClient.refreshToken(storage.refresh_token);

      if (!result.success) {
        // Don't clear tokens on refresh failure - let user retry
        return null;
      }

      // Update storage with new tokens
      const newStorageData = {
        'access_token': result.access_token,
        'refresh_token': result.refresh_token || storage.refresh_token,
        'token_expires_at': Date.now() + (result.expires_in * 1000),
        'user_info': result.user || storage.user_info
      };
      await chrome.storage.local.set(newStorageData);

      return result.access_token;

    } else {
      // Legacy or Google auth - use backend refresh endpoint
      if (!storage.refresh_token) {
        return null;
      }

      const response = await fetch(`${API_BASE_URL}/api/auth/refresh`, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${storage.refresh_token}`,
          'Content-Type': 'application/json'
        }
      });

      if (!response.ok) {
        return null;
      }

      const tokenData = await response.json();

      // Update storage with new tokens
      const newStorageData = {
        'access_token': tokenData.access_token,
        'refresh_token': tokenData.refresh_token || storage.refresh_token,
        'token_expires_at': Date.now() + (tokenData.expires_in || 3600) * 1000
      };
      await chrome.storage.local.set(newStorageData);

      return tokenData.access_token;
    }

  } catch (error) {
    console.error('Token validation error:', error);
    return null;
  }
}
// Handle user signup
async function handleUserSignup(userData) {
  try {
    // ========================================================================
    // AUTHORIZER AUTHENTICATION PATH
    // ========================================================================
    if (USE_AUTHORIZER) {
      const result = await AuthorizerClient.signup(
        userData.email,
        userData.password,
        userData.first_name || userData.given_name || '',
        userData.last_name || userData.family_name || ''
      );

      if (!result.success) {
        throw new Error(result.error || 'Signup failed');
      }

      // Authorizer requires email verification
      return {
        success: true,
        requiresVerification: true,
        message: result.message || 'Please check your email to verify your account.',
        user: result.user
      };
    }

    // ========================================================================
    // LEGACY AUTHENTICATION PATH (fallback when USE_AUTHORIZER is false)
    // ========================================================================
    const response = await fetch(`${API_BASE_URL}/api/auth/register`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(userData),
    });

    if (!response.ok) {
      const error = await response.json();
      throw new Error(error.message || error.detail || 'Signup failed');
    }

    const data = await response.json();

    // Check if user requires email verification
    if (data.requires_verification) {
      return {
        success: true,
        user: data,
        requiresVerification: true,
        message: 'Account created! Please check your email to verify your account.'
      };
    }

    // Only store tokens if user doesn't require verification (shouldn't happen in current flow)
    if (data.access_token && data.refresh_token) {
      const storageData = {
        'access_token': data.access_token,
        'refresh_token': data.refresh_token,
        'user_info': data.user || data,
        'token_expires_at': Date.now() + (data.expires_in || 3600) * 1000,
        'auth_provider': 'legacy'
      };
      await chrome.storage.local.set(storageData);

      return {
        success: true,
        user: data.user || data,
        session: { access_token: data.access_token, refresh_token: data.refresh_token }
      };
    }

    // Fallback for other cases
    return {
      success: true,
      user: data,
      requiresVerification: true,
      message: 'Account created! Please check your email to verify your account.'
    };

  } catch (error) {
    console.error('Signup error:', error);
    throw error;
  }
}
// Handle user logout
async function handleUserLogout() {
  try {
    // Get access token and auth provider from storage
    const result = await chrome.storage.local.get(['access_token', 'auth_provider']);
    const accessToken = result.access_token;
    const authProvider = result.auth_provider;

    // ========================================================================
    // AUTHORIZER LOGOUT PATH
    // ========================================================================
    if (authProvider === 'authorizer' && USE_AUTHORIZER) {
      try {
        await AuthorizerClient.logout();
      } catch (error) {
        // Logout failed, continue with local cleanup
      }
    }
    // ========================================================================
    // LEGACY LOGOUT PATH
    // ========================================================================
    else if (accessToken) {
      try {
        // Call backend logout endpoint
        await fetch(`${API_BASE_URL}/api/auth/logout`, {
          method: 'POST',
          headers: {
            'Authorization': `Bearer ${accessToken}`,
            'Content-Type': 'application/json'
          }
        });
      } catch (error) {
        // Backend logout error, continue with local cleanup
      }
    }

    // Clear stored tokens regardless of backend response
    // First, ask TokenManager to wipe its consolidated key
    if (typeof TokenManager !== 'undefined' && typeof TokenManager.clearTokenData === 'function') {
      try {
        await TokenManager.clearTokenData();
      } catch (e) {
        // TokenManager cleanup failed, continue
      }
    }

    // Fallback / legacy cleanup - include auth_provider in cleanup
    await chrome.storage.local.remove([
      'simply_token_data', // consolidated token store
      'access_token',
      'refresh_token',
      'user_info',
      'token_expires_at',
      'auth_provider'
    ]);
    return {
      success: true,
      message: 'Successfully logged out'
    };
  } catch (error) {
    console.error('Logout error:', error);
    // Try to clear tokens even on error
    try {
      await chrome.storage.local.remove(['access_token', 'refresh_token', 'user_info', 'token_expires_at', 'auth_provider']);
    } catch (clearError) {
      console.error('Failed to clear tokens:', clearError);
    }
    return {
      success: false,
      error: error.message
    };
  }
}
// Handle Google OAuth authentication via Web Auth Flow
async function handleGoogleAuth() {
  try {
    // ========================================================================
    // AUTHORIZER GOOGLE OAUTH PATH
    // ========================================================================
    if (USE_AUTHORIZER) {
      const result = await AuthorizerClient.googleOAuth();

      if (!result.success) {
        throw new Error(result.error || 'Google authentication failed');
      }

      // Store tokens with auth_provider marker
      const storageData = {
        'access_token': result.access_token,
        'refresh_token': result.refresh_token,
        'user_info': result.user,
        'token_expires_at': Date.now() + (result.expires_in * 1000),
        'auth_provider': 'authorizer'
      };
      await chrome.storage.local.set(storageData);

      return {
        success: true,
        user: result.user,
        session: {
          access_token: result.access_token,
          refresh_token: result.refresh_token
        },
        provider: 'google'
      };
    }

    // ========================================================================
    // LEGACY GOOGLE OAUTH PATH (fallback when USE_AUTHORIZER is false)
    // ========================================================================

    // Step 1: Get access token using launchWebAuthFlow (more reliable than getAuthToken)
    const clientId = '1049678014825-r2sgcffbksmm2jb8ikkdvdpfv23j8v7a.apps.googleusercontent.com';
    const redirectUrl = chrome.identity.getRedirectURL();

    const authUrl = new URL('https://accounts.google.com/o/oauth2/v2/auth');
    authUrl.searchParams.set('client_id', clientId);
    authUrl.searchParams.set('response_type', 'token');
    authUrl.searchParams.set('redirect_uri', redirectUrl);
    authUrl.searchParams.set('scope', 'openid email profile');

    const responseUrl = await chrome.identity.launchWebAuthFlow({
      url: authUrl.toString(),
      interactive: true
    });

    // Extract token from response
    const url = new URL(responseUrl);
    const accessToken = new URLSearchParams(url.hash.substring(1)).get('access_token');

    if (!accessToken) {
      throw new Error('Failed to get access token from OAuth response');
    }

    // Step 2: Get user info using the access token
    let userInfo = null;
    try {
      const userResponse = await fetch('https://www.googleapis.com/oauth2/v2/userinfo', {
        headers: {
          'Authorization': `Bearer ${accessToken}`
        }
      });

      if (userResponse.ok) {
        const userData = await userResponse.json();
        userInfo = userData; // Google API returns user data directly

        // Step 3: Send user data to backend for account creation/login
        const backendResponse = await fetch(`${API_BASE_URL}/api/auth/google`, {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
          },
          body: JSON.stringify({
            google_id: userInfo.id,
            email: userInfo.email,
            name: userInfo.name,
            given_name: userInfo.given_name,
            family_name: userInfo.family_name,
            picture: userInfo.picture
          }),
        });

        if (!backendResponse.ok) {
          throw new Error('Failed to authenticate with backend');
        }

        const backendData = await backendResponse.json();

        // Step 4: Store tokens and user data
        const storageData = {
          'access_token': accessToken,
          'refresh_token': null, // Chrome identity API doesn't provide refresh tokens
          'user_info': backendData.user || userInfo,
          'token_expires_at': Date.now() + 3600 * 1000, // 1 hour default
          'auth_provider': 'google'
        };

        await chrome.storage.local.set(storageData);

        return {
          success: true,
          user: backendData.user || userInfo,
          session: {
            access_token: accessToken,
            refresh_token: null
          },
          provider: 'google'
        };
      } else {
        throw new Error('Failed to fetch user info from Google');
      }
    } catch (error) {
      throw error;
    }

  } catch (error) {
    console.error('Google OAuth error:', error);

    // Provide user-friendly error messages
    let userMessage = error.message;
    if (error.message.includes('popup_closed_by_user') || error.message.includes('canceled') || error.message.includes('cancelled')) {
      userMessage = 'Google sign-in was cancelled. Please try again.';
    } else if (error.message.includes('authorization')) {
      userMessage = 'Google sign-in failed. Please try again.';
    } else if (error.message.includes('network') || error.message.includes('fetch')) {
      userMessage = 'Network error. Please check your connection and try again.';
    } else if (error.message === 'Authorization page could not be loaded.') {
      userMessage = 'Google authorization failed. Please check your internet connection and try again.';
    } else if (error.message.includes('bad client id')) {
      userMessage = 'Google authentication configuration error. Please try regular email login.';
    }

    return {
      success: false,
      error: userMessage
    };
  }
}
// Handle transcript processing - Save video to TubeVibe Library (Unified API)
async function handleTranscriptProcessing(transcriptData) {
  try {
    // Get valid access token for authentication
    const accessToken = await getValidAccessToken();
    if (!accessToken) {
      throw new Error('Authentication required. Please sign in again.');
    }

    // Build request headers with auth
    const headers = {
      'Content-Type': 'application/json',
      'Authorization': `Bearer ${accessToken}`
    };

    // Use the unified transcripts API endpoint
    const endpoint = `${API_BASE_URL}/api/transcripts`;

    // Parse duration string to seconds
    const durationSeconds = parseDuration(transcriptData.duration);

    const response = await fetch(endpoint, {
      method: 'POST',
      headers: headers,
      body: JSON.stringify({
        source_type: 'youtube',
        external_id: transcriptData.video_id,
        title: transcriptData.title,
        transcript_text: transcriptData.transcript,
        group_id: transcriptData.group_id || null,
        metadata: {
          youtube_id: transcriptData.video_id,
          channel_name: transcriptData.channel_name || 'Unknown Channel',
          duration_seconds: durationSeconds,
          thumbnail_url: transcriptData.thumbnail_url || `https://i.ytimg.com/vi/${transcriptData.video_id}/maxresdefault.jpg`
        }
      })
    });

    if (!response.ok) {
      const errorData = await response.json().catch(() => ({}));
      throw new Error(errorData.detail || `API request failed: ${response.status}`);
    }

    const result_data = await response.json();

    // Store the saved transcript ID for reference
    await chrome.storage.local.set({
      [`saved_video_${transcriptData.video_id}`]: {
        id: result_data.id,
        saved_at: new Date().toISOString()
      }
    });

    return {
      success: true,
      data: result_data,
      message: 'Video saved to library successfully!'
    };

  } catch (error) {
    console.error('Transcript processing error:', error);
    throw error;
  }
}
// Poll for job completion
async function pollForJobCompletion(jobId, accessToken) {
  const maxAttempts = 30;
  const pollInterval = 5000;
  for (let attempt = 1; attempt <= maxAttempts; attempt++) {
    try {
              const response = await fetch(`${API_BASE_URL}/api/yt_job/${jobId}`, {
        headers: {
          'Authorization': `Bearer ${accessToken}`
        }
      });
      if (!response.ok) {
        throw new Error(`Job status check failed: ${response.status}`);
      }
      const jobStatus = await response.json();
      if (jobStatus.status === 'completed') {
        return jobStatus;
      } else if (jobStatus.status === 'failed') {
        throw new Error(jobStatus.error || 'Job processing failed');
      }
      // Wait before next poll
      await new Promise(resolve => setTimeout(resolve, pollInterval));
    } catch (error) {
      if (attempt === maxAttempts) {
        throw error;
      }
    }
  }
  throw new Error('Job polling timeout');
}

// Handle subscription upgrade initiation
async function handleUpgradeInitiation(data) {
  try {
    const accessToken = await getValidAccessToken();
    if (!accessToken) {
      throw new Error('Authentication required. Please sign in to upgrade.');
    }

            const response = await fetch(`${API_BASE_URL}/api/payments/upgrade`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${accessToken}`
      },
      body: JSON.stringify({
        plan: data.plan || 'premium',
        billing_cycle: data.billing_cycle || 'monthly',
        return_url: data.return_url || 'https://tubevibe.app/success'
      })
    });

    if (!response.ok) {
      const error = await response.json();
      throw new Error(error.detail || error.message || 'Upgrade request failed');
    }

    const result = await response.json();
    
    if (result.success && result.checkout_url) {
      // Open checkout URL in new tab
      chrome.tabs.create({ url: result.checkout_url });
      
      return {
        success: true,
        message: 'Redirecting to checkout...',
        checkout_url: result.checkout_url
      };
    } else {
      throw new Error(result.message || 'Failed to create checkout session');
    }
  } catch (error) {
    console.error('Upgrade initiation error:', error);
    throw error;
  }
}

// Handle subscription status check
async function handleGetSubscriptionStatus() {
  try {
    const accessToken = await getValidAccessToken();
    if (!accessToken) {
      return {
        success: false,
        authenticated: false,
        message: 'Not authenticated'
      };
    }

    // First, refresh user info to get latest plan information
    let userInfo = null;
    try {
      const userResponse = await fetch(`${API_BASE_URL}/api/auth/me`, {
        headers: {
          'Authorization': `Bearer ${accessToken}`
        }
      });

      if (userResponse.ok) {
        userInfo = await userResponse.json();
        // Update cached user info in Chrome storage
        await chrome.storage.local.set({ 'user_info': userInfo });
      }
    } catch (error) {
      // Could not refresh user info, continue with subscription check
    }

    // Then get subscription details
            const response = await fetch(`${API_BASE_URL}/api/payments/subscription`, {
      headers: {
        'Authorization': `Bearer ${accessToken}`
      }
    });

    if (!response.ok) {
      const error = await response.json();
      throw new Error(error.detail || error.message || 'Failed to get subscription status');
    }

    const subscriptionData = await response.json();
    
    // Merge subscription plan into userInfo
    if (userInfo && subscriptionData?.plan) {
      userInfo.plan = subscriptionData.plan;
    }
    
    return {
      success: true,
      authenticated: true,
      subscription: subscriptionData,
      userInfo: userInfo // Include refreshed user info in response
    };
  } catch (error) {
    console.error('Subscription status error:', error);
    return {
      success: false,
      error: error.message
    };
  }
}

// Handle token refresh
async function handleTokenRefresh() {
  try {
    // Get current refresh token and auth provider from storage
    const storageResult = await chrome.storage.local.get(['refresh_token', 'auth_provider']);
    const refreshToken = storageResult.refresh_token;
    const authProvider = storageResult.auth_provider;

    if (!refreshToken) {
      return {
        success: false,
        error: 'No refresh token available'
      };
    }

    // ========================================================================
    // AUTHORIZER TOKEN REFRESH PATH
    // ========================================================================
    if (authProvider === 'authorizer' && USE_AUTHORIZER) {
      const result = await AuthorizerClient.refreshToken(refreshToken);

      if (!result.success) {
        return {
          success: false,
          error: result.error || 'Token refresh failed'
        };
      }

      // Update storage with new tokens
      const newStorageData = {
        'access_token': result.access_token,
        'refresh_token': result.refresh_token || refreshToken,
        'token_expires_at': Date.now() + (result.expires_in * 1000)
      };
      await chrome.storage.local.set(newStorageData);

      return {
        success: true,
        access_token: result.access_token,
        refresh_token: result.refresh_token || refreshToken,
        expires_in: result.expires_in
      };
    }

    // ========================================================================
    // LEGACY TOKEN REFRESH PATH (fallback)
    // ========================================================================

    // Call backend refresh endpoint
    const response = await fetch(`${API_BASE_URL}/api/auth/refresh`, {
      method: 'POST',
      headers: {
        'Authorization': `Bearer ${refreshToken}`,
        'Content-Type': 'application/json'
      }
    });

    if (!response.ok) {
      const errorData = await response.json().catch(() => ({}));
      const errorMessage = errorData.detail || errorData.message || `HTTP ${response.status}`;
      return {
        success: false,
        error: `Token refresh failed: ${errorMessage}`
      };
    }

    const tokenData = await response.json();

    // Update storage with new tokens
    const storageData = {
      'access_token': tokenData.access_token,
      'refresh_token': tokenData.refresh_token,
      'token_expires_at': Date.now() + (tokenData.expires_in || 3600) * 1000
    };

    await chrome.storage.local.set(storageData);

    return {
      success: true,
      access_token: tokenData.access_token,
      refresh_token: tokenData.refresh_token,
      expires_in: tokenData.expires_in
    };

  } catch (error) {
    console.error('Token refresh error:', error);
    return {
      success: false,
      error: error.message
    };
  }
}

// ============================================================================
// MAGIC LINK HANDLER (Authorizer only)
// ============================================================================

// Handle magic link request for passwordless login
async function handleMagicLinkRequest(data) {
  try {
    if (!USE_AUTHORIZER) {
      return {
        success: false,
        error: 'Magic link login is only available with Authorizer authentication.'
      };
    }

    const result = await AuthorizerClient.requestMagicLink(data.email);

    if (!result.success) {
      throw new Error(result.error || 'Failed to send magic link');
    }

    return {
      success: true,
      message: result.message || 'Magic link sent! Check your email.'
    };

  } catch (error) {
    console.error('Magic link error:', error);
    return {
      success: false,
      error: error.message || 'Failed to send magic link'
    };
  }
}

// ============================================================================
// FORGOT PASSWORD HANDLER (Authorizer only)
// ============================================================================

// Handle forgot password request
async function handleForgotPassword(data) {
  try {
    if (!USE_AUTHORIZER) {
      return {
        success: false,
        error: 'Password reset is only available with Authorizer authentication.'
      };
    }

    const result = await AuthorizerClient.forgotPassword(data.email);

    if (!result.success) {
      throw new Error(result.error || 'Failed to send password reset email');
    }

    return {
      success: true,
      message: result.message || 'Password reset email sent! Check your inbox.'
    };

  } catch (error) {
    console.error('Forgot password error:', error);
    return {
      success: false,
      error: error.message || 'Failed to send password reset email'
    };
  }
}

// ============================================================================
// HANDLERS FOR TUBEVIBE LIBRARY INTEGRATION
// ============================================================================

// Get auth status with TEST_MODE support
async function handleGetAuthStatus() {
  if (TEST_MODE) {
    return {
      success: true,
      isAuthenticated: true,
      user: {
        id: TEST_USER_ID,
        email: 'test@example.com',
        name: 'Test User',
        plan: 'premium'
      }
    };
  }

  // Normal auth check
  const storage = await chrome.storage.local.get(['access_token', 'user_info']);
  if (storage.access_token) {
    return {
      success: true,
      isAuthenticated: true,
      user: storage.user_info
    };
  }
  return {
    success: true,
    isAuthenticated: false
  };
}

// Save video transcript to TubeVibe Library (Unified Transcripts API)
async function handleSaveToLibrary(videoData) {
  try {
    // Get valid access token for authentication
    const accessToken = await getValidAccessToken();
    if (!accessToken) {
      throw new Error('Authentication required. Please sign in to the extension first.');
    }

    const durationSeconds = parseDuration(videoData.duration) || 0;

    const response = await fetch(`${API_BASE_URL}/api/transcripts`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${accessToken}`
      },
      body: JSON.stringify({
        source_type: 'youtube',
        external_id: videoData.video_id,
        title: videoData.title,
        transcript_text: videoData.transcript,
        group_id: videoData.group_id || null,
        metadata: {
          youtube_id: videoData.video_id,
          channel_name: videoData.channel_name || 'Unknown Channel',
          duration_seconds: durationSeconds,
          thumbnail_url: videoData.thumbnail_url || `https://i.ytimg.com/vi/${videoData.video_id}/maxresdefault.jpg`
        }
      })
    });

    if (!response.ok) {
      const errorData = await response.json().catch(() => ({}));
      throw new Error(errorData.detail || `Failed to save: ${response.status}`);
    }

    const result = await response.json();

    // Store the saved transcript ID for reference
    await chrome.storage.local.set({
      [`saved_video_${videoData.video_id}`]: {
        id: result.id,
        saved_at: new Date().toISOString()
      }
    });

    return {
      success: true,
      video: result,
      message: 'Video saved to library successfully!'
    };

  } catch (error) {
    console.error('Save to library error:', error);
    throw error;
  }
}

// Helper: Parse duration string to seconds
function parseDuration(durationStr) {
  if (!durationStr) return 0;
  if (typeof durationStr === 'number') return durationStr;

  const parts = durationStr.split(':').reverse();
  let seconds = 0;
  if (parts[0]) seconds += parseInt(parts[0]) || 0;
  if (parts[1]) seconds += (parseInt(parts[1]) || 0) * 60;
  if (parts[2]) seconds += (parseInt(parts[2]) || 0) * 3600;
  return seconds;
}

// Check if video is already saved in library (Unified Transcripts API)
async function handleCheckVideoSaved(data) {
  const youtubeId = data.video_id || data.youtube_id;

  try {
    // First check local storage cache for quick response
    const cached = await chrome.storage.local.get([`saved_video_${youtubeId}`]);
    if (cached[`saved_video_${youtubeId}`]) {
      return {
        success: true,
        isSaved: true,
        video: cached[`saved_video_${youtubeId}`],
        source: 'cache'
      };
    }

    // Get valid access token for backend check
    const accessToken = await getValidAccessToken();
    if (!accessToken) {
      return {
        success: true,
        isSaved: false,
        reason: 'not_authenticated'
      };
    }

    // Check backend using unified transcripts API
    const response = await fetch(`${API_BASE_URL}/api/transcripts/check/youtube/${youtubeId}`, {
      method: 'GET',
      headers: {
        'Authorization': `Bearer ${accessToken}`
      }
    });

    if (!response.ok) {
      return {
        success: true,
        isSaved: false,
        reason: 'backend_error'
      };
    }

    const result = await response.json();

    // Cache the result if video is saved
    if (result.exists && result.transcript_id) {
      await chrome.storage.local.set({
        [`saved_video_${youtubeId}`]: {
          id: result.transcript_id,
          title: result.title
        }
      });
    }

    return {
      success: true,
      isSaved: result.exists,
      video: result.exists ? { id: result.transcript_id, title: result.title } : null,
      source: 'backend'
    };

  } catch (error) {
    console.error('Check video saved error:', error);
    return {
      success: false,
      isSaved: false,
      error: error.message
    };
  }
}

// Get user's transcripts for history display (Unified Transcripts API)
async function handleGetUserVideos(data) {
  const limit = data?.limit || 10;
  const offset = ((data?.page || 1) - 1) * limit;
  const sourceType = data?.source_type || null; // Optional: filter by source type

  try {
    // Get valid access token for authentication
    const accessToken = await getValidAccessToken();
    if (!accessToken) {
      return {
        success: false,
        error: 'Authentication required. Please sign in to view history.'
      };
    }

    // Build query params
    const params = new URLSearchParams({
      limit: limit.toString(),
      offset: offset.toString(),
      sort_by: 'created_at',
      sort_order: 'desc'
    });
    if (sourceType) {
      params.set('source_type', sourceType);
    }

    // Fetch transcripts from unified API
    const response = await fetch(`${API_BASE_URL}/api/transcripts?${params}`, {
      method: 'GET',
      headers: {
        'Authorization': `Bearer ${accessToken}`
      }
    });

    if (!response.ok) {
      const errorData = await response.json().catch(() => ({}));
      throw new Error(errorData.detail || `Failed to fetch transcripts: ${response.status}`);
    }

    const result = await response.json();

    // Map transcripts to legacy video format for backward compatibility
    const videos = (result.transcripts || []).map(t => ({
      id: t.id,
      youtube_id: t.external_id,
      title: t.title,
      channel_name: t.metadata?.channel_name,
      duration_seconds: t.metadata?.duration_seconds,
      thumbnail_url: t.metadata?.thumbnail_url,
      has_summary: t.has_summary,
      created_at: t.created_at,
      source_type: t.source_type
    }));

    return {
      success: true,
      videos: videos,
      total: result.total || 0,
      page: data?.page || 1,
      per_page: limit,
      pages: Math.ceil((result.total || 0) / limit)
    };

  } catch (error) {
    console.error('Get user videos error:', error);
    return {
      success: false,
      error: error.message
    };
  }
}

// Chat with video transcript using Pinecone Assistant
async function handleChatWithVideo(data) {
  try {
    // Get valid access token for authentication
    const accessToken = await getValidAccessToken();
    if (!accessToken) {
      throw new Error('Authentication required. Please sign in to use chat.');
    }

    // Use the search/chat endpoint with the video context
    const response = await fetch(`${API_BASE_URL}/api/search/chat`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${accessToken}`
      },
      body: JSON.stringify({
        query: data.query,
        history: data.history || []
      })
    });

    if (!response.ok) {
      const errorData = await response.json().catch(() => ({}));
      throw new Error(errorData.detail || `Chat failed: ${response.status}`);
    }

    const result = await response.json();

    return {
      success: true,
      answer: result.answer,
      citations: result.citations || []
    };

  } catch (error) {
    console.error('Chat with video error:', error);
    throw error;
  }
}

// ============================================================================
// Generate video summary using TubeVibe Library (Unified Transcripts API)
// ============================================================================
async function handleGenerateVideoSummary(data) {
  try {
    // Step 1: Check if video is already saved to library
    let transcriptId = null;
    const cached = await chrome.storage.local.get([`saved_video_${data.video_id}`]);

    if (cached[`saved_video_${data.video_id}`]) {
      transcriptId = cached[`saved_video_${data.video_id}`].id;
    } else {
      // Step 2: Save video to library first
      const saveResult = await handleSaveToLibrary(data);
      if (!saveResult.success) {
        throw new Error(saveResult.error || 'Failed to save transcript to library');
      }
      transcriptId = saveResult.video.id;
    }

    // Step 3: Get access token for summary endpoint
    const accessToken = await getValidAccessToken();
    if (!accessToken) {
      throw new Error('Authentication required');
    }

    // Step 4: Call the unified transcripts summary endpoint
    const response = await fetch(`${API_BASE_URL}/api/transcripts/${transcriptId}/summary`, {
      method: 'GET',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${accessToken}`
      }
    });

    if (!response.ok) {
      const errorData = await response.json().catch(() => ({}));
      throw new Error(errorData.detail || `Summary generation failed: ${response.status}`);
    }

    const summary = await response.json();

    // Format the summary for display
    const formattedHtml = formatSummaryAsHtml(summary);

    return {
      success: true,
      summary: formattedHtml,
      rawSummary: summary
    };

  } catch (error) {
    console.error('Generate video summary error:', error);
    throw error;
  }
}

// ============================================================================
// Email video summary using TubeVibe Library (Unified Transcripts API)
// ============================================================================
async function handleEmailVideoSummary(data) {
  try {
    // Step 1: Check if video is already saved to library
    let transcriptId = null;
    const cached = await chrome.storage.local.get([`saved_video_${data.video_id}`]);

    if (cached[`saved_video_${data.video_id}`]) {
      transcriptId = cached[`saved_video_${data.video_id}`].id;
    } else {
      // Transcript not in library - save it first
      const saveResult = await handleSaveToLibrary(data);
      if (!saveResult.success) {
        throw new Error(saveResult.error || 'Failed to save transcript to library before emailing');
      }
      transcriptId = saveResult.video.id;
    }

    // Step 2: Get access token for email endpoint
    const accessToken = await getValidAccessToken();
    if (!accessToken) {
      throw new Error('Authentication required');
    }

    // Step 3: Call the unified transcripts email endpoint
    const response = await fetch(`${API_BASE_URL}/api/transcripts/${transcriptId}/email-summary`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${accessToken}`
      },
      body: JSON.stringify({
        recipient_email: data.recipient_email,
        summary_html: data.summary_html,
        title: data.video_title,
        metadata: {
          channel_name: data.channel_name,
          duration_seconds: data.duration_seconds,
          transcript_length: data.transcript_length
        }
      })
    });

    if (!response.ok) {
      const errorData = await response.json().catch(() => ({}));
      throw new Error(errorData.detail || `Email sending failed: ${response.status}`);
    }

    const result = await response.json();

    return {
      success: true,
      message: result.message || 'Email sent successfully',
      recipient: data.recipient_email
    };

  } catch (error) {
    console.error('Email video summary error:', error);
    throw error;
  }
}

// Format the structured summary response into HTML for display
function formatSummaryAsHtml(summary) {
  let html = '';

  // Executive Summary
  if (summary.executive_summary) {
    html += `<div class="summary-executive">
      <h3>Overview</h3>
      <p>${escapeHtml(summary.executive_summary)}</p>
    </div>`;
  }

  // Key Takeaways
  if (summary.key_takeaways && summary.key_takeaways.length > 0) {
    html += `<div class="summary-takeaways">
      <h3>Key Takeaways</h3>
      <ul>`;
    for (const takeaway of summary.key_takeaways) {
      html += `<li>${escapeHtml(takeaway)}</li>`;
    }
    html += `</ul></div>`;
  }

  // Target Audience
  if (summary.target_audience) {
    html += `<div class="summary-audience">
      <p><strong>Who this is for:</strong> ${escapeHtml(summary.target_audience)}</p>
    </div>`;
  }

  // Sections
  if (summary.sections && summary.sections.length > 0) {
    html += `<div class="summary-sections">
      <h3>Detailed Breakdown</h3>`;

    for (const section of summary.sections) {
      html += `<div class="summary-section">
        <h4>${escapeHtml(section.title)} <span class="timestamp">(${escapeHtml(section.timestamp)})</span></h4>
        <p>${escapeHtml(section.summary)}</p>`;

      if (section.key_points && section.key_points.length > 0) {
        html += `<ul class="key-points">`;
        for (const point of section.key_points) {
          html += `<li>${escapeHtml(point)}</li>`;
        }
        html += `</ul>`;
      }

      html += `</div>`;
    }

    html += `</div>`;
  }

  return html;
}

// Helper: Escape HTML entities
function escapeHtml(text) {
  if (!text) return '';
  return text
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}