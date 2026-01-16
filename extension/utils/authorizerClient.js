/**
 * Authorizer Client for TubeVibe Chrome Extension
 *
 * Wraps Authorizer's GraphQL API and provides authentication methods
 * for email/password login, signup, magic link, and Google OAuth.
 *
 * @version 1.0.0
 * @author TubeVibe Team
 */

class AuthorizerClient {
    // Configuration
    static AUTHORIZER_URL = 'https://authorizer-production-179c.up.railway.app';
    static API_BASE_URL = 'https://simply-backend-production.up.railway.app';
    static LOG_PREFIX = '[AuthorizerClient]';

    /**
     * Enhanced logging for authentication operations
     */
    static log(operation, data = {}, success = true, error = null) {
        const logData = {
            timestamp: new Date().toISOString(),
            operation,
            success,
            error: error?.message || null
        };

        if (success) {
            console.log(`${this.LOG_PREFIX} ${operation}:`, logData);
        } else {
            console.error(`${this.LOG_PREFIX} ${operation} FAILED:`, logData);
        }

        return logData;
    }

    /**
     * Make a GraphQL request to Authorizer
     * @param {string} query - GraphQL query or mutation
     * @param {object} variables - Query variables
     * @returns {Promise<object>} - GraphQL response data
     */
    static async graphqlRequest(query, variables = {}) {
        this.log('GRAPHQL_REQUEST_START', { query: query.substring(0, 100) });

        try {
            const response = await fetch(`${this.AUTHORIZER_URL}/graphql`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                    query,
                    variables
                })
            });

            if (!response.ok) {
                const errorText = await response.text();
                throw new Error(`HTTP ${response.status}: ${errorText}`);
            }

            const result = await response.json();

            // Check for GraphQL errors
            if (result.errors && result.errors.length > 0) {
                const errorMessage = result.errors.map(e => e.message).join(', ');
                throw new Error(errorMessage);
            }

            this.log('GRAPHQL_REQUEST_SUCCESS');
            return result.data;

        } catch (error) {
            this.log('GRAPHQL_REQUEST_FAILED', {}, false, error);
            throw error;
        }
    }

    /**
     * Login with email and password
     * @param {string} email - User email
     * @param {string} password - User password
     * @returns {Promise<object>} - Authentication response with tokens and user data
     */
    static async login(email, password) {
        this.log('LOGIN_START', { email });

        try {
            const query = `
                mutation Login($data: LoginInput!) {
                    login(params: $data) {
                        access_token
                        refresh_token
                        expires_in
                        user {
                            id
                            email
                            given_name
                            family_name
                            email_verified
                        }
                    }
                }
            `;

            const variables = {
                data: {
                    email,
                    password
                }
            };

            const data = await this.graphqlRequest(query, variables);
            const authResponse = data.login;

            // Exchange Authorizer token for TubeVibe user data
            const tubeVibeData = await this.exchangeForTubeVibeToken(authResponse);

            this.log('LOGIN_SUCCESS', { email });

            return {
                success: true,
                access_token: authResponse.access_token,
                refresh_token: authResponse.refresh_token,
                expires_in: authResponse.expires_in,
                authorizer_user: authResponse.user,
                tubevibe_user: tubeVibeData.user,
                user: tubeVibeData.user || authResponse.user
            };

        } catch (error) {
            this.log('LOGIN_FAILED', { email }, false, error);

            // Provide user-friendly error messages
            let userMessage = error.message;
            if (error.message.includes('invalid credentials') || error.message.includes('Invalid credentials')) {
                userMessage = 'Invalid email or password. Please try again.';
            } else if (error.message.includes('not found')) {
                userMessage = 'No account found with this email. Please sign up first.';
            } else if (error.message.includes('email_verified') || error.message.includes('not verified')) {
                userMessage = 'Please verify your email before logging in.';
            }

            return {
                success: false,
                error: userMessage
            };
        }
    }

    /**
     * Sign up a new user
     * @param {string} email - User email
     * @param {string} password - User password
     * @param {string} firstName - User first name (optional)
     * @param {string} lastName - User last name (optional)
     * @returns {Promise<object>} - Signup response
     */
    static async signup(email, password, firstName = '', lastName = '') {
        this.log('SIGNUP_START', { email });

        try {
            const query = `
                mutation Signup($data: SignUpInput!) {
                    signup(params: $data) {
                        message
                        user {
                            id
                            email
                        }
                    }
                }
            `;

            const variables = {
                data: {
                    email,
                    password,
                    confirm_password: password,
                    given_name: firstName,
                    family_name: lastName
                }
            };

            const data = await this.graphqlRequest(query, variables);
            const signupResponse = data.signup;

            this.log('SIGNUP_SUCCESS', { email });

            return {
                success: true,
                message: signupResponse.message || 'Account created successfully!',
                user: signupResponse.user,
                requiresVerification: true
            };

        } catch (error) {
            this.log('SIGNUP_FAILED', { email }, false, error);

            // Provide user-friendly error messages
            let userMessage = error.message;
            if (error.message.includes('already exists') || error.message.includes('duplicate')) {
                userMessage = 'An account with this email already exists. Please login instead.';
            } else if (error.message.includes('password')) {
                userMessage = 'Password does not meet requirements. Please use a stronger password.';
            } else if (error.message.includes('email')) {
                userMessage = 'Please enter a valid email address.';
            }

            return {
                success: false,
                error: userMessage
            };
        }
    }

    /**
     * Request a magic link for passwordless login
     * @param {string} email - User email
     * @returns {Promise<object>} - Magic link response
     */
    static async requestMagicLink(email) {
        this.log('MAGIC_LINK_START', { email });

        try {
            const query = `
                mutation MagicLink($data: MagicLinkLoginInput!) {
                    magic_link_login(params: $data) {
                        message
                    }
                }
            `;

            const variables = {
                data: {
                    email
                }
            };

            const data = await this.graphqlRequest(query, variables);
            const magicLinkResponse = data.magic_link_login;

            this.log('MAGIC_LINK_SUCCESS', { email });

            return {
                success: true,
                message: magicLinkResponse.message || 'Magic link sent! Check your email.'
            };

        } catch (error) {
            this.log('MAGIC_LINK_FAILED', { email }, false, error);

            let userMessage = error.message;
            if (error.message.includes('not found')) {
                userMessage = 'No account found with this email. Please sign up first.';
            }

            return {
                success: false,
                error: userMessage
            };
        }
    }

    /**
     * Initiate Google OAuth authentication
     * Uses direct Google OAuth, then syncs with TubeVibe backend
     * (Authorizer's OAuth redirect doesn't work with Chrome extensions due to cookie limitations)
     * @returns {Promise<object>} - Authentication response with tokens and user data
     */
    static async googleOAuth() {
        this.log('GOOGLE_OAUTH_START');

        try {
            // Step 1: Get Google OAuth token directly using Chrome identity API
            // Using the same Google Client ID configured in Authorizer
            const clientId = '1049678014825-r2sgcffbksmm2jb8ikkdvdpfv23j8v7a.apps.googleusercontent.com';
            const redirectUri = chrome.identity.getRedirectURL();

            this.log('GOOGLE_OAUTH_REDIRECT_URI', { redirectUri });

            // Build Google OAuth URL - request both access_token and id_token
            const authUrl = new URL('https://accounts.google.com/o/oauth2/v2/auth');
            authUrl.searchParams.set('client_id', clientId);
            authUrl.searchParams.set('response_type', 'token');
            authUrl.searchParams.set('redirect_uri', redirectUri);
            authUrl.searchParams.set('scope', 'openid email profile');

            this.log('GOOGLE_OAUTH_AUTH_URL', { authUrl: authUrl.toString() });

            // Launch the OAuth flow
            const responseUrl = await chrome.identity.launchWebAuthFlow({
                url: authUrl.toString(),
                interactive: true
            });

            console.log('[AuthorizerClient] Google OAuth response URL received');

            // Parse the response URL to extract tokens
            const url = new URL(responseUrl);
            const params = new URLSearchParams(url.hash.substring(1));

            const accessToken = params.get('access_token');
            const expiresIn = parseInt(params.get('expires_in') || '3600');

            if (!accessToken) {
                const error = params.get('error') || params.get('error_description');
                if (error) {
                    throw new Error(error);
                }
                throw new Error('Failed to get access token from Google OAuth');
            }

            this.log('GOOGLE_OAUTH_TOKEN_RECEIVED', { hasAccessToken: !!accessToken });

            // Step 2: Get user info from Google
            const userInfoResponse = await fetch('https://www.googleapis.com/oauth2/v2/userinfo', {
                headers: {
                    'Authorization': `Bearer ${accessToken}`
                }
            });

            if (!userInfoResponse.ok) {
                throw new Error('Failed to get user info from Google');
            }

            const googleUser = await userInfoResponse.json();
            this.log('GOOGLE_USER_INFO', { email: googleUser.email });

            // Step 3: Send to TubeVibe backend to create/get user
            const backendResponse = await fetch(`${this.API_BASE_URL}/api/auth/google/extension`, {
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
            this.log('GOOGLE_OAUTH_SUCCESS', { email: backendData.user?.email });

            return {
                success: true,
                access_token: backendData.access_token || accessToken,
                refresh_token: null,
                expires_in: backendData.expires_in || expiresIn,
                user: backendData.user || googleUser,
                provider: 'google'
            };

        } catch (error) {
            this.log('GOOGLE_OAUTH_FAILED', {}, false, error);

            // Provide user-friendly error messages
            let userMessage = error.message;
            if (error.message.includes('popup_closed_by_user') ||
                error.message.includes('canceled') ||
                error.message.includes('cancelled')) {
                userMessage = 'Google sign-in was cancelled. Please try again.';
            } else if (error.message.includes('authorization') ||
                       error.message.includes('Authorization page could not be loaded')) {
                userMessage = 'Google authorization failed. Please check your internet connection and try again.';
            } else if (error.message.includes('network') || error.message.includes('fetch')) {
                userMessage = 'Network error. Please check your connection and try again.';
            }

            return {
                success: false,
                error: userMessage
            };
        }
    }

    /**
     * Get user profile from Authorizer using access token
     * @param {string} accessToken - Authorizer access token
     * @returns {Promise<object>} - User profile data
     */
    static async getAuthorizerUserProfile(accessToken) {
        this.log('GET_USER_PROFILE_START');

        try {
            const query = `
                query {
                    profile {
                        id
                        email
                        given_name
                        family_name
                        email_verified
                        picture
                    }
                }
            `;

            const response = await fetch(`${this.AUTHORIZER_URL}/graphql`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'Authorization': `Bearer ${accessToken}`
                },
                body: JSON.stringify({ query })
            });

            if (!response.ok) {
                throw new Error(`Failed to get user profile: ${response.status}`);
            }

            const result = await response.json();

            if (result.errors && result.errors.length > 0) {
                throw new Error(result.errors[0].message);
            }

            this.log('GET_USER_PROFILE_SUCCESS');
            return result.data.profile;

        } catch (error) {
            this.log('GET_USER_PROFILE_FAILED', {}, false, error);
            // Return minimal profile if we can't fetch from Authorizer
            return null;
        }
    }

    /**
     * Exchange Authorizer authentication response for TubeVibe user data
     * Calls TubeVibe backend to create/update user and get TubeVibe-specific data
     * @param {object} authorizerResponse - Response from Authorizer authentication
     * @returns {Promise<object>} - TubeVibe user data
     */
    static async exchangeForTubeVibeToken(authorizerResponse) {
        this.log('EXCHANGE_TOKEN_START');

        try {
            const response = await fetch(`${this.API_BASE_URL}/api/auth/authorizer/token`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'Authorization': `Bearer ${authorizerResponse.access_token}`
                },
                body: JSON.stringify({
                    access_token: authorizerResponse.access_token,
                    refresh_token: authorizerResponse.refresh_token,
                    expires_in: authorizerResponse.expires_in,
                    user: authorizerResponse.user
                })
            });

            if (!response.ok) {
                const errorData = await response.json().catch(() => ({}));
                throw new Error(errorData.detail || `TubeVibe token exchange failed: ${response.status}`);
            }

            const data = await response.json();
            this.log('EXCHANGE_TOKEN_SUCCESS', { user_email: data.user?.email });

            return {
                success: true,
                user: data.user,
                access_token: data.access_token || authorizerResponse.access_token,
                refresh_token: data.refresh_token || authorizerResponse.refresh_token
            };

        } catch (error) {
            this.log('EXCHANGE_TOKEN_FAILED', {}, false, error);

            // Return Authorizer data if TubeVibe exchange fails
            // The user can still authenticate, we'll try again later
            console.warn(`${this.LOG_PREFIX} Token exchange failed, using Authorizer data directly`);

            return {
                success: false,
                error: error.message,
                user: authorizerResponse.user
            };
        }
    }

    /**
     * Refresh the access token using a refresh token
     * @param {string} refreshToken - The refresh token
     * @returns {Promise<object>} - New tokens
     */
    static async refreshToken(refreshToken) {
        this.log('REFRESH_TOKEN_START');

        try {
            const query = `
                mutation {
                    session(params: {}) {
                        access_token
                        refresh_token
                        expires_in
                        user {
                            id
                            email
                            given_name
                            family_name
                            email_verified
                        }
                    }
                }
            `;

            const response = await fetch(`${this.AUTHORIZER_URL}/graphql`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'Cookie': `refresh_token=${refreshToken}`
                },
                body: JSON.stringify({ query }),
                credentials: 'include'
            });

            if (!response.ok) {
                throw new Error(`Token refresh failed: ${response.status}`);
            }

            const result = await response.json();

            if (result.errors && result.errors.length > 0) {
                throw new Error(result.errors[0].message);
            }

            const sessionData = result.data.session;

            // Also exchange with TubeVibe backend
            const tubeVibeData = await this.exchangeForTubeVibeToken(sessionData);

            this.log('REFRESH_TOKEN_SUCCESS');

            return {
                success: true,
                access_token: sessionData.access_token,
                refresh_token: sessionData.refresh_token,
                expires_in: sessionData.expires_in,
                user: tubeVibeData.user || sessionData.user
            };

        } catch (error) {
            this.log('REFRESH_TOKEN_FAILED', {}, false, error);

            return {
                success: false,
                error: error.message
            };
        }
    }

    /**
     * Logout the user from Authorizer
     * @returns {Promise<object>} - Logout response
     */
    static async logout() {
        this.log('LOGOUT_START');

        try {
            const query = `
                mutation Logout {
                    logout {
                        message
                    }
                }
            `;

            const data = await this.graphqlRequest(query);

            this.log('LOGOUT_SUCCESS');

            return {
                success: true,
                message: data.logout?.message || 'Successfully logged out'
            };

        } catch (error) {
            this.log('LOGOUT_FAILED', {}, false, error);

            // Even if Authorizer logout fails, we should still clear local state
            return {
                success: true,
                message: 'Logged out locally',
                warning: error.message
            };
        }
    }

    /**
     * Verify email with token (for magic link or email verification)
     * @param {string} token - Verification token from email
     * @returns {Promise<object>} - Verification response with tokens
     */
    static async verifyEmail(token) {
        this.log('VERIFY_EMAIL_START');

        try {
            const query = `
                mutation VerifyEmail($data: VerifyEmailInput!) {
                    verify_email(params: $data) {
                        access_token
                        refresh_token
                        expires_in
                        user {
                            id
                            email
                            given_name
                            family_name
                            email_verified
                        }
                    }
                }
            `;

            const variables = {
                data: {
                    token
                }
            };

            const data = await this.graphqlRequest(query, variables);
            const verifyResponse = data.verify_email;

            // Exchange for TubeVibe token
            const tubeVibeData = await this.exchangeForTubeVibeToken(verifyResponse);

            this.log('VERIFY_EMAIL_SUCCESS');

            return {
                success: true,
                access_token: verifyResponse.access_token,
                refresh_token: verifyResponse.refresh_token,
                expires_in: verifyResponse.expires_in,
                user: tubeVibeData.user || verifyResponse.user
            };

        } catch (error) {
            this.log('VERIFY_EMAIL_FAILED', {}, false, error);

            let userMessage = error.message;
            if (error.message.includes('expired')) {
                userMessage = 'Verification link has expired. Please request a new one.';
            } else if (error.message.includes('invalid')) {
                userMessage = 'Invalid verification link. Please request a new one.';
            }

            return {
                success: false,
                error: userMessage
            };
        }
    }

    /**
     * Request password reset email
     * Routes through TubeVibe backend which sends via Postmark
     * (bypasses Authorizer's broken SMTP on Railway)
     * @param {string} email - User email
     * @returns {Promise<object>} - Password reset response
     */
    static async forgotPassword(email) {
        this.log('FORGOT_PASSWORD_START', { email });

        try {
            // Call TubeVibe backend instead of Authorizer
            // Backend handles password reset and sends email via Postmark
            const response = await fetch(`${this.API_BASE_URL}/api/auth/forgot-password`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({ email })
            });

            const data = await response.json();

            if (data.success) {
                this.log('FORGOT_PASSWORD_SUCCESS', { email });
                return {
                    success: true,
                    message: data.message || 'New credentials have been sent to your email.'
                };
            } else {
                throw new Error(data.error || 'Failed to reset password');
            }

        } catch (error) {
            this.log('FORGOT_PASSWORD_FAILED', { email }, false, error);

            return {
                success: false,
                error: error.message
            };
        }
    }

    /**
     * Reset password with token
     * @param {string} token - Reset token from email
     * @param {string} newPassword - New password
     * @returns {Promise<object>} - Reset response
     */
    static async resetPassword(token, newPassword) {
        this.log('RESET_PASSWORD_START');

        try {
            const query = `
                mutation ResetPassword($data: ResetPasswordInput!) {
                    reset_password(params: $data) {
                        message
                    }
                }
            `;

            const variables = {
                data: {
                    token,
                    password: newPassword,
                    confirm_password: newPassword
                }
            };

            const data = await this.graphqlRequest(query, variables);

            this.log('RESET_PASSWORD_SUCCESS');

            return {
                success: true,
                message: data.reset_password?.message || 'Password reset successfully! You can now login.'
            };

        } catch (error) {
            this.log('RESET_PASSWORD_FAILED', {}, false, error);

            let userMessage = error.message;
            if (error.message.includes('expired')) {
                userMessage = 'Reset link has expired. Please request a new one.';
            } else if (error.message.includes('password')) {
                userMessage = 'Password does not meet requirements. Please use a stronger password.';
            }

            return {
                success: false,
                error: userMessage
            };
        }
    }
}

// Export for use in other extension files
if (typeof module !== 'undefined' && module.exports) {
    module.exports = AuthorizerClient;
} else if (typeof window !== 'undefined') {
    window.AuthorizerClient = AuthorizerClient;
}
