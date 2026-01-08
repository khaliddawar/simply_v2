// TubeVibe Embedded Popup - Embed the complete popup UI into YouTube page
// Security loading disabled to prevent injection issues
console.log('🎬 TubeVibe embedded-popup.js loaded at', new Date().toISOString());
// ============================================================================
// TEST MODE - Set to true to bypass authentication for testing
// ============================================================================
const TEST_MODE = false;
// -------------------------------------------------------------------------
// Premium upgrade URL (can be overridden at runtime by setting
//   window.TUBEVIBE_PREMIUM_URL from a <script> tag injected by build script
//   or by reading from chrome.storage/local if you prefer).
// -------------------------------------------------------------------------
const PREMIUM_UPGRADE_URL = (typeof window !== 'undefined' && window.TUBEVIBE_PREMIUM_URL)
  || 'https://tubevibe.app/pricing';
class EmbeddedPopupUI {
    constructor() {
        this.embeddedContainer = null;
        this.popupFrame = null;
        this.retryCount = 0;
        this.maxRetries = 20;
        this.lastExtractedTranscript = null; // Store transcript for summary generation
        // Create a safe HTML setter
        this.safeSetHTML = this.createSafeHTMLSetter();
        
        // Load enhanced TokenManager and PaymentManager
        this.initializeAsync();
        // Listen for storage changes to update authentication UI
        chrome.storage.onChanged.addListener((changes, namespace) => {
            if (namespace === 'local' && (changes.access_token || changes.user_info)) {
                this.updateEmbeddedAuthUI();
            }
        });
    }
    
    // Async initialization to properly load managers before proceeding
    async initializeAsync() {
        try {
            console.log('🔄 [EmbeddedPopup] Starting async initialization...');
            
            // Load managers with individual error handling
            const loadResults = await Promise.allSettled([
                this.loadTokenManager(),
                this.loadPaymentManager()
            ]);
            
            // Log results
            loadResults.forEach((result, index) => {
                const managerName = index === 0 ? 'TokenManager' : 'PaymentManager';
                if (result.status === 'fulfilled') {
                    console.log(`✅ [EmbeddedPopup] ${managerName} loaded successfully`);
                } else {
                    console.warn(`⚠️ [EmbeddedPopup] ${managerName} failed to load:`, result.reason);
                }
            });
            
            console.log('🎬 [EmbeddedPopup] Manager loading complete, starting initialization...');
            
            // Now initialize the popup
            await this.initialize();
            
            // Start proactive token refresh mechanism
            this.startTokenRefreshInterval();
            
        } catch (error) {
            console.error('❌ [EmbeddedPopup] Error in async initialization:', error);
            // Fallback to normal initialization
            try {
                await this.initialize();
                this.startTokenRefreshInterval();
            } catch (fallbackError) {
                console.error('❌ [EmbeddedPopup] Fallback initialization also failed:', fallbackError);
            }
        }
    }
    
    // Create a safe HTML setter that handles TrustedHTML requirements
    createSafeHTMLSetter() {
        if (window.trustedTypes && window.trustedTypes.createPolicy) {
            try {
                const policy = window.trustedTypes.createPolicy('tubevibe-embedded', {
                    createHTML: (html) => html
                });
                return (element, html) => {
                    element.innerHTML = policy.createHTML(html);
                };
            } catch (e) {
                console.warn('Failed to create TrustedHTML policy:', e);
            }
        }
        // Fallback for browsers without TrustedHTML
        return (element, html) => {
            element.innerHTML = html;
        };
    }
    
    // Load enhanced TokenManager utility
    loadTokenManager() {
        return new Promise((resolve, reject) => {
            try {
                // Create script element to load TokenManager
                const script = document.createElement('script');
                script.src = chrome.runtime.getURL('utils/tokenManager.js');
                script.onload = () => {
                    console.log('✅ [EmbeddedPopup] TokenManager loaded successfully');
                    this.tokenManagerLoaded = true;
                    resolve();
                };
                script.onerror = (error) => {
                    console.error('❌ [EmbeddedPopup] Failed to load TokenManager:', error);
                    this.tokenManagerLoaded = false;
                    reject(error);
                };
                document.head.appendChild(script);
            } catch (error) {
                console.error('❌ [EmbeddedPopup] Error loading TokenManager:', error);
                this.tokenManagerLoaded = false;
                reject(error);
            }
        });
    }
    
    // Load PaymentManager utility for subscription handling
    loadPaymentManager() {
        return new Promise((resolve, reject) => {
            try {
                const script = document.createElement('script');
                script.src = chrome.runtime.getURL('utils/paymentManager.js');
                script.onload = () => {
                    console.log('✅ [EmbeddedPopup] PaymentManager loaded successfully');
                    this.paymentManagerLoaded = true;
                    resolve();
                };
                script.onerror = (error) => {
                    console.error('❌ [EmbeddedPopup] Failed to load PaymentManager:', error);
                    this.paymentManagerLoaded = false;
                    reject(error);
                };
                document.head.appendChild(script);
            } catch (error) {
                console.error('❌ [EmbeddedPopup] Error loading PaymentManager:', error);
                this.paymentManagerLoaded = false;
                reject(error);
            }
        });
    }
    
    async initialize() {
        console.log('🎬 Starting EmbeddedPopupUI initialization...');
        try {
            // Initialize video saved state
            this.isVideoSaved = false;
            this.savedVideoInfo = null;

            // Wait for YouTube to be ready
            console.log('🎬 Waiting for YouTube to be ready...');
            await this.waitForYouTube();

            // Create and embed the popup
            console.log('🎬 Creating embedded popup...');
            await this.createEmbeddedPopup();

            // Check and update authentication status
            console.log('🎬 Checking authentication status...');
            const authState = await this.checkAuthenticationStatus();

            // 🔧 ENHANCED: Force update UI with fresh data after initialization
            console.log('🎬 Forcing UI refresh with latest user data...');
            await this.updateEmbeddedAuthUI();

            // Check if current video is already saved (only if authenticated)
            if (authState?.isAuthenticated) {
                console.log('🎬 Checking if video is already saved...');
                await this.checkIfVideoSaved();
            }

            // Set up listener for YouTube SPA navigation (video changes)
            this.setupNavigationListener();

            console.log('🎬 Initialization complete!');
        } catch (error) {
            console.error('❌ Error initializing embedded popup:', error);
        }
    }

    // Listen for YouTube SPA navigation to detect video changes
    setupNavigationListener() {
        // Track the current video ID
        this.lastVideoId = this.getYouTubeVideoId();

        // YouTube uses History API for SPA navigation
        // Listen for yt-navigate-finish event (YouTube's custom event)
        document.addEventListener('yt-navigate-finish', async () => {
            const newVideoId = this.getYouTubeVideoId();
            if (newVideoId && newVideoId !== this.lastVideoId) {
                console.log('🔄 YouTube navigation detected, new video:', newVideoId);
                this.lastVideoId = newVideoId;

                // Reset saved state for new video
                this.isVideoSaved = false;
                this.savedVideoInfo = null;
                this.currentVideoSaved = false;

                // Re-check if the new video is saved
                const authState = await this.checkAuthenticationStatus();
                if (authState?.isAuthenticated) {
                    await this.checkIfVideoSaved();
                }

                // Reset transcript tab to default state if not saved
                if (!this.isVideoSaved) {
                    this.resetTranscriptTab();
                }
            }
        });

        // Fallback: Also listen for popstate (browser back/forward)
        window.addEventListener('popstate', async () => {
            setTimeout(async () => {
                const newVideoId = this.getYouTubeVideoId();
                if (newVideoId && newVideoId !== this.lastVideoId) {
                    console.log('🔄 Popstate navigation detected, new video:', newVideoId);
                    this.lastVideoId = newVideoId;

                    // Reset and re-check
                    this.isVideoSaved = false;
                    this.savedVideoInfo = null;
                    this.currentVideoSaved = false;

                    const authState = await this.checkAuthenticationStatus();
                    if (authState?.isAuthenticated) {
                        await this.checkIfVideoSaved();
                    }

                    if (!this.isVideoSaved) {
                        this.resetTranscriptTab();
                    }
                }
            }, 500); // Small delay for URL to update
        });
    }

    // Reset transcript tab to default extract state
    resetTranscriptTab() {
        const transcriptContent = this.embeddedContainer?.querySelector('#transcript-content');
        if (!transcriptContent) return;

        console.log('🔄 Resetting transcript tab to default state');

        this.safeSetHTML(transcriptContent, `
            <div class="simply-empty-state" style="padding: 24px;">
                <div class="simply-empty-state__icon" style="margin-bottom: 16px;">
                    <svg width="48" height="48" viewBox="0 0 24 24" fill="#ff0000">
                        <path d="M14,2H6A2,2 0 0,0 4,4V20A2,2 0 0,0 6,22H18A2,2 0 0,0 20,20V8L14,2M18,20H6V4H13V9H18V20Z"/>
                    </svg>
                </div>
                <h3 class="simply-empty-state__title" style="font-size: 16px; font-weight: 600; color: #333; margin-bottom: 8px;">Extract Transcript</h3>
                <p class="simply-empty-state__description" style="color: #666; font-size: 13px; margin-bottom: 16px;">Click to extract the transcript from this video</p>
                <button id="extract-transcript-btn" class="simply-btn simply-btn--primary">
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor" style="margin-right: 6px;">
                        <path d="M14,2H6A2,2 0 0,0 4,4V20A2,2 0 0,0 6,22H18A2,2 0 0,0 20,20V8L14,2M18,20H6V4H13V9H18V20Z"/>
                    </svg>
                    Extract Transcript
                </button>
            </div>
        `);

        // Re-bind the extract button
        const extractBtn = transcriptContent.querySelector('#extract-transcript-btn');
        if (extractBtn) {
            extractBtn.addEventListener('click', () => {
                this.handleExtractTranscript();
            });
        }
    }

    // Check if the current YouTube video is already saved in the user's library
    async checkIfVideoSaved() {
        try {
            const videoId = this.getYouTubeVideoId();
            if (!videoId) {
                console.log('⚠️ Could not get YouTube video ID');
                return;
            }

            console.log('🔍 Checking if video is saved:', videoId);

            const response = await chrome.runtime.sendMessage({
                type: 'CHECK_VIDEO_SAVED',
                data: { video_id: videoId }
            });

            if (response?.success && response?.isSaved) {
                console.log('✅ Video is already saved:', response.video?.title);
                this.isVideoSaved = true;
                this.savedVideoInfo = response.video;

                // Update the UI to reflect saved state
                this.updateTranscriptTabForSavedVideo();
                this.updateChatTabForSavedVideo();
            } else {
                console.log('ℹ️ Video is not saved yet');
                this.isVideoSaved = false;
                this.savedVideoInfo = null;
            }
        } catch (error) {
            console.error('❌ Error checking if video is saved:', error);
        }
    }

    // Get YouTube video ID from the current URL
    getYouTubeVideoId() {
        const url = new URL(window.location.href);
        return url.searchParams.get('v');
    }

    // Update transcript tab UI when video is already saved
    updateTranscriptTabForSavedVideo() {
        if (!this.isVideoSaved || !this.savedVideoInfo) return;

        const transcriptContent = this.embeddedContainer?.querySelector('#transcript-content');
        if (!transcriptContent) return;

        console.log('🔄 Updating transcript tab for saved video');

        // Show saved video state with option to extract transcript again
        this.safeSetHTML(transcriptContent, `
            <div style="padding: 16px;">
                <div style="display: flex; align-items: center; gap: 8px; margin-bottom: 16px; padding: 12px; background: linear-gradient(135deg, #e8f5e9 0%, #f1f8e9 100%); border-radius: 8px; border: 1px solid #c8e6c9;">
                    <svg width="24" height="24" viewBox="0 0 24 24" fill="#4caf50">
                        <path d="M9 16.17L4.83 12l-1.42 1.41L9 19 21 7l-1.41-1.41z"/>
                    </svg>
                    <div>
                        <div style="font-weight: 600; color: #2e7d32;">Video Already Saved</div>
                        <div style="font-size: 12px; color: #558b2f;">You can use Chat to ask questions about this video</div>
                    </div>
                </div>

                <div style="background: #f5f5f5; padding: 12px; border-radius: 8px; margin-bottom: 16px;">
                    <div style="font-size: 13px; color: #666; margin-bottom: 4px;">Saved as:</div>
                    <div style="font-size: 14px; font-weight: 500; color: #333;">${this.savedVideoInfo.title || 'Untitled Video'}</div>
                    ${this.savedVideoInfo.created_at ? `<div style="font-size: 11px; color: #999; margin-top: 4px;">Saved on ${new Date(this.savedVideoInfo.created_at).toLocaleDateString()}</div>` : ''}
                </div>

                <button id="extract-transcript-anyway-btn" class="simply-btn simply-btn--secondary simply-w-full" style="margin-bottom: 8px;">
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor" style="margin-right: 6px;">
                        <path d="M14,2H6A2,2 0 0,0 4,4V20A2,2 0 0,0 6,22H18A2,2 0 0,0 20,20V8L14,2M18,20H6V4H13V9H18V20Z"/>
                    </svg>
                    Extract Transcript Again
                </button>

                <div style="text-align: center; margin-top: 12px;">
                    <button id="go-to-chat-btn" class="simply-btn simply-btn--primary">
                        <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor" style="margin-right: 6px;">
                            <path d="M20,2H4A2,2 0 0,0 2,4V22L6,18H20A2,2 0 0,0 22,16V4A2,2 0 0,0 20,2M6,9H18V11H6M14,14H6V12H14M18,8H6V6H18"/>
                        </svg>
                        Chat with Video
                    </button>
                </div>
            </div>
        `);

        // Bind event listeners
        const extractBtn = this.embeddedContainer?.querySelector('#extract-transcript-anyway-btn');
        if (extractBtn) {
            extractBtn.addEventListener('click', () => {
                this.handleExtractTranscript();
            });
        }

        const chatBtn = this.embeddedContainer?.querySelector('#go-to-chat-btn');
        if (chatBtn) {
            chatBtn.addEventListener('click', () => {
                this.switchTab('chat');
            });
        }
    }

    // Update chat tab UI when video is already saved
    updateChatTabForSavedVideo() {
        if (!this.isVideoSaved) return;

        // Set video saved flags for chat functionality
        this.currentVideoSaved = true;
        this.currentVideoId = this.getYouTubeVideoId();

        // Use the existing showChatInterface method to toggle UI
        this.showChatInterface();

        console.log('✅ Chat tab updated for saved video');
    }
    async waitForYouTube() {
        return new Promise((resolve) => {
            const checkYouTube = () => {
                // Check if we're on a YouTube watch page
                if (!window.location.href.includes('youtube.com/watch')) {
                    resolve(); // Still resolve to avoid hanging
                    return;
                }
                // Check if YouTube's secondary sidebar exists
                const sidebar = this.findSidebar();
                if (sidebar) {
                    resolve();
                } else {
                    this.retryCount++;
                    if (this.retryCount < this.maxRetries) {
                        setTimeout(checkYouTube, 500);
                    } else {
                        console.warn('⚠️ YouTube sidebar not found, creating fallback');
                        resolve();
                    }
                }
            };
            checkYouTube();
        });
    }
    findSidebar() {
        console.log('🔍 Looking for YouTube sidebar...');
        const selectors = [
            '#secondary.style-scope.ytd-watch-flexy',
            '#secondary-inner.style-scope.ytd-watch-flexy',
            '#secondary.ytd-watch-flexy',
            'ytd-watch-flexy #secondary',
            '[id="secondary"]'
        ];
        for (const selector of selectors) {
            const element = document.querySelector(selector);
            if (element) {
                console.log('✅ Found sidebar with selector:', selector);
                return element;
            }
        }
        console.log('❌ No sidebar found with any selector');
        return null;
    }
    async createEmbeddedPopup() {
        // Don't create multiple containers
        if (this.embeddedContainer) {
            return;
        }
        // Create the main container
        this.embeddedContainer = document.createElement('div');
        this.embeddedContainer.className = 'tubevibe-embedded-container';
        this.embeddedContainer.id = 'tubevibe-embedded-container';
        // Create the popup content container
        const popupContent = document.createElement('div');
        popupContent.className = 'tubevibe-embedded-popup';
        popupContent.id = 'tubevibe-embedded-popup';
        // Add CSS styles first
        this.injectStyles();
        // Load and embed the popup HTML (now loads scripts first)
        await this.loadPopupContent(popupContent);
        // Add to container
        this.embeddedContainer.appendChild(popupContent);
        // Insert into sidebar
        this.insertIntoSidebar();
    }
    async loadPopupContent(container) {
        try {
            // DON'T load popup scripts - they cause chrome.tabs.query errors
            // Just load CSS for styling
            await this.loadPopupCSS();
            // Get the popup HTML content
            const popupHtml = await this.getPopupHTML();
            // Set the HTML content
            this.safeSetHTML(container, popupHtml);
            // Bind event listeners manually (no TubeVibeUI needed)
            // Add a small delay to ensure DOM is processed
            setTimeout(() => {
                this.bindEventListeners();
            }, 100);
        } catch (error) {
            console.error('❌ Error loading popup content:', error);
            // Fallback: show basic content
            // Use SafeDOM if available for static content
            const fallbackHTML = '<div style="padding: 20px; text-align: center; color: #333;">' +
                '<h3>TubeVibe Loading...</h3>' +
                '<p>Please refresh the page if this persists.</p>' +
                '</div>';
            
            if (window.SafeDOM && window.FeatureFlags?.isEnabled('SAFE_DOM_ENABLED')) {
                window.SafeDOM.setHTML(container, fallbackHTML);
            } else {
                this.safeSetHTML(container, fallbackHTML);
            }
        }
    }
    async getPopupHTML() {
        // Return the complete popup HTML structure
        // Using string concatenation to avoid Chrome content script template literal issues
        var html = '';
        html += '<!-- Main Popup Container -->';
        html += '<div id="popup-root" class="simply-popup">';
        html += '<!-- Header -->';
        html += '<div class="simply-header">';
        html += '<div class="simply-header__main">';
        html += '<a class="simply-logo" href="#">';
        html += '<div class="simply-logo__icon">';
        html += '<svg viewBox="0 0 32 32" fill="none" xmlns="http://www.w3.org/2000/svg">';
        html += '<rect width="32" height="32" rx="6" fill="#FF0000"/>';
        html += '<path d="M10 8v16l12-8z" fill="white"/>';
        html += '<path d="M4 16c0 6.627 5.373 12 12 12s12-5.373 12-12S22.627 4 16 4 4 9.373 4 16z" fill="none" stroke="white" stroke-width="2" opacity="0.6"/>';
        html += '<path d="M10 16h12" stroke="white" stroke-width="1.5" opacity="0.4"/>';
        html += '</svg>';
        html += '</div>';
        html += '<div class="simply-logo__content">';
        html += '<span class="simply-logo__text">TubeVibe</span>';
        html += '<span class="simply-logo__tagline">AI Video Summaries</span>';
        html += '</div>';
        html += '</a>';
        html += '</div>';
        html += '</div>';
        html += '<!-- Tab Navigation -->';
        html += '<div class="simply-tabs">';
        html += '<div class="simply-tab-list">';
        html += '<button id="transcript-tab" class="simply-tab simply-tab--active" data-tab="transcript">';
        html += '<svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor" class="simply-mr-1">';
        html += '<path d="M12 14c1.66 0 2.99-1.34 2.99-3L15 5c0-1.66-1.34-3-3-3S9 3.34 9 5v6c0 1.66 1.34 3 3 3zm5.3-3c0 3-2.54 5.1-5.3 5.1S6.7 14 6.7 11H5c0 3.41 2.72 6.23 6 6.72V21h2v-3.28c3.28-.48 6-3.3 6-6.72h-1.7z"/>';
        html += '</svg>';
        html += 'Transcript';
        html += '</button>';
        html += '<button id="summary-tab" class="simply-tab" data-tab="summary">';
        html += '<svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor" class="simply-mr-1">';
        html += '<path d="M14,2H6A2,2 0 0,0 4,4V20A2,2 0 0,0 6,22H18A2,2 0 0,0 20,20V8L14,2M18,20H6V4H13V9H18V20Z"/>';
        html += '</svg>';
        html += 'Summary';
        html += '</button>';
        html += '<button id="chat-tab" class="simply-tab" data-tab="chat">';
        html += '<svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor" class="simply-mr-1">';
        html += '<path d="M20,2H4A2,2 0 0,0 2,4V22L6,18H20A2,2 0 0,0 22,16V4A2,2 0 0,0 20,2M6,9H18V11H6V9M14,14H6V12H14V14M18,8H6V6H18V8Z"/>';
        html += '</svg>';
        html += 'Chat';
        html += '</button>';
        html += '<button id="menu-tab" class="simply-tab" data-tab="menu">';
        html += '<svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor">';
        html += '<path d="M3,6H21V8H3V6M3,11H21V13H3V11M3,16H21V18H3V16Z"/>';
        html += '</svg>';
        html += '</button>';
        html += '</div>';
        html += '</div>';
        html += '<!-- Error Display -->';
        html += '<div id="error-display" class="simply-alert simply-alert--error hidden">';
        html += '<div id="error-message" class="simply-alert__message"></div>';
        html += '</div>';
        html += '<!-- Main Content -->';
        html += '<div class="simply-content">';
        html += '<!-- Transcript Tab Content -->';
        html += '<div id="transcript-content" class="simply-tab-content">';
        html += '<div id="transcript-empty" class="simply-empty-state">';
        html += '<div class="simply-empty-state__icon">';
        html += '<svg width="48" height="48" viewBox="0 0 24 24" fill="currentColor">';
        html += '<path d="M12 14c1.66 0 2.99-1.34 2.99-3L15 5c0-1.66-1.34-3-3-3S9 3.34 9 5v6c0 1.66 1.34 3 3 3zm5.3-3c0 3-2.54 5.1-5.3 5.1S6.7 14 6.7 11H5c0 3.41 2.72 6.23 6 6.72V21h2v-3.28c3.28-.48 6-3.3 6-6.72h-1.7z"/>';
        html += '</svg>';
        html += '</div>';
        html += '<h3 class="simply-empty-state__title">No Transcript Available</h3>';
        html += '<p class="simply-empty-state__description">Click "Extract Transcript" to get captions from the YouTube video</p>';
        html += '<div class="simply-flex simply-flex-col simply-gap-3 simply-mb-4">';
        html += '<button id="extract-transcript-btn" class="simply-btn simply-btn--primary simply-w-full">';
        html += '<svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor" class="simply-mr-1">';
        html += '<path d="M12 14c1.66 0 2.99-1.34 2.99-3L15 5c0-1.66-1.34-3-3-3S9 3.34 9 5v6c0 1.66 1.34 3 3 3zm5.3-3c0 3-2.54 5.1-5.3 5.1S6.7 14 6.7 11H5c0 3.41 2.72 6.23 6 6.72V21h2v-3.28c3.28-.48 6-3.3 6-6.72h-1.7z"/>';
        html += '</svg>';
        html += 'Extract Transcript';
        html += '</button>';
        html += '</div>';
        html += '</div>';
        html += '<!-- Transcript Display -->';
        html += '<div id="transcript-display" class="simply-transcript-viewer hidden"></div>';
        html += '</div>';
        html += '<!-- Summary Tab Content -->';
        html += '<div id="summary-content" class="simply-tab-content hidden">';
        html += '<!-- Authentication Required State (hidden in TEST_MODE) -->';
        html += '<div id="summary-auth-required" class="simply-auth-prompt' + (TEST_MODE ? ' hidden' : '') + '">';
        html += '<div class="simply-auth-prompt__icon">';
        html += '<svg width="36" height="36" viewBox="0 0 24 24" fill="currentColor">';
        html += '<path d="M12,4A4,4 0 0,1 16,8A4,4 0 0,1 12,12A4,4 0 0,1 8,8A4,4 0 0,1 12,4M12,14C16.42,14 20,15.79 20,18V20H4V18C4,15.79 7.58,14 12,14Z"/>';
        html += '</svg>';
        html += '</div>';
        html += '<h3 class="simply-auth-prompt__title">Sign In Required</h3>';
        html += '<p class="simply-auth-prompt__description">Create an account to generate AI-powered video summaries</p>';
        html += '<div class="simply-auth-prompt__actions">';
        html += '<button id="summary-signin-btn" class="simply-btn simply-btn--primary simply-w-full">';
        html += 'Sign In';
        html += '</button>';
        html += '<button id="summary-signup-btn" class="simply-btn simply-btn--secondary simply-w-full">';
        html += 'Create Account';
        html += '</button>';
        html += '</div>';
        html += '<div class="simply-auth-prompt__features">';
        html += '<h4>Free Account Benefits</h4>';
        html += '<ul>';
        html += '<li>1 video summary per week</li>';
        html += '<li>AI-powered content analysis</li>';
        html += '<li>Save transcripts and summaries</li>';
        html += '</ul>';
        html += '</div>';
        html += '</div>';
        html += '<!-- Summary Ready State (visible in TEST_MODE) -->';
        html += '<div id="summary-ready" class="simply-empty-state' + (TEST_MODE ? '' : ' hidden') + '">';
        html += '<div class="simply-empty-state__icon">';
        html += '<svg width="48" height="48" viewBox="0 0 24 24" fill="currentColor">';
        html += '<path d="M14,2H6A2,2 0 0,0 4,4V20A2,2 0 0,0 6,22H18A2,2 0 0,0 20,20V8L14,2M18,20H6V4H13V9H18V20Z"/>';
        html += '</svg>';
        html += '</div>';
        html += '<h3 class="simply-empty-state__title">Generate Summary</h3>';
        html += '<p class="simply-empty-state__description">Extract the transcript first, then generate an AI summary of the video content.</p>';
        html += '<div class="simply-flex simply-flex-col simply-gap-3 simply-mb-4">';
        html += '<button id="generate-summary-btn" class="simply-btn simply-btn--primary simply-w-full">';
        html += '<svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor" class="simply-mr-1">';
        html += '<path d="M14,2H6A2,2 0 0,0 4,4V20A2,2 0 0,0 6,22H18A2,2 0 0,0 20,20V8L14,2M18,20H6V4H13V9H18V20Z"/>';
        html += '</svg>';
        html += 'Generate Summary';
        html += '</button>';
        html += '</div>';
        html += '</div>';
        html += '<!-- Summary Display -->';
        html += '<div id="summary-display" class="simply-summary-viewer hidden">';
        html += '<div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px; padding-bottom: 8px; border-bottom: 1px solid rgba(0, 0, 0, 0.08);">';
        html += '<h4 style="margin: 0; font-size: 15px; color: #333; font-weight: 600;">AI Summary</h4>';
        html += '<div style="font-size: 11px; color: #666; display: flex; align-items: center; gap: 4px;">';
        html += '<svg width="12" height="12" viewBox="0 0 24 24" fill="currentColor" style="opacity: 0.7;">';
        html += '<path d="M9 11H7v6h2v-6zm4 0h-2v6h2v-6zm4 0h-2v6h2v-6zm2.5-9H19V1h-2v1H7V1H5v1H3.5C2.67 2 2 2.67 2 3.5v15C2 19.33 2.67 20 3.5 20h17c.83 0 1.5-.67 1.5-1.5v-15C22 2.67 21.33 2 20.5 2zM20.5 18.5h-17v-13h17v13z"/>';
        html += '</svg>';
        html += 'Generated with AI';
        html += '</div>';
        html += '</div>';
        html += '<div id="summary-content-area" class="summary-content-area">';
        html += '<!-- Summary content will be populated here -->';
        html += '</div>';
        html += '<div class="summary-actions">';
        html += '<button id="copy-summary-btn" class="simply-btn simply-btn--secondary simply-btn--sm">';
        html += '<svg width="12" height="12" viewBox="0 0 24 24" fill="currentColor" class="simply-mr-1">';
        html += '<path d="M16 1H4C2.9 1 2 1.9 2 3V17H4V3H16V1ZM19 5H8C6.9 5 6 5.9 6 7V21C6 22.1 6.9 23 8 23H19C20.1 23 21 22.1 21 21V7C21 5.9 20.1 5 19 5ZM19 21H8V7H19V21Z"/>';
        html += '</svg>';
        html += 'Copy';
        html += '</button>';
        html += '<button id="download-summary-btn" class="simply-btn simply-btn--secondary simply-btn--sm">';
        html += '<svg width="12" height="12" viewBox="0 0 24 24" fill="currentColor" class="simply-mr-1">';
        html += '<path d="M19 9h-4V3H9v6H5l7 7 7-7zM5 18v2h14v-2H5z"/>';
        html += '</svg>';
        html += 'Download';
        html += '</button>';
        html += '<button id="email-summary-btn" class="simply-btn simply-btn--secondary simply-btn--sm">';
        html += '<svg width="12" height="12" viewBox="0 0 24 24" fill="currentColor" class="simply-mr-1">';
        html += '<path d="M20 4H4c-1.1 0-1.99.9-1.99 2L2 18c0 1.1.9 2 2 2h16c1.1 0 2-.9 2-2V6c0-1.1-.9-2-2-2zm0 4l-8 5-8-5V6l8 5 8-5v2z"/>';
        html += '</svg>';
        html += 'Email';
        html += '</button>';
        html += '<button id="regenerate-summary-btn" class="simply-btn simply-btn--secondary simply-btn--sm">';
        html += '<svg width="12" height="12" viewBox="0 0 24 24" fill="currentColor" class="simply-mr-1">';
        html += '<path d="M17.65,6.35C16.2,4.9 14.21,4 12,4A8,8 0 0,0 4,12A8,8 0 0,0 12,20C15.73,20 18.84,17.45 19.73,14H17.65C16.83,16.33 14.61,18 12,18A6,6 0 0,1 6,12A6,6 0 0,1 12,6C13.66,6 15.14,6.69 16.22,7.78L13,11H20V4L17.65,6.35Z"/>';
        html += '</svg>';
        html += 'Regenerate';
        html += '</button>';
        html += '</div>';
        html += '</div>';
        html += '</div>';
        html += '<!-- Chat Tab Content -->';
        html += '<div id="chat-content" class="simply-tab-content hidden">';
        html += '<div id="chat-not-saved" class="simply-empty-state">';
        html += '<div class="simply-empty-state__icon">';
        html += '<svg width="32" height="32" viewBox="0 0 24 24" fill="currentColor">';
        html += '<path d="M20,2H4A2,2 0 0,0 2,4V22L6,18H20A2,2 0 0,0 22,16V4A2,2 0 0,0 20,2M6,9H18V11H6V9M14,14H6V12H14V14M18,8H6V6H18V8Z"/>';
        html += '</svg>';
        html += '</div>';
        html += '<h3 class="simply-empty-state__title">Chat with Video</h3>';
        html += '<p class="simply-empty-state__description">';
        html += 'Save the transcript to your library to start chatting about the video content';
        html += '</p>';
        html += '</div>';
        html += '<div id="chat-interface" class="hidden">';
        html += '<div id="chat-messages"></div>';
        html += '<div class="chat-input-wrapper">';
        html += '<input type="text" id="chat-input" class="simply-input" placeholder="Ask about this video..." />';
        html += '<button id="chat-send-btn">Send</button>';
        html += '</div>';
        html += '</div>';
        html += '</div>';
        html += '<!-- Menu Tab Content -->';
        html += '<div id="menu-content" class="simply-tab-content hidden">';
        html += '<div style="padding: 0;">';
        html += '<!-- User Status Card -->';
        html += '<div id="auth-section">';
        html += '<div id="logged-out-menu" class="user-status-card user-status-card--logged-out">';
        html += '<div class="user-status-card__info">';
        html += '<div class="user-status-card__label">Not signed in</div>';
        html += '<div class="user-status-card__email" style="color: var(--simply-text-secondary); font-size: var(--simply-text-xs);">Sign in to sync your data</div>';
        html += '</div>';
        html += '</div>';
        html += '<div id="logged-in-menu" class="user-status-card user-status-card--logged-in hidden">';
        html += '<div class="user-status-card__info">';
        html += '<div class="user-status-card__label">Signed in as</div>';
        html += '<div id="menu-user-email" class="user-status-card__email">Loading...</div>';
        html += '<div id="menu-user-plan" class="user-status-card__plan">Loading...</div>';
        html += '</div>';
        html += '</div>';
        html += '</div>';
        html += '<!-- Auth Buttons -->';
        html += '<div id="auth-buttons-logged-out" style="display: flex; gap: var(--simply-space-2); margin-bottom: var(--simply-space-4);">';
        html += '<button id="menu-login-btn" class="simply-btn simply-btn--primary" style="flex: 1;">';
        html += 'Sign In';
        html += '</button>';
        html += '<button id="menu-signup-btn" class="simply-btn simply-btn--secondary" style="flex: 1;">';
        html += 'Sign Up';
        html += '</button>';
        html += '</div>';
        html += '<div id="auth-buttons-logged-in" class="hidden" style="margin-bottom: var(--simply-space-4);">';
        html += '<button id="menu-logout-btn" class="simply-btn simply-btn--danger simply-w-full">';
        html += 'Sign Out';
        html += '</button>';
        html += '</div>';
        html += '<!-- Upgrade Banner (shown only for free users) -->';
        html += '<div id="menu-upgrade-banner" class="menu-upgrade-banner hidden">';
        html += '<div class="upgrade-banner-content">';
        html += '<svg width="20" height="20" viewBox="0 0 24 24" fill="currentColor" style="color: #f59e0b;">';
        html += '<path d="M12,17.27L18.18,21L16.54,13.97L22,9.24L14.81,8.62L12,2L9.19,8.62L2,9.24L7.45,13.97L5.82,21L12,17.27Z"/>';
        html += '</svg>';
        html += '<div class="upgrade-banner-text">';
        html += '<div class="upgrade-banner-title">Upgrade to Premium</div>';
        html += '<div class="upgrade-banner-desc">Unlimited summaries, priority support</div>';
        html += '</div>';
        html += '</div>';
        html += '<button id="menu-upgrade-btn" class="simply-btn simply-btn--primary" style="font-size: 12px; padding: 6px 12px;">Upgrade</button>';
        html += '</div>';
        html += '<!-- Quick Actions Section -->';
        html += '<div class="menu-section">';
        html += '<h5>Quick Actions</h5>';
        html += '<button id="menu-dashboard-btn" class="menu-item">';
        html += '<svg width="18" height="18" viewBox="0 0 24 24" fill="currentColor">';
        html += '<path d="M13,3V9H21V3M13,21H21V11H13M3,21H11V15H3M3,13H11V3H3V13Z"/>';
        html += '</svg>';
        html += 'Open Dashboard';
        html += '</button>';
        html += '<button id="menu-history-btn" class="menu-item">';
        html += '<svg width="18" height="18" viewBox="0 0 24 24" fill="currentColor">';
        html += '<path d="M13.5,8H12V13L16.28,15.54L17,14.33L13.5,12.25V8M13,3A9,9 0 0,0 4,12H1L4.96,16.03L9,12H6A7,7 0 0,1 13,5A7,7 0 0,1 20,12A7,7 0 0,1 13,19C11.07,19 9.32,18.21 8.06,16.94L6.64,18.36C8.27,20 10.5,21 13,21A9,9 0 0,0 22,12A9,9 0 0,0 13,3"/>';
        html += '</svg>';
        html += 'Recent Videos';
        html += '</button>';
        html += '</div>';
        html += '<!-- Settings & Support Section -->';
        html += '<div class="menu-section">';
        html += '<h5>Settings & Support</h5>';
        html += '<button id="menu-settings-btn" class="menu-item">';
        html += '<svg width="18" height="18" viewBox="0 0 24 24" fill="currentColor">';
        html += '<path d="M12,15.5A3.5,3.5 0 0,1 8.5,12A3.5,3.5 0 0,1 12,8.5A3.5,3.5 0 0,1 15.5,12A3.5,3.5 0 0,1 12,15.5M19.43,12.97C19.47,12.65 19.5,12.33 19.5,12C19.5,11.67 19.47,11.34 19.43,11L21.54,9.37C21.73,9.22 21.78,8.95 21.66,8.73L19.66,5.27C19.54,5.05 19.27,4.96 19.05,5.05L16.56,6.05C16.04,5.66 15.5,5.32 14.87,5.07L14.5,2.42C14.46,2.18 14.25,2 14,2H10C9.75,2 9.54,2.18 9.5,2.42L9.13,5.07C8.5,5.32 7.96,5.66 7.44,6.05L4.95,5.05C4.73,4.96 4.46,5.05 4.34,5.27L2.34,8.73C2.21,8.95 2.27,9.22 2.46,9.37L4.57,11C4.53,11.34 4.5,11.67 4.5,12C4.5,12.33 4.53,12.65 4.57,12.97L2.46,14.63C2.27,14.78 2.21,15.05 2.34,15.27L4.34,18.73C4.46,18.95 4.73,19.03 4.95,18.95L7.44,17.94C7.96,18.34 8.5,18.68 9.13,18.93L9.5,21.58C9.54,21.82 9.75,22 10,22H14C14.25,22 14.46,21.82 14.5,21.58L14.87,18.93C15.5,18.68 16.04,18.34 16.56,17.94L19.05,18.95C19.27,19.03 19.54,18.95 19.66,18.73L21.66,15.27C21.78,15.05 21.73,14.78 21.54,14.63L19.43,12.97Z"/>';
        html += '</svg>';
        html += 'Extension Settings';
        html += '</button>';
        html += '<button id="menu-help-btn" class="menu-item">';
        html += '<svg width="18" height="18" viewBox="0 0 24 24" fill="currentColor">';
        html += '<path d="M15.07,11.25L14.17,12.17C13.45,12.89 13,13.5 13,15H11V14.5C11,13.39 11.45,12.39 12.17,11.67L13.41,10.41C13.78,10.05 14,9.55 14,9C14,7.89 13.1,7 12,7A2,2 0 0,0 10,9H8A4,4 0 0,1 12,5A4,4 0 0,1 16,9C16,9.88 15.64,10.67 15.07,11.25M13,19H11V17H13M12,2A10,10 0 0,0 2,12A10,10 0 0,0 12,22A10,10 0 0,0 22,12C22,6.47 17.5,2 12,2Z"/>';
        html += '</svg>';
        html += 'Help & Feedback';
        html += '</button>';
        html += '</div>';
        html += '<!-- Info Section -->';
        html += '<div style="padding: var(--simply-space-3); background: var(--simply-bg-secondary); border-radius: var(--simply-radius-lg); text-align: center;">';
        html += '<div style="font-size: var(--simply-text-xs); color: var(--simply-text-tertiary);">TubeVibe Extension</div>';
        html += '<div style="font-size: 10px; color: var(--simply-text-tertiary); margin-top: 2px;">Version 1.0.6 - AI Video Summaries</div>';
        html += '</div>';
        html += '</div>';
        html += '</div>';
        html += '<!-- Footer -->';
        html += '<div class="simply-footer">';
        html += '<small id="footer-text">v1.0.6 • © 2025 TubeVibe by AutoBotic</small>';
        html += '</div>';
        html += '</div>';
        
        return html;
    }
    async loadPopupScripts() {
        const scripts = [
            'popup-state.js',
            'popup-auth.js',
            'popup-api.js',
            'popup-modals.js',
            'popup-utils.js',
            'popup-transcript-extractor.js',
            'popup-sophisticated.js'
        ];
        for (const scriptName of scripts) {
            await this.loadScript(scriptName);
        }
    }
    async loadScript(scriptName) {
        return new Promise((resolve, reject) => {
            const script = document.createElement('script');
            script.src = chrome.runtime.getURL(scriptName);
            script.onload = () => {
                // Special handling for popup-sophisticated.js
                if (scriptName === 'popup-sophisticated.js') {
                    setTimeout(() => {
                        console.log('popup-sophisticated.js loaded');
                    }, 100);
                }
                resolve();
            };
            script.onerror = (error) => {
                console.error('❌ Failed to load script: ' + scriptName, error);
                resolve(); // Continue even if a script fails
            };
            document.head.appendChild(script);
        });
    }
    async loadCSS(cssName) {
        return new Promise((resolve, reject) => {
            const link = document.createElement('link');
            link.rel = 'stylesheet';
            link.href = chrome.runtime.getURL(cssName);
            link.onload = () => {
                resolve();
            };
            link.onerror = (error) => {
                console.error('❌ Failed to load CSS: ' + cssName, error);
                resolve(); // Continue even if CSS fails
            };
            document.head.appendChild(link);
        });
    }
    injectStyles() {
        // Don't inject styles multiple times
        if (document.getElementById('tubevibe-embedded-popup-styles')) {
            const oldStyle = document.getElementById('tubevibe-embedded-popup-styles');
            oldStyle?.remove();
        }
        const style = document.createElement('style');
        style.id = 'tubevibe-embedded-popup-styles';
        style.setAttribute('data-extension', 'tubevibe');
        style.textContent = `
            .tubevibe-embedded-container {
                width: 100%;
                margin-bottom: 16px;
                /* CSS containment to prevent style leakage */
                contain: style layout;
            }
            .tubevibe-embedded-popup {
                width: 100%;
                max-height: 600px;
                overflow-y: auto;
                overflow-x: hidden;
                border: 1px solid rgba(226, 232, 240, 0.6);
                border-radius: 16px;
                background: linear-gradient(135deg, rgba(255, 255, 255, 0.95) 0%, rgba(248, 250, 252, 0.95) 100%);
                box-shadow: 0 8px 32px rgba(0, 0, 0, 0.12), 0 2px 6px rgba(0, 0, 0, 0.08);
                font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Inter", "SF Pro Display", sans-serif !important;
                font-size: 14px !important;
                line-height: 1.5 !important;
                backdrop-filter: blur(20px);
                position: relative;
                /* CSS containment to prevent any style leakage */
                contain: style layout;
            }
            .tubevibe-embedded-popup::before {
                content: '';
                position: absolute;
                top: 0;
                left: 0;
                right: 0;
                height: 1px;
                background: linear-gradient(90deg, transparent, rgba(102, 126, 234, 0.3), transparent);
            }
            /* Ensure the popup content fits properly */
            .tubevibe-embedded-popup .simply-popup {
                width: 100%;
                min-height: auto;
                margin: 0;
                padding: 0;
                background: #ffffff;
                /* TEST: Border matching header dark color - remove if not desired */
                border: 2px solid #0f172a;
                border-radius: 18px;
                box-shadow: 0 4px 20px rgba(0, 0, 0, 0.15);
                font-family: system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif !important;
                font-size: 14px !important;
                overflow: visible;
            }
            /* Modern typography system - specific selectors to avoid affecting YouTube elements */
            .tubevibe-embedded-popup,
            .tubevibe-embedded-popup p,
            .tubevibe-embedded-popup span,
            .tubevibe-embedded-popup div,
            .tubevibe-embedded-popup button,
            .tubevibe-embedded-popup input,
            .tubevibe-embedded-popup textarea,
            .tubevibe-embedded-popup select,
            .tubevibe-embedded-popup h1,
            .tubevibe-embedded-popup h2,
            .tubevibe-embedded-popup h3,
            .tubevibe-embedded-popup h4,
            .tubevibe-embedded-popup h5,
            .tubevibe-embedded-popup h6,
            .tubevibe-embedded-popup label,
            .tubevibe-embedded-popup a {
                font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Inter", "SF Pro Display", sans-serif !important;
            }
            /* Utility classes for logo design */
            .tubevibe-embedded-popup .flex {
                display: flex !important;
                flex-direction: row !important;
            }
            .tubevibe-embedded-popup .items-center {
                align-items: center !important;
            }
            .tubevibe-embedded-popup .space-x-2 > :not(:first-child) {
                margin-left: 12px !important;
            }
            .tubevibe-embedded-popup .space-x-2 {
                display: flex !important;
                flex-direction: row !important;
                align-items: center !important;
                gap: 12px !important;
            }
            .tubevibe-embedded-popup .relative {
                position: relative !important;
            }
            .tubevibe-embedded-popup .absolute {
                position: absolute !important;
            }
            .tubevibe-embedded-popup .inset-0 {
                top: 0 !important;
                right: 0 !important;
                bottom: 0 !important;
                left: 0 !important;
            }
            .tubevibe-embedded-popup .rounded-lg {
                border-radius: 8px !important;
            }
            .tubevibe-embedded-popup .drop-shadow-lg {
                filter: drop-shadow(0 10px 8px rgb(0 0 0 / 0.04)) drop-shadow(0 4px 3px rgb(0 0 0 / 0.1)) !important;
            }
            /* Scoped SVG styles to prevent YouTube logo interference */
            /* Use very specific selectors to only target TubeVibe's own SVG elements */
            .tubevibe-embedded-popup .simply-logo svg .simply-svg-play-icon {
                fill: white !important;
            }
            .tubevibe-embedded-popup .simply-logo svg .simply-svg-circle-stroke {
                fill: none !important;
                stroke: white !important;
                stroke-width: 2;
                opacity: 0.6;
            }
            .tubevibe-embedded-popup .simply-logo svg .simply-svg-line-stroke {
                stroke: white !important;
                stroke-width: 1.5;
                opacity: 0.4;
            }
            /* Ensure TubeVibe SVG colors are contained - more specific selectors */
            .tubevibe-embedded-popup .simply-tab svg,
            .tubevibe-embedded-popup .simply-btn svg,
            .tubevibe-embedded-popup .simply-empty-state svg,
            .tubevibe-embedded-popup button svg {
                fill: currentColor;
            }
            .tubevibe-embedded-popup {
                font-feature-settings: "kern" 1, "liga" 1, "calt" 1;
                text-rendering: optimizeLegibility;
                -webkit-font-smoothing: antialiased;
                -moz-osx-font-smoothing: grayscale;
            }
            /* Use more specific selectors to avoid affecting YouTube elements */
            .tubevibe-embedded-popup > p,
            .tubevibe-embedded-popup .simply-tab-content p,
            .tubevibe-embedded-popup .simply-tab-content > span:not(.transcript-segment-text),
            .tubevibe-embedded-popup .simply-tab-content > div:not(.transcript-segment-text),
            .tubevibe-embedded-popup .simply-tab,
            .tubevibe-embedded-popup .simply-button {
                font-size: 14px !important;
                line-height: 1.5 !important;
                font-weight: 400 !important;
            }
            .tubevibe-embedded-popup h2,
            .tubevibe-embedded-popup h3,
            .tubevibe-embedded-popup h4 {
                font-size: 16px !important;
                line-height: 1.3 !important;
                margin: 0 !important;
                font-weight: 600 !important;
                letter-spacing: -0.01em !important;
            }
            .tubevibe-embedded-popup .simply-btn {
                font-size: 12px !important;
                padding: 6px 12px !important;
                font-weight: 500 !important;
                border-radius: 4px !important;
                transition: all 0.15s ease !important;
                border: 1px solid transparent !important;
                cursor: pointer !important;
                letter-spacing: 0px !important;
            }
            .tubevibe-embedded-popup .simply-btn--sm {
                font-size: 11px !important;
                padding: 4px 8px !important;
                border-radius: 3px !important;
            }
            /* Professional button styles */
            .tubevibe-embedded-popup .simply-btn--primary {
                background: #1e40af !important;
                color: white !important;
                border-color: #1e40af !important;
            }
            .tubevibe-embedded-popup .simply-btn--primary:hover {
                background: #1e3a8a !important;
                border-color: #1e3a8a !important;
            }
            .tubevibe-embedded-popup .simply-btn--secondary {
                background: #f9f9f9 !important;
                color: #606060 !important;
                border: 1px solid #d0d0d0 !important;
            }
            .tubevibe-embedded-popup .simply-btn--secondary:hover {
                background: #f0f0f0 !important;
                border-color: #c0c0c0 !important;
            }
            /* Menu section styles - consistent with other tabs */
            .tubevibe-embedded-popup .menu-section {
                background: #ffffff !important;
                border: 1px solid #e5e7eb !important;
                border-radius: 12px !important;
                padding: 16px !important;
                margin-bottom: 12px !important;
            }
            .tubevibe-embedded-popup .menu-section h5 {
                font-size: 13px !important;
                font-weight: 600 !important;
                color: #374151 !important;
                text-transform: uppercase !important;
                letter-spacing: 0.5px !important;
                margin: 0 0 12px 0 !important;
            }
            .tubevibe-embedded-popup .menu-item {
                display: flex !important;
                align-items: center !important;
                gap: 12px !important;
                padding: 12px 14px !important;
                background: #f9fafb !important;
                border: 1px solid #e5e7eb !important;
                border-radius: 8px !important;
                cursor: pointer !important;
                transition: all 0.15s ease !important;
                margin-bottom: 8px !important;
                font-size: 14px !important;
                font-weight: 500 !important;
                color: #374151 !important;
                text-align: left !important;
                width: 100% !important;
            }
            .tubevibe-embedded-popup .menu-item:last-child {
                margin-bottom: 0 !important;
            }
            .tubevibe-embedded-popup .menu-item:hover {
                background: #f3f4f6 !important;
                border-color: #d1d5db !important;
                transform: translateX(4px) !important;
            }
            .tubevibe-embedded-popup .menu-item svg {
                width: 20px !important;
                height: 20px !important;
                color: #6b7280 !important;
                flex-shrink: 0 !important;
            }
            /* Upgrade banner styles */
            .tubevibe-embedded-popup .menu-upgrade-banner {
                display: flex !important;
                align-items: center !important;
                justify-content: space-between !important;
                padding: 12px 14px !important;
                background: linear-gradient(135deg, #fef3c7 0%, #fde68a 100%) !important;
                border: 1px solid #f59e0b !important;
                border-radius: 10px !important;
                margin-bottom: 12px !important;
            }
            .tubevibe-embedded-popup .upgrade-banner-content {
                display: flex !important;
                align-items: center !important;
                gap: 10px !important;
            }
            .tubevibe-embedded-popup .upgrade-banner-text {
                display: flex !important;
                flex-direction: column !important;
            }
            .tubevibe-embedded-popup .upgrade-banner-title {
                font-size: 13px !important;
                font-weight: 600 !important;
                color: #92400e !important;
            }
            .tubevibe-embedded-popup .upgrade-banner-desc {
                font-size: 11px !important;
                color: #b45309 !important;
            }
            /* History modal styles */
            .tubevibe-embedded-popup .history-modal-overlay {
                position: fixed !important;
                top: 0 !important;
                left: 0 !important;
                right: 0 !important;
                bottom: 0 !important;
                background: rgba(0, 0, 0, 0.5) !important;
                z-index: 10000 !important;
                display: flex !important;
                align-items: center !important;
                justify-content: center !important;
            }
            .tubevibe-embedded-popup .history-modal {
                background: white !important;
                border-radius: 12px !important;
                width: 90% !important;
                max-width: 400px !important;
                max-height: 80vh !important;
                overflow: hidden !important;
                box-shadow: 0 20px 40px rgba(0, 0, 0, 0.3) !important;
            }
            .tubevibe-embedded-popup .history-modal-header {
                display: flex !important;
                align-items: center !important;
                justify-content: space-between !important;
                padding: 16px !important;
                border-bottom: 1px solid #e5e7eb !important;
            }
            .tubevibe-embedded-popup .history-modal-header h3 {
                margin: 0 !important;
                font-size: 16px !important;
                font-weight: 600 !important;
                color: #111827 !important;
            }
            .tubevibe-embedded-popup .history-modal-close {
                background: none !important;
                border: none !important;
                cursor: pointer !important;
                padding: 4px !important;
                color: #6b7280 !important;
            }
            .tubevibe-embedded-popup .history-modal-close:hover {
                color: #111827 !important;
            }
            .tubevibe-embedded-popup .history-modal-content {
                padding: 16px !important;
                max-height: 400px !important;
                overflow-y: auto !important;
            }
            .tubevibe-embedded-popup .history-item {
                display: flex !important;
                align-items: center !important;
                gap: 12px !important;
                padding: 10px !important;
                border-radius: 8px !important;
                cursor: pointer !important;
                transition: background 0.15s ease !important;
                margin-bottom: 8px !important;
            }
            .tubevibe-embedded-popup .history-item:hover {
                background: #f3f4f6 !important;
            }
            .tubevibe-embedded-popup .history-item-thumb {
                width: 80px !important;
                height: 45px !important;
                border-radius: 6px !important;
                object-fit: cover !important;
                flex-shrink: 0 !important;
            }
            .tubevibe-embedded-popup .history-item-info {
                flex: 1 !important;
                min-width: 0 !important;
            }
            .tubevibe-embedded-popup .history-item-title {
                font-size: 13px !important;
                font-weight: 500 !important;
                color: #111827 !important;
                white-space: nowrap !important;
                overflow: hidden !important;
                text-overflow: ellipsis !important;
            }
            .tubevibe-embedded-popup .history-item-date {
                font-size: 11px !important;
                color: #6b7280 !important;
                margin-top: 2px !important;
            }
            .tubevibe-embedded-popup .history-empty {
                text-align: center !important;
                padding: 32px 16px !important;
                color: #6b7280 !important;
            }
            .tubevibe-embedded-popup .history-empty svg {
                width: 48px !important;
                height: 48px !important;
                color: #d1d5db !important;
                margin-bottom: 12px !important;
            }
            /* Settings modal styles */
            .tubevibe-embedded-popup .settings-modal-overlay {
                position: fixed !important;
                top: 0 !important;
                left: 0 !important;
                right: 0 !important;
                bottom: 0 !important;
                background: rgba(0, 0, 0, 0.5) !important;
                z-index: 10000 !important;
                display: flex !important;
                align-items: center !important;
                justify-content: center !important;
            }
            .tubevibe-embedded-popup .settings-modal {
                background: white !important;
                border-radius: 12px !important;
                width: 90% !important;
                max-width: 360px !important;
                overflow: hidden !important;
                box-shadow: 0 20px 40px rgba(0, 0, 0, 0.3) !important;
            }
            .tubevibe-embedded-popup .settings-modal-header {
                display: flex !important;
                align-items: center !important;
                justify-content: space-between !important;
                padding: 16px !important;
                border-bottom: 1px solid #e5e7eb !important;
            }
            .tubevibe-embedded-popup .settings-modal-header h3 {
                margin: 0 !important;
                font-size: 16px !important;
                font-weight: 600 !important;
                color: #111827 !important;
            }
            .tubevibe-embedded-popup .settings-modal-close {
                background: none !important;
                border: none !important;
                cursor: pointer !important;
                padding: 4px !important;
                color: #6b7280 !important;
            }
            .tubevibe-embedded-popup .settings-modal-close:hover {
                color: #111827 !important;
            }
            .tubevibe-embedded-popup .settings-modal-content {
                padding: 16px !important;
            }
            .tubevibe-embedded-popup .settings-item {
                display: flex !important;
                align-items: center !important;
                justify-content: space-between !important;
                padding: 12px 0 !important;
                border-bottom: 1px solid #f3f4f6 !important;
            }
            .tubevibe-embedded-popup .settings-item:last-child {
                border-bottom: none !important;
            }
            .tubevibe-embedded-popup .settings-item-label {
                font-size: 14px !important;
                color: #374151 !important;
            }
            .tubevibe-embedded-popup .settings-item-desc {
                font-size: 11px !important;
                color: #9ca3af !important;
                margin-top: 2px !important;
            }
            .tubevibe-embedded-popup .settings-toggle {
                position: relative !important;
                width: 44px !important;
                height: 24px !important;
                background: #e5e7eb !important;
                border-radius: 12px !important;
                cursor: pointer !important;
                transition: background 0.2s ease !important;
            }
            .tubevibe-embedded-popup .settings-toggle.active {
                background: #2563eb !important;
            }
            .tubevibe-embedded-popup .settings-toggle::after {
                content: '' !important;
                position: absolute !important;
                top: 2px !important;
                left: 2px !important;
                width: 20px !important;
                height: 20px !important;
                background: white !important;
                border-radius: 50% !important;
                transition: transform 0.2s ease !important;
                box-shadow: 0 1px 3px rgba(0, 0, 0, 0.2) !important;
            }
            .tubevibe-embedded-popup .settings-toggle.active::after {
                transform: translateX(20px) !important;
            }
            .tubevibe-embedded-popup .settings-modal-footer {
                padding: 12px 16px !important;
                border-top: 1px solid #e5e7eb !important;
                text-align: center !important;
            }
            .tubevibe-embedded-popup .settings-clear-cache-btn {
                background: #fef2f2 !important;
                color: #dc2626 !important;
                border: 1px solid #fecaca !important;
                padding: 8px 16px !important;
                border-radius: 6px !important;
                font-size: 13px !important;
                cursor: pointer !important;
                transition: all 0.15s ease !important;
            }
            .tubevibe-embedded-popup .settings-clear-cache-btn:hover {
                background: #fee2e2 !important;
            }
            /* Auth buttons in menu - larger size */
            .tubevibe-embedded-popup #auth-buttons-logged-out .simply-btn,
            .tubevibe-embedded-popup #auth-buttons-logged-in .simply-btn {
                font-size: 14px !important;
                padding: 10px 16px !important;
                font-weight: 600 !important;
                border-radius: 8px !important;
            }
            /* Auth form styles - consistent with other tabs */
            .tubevibe-embedded-popup .simply-auth-form {
                display: flex !important;
                flex-direction: column !important;
                gap: 14px !important;
            }
            .tubevibe-embedded-popup .simply-auth-social__btn {
                display: flex !important;
                align-items: center !important;
                justify-content: center !important;
                gap: 10px !important;
                width: 100% !important;
                padding: 12px 16px !important;
                font-size: 14px !important;
                font-weight: 500 !important;
                color: #374151 !important;
                background: white !important;
                border: 1px solid #d1d5db !important;
                border-radius: 8px !important;
                cursor: pointer !important;
                transition: all 0.15s ease !important;
            }
            .tubevibe-embedded-popup .simply-auth-social__btn:hover {
                background: #f9fafb !important;
                border-color: #9ca3af !important;
            }
            .tubevibe-embedded-popup .simply-auth-social__btn svg {
                width: 20px !important;
                height: 20px !important;
            }
            .tubevibe-embedded-popup .simply-auth-form__divider {
                display: flex !important;
                align-items: center !important;
                gap: 12px !important;
                color: #9ca3af !important;
                font-size: 13px !important;
                margin: 4px 0 !important;
            }
            .tubevibe-embedded-popup .simply-auth-form__divider::before,
            .tubevibe-embedded-popup .simply-auth-form__divider::after {
                content: '' !important;
                flex: 1 !important;
                height: 1px !important;
                background: #e5e7eb !important;
            }
            .tubevibe-embedded-popup .simply-input-group {
                display: flex !important;
                flex-direction: column !important;
                gap: 6px !important;
            }
            .tubevibe-embedded-popup .simply-input-row {
                display: flex !important;
                gap: 12px !important;
            }
            .tubevibe-embedded-popup .simply-input-row .simply-input-group {
                flex: 1 !important;
            }
            .tubevibe-embedded-popup .simply-input-label {
                font-size: 13px !important;
                font-weight: 500 !important;
                color: #374151 !important;
            }
            .tubevibe-embedded-popup .simply-input {
                width: 100% !important;
                padding: 10px 12px !important;
                font-size: 14px !important;
                color: #374151 !important;
                background: white !important;
                border: 1px solid #d1d5db !important;
                border-radius: 6px !important;
                outline: none !important;
                transition: border-color 0.15s ease !important;
                box-sizing: border-box !important;
            }
            .tubevibe-embedded-popup .simply-input:focus {
                border-color: #1e40af !important;
                box-shadow: 0 0 0 3px rgba(30, 64, 175, 0.1) !important;
            }
            .tubevibe-embedded-popup .simply-auth-form__footer {
                text-align: center !important;
                font-size: 13px !important;
                color: #6b7280 !important;
                margin-top: 4px !important;
            }
            .tubevibe-embedded-popup .simply-auth-form__link {
                background: none !important;
                border: none !important;
                color: #1e40af !important;
                font-size: 13px !important;
                font-weight: 500 !important;
                cursor: pointer !important;
                padding: 0 !important;
                text-decoration: underline !important;
            }
            .tubevibe-embedded-popup .simply-auth-form__link:hover {
                color: #1e3a8a !important;
            }
            .tubevibe-embedded-popup .simply-auth-error,
            .tubevibe-embedded-popup .simply-input-error {
                color: #dc2626 !important;
                font-size: 13px !important;
                padding: 8px 12px !important;
                background: #fef2f2 !important;
                border: 1px solid #fecaca !important;
                border-radius: 6px !important;
                margin-top: 8px !important;
            }
            .tubevibe-embedded-popup .simply-btn--full {
                width: 100% !important;
            }
            /* Magic link auth divider */
            .tubevibe-embedded-popup .simply-auth-divider {
                display: flex !important;
                align-items: center !important;
                margin: 16px 0 !important;
                color: #94a3b8 !important;
                font-size: 12px !important;
            }
            .tubevibe-embedded-popup .simply-auth-divider::before,
            .tubevibe-embedded-popup .simply-auth-divider::after {
                content: '' !important;
                flex: 1 !important;
                height: 1px !important;
                background: #e2e8f0 !important;
            }
            .tubevibe-embedded-popup .simply-auth-divider span {
                padding: 0 12px !important;
            }
            /* Magic link button outline style */
            .tubevibe-embedded-popup .simply-btn--outline {
                display: flex !important;
                align-items: center !important;
                justify-content: center !important;
                gap: 8px !important;
                background: white !important;
                color: #374151 !important;
                border: 1px solid #d1d5db !important;
                border-radius: 6px !important;
                padding: 10px 16px !important;
                font-size: 14px !important;
                font-weight: 500 !important;
                cursor: pointer !important;
                transition: all 0.15s ease !important;
            }
            .tubevibe-embedded-popup .simply-btn--outline:hover {
                background: #f9fafb !important;
                border-color: #9ca3af !important;
            }
            .tubevibe-embedded-popup .simply-btn--outline:disabled {
                opacity: 0.6 !important;
                cursor: not-allowed !important;
            }
            /* Auth spinner for loading states */
            .tubevibe-embedded-popup .simply-spinner {
                display: inline-block !important;
                width: 14px !important;
                height: 14px !important;
                border: 2px solid #e2e8f0 !important;
                border-top-color: currentColor !important;
                border-radius: 50% !important;
                animation: simply-spin 0.8s linear infinite !important;
            }
            @keyframes simply-spin {
                to { transform: rotate(360deg); }
            }
            /* Transcript action buttons hover effects */
            .tubevibe-embedded-popup #tubevibe-copy-btn:hover,
            .tubevibe-embedded-popup #tubevibe-download-btn:hover,
            .tubevibe-embedded-popup #tubevibe-save-library-btn:hover {
                background: #f3f4f6 !important;
                border-color: #d1d5db !important;
            }
            /* Adjust content area for embedded view */
            .tubevibe-embedded-popup .simply-content {
                max-height: 400px;
                overflow-y: auto;
            }
            /* Modern logo styling - updated for new design */
            .tubevibe-embedded-popup .simply-logo {
                display: flex !important;
                flex-direction: row !important;
                align-items: center !important;
                gap: 12px !important;
                text-decoration: none !important;
                color: inherit !important;
                transition: all 0.2s ease !important;
            }
            .tubevibe-embedded-popup .simply-logo:hover {
                transform: translateY(-1px) !important;
                filter: brightness(1.05) !important;
            }
            .tubevibe-embedded-popup .simply-logo .relative {
                position: relative !important;
            }
            .tubevibe-embedded-popup .simply-logo .absolute {
                position: absolute !important;
                top: 0 !important;
                right: 0 !important;
                bottom: 0 !important;
                left: 0 !important;
                border-radius: 8px !important;
                opacity: 0.2 !important;
            }
            .tubevibe-embedded-popup .simply-logo__text {
                font-size: 18px !important;
                font-weight: 700 !important;
                color: #ffffff !important;
                text-shadow: 0 1px 2px rgba(0, 0, 0, 0.3) !important;
            }
            .tubevibe-embedded-popup .simply-logo__tagline {
                font-size: 11px !important;
                font-weight: 400 !important;
                color: #e2e8f0 !important;
                text-shadow: none !important;
                white-space: nowrap !important;
                flex-shrink: 0 !important;
            }
            /* Ensure logo icon container is properly sized */
            .tubevibe-embedded-popup .simply-logo > div.relative {
                flex-shrink: 0 !important;
                width: 32px !important;
                height: 32px !important;
            }
            /* Header layout fixes */
            .tubevibe-embedded-popup .simply-header {
                padding: 12px 16px 8px 16px !important;
                margin-bottom: 0 !important;
            }
            .tubevibe-embedded-popup .simply-header__main {
                display: flex !important;
                flex-direction: row !important;
                align-items: center !important;
                justify-content: flex-start !important;
            }
            /* YouTube-inspired tab styling */
            .tubevibe-embedded-popup .simply-tabs {
                background: rgba(255, 255, 255, 0.8);
                border-radius: 8px;
                padding: 3px;
                margin-bottom: 8px;
                border: 1px solid rgba(0, 0, 0, 0.05);
            }
            .tubevibe-embedded-popup .simply-tab-list {
                display: flex;
                gap: 1px;
            }
            .tubevibe-embedded-popup .simply-tab {
                flex: 1;
                padding: 8px 12px;
                border: none;
                background: transparent;
                border-radius: 6px;
                font-size: 12px !important;
                font-weight: 500 !important;
                color: #606060 !important;
                cursor: pointer;
                transition: all 0.15s ease;
                display: flex;
                align-items: center;
                justify-content: center;
                gap: 4px;
                position: relative;
            }
            .tubevibe-embedded-popup .simply-tab:hover {
                background: rgba(0, 0, 0, 0.05);
                color: #404040 !important;
            }
            .tubevibe-embedded-popup .simply-tab--active {
                background: #1e40af !important;
                color: white !important;
            }
            .tubevibe-embedded-popup .simply-tab--active:hover {
                background: #1e3a8a !important;
                color: white !important;
            }
            /* Invisible scrollbar styling */
            .tubevibe-embedded-popup::-webkit-scrollbar,
            .tubevibe-transcript-scroll::-webkit-scrollbar {
                width: 0px;
                background: transparent;
            }
            .tubevibe-embedded-popup::-webkit-scrollbar-track,
            .tubevibe-transcript-scroll::-webkit-scrollbar-track {
                background: transparent;
            }
            .tubevibe-embedded-popup::-webkit-scrollbar-thumb,
            .tubevibe-transcript-scroll::-webkit-scrollbar-thumb {
                background: transparent;
                border-radius: 0px;
            }
            .tubevibe-embedded-popup::-webkit-scrollbar-thumb:hover,
            .tubevibe-transcript-scroll::-webkit-scrollbar-thumb:hover {
                background: transparent;
            }
            /* Firefox scrollbar hiding */
            .tubevibe-embedded-popup,
            .tubevibe-transcript-scroll {
                scrollbar-width: none;
                -ms-overflow-style: none;
            }
            /* Summary viewer styles */
            .tubevibe-embedded-popup .simply-summary-viewer {
                padding: 12px;
                background: rgba(255, 255, 255, 0.9);
                border-radius: 8px;
                border: 1px solid rgba(0, 0, 0, 0.05);
                margin-bottom: 12px;
            }
            .tubevibe-embedded-popup .summary-content-area {
                margin-bottom: 12px;
                padding: 12px;
                background: rgba(248, 250, 252, 0.8);
                border-radius: 6px;
                border: 1px solid rgba(0, 0, 0, 0.05);
                font-size: 11px !important;
                line-height: 1.5 !important;
                text-align: justify !important;
                max-height: 300px;
                overflow-y: auto;
            }
            .tubevibe-embedded-popup .summary-actions {
                display: flex;
                justify-content: flex-end;
                gap: 8px;
            }
            .tubevibe-embedded-popup .summary-content-area::-webkit-scrollbar {
                width: 0px;
                background: transparent;
            }
            .tubevibe-embedded-popup .summary-content-area {
                scrollbar-width: none;
                -ms-overflow-style: none;
            }
            /* Chat messages styling */
            .tubevibe-embedded-popup #chat-messages {
                font-size: 11px !important;
                flex: 1;
                overflow-y: auto;
                padding: 12px;
                min-height: 150px;
            }
            .tubevibe-embedded-popup #chat-messages div {
                font-size: 11px !important;
                line-height: 1.5 !important;
                text-align: justify !important;
            }
            /* Chat tab content styling */
            .tubevibe-embedded-popup #chat-content {
                width: 100% !important;
                box-sizing: border-box !important;
                padding: 0 !important;
                overflow: visible !important;
            }
            /* Chat interface layout */
            .tubevibe-embedded-popup #chat-interface {
                display: flex !important;
                flex-direction: column !important;
                width: 100% !important;
                min-height: 300px !important;
                box-sizing: border-box !important;
            }
            /* Chat input wrapper styling */
            .tubevibe-embedded-popup .chat-input-wrapper {
                display: flex !important;
                flex-direction: row !important;
                gap: 12px !important;
                padding: 16px !important;
                border-top: 1px solid #e5e7eb !important;
                background: #f9fafb !important;
                align-items: center !important;
                width: 100% !important;
                box-sizing: border-box !important;
                flex-shrink: 0 !important;
            }
            .tubevibe-embedded-popup #chat-input {
                flex: 1 !important;
                min-width: 0 !important;
                width: 100% !important;
                padding: 12px 16px !important;
                font-size: 14px !important;
                border: 1px solid #d1d5db !important;
                border-radius: 8px !important;
                outline: none !important;
                transition: border-color 0.2s, box-shadow 0.2s !important;
                box-sizing: border-box !important;
                height: 44px !important;
            }
            .tubevibe-embedded-popup #chat-input:focus {
                border-color: #667eea !important;
                box-shadow: 0 0 0 3px rgba(102, 126, 234, 0.1) !important;
            }
            .tubevibe-embedded-popup #chat-input::placeholder {
                color: #9ca3af !important;
            }
            /* Chat send button styling */
            .tubevibe-embedded-popup #chat-send-btn {
                flex-shrink: 0 !important;
                padding: 12px 24px !important;
                font-size: 14px !important;
                font-weight: 600 !important;
                color: white !important;
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%) !important;
                border: none !important;
                border-radius: 8px !important;
                cursor: pointer !important;
                transition: all 0.2s ease !important;
                white-space: nowrap !important;
                height: 44px !important;
                min-width: 80px !important;
                box-sizing: border-box !important;
            }
            .tubevibe-embedded-popup #chat-send-btn:hover {
                transform: translateY(-1px) !important;
                box-shadow: 0 4px 12px rgba(102, 126, 234, 0.4) !important;
            }
            .tubevibe-embedded-popup #chat-send-btn:disabled {
                opacity: 0.6 !important;
                cursor: not-allowed !important;
                transform: none !important;
                box-shadow: none !important;
            }
            /* Tab content container - ensure proper width and layout */
            .tubevibe-embedded-popup .simply-tab-content {
                width: 100% !important;
                box-sizing: border-box !important;
                overflow: visible !important;
            }
            .tubevibe-embedded-popup .simply-tab-content:not(.hidden) {
                display: block !important;
            }
            /* Enhanced transcript styling */
            .tubevibe-embedded-popup .tubevibe-transcript-scroll {
                font-feature-settings: "kern" 1, "liga" 1;
                text-rendering: optimizeLegibility;
                -webkit-font-smoothing: antialiased;
                -moz-osx-font-smoothing: grayscale;
            }
            .tubevibe-embedded-popup .tubevibe-transcript-scroll::-webkit-scrollbar {
                width: 0px;
                background: transparent;
            }
            /* Transcript segment hover effects */
            .tubevibe-embedded-popup .transcript-segment:hover {
                background: rgba(30, 64, 175, 0.02) !important;
                border-left-color: #1e40af !important;
            }
            /* Copy button enhancements */
            .tubevibe-embedded-popup button:hover {
                transform: translateY(-1px);
                box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
            }
            /* Specific button hover states */
            .tubevibe-embedded-popup #tubevibe-copy-btn:hover {
                background: rgba(30, 64, 175, 0.1) !important;
                border-color: #1e40af !important;
                color: #1e40af !important;
            }
            .tubevibe-embedded-popup #tubevibe-download-btn:hover {
                background: rgba(16, 185, 129, 0.1) !important;
                border-color: #10b981 !important;
                color: #10b981 !important;
            }
            .tubevibe-embedded-popup .tubevibe-seek-btn:hover {
                background: linear-gradient(135deg, #ff0000 0%, #cc0000 100%) !important;
                color: white !important;
                border-color: #ff0000 !important;
            }
            /* Retry and Cancel button hover states */
            .tubevibe-embedded-popup #retry-summary-btn:hover {
                background: #1e3a8a !important;
                transform: translateY(-1px);
                box-shadow: 0 2px 4px rgba(0, 0, 0, 0.1);
            }
            .tubevibe-embedded-popup #cancel-summary-btn:hover {
                background: #e5e7eb !important;
                border-color: #9ca3af !important;
                transform: translateY(-1px);
                box-shadow: 0 2px 4px rgba(0, 0, 0, 0.1);
            }
            /* Improved readability for transcript text */
            .tubevibe-embedded-popup .transcript-text {
                word-spacing: 0.05em;
                text-align: justify;
                hyphens: auto;
                -webkit-hyphens: auto;
                -ms-hyphens: auto;
            }
            /* Better visual hierarchy */
            .tubevibe-embedded-popup .transcript-header {
                background: linear-gradient(135deg, rgba(255, 255, 255, 0.9) 0%, rgba(248, 250, 252, 0.9) 100%);
                backdrop-filter: blur(10px);
                -webkit-backdrop-filter: blur(10px);
            }
        `;
        document.head.appendChild(style);
        // Also load the original popup CSS files
        this.loadPopupCSS();
    }
    async loadPopupCSS() {
        const cssFiles = [
            'styles/design-tokens.css',
            'styles/index-scoped.css',  // Use scoped version instead of index.css
            'styles/components.css',
            'styles/auth.css',
            'styles/popup.css'
        ];
        for (const cssFile of cssFiles) {
            await this.loadCSS(cssFile);
        }
    }
    // TubeVibeUI initialization removed - we're using direct content.ts methods instead
    bindEventListeners() {
        if (!this.embeddedContainer) {
            console.error('❌ Embedded container not found, cannot bind event listeners');
            return;
        }
        // Extract transcript button (search within embedded container)
        const extractBtn = this.embeddedContainer.querySelector('#extract-transcript-btn');
        if (extractBtn) {
            extractBtn.addEventListener('click', (e) => {
                e.preventDefault();
                this.handleExtractTranscript();
            });
        } else {
            console.warn('⚠️ Extract transcript button not found');
        }
        // Generate summary button (for authenticated users)
        const generateSummaryBtn = this.embeddedContainer.querySelector('#generate-summary-btn');
        if (generateSummaryBtn) {
            generateSummaryBtn.addEventListener('click', (e) => {
                e.preventDefault();
                this.handleGenerateSummary();
            });
        }
        // Regenerate summary button
        const regenerateSummaryBtn = this.embeddedContainer.querySelector('#regenerate-summary-btn');
        if (regenerateSummaryBtn) {
            regenerateSummaryBtn.addEventListener('click', (e) => {
                e.preventDefault();
                this.handleGenerateSummary();
            });
        }
        // Summary authentication buttons
        const summarySigninBtn = this.embeddedContainer.querySelector('#summary-signin-btn');
        if (summarySigninBtn) {
            summarySigninBtn.addEventListener('click', (e) => {
                e.preventDefault();
                this.handleSummarySignin();
            });
        }
        const summarySignupBtn = this.embeddedContainer.querySelector('#summary-signup-btn');
        if (summarySignupBtn) {
            summarySignupBtn.addEventListener('click', (e) => {
                e.preventDefault();
                this.handleSummarySignup();
            });
        }
        // Tab switching (simple implementation) - search within embedded container
        const tabs = this.embeddedContainer.querySelectorAll('.simply-tab');
        tabs.forEach(tab => {
            tab.addEventListener('click', (e) => {
                e.preventDefault();
                const tabName = e.target.closest('.simply-tab').getAttribute('data-tab');
                this.switchTab(tabName);
            });
        });
        // Menu button event listeners
        this.bindMenuEventListeners();
        // Chat event listeners
        this.bindChatEventListeners();
    }
    // Bind chat event listeners
    bindChatEventListeners() {
        const chatInput = this.embeddedContainer?.querySelector('#chat-input');
        const chatSendBtn = this.embeddedContainer?.querySelector('#chat-send-btn');

        if (chatSendBtn) {
            chatSendBtn.addEventListener('click', () => this.handleChatSend());
        }
        if (chatInput) {
            chatInput.addEventListener('keypress', (e) => {
                if (e.key === 'Enter') {
                    this.handleChatSend();
                }
            });
        }
    }
    // Handle sending chat message
    async handleChatSend() {
        const chatInput = this.embeddedContainer?.querySelector('#chat-input');
        const chatMessages = this.embeddedContainer?.querySelector('#chat-messages');
        const chatSendBtn = this.embeddedContainer?.querySelector('#chat-send-btn');

        if (!chatInput || !chatMessages) return;

        const query = chatInput.value.trim();
        if (!query) return;

        // Clear input and disable send button
        chatInput.value = '';
        if (chatSendBtn) {
            chatSendBtn.disabled = true;
            chatSendBtn.textContent = '...';
        }

        // Add user message to chat
        this.addChatMessage(query, 'user');

        try {
            // Send to background script for Pinecone Assistant
            const response = await chrome.runtime.sendMessage({
                type: 'CHAT_WITH_VIDEO',
                data: {
                    query: query,
                    video_id: this.currentVideoId,
                    history: this.chatHistory || []
                }
            });

            if (response && response.success) {
                // Add AI response to chat
                this.addChatMessage(response.answer || response.data?.answer || 'No response received', 'assistant');
                // Store history for context
                if (!this.chatHistory) this.chatHistory = [];
                this.chatHistory.push({ role: 'user', content: query });
                this.chatHistory.push({ role: 'assistant', content: response.answer || response.data?.answer });
            } else {
                this.addChatMessage('Sorry, I encountered an error: ' + (response?.error || 'Unknown error'), 'error');
            }
        } catch (error) {
            console.error('Chat error:', error);
            this.addChatMessage('Failed to get response: ' + error.message, 'error');
        } finally {
            if (chatSendBtn) {
                chatSendBtn.disabled = false;
                chatSendBtn.textContent = 'Send';
            }
            chatInput.focus();
        }
    }
    // Add message to chat display
    addChatMessage(text, type) {
        const chatMessages = this.embeddedContainer?.querySelector('#chat-messages');
        if (!chatMessages) return;

        const messageDiv = document.createElement('div');
        messageDiv.style.cssText = `
            padding: 8px 10px;
            margin-bottom: 6px;
            border-radius: 10px;
            font-size: 11px;
            line-height: 1.5;
            max-width: 85%;
            word-wrap: break-word;
            text-align: justify;
            ${type === 'user'
                ? 'background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; margin-left: auto; border-bottom-right-radius: 4px;'
                : type === 'error'
                    ? 'background: #fee2e2; color: #dc2626; border: 1px solid #fecaca;'
                    : 'background: white; color: #333; border: 1px solid #e5e7eb; border-bottom-left-radius: 4px;'
            }
        `;
        messageDiv.textContent = text;
        chatMessages.appendChild(messageDiv);
        chatMessages.scrollTop = chatMessages.scrollHeight;
    }
    // Show chat interface (called when video is saved)
    showChatInterface() {
        const chatNotSaved = this.embeddedContainer?.querySelector('#chat-not-saved');
        const chatInterface = this.embeddedContainer?.querySelector('#chat-interface');

        if (chatNotSaved) chatNotSaved.classList.add('hidden');
        if (chatInterface) {
            chatInterface.classList.remove('hidden');
            chatInterface.style.display = 'flex';
        }
    }
    // Bind menu event listeners
    bindMenuEventListeners() {
        // Authentication buttons
        const menuLoginBtn = this.embeddedContainer.querySelector('#menu-login-btn');
        const menuSignupBtn = this.embeddedContainer.querySelector('#menu-signup-btn');
        const menuLogoutBtn = this.embeddedContainer.querySelector('#menu-logout-btn');
        // Quick action buttons
        const menuDashboardBtn = this.embeddedContainer.querySelector('#menu-dashboard-btn');
        const menuHistoryBtn = this.embeddedContainer.querySelector('#menu-history-btn');
        // Settings buttons
        const menuSettingsBtn = this.embeddedContainer.querySelector('#menu-settings-btn');
        const menuHelpBtn = this.embeddedContainer.querySelector('#menu-help-btn');
        // Upgrade button
        const menuUpgradeBtn = this.embeddedContainer.querySelector('#menu-upgrade-btn');

        const openAuth = (mode) => {
            // Show auth form in menu tab instead of switching to summary
            this.showInlineAuthForm(mode, '#menu-content');
        };

        if (menuLoginBtn) {
            menuLoginBtn.addEventListener('click', () => {
                openAuth('login');
            });
        }
        if (menuSignupBtn) {
            menuSignupBtn.addEventListener('click', () => {
                openAuth('signup');
            });
        }
        if (menuLogoutBtn) {
            menuLogoutBtn.addEventListener('click', () => {
                this.handleLogout();
            });
        }
        if (menuDashboardBtn) {
            menuDashboardBtn.addEventListener('click', () => {
                this.handleOpenDashboard();
            });
        }
        if (menuHistoryBtn) {
            menuHistoryBtn.addEventListener('click', () => {
                this.showHistoryModal();
            });
        }
        if (menuSettingsBtn) {
            menuSettingsBtn.addEventListener('click', () => {
                this.showSettingsModal();
            });
        }
        if (menuHelpBtn) {
            menuHelpBtn.addEventListener('click', () => {
                this.handleOpenHelp();
            });
        }
        if (menuUpgradeBtn) {
            menuUpgradeBtn.addEventListener('click', () => {
                this.handleUpgrade();
            });
        }

        // Check subscription status and show/hide upgrade banner
        this.updateUpgradeBannerVisibility();
    }
    // Handle summary sign in button
    async handleSummarySignin() {
        // Show inline login form
        this.showInlineAuthForm('login');
    }
    // Handle summary sign up button
    async handleSummarySignup() {
        // Show inline signup form
        this.showInlineAuthForm('signup');
    }
    // Show inline authentication form
    showInlineAuthForm(type, targetSelector = '#summary-content') {
        const targetContent = this.embeddedContainer?.querySelector(targetSelector);
        if (!targetContent) return;

        // Store the current target for back button functionality
        this.currentAuthTarget = targetSelector;
        const formHTML = type === 'login' ? this.getLoginFormHTML() : this.getSignupFormHTML();
        this.safeSetHTML(targetContent, `
            <div style="padding: 16px;">
                <div style="display: flex; align-items: center; gap: 8px; margin-bottom: 16px;">
                    <button id="back-to-auth-prompt" style="background: none; border: none; cursor: pointer; color: #666; font-size: 18px;">
                        ←
                    </button>
                    <h3 style="margin: 0; font-size: 18px; color: #333;">${type === 'login' ? 'Sign In' : 'Create Account'}</h3>
                </div>
                ${formHTML}
            </div>
        `);
        // Bind form events
        this.bindAuthFormEvents(type);
    }
    // Get login form HTML
    getLoginFormHTML() {
        return `
            <form id="auth-form" class="simply-auth-form">
                <!-- Google OAuth Button -->
                <button type="button" id="google-auth-btn" class="simply-auth-social__btn">
                    <svg width="18" height="18" viewBox="0 0 24 24">
                        <path fill="#4285F4" d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z"/>
                        <path fill="#34A853" d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z"/>
                        <path fill="#FBBC05" d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z"/>
                        <path fill="#EA4335" d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z"/>
                    </svg>
                    Continue with Google
                </button>

                <!-- Divider -->
                <div class="simply-auth-form__divider">
                    <span>or</span>
                </div>

                <!-- Email/Password Form -->
                <div class="simply-input-group">
                    <label class="simply-input-label">Email</label>
                    <input type="email" id="auth-email" class="simply-input" required />
                </div>
                <div class="simply-input-group">
                    <label class="simply-input-label">Password</label>
                    <input type="password" id="auth-password" class="simply-input" required />
                </div>
                <div style="text-align: right; margin-bottom: 12px;">
                    <button type="button" id="forgot-password-btn" class="simply-auth-form__link" style="font-size: 13px;">
                        Forgot Password?
                    </button>
                </div>
                <div id="auth-error" class="simply-input-error" style="display: none;"></div>
                <button type="submit" id="auth-submit" class="simply-btn simply-btn--primary simply-w-full">
                    Sign In
                </button>
                <div class="simply-auth-form__footer">
                    <p>Don't have an account?
                        <button type="button" id="switch-to-signup" class="simply-auth-form__link">Sign Up</button>
                    </p>
                </div>

                <!-- Magic Link Option -->
                <div class="simply-auth-divider">
                    <span>or</span>
                </div>

                <button type="button" id="magic-link-btn" class="simply-btn simply-btn--outline" style="width: 100%; margin-top: 12px;">
                    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                        <path d="M4 4h16c1.1 0 2 .9 2 2v12c0 1.1-.9 2-2 2H4c-1.1 0-2-.9-2-2V6c0-1.1.9-2 2-2z"></path>
                        <polyline points="22,6 12,13 2,6"></polyline>
                    </svg>
                    <span>Send Magic Link</span>
                </button>
            </form>
        `;
    }
    // Get signup form HTML
    getSignupFormHTML() {
        return `
            <form id="auth-form" class="simply-auth-form">
                <!-- Google OAuth Button -->
                <button type="button" id="google-auth-btn" class="simply-auth-social__btn">
                    <svg width="18" height="18" viewBox="0 0 24 24">
                        <path fill="#4285F4" d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z"/>
                        <path fill="#34A853" d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z"/>
                        <path fill="#FBBC05" d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z"/>
                        <path fill="#EA4335" d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z"/>
                    </svg>
                    Continue with Google
                </button>

                <!-- Divider -->
                <div class="simply-auth-form__divider">
                    <span>or</span>
                </div>

                <!-- Name Fields Row -->
                <div class="simply-input-row">
                    <div class="simply-input-group">
                        <label class="simply-input-label" for="auth-firstname">First Name</label>
                        <input type="text" id="auth-firstname" class="simply-input" required />
                    </div>
                    <div class="simply-input-group">
                        <label class="simply-input-label" for="auth-lastname">Last Name</label>
                        <input type="text" id="auth-lastname" class="simply-input" required />
                    </div>
                </div>

                <!-- Email Field -->
                <div class="simply-input-group">
                    <label class="simply-input-label" for="auth-email">Email</label>
                    <input type="email" id="auth-email" class="simply-input" required />
                </div>

                <!-- Password Field -->
                <div class="simply-input-group">
                    <label class="simply-input-label" for="auth-password">Password</label>
                    <input type="password" id="auth-password" class="simply-input" required minlength="8" />
                </div>

                <!-- Confirm Password Field -->
                <div class="simply-input-group">
                    <label class="simply-input-label" for="auth-confirm-password">Confirm Password</label>
                    <input type="password" id="auth-confirm-password" class="simply-input" required />
                </div>

                <div id="auth-error" class="simply-auth-error"></div>

                <button type="submit" id="auth-submit" class="simply-btn simply-btn--primary simply-btn--full">
                    Create Account
                </button>

                <div class="simply-auth-form__footer">
                    Already have an account?
                    <button type="button" id="switch-to-login" class="simply-auth-form__link">
                        Sign In
                    </button>
                </div>
            </form>
        `;
    }
    // Bind authentication form events
    bindAuthFormEvents(type) {
        const form = this.embeddedContainer?.querySelector('#auth-form');
        const backBtn = this.embeddedContainer?.querySelector('#back-to-auth-prompt');
        const switchBtn = this.embeddedContainer?.querySelector(type === 'login' ? '#switch-to-signup' : '#switch-to-login');
        const googleBtn = this.embeddedContainer?.querySelector('#google-auth-btn');
        
        if (form) {
            form.addEventListener('submit', (e) => {
                e.preventDefault();
                this.handleAuthSubmit(type);
            });
        }
        if (backBtn) {
            backBtn.addEventListener('click', () => {
                if (this.currentAuthTarget === '#menu-content') {
                    this.restoreMenuContent();
                } else if (this.currentAuthTarget === '#summary-content') {
                    this.showSummaryAuthPrompt(); // Go back to auth prompt in summary tab
                } else {
                    this.updateEmbeddedAuthUI(); // Go back to auth prompt
                }
            });
        }
        if (switchBtn) {
            switchBtn.addEventListener('click', () => {
                this.showInlineAuthForm(type === 'login' ? 'signup' : 'login', this.currentAuthTarget);
            });
        }
        if (googleBtn) {
            googleBtn.addEventListener('click', () => {
                this.handleGoogleAuth();
            });

            // Add hover effect
            googleBtn.addEventListener('mouseenter', () => {
                googleBtn.style.background = '#f8f9fa';
                googleBtn.style.borderColor = '#00C2B8';
                googleBtn.style.boxShadow = '0 2px 4px rgba(0,194,184,0.1)';
            });

            googleBtn.addEventListener('mouseleave', () => {
                googleBtn.style.background = 'white';
                googleBtn.style.borderColor = '#ddd';
                googleBtn.style.boxShadow = 'none';
            });
        }

        // Magic link button event listener (only for login form)
        if (type === 'login') {
            const magicLinkBtn = this.embeddedContainer?.querySelector('#magic-link-btn');
            if (magicLinkBtn) {
                magicLinkBtn.addEventListener('click', () => this.handleMagicLinkRequest());
            }

            // Forgot password button event listener
            const forgotPasswordBtn = this.embeddedContainer?.querySelector('#forgot-password-btn');
            if (forgotPasswordBtn) {
                forgotPasswordBtn.addEventListener('click', () => this.showForgotPasswordForm());
            }
        }
    }

    // Handle magic link request
    async handleMagicLinkRequest() {
        const emailInput = this.embeddedContainer?.querySelector('#auth-email');
        const email = emailInput?.value?.trim();
        const errorDiv = this.embeddedContainer?.querySelector('#auth-error');

        if (!email) {
            this.showAuthFormError('Please enter your email address first.');
            return;
        }

        // Validate email format
        const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
        if (!emailRegex.test(email)) {
            this.showAuthFormError('Please enter a valid email address.');
            return;
        }

        // Show loading state
        const magicLinkBtn = this.embeddedContainer?.querySelector('#magic-link-btn');
        if (!magicLinkBtn) return;

        const originalHTML = magicLinkBtn.innerHTML;
        magicLinkBtn.innerHTML = '<span class="simply-spinner"></span> Sending...';
        magicLinkBtn.disabled = true;

        try {
            // Check extension context before making API call
            if (!(await this.isContextValid())) {
                throw new Error('Extension was reloaded. Please refresh the page and try again.');
            }

            const response = await chrome.runtime.sendMessage({
                type: 'REQUEST_MAGIC_LINK',
                data: { email }
            });

            if (response && response.success) {
                this.showMagicLinkSentMessage(email);
            } else {
                const errorMessage = response?.error || 'Failed to send magic link. Please try again.';
                this.showAuthFormError(errorMessage);
                magicLinkBtn.innerHTML = originalHTML;
                magicLinkBtn.disabled = false;
            }
        } catch (error) {
            console.error('Magic link request error:', error);
            let errorMessage = 'Failed to send magic link. Please try again.';
            if (error.message.includes('Extension context invalidated') || error.message.includes('Extension was reloaded')) {
                errorMessage = 'Extension was reloaded. Please refresh the page and try again.';
            }
            this.showAuthFormError(errorMessage);
            magicLinkBtn.innerHTML = originalHTML;
            magicLinkBtn.disabled = false;
        }
    }

    // Show magic link sent confirmation message
    showMagicLinkSentMessage(email) {
        const targetContent = this.embeddedContainer?.querySelector(this.currentAuthTarget || '#summary-content');
        if (!targetContent) return;

        // Safely escape the email for display
        const safeEmail = this.escapeHtml(email);

        this.safeSetHTML(targetContent, `
            <div style="padding: 16px;">
                <div class="simply-auth-success" style="text-align: center; padding: 24px;">
                    <div style="width: 48px; height: 48px; margin: 0 auto 16px; background: #ecfdf5; border-radius: 50%; display: flex; align-items: center; justify-content: center;">
                        <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="#10b981" stroke-width="2">
                            <path d="M4 4h16c1.1 0 2 .9 2 2v12c0 1.1-.9 2-2 2H4c-1.1 0-2-.9-2-2V6c0-1.1.9-2 2-2z"></path>
                            <polyline points="22,6 12,13 2,6"></polyline>
                        </svg>
                    </div>
                    <h3 style="margin: 0 0 8px; font-size: 16px; font-weight: 600; color: #1e293b;">Check your email</h3>
                    <p style="margin: 0 0 16px; font-size: 14px; color: #64748b;">
                        We've sent a magic link to<br>
                        <strong style="color: #1e293b;">${safeEmail}</strong>
                    </p>
                    <p style="margin: 0 0 24px; font-size: 13px; color: #94a3b8;">
                        Click the link in the email to sign in. The link will expire in 30 minutes.
                    </p>
                    <button type="button" id="back-to-login" class="simply-btn simply-btn--outline" style="padding: 8px 16px; font-size: 13px;">
                        Back to Sign In
                    </button>
                </div>
            </div>
        `);

        const backBtn = targetContent.querySelector('#back-to-login');
        if (backBtn) {
            backBtn.addEventListener('click', () => {
                this.showInlineAuthForm('login', this.currentAuthTarget);
            });
        }
    }

    // Show forgot password form
    showForgotPasswordForm() {
        const targetContent = this.embeddedContainer?.querySelector(this.currentAuthTarget || '#summary-content');
        if (!targetContent) return;

        // Pre-fill email if available from login form
        const currentEmail = this.embeddedContainer?.querySelector('#auth-email')?.value || '';

        this.safeSetHTML(targetContent, `
            <div style="padding: 16px;">
                <div style="display: flex; align-items: center; gap: 8px; margin-bottom: 16px;">
                    <button id="back-to-login-from-forgot" style="background: none; border: none; cursor: pointer; color: #666; font-size: 18px;">
                        ←
                    </button>
                    <h3 style="margin: 0; font-size: 18px; color: #333;">Reset Password</h3>
                </div>
                <p style="margin: 0 0 16px; font-size: 14px; color: #64748b;">
                    Enter your email address and we'll send you a link to reset your password.
                </p>
                <form id="forgot-password-form" class="simply-auth-form">
                    <div class="simply-input-group">
                        <label class="simply-input-label">Email</label>
                        <input type="email" id="forgot-email" class="simply-input" required value="${this.escapeHtml(currentEmail)}" />
                    </div>
                    <div id="forgot-error" class="simply-input-error" style="display: none;"></div>
                    <button type="submit" id="forgot-submit" class="simply-btn simply-btn--primary simply-w-full">
                        Send Reset Link
                    </button>
                </form>
            </div>
        `);

        // Bind events
        const backBtn = targetContent.querySelector('#back-to-login-from-forgot');
        if (backBtn) {
            backBtn.addEventListener('click', () => {
                this.showInlineAuthForm('login', this.currentAuthTarget);
            });
        }

        const form = targetContent.querySelector('#forgot-password-form');
        if (form) {
            form.addEventListener('submit', (e) => {
                e.preventDefault();
                this.handleForgotPasswordRequest();
            });
        }
    }

    // Handle forgot password request
    async handleForgotPasswordRequest() {
        const emailInput = this.embeddedContainer?.querySelector('#forgot-email');
        const email = emailInput?.value?.trim();
        const errorDiv = this.embeddedContainer?.querySelector('#forgot-error');
        const submitBtn = this.embeddedContainer?.querySelector('#forgot-submit');

        if (!email) {
            if (errorDiv) {
                errorDiv.textContent = 'Please enter your email address.';
                errorDiv.style.display = 'block';
            }
            return;
        }

        // Validate email format
        const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
        if (!emailRegex.test(email)) {
            if (errorDiv) {
                errorDiv.textContent = 'Please enter a valid email address.';
                errorDiv.style.display = 'block';
            }
            return;
        }

        // Show loading state
        if (!submitBtn) return;
        const originalText = submitBtn.textContent;
        submitBtn.textContent = 'Sending...';
        submitBtn.disabled = true;

        try {
            // Check extension context before making API call
            if (!(await this.isContextValid())) {
                throw new Error('Extension was reloaded. Please refresh the page and try again.');
            }

            const response = await chrome.runtime.sendMessage({
                type: 'FORGOT_PASSWORD',
                data: { email }
            });

            if (response && response.success) {
                this.showPasswordResetSentMessage(email);
            } else {
                const errorMessage = response?.error || 'Failed to send reset email. Please try again.';
                if (errorDiv) {
                    errorDiv.textContent = errorMessage;
                    errorDiv.style.display = 'block';
                }
                submitBtn.textContent = originalText;
                submitBtn.disabled = false;
            }
        } catch (error) {
            console.error('Forgot password request error:', error);
            let errorMessage = 'Failed to send reset email. Please try again.';
            if (error.message.includes('Extension context invalidated') || error.message.includes('Extension was reloaded')) {
                errorMessage = 'Extension was reloaded. Please refresh the page and try again.';
            }
            if (errorDiv) {
                errorDiv.textContent = errorMessage;
                errorDiv.style.display = 'block';
            }
            submitBtn.textContent = originalText;
            submitBtn.disabled = false;
        }
    }

    // Show password reset email sent confirmation message
    showPasswordResetSentMessage(email) {
        const targetContent = this.embeddedContainer?.querySelector(this.currentAuthTarget || '#summary-content');
        if (!targetContent) return;

        // Safely escape the email for display
        const safeEmail = this.escapeHtml(email);

        this.safeSetHTML(targetContent, `
            <div style="padding: 16px;">
                <div class="simply-auth-success" style="text-align: center; padding: 24px;">
                    <div style="width: 48px; height: 48px; margin: 0 auto 16px; background: #ecfdf5; border-radius: 50%; display: flex; align-items: center; justify-content: center;">
                        <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="#10b981" stroke-width="2">
                            <path d="M9 12l2 2 4-4"></path>
                            <circle cx="12" cy="12" r="10"></circle>
                        </svg>
                    </div>
                    <h3 style="margin: 0 0 8px; font-size: 16px; font-weight: 600; color: #1e293b;">Check your email</h3>
                    <p style="margin: 0 0 16px; font-size: 14px; color: #64748b;">
                        We've sent a password reset link to<br>
                        <strong style="color: #1e293b;">${safeEmail}</strong>
                    </p>
                    <p style="margin: 0 0 24px; font-size: 13px; color: #94a3b8;">
                        Click the link in the email to reset your password. The link will expire in 30 minutes.
                    </p>
                    <button type="button" id="back-to-login-from-reset" class="simply-btn simply-btn--outline" style="padding: 8px 16px; font-size: 13px;">
                        Back to Sign In
                    </button>
                </div>
            </div>
        `);

        const backBtn = targetContent.querySelector('#back-to-login-from-reset');
        if (backBtn) {
            backBtn.addEventListener('click', () => {
                this.showInlineAuthForm('login', this.currentAuthTarget);
            });
        }
    }

    // Show error message in auth form
    showAuthFormError(message) {
        const errorDiv = this.embeddedContainer?.querySelector('#auth-error');
        if (errorDiv) {
            errorDiv.style.display = 'block';
            errorDiv.textContent = message;
        }
    }

    // Escape HTML to prevent XSS
    escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }

    // Check if extension context is still valid
    async isContextValid() {
        try {
            await chrome.runtime.sendMessage({type: 'PING'});
            return true;
        } catch (error) {
            return false;
        }
    }

    // Handle authentication form submission
    async handleAuthSubmit(type) {
        const submitBtn = this.embeddedContainer?.querySelector('#auth-submit');
        const errorDiv = this.embeddedContainer?.querySelector('#auth-error');
        if (!submitBtn) return;
        // Show loading state
        submitBtn.disabled = true;
        submitBtn.textContent = type === 'login' ? 'Signing In...' : 'Creating Account...';
        try {
            const formData = this.getAuthFormData(type);
            // Validate form data with InputValidator if available
            if (window.InputValidator && window.FeatureFlags?.isEnabled('INPUT_VALIDATION_ENABLED')) {
                // Validate email
                const emailValidation = window.InputValidator.validate(formData.email, 'email');
                if (!emailValidation.isValid) {
                    throw new Error(emailValidation.error);
                }
                formData.email = emailValidation.sanitized;
                // Validate password
                const passwordOptions = type === 'signup' ? { checkStrength: true } : {};
                const passwordValidation = window.InputValidator.validate(formData.password, 'password', passwordOptions);
                if (!passwordValidation.isValid) {
                    throw new Error(passwordValidation.error);
                }
                // Validate signup fields
            if (type === 'signup') {
                    // Check password match first
                if (formData.password !== formData.confirmPassword) {
                    throw new Error('Passwords do not match');
                }
                    // Validate names
                    const firstNameValidation = window.InputValidator.validate(formData.first_name, 'name');
                    if (!firstNameValidation.isValid) {
                        throw new Error('First name: ' + firstNameValidation.error);
                    }
                    formData.first_name = firstNameValidation.sanitized;
                    const lastNameValidation = window.InputValidator.validate(formData.last_name, 'name');
                    if (!lastNameValidation.isValid) {
                        throw new Error('Last name: ' + lastNameValidation.error);
                    }
                    formData.last_name = lastNameValidation.sanitized;
                }
            } else {
                // Fallback validation if InputValidator not available
                if (type === 'signup') {
                    if (formData.password !== formData.confirmPassword) {
                        throw new Error('Passwords do not match');
                    }
                }
            }
            
            // Check extension context before making API call
            if (!(await this.isContextValid())) {
                throw new Error('Extension was reloaded. Please refresh the page and try again.');
            }
            
            // Call the authentication API with context validation
            let authResponse;
            try {
                authResponse = await chrome.runtime.sendMessage({
                    type: type === 'login' ? 'USER_LOGIN' : 'USER_SIGNUP',
                    data: formData
                });
            } catch (contextError) {
                if (contextError.message.includes('Extension context invalidated')) {
                    // Extension was reloaded - show user-friendly message
                    throw new Error('Extension was reloaded. Please refresh the page and try again.');
                }
                throw contextError; // Re-throw other errors
            }

            // Guard against undefined response (background script didn't respond)
            if (!authResponse) {
                throw new Error('No response from extension. Please refresh the page and try again.');
            }

            if (authResponse.success) {
                // Check if user requires email verification
                if (authResponse.requiresVerification) {
                    console.log('📧 User requires email verification');
                    this.showEmailVerificationMessage(authResponse.user, authResponse.message);
                } else {
                    // Handle successful authentication with unified method
                    await this.handleSuccessfulAuthentication(authResponse.user, type);
                }
            } else {
                throw new Error(authResponse.error || 'Authentication failed');
            }
        } catch (error) {
            console.error('❌ Authentication error:', error);
            if (errorDiv) {
                // Handle specific error cases with user-friendly messages
                let errorMessage = error.message;
                
                if (error.message.includes('already exists')) {
                    errorMessage = 'An account with this email already exists. Please try signing in instead.';
                    
                    // Also show a "Switch to Sign In" button
                    errorDiv.innerHTML = `
                        <div style="color: #d32f2f; margin-bottom: 12px;">${errorMessage}</div>
                        <button type="button" id="switch-to-signin-error" style="
                            background: #1976d2; 
                            color: white; 
                            border: none; 
                            padding: 8px 16px; 
                            border-radius: 4px; 
                            cursor: pointer; 
                            font-size: 12px;
                        ">
                            Switch to Sign In
                        </button>
                    `;
                    
                    // Add click handler for the switch button
                    const switchBtn = errorDiv.querySelector('#switch-to-signin-error');
                    if (switchBtn) {
                        switchBtn.addEventListener('click', () => {
                            this.showInlineAuthForm('login');
                        });
                    }
                } else {
                    errorDiv.textContent = errorMessage;
                }
                
                errorDiv.style.display = 'block';
            }
        } finally {
            // Reset button state
            submitBtn.disabled = false;
            submitBtn.textContent = type === 'login' ? 'Sign In' : 'Create Account';
        }
    }
    // Get form data
    getAuthFormData(type) {
        const email = this.embeddedContainer?.querySelector('#auth-email')?.value || '';
        const password = this.embeddedContainer?.querySelector('#auth-password')?.value || '';
        const data = { email, password };
        if (type === 'signup') {
            data.first_name = this.embeddedContainer?.querySelector('#auth-firstname')?.value || '';
            data.last_name = this.embeddedContainer?.querySelector('#auth-lastname')?.value || '';
            data.confirmPassword = this.embeddedContainer?.querySelector('#auth-confirm-password')?.value || '';
        }
        return data;
    }
    // Handle Google OAuth authentication
    async handleGoogleAuth() {
        const googleBtn = this.embeddedContainer?.querySelector('#google-auth-btn');
        const errorDiv = this.embeddedContainer?.querySelector('#auth-error');
        
        if (!googleBtn) return;
        
        try {
            // Show loading state
            googleBtn.disabled = true;
            googleBtn.innerHTML = `
                <div style="display: flex; align-items: center; gap: 8px;">
                    <div style="width: 16px; height: 16px; border: 2px solid #ddd; border-top: 2px solid #666; border-radius: 50%; animation: spin 1s linear infinite;"></div>
                    Signing in with Google...
                </div>
            `;
            
            // Hide any existing errors
            if (errorDiv) {
                errorDiv.style.display = 'none';
            }
            
            console.log('🔐 Starting Google OAuth from embedded popup...');
            
            // Send Google auth request to background script
            const response = await chrome.runtime.sendMessage({
                type: 'GOOGLE_AUTH'
            });
            
            if (response.success) {
                console.log('✅ Google authentication successful:', response.user?.email);
                
                // Show success message briefly
                googleBtn.innerHTML = `
                    <div style="display: flex; align-items: center; gap: 8px;">
                        <div style="color: #00C2B8;">✓</div>
                        Successfully signed in!
                    </div>
                `;
                
                // Store the user info and trigger authenticated state
                this.currentUser = response.user;
                
                // Wait a moment to show success, then switch to authenticated UI
                setTimeout(async () => {
                    await this.handleSuccessfulAuthentication(response.user, 'google');
                }, 1500);
                
            } else {
                throw new Error(response.error || 'Google authentication failed');
            }
            
        } catch (error) {
            console.error('❌ Google authentication error:', error);
            
            // Show error message
            if (errorDiv) {
                errorDiv.textContent = error.message;
                errorDiv.style.display = 'block';
            }
            
            // Reset button state
            googleBtn.innerHTML = `
                <svg width="18" height="18" viewBox="0 0 24 24">
                    <path fill="#4285F4" d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z"/>
                    <path fill="#34A853" d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z"/>
                    <path fill="#FBBC05" d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z"/>
                    <path fill="#EA4335" d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z"/>
                </svg>
                Continue with Google
            `;
            
        } finally {
            // Re-enable button
            googleBtn.disabled = false;
        }
    }

    // Show email verification message after successful signup
    showEmailVerificationMessage(user, message) {
        console.log('📧 Showing email verification message for:', user?.email);
        
        // Try multiple possible selectors for the auth container
        let authWrapper = this.embeddedContainer?.querySelector('#auth-wrapper');
        if (!authWrapper) {
            authWrapper = this.embeddedContainer?.querySelector('#auth-form');
        }
        if (!authWrapper) {
            authWrapper = this.embeddedContainer?.querySelector('#auth-section');
        }
        
        if (!authWrapper) {
            console.error('❌ No auth container found! Available elements:', 
                this.embeddedContainer ? Array.from(this.embeddedContainer.querySelectorAll('[id]')).map(el => el.id) : 'no embeddedContainer');
            return;
        }
        
        console.log('✅ Found auth-wrapper, proceeding with verification message');
        
        // Create verification message HTML
        const verificationHTML = `
            <div id="verification-message" style="text-align: center; padding: 20px;">
                <div style="background: #e8f5e9; border: 1px solid #4caf50; border-radius: 8px; padding: 20px; margin-bottom: 16px;">
                    <div style="color: #2e7d32; font-size: 20px; margin-bottom: 8px;">📧</div>
                    <h3 style="color: #2e7d32; margin: 0 0 12px 0; font-size: 16px;">Account Created Successfully!</h3>
                    <p style="color: #2e7d32; margin: 0 0 8px 0; font-size: 14px;">
                        ${message || 'Please check your email to verify your account.'}
                    </p>
                    <p style="color: #666; margin: 0; font-size: 12px;">
                        Email sent to: <strong>${user?.email}</strong>
                    </p>
                </div>
                
                <div style="background: #f5f5f5; border-radius: 8px; padding: 16px; margin-bottom: 16px;">
                    <h4 style="margin: 0 0 8px 0; font-size: 14px; color: #333;">Next Steps:</h4>
                    <ol style="margin: 0; padding-left: 20px; font-size: 12px; color: #666; text-align: left;">
                        <li>Check your email inbox (and spam folder)</li>
                        <li>Click the verification link in the email</li>
                        <li>Return here and sign in with your credentials</li>
                    </ol>
                </div>
                
                <div style="display: flex; gap: 8px; justify-content: center;">
                    <button id="back-to-signin" class="simply-btn simply-btn--primary" style="flex: 1; max-width: 120px;">
                        Sign In
                    </button>
                    <button id="resend-verification" class="simply-btn simply-btn--secondary" style="flex: 1; max-width: 120px;">
                        Resend Email
                    </button>
                </div>
            </div>
        `;
        
        // Replace auth form with verification message
        this.safeSetHTML(authWrapper, verificationHTML);
        console.log('✅ Verification message HTML set successfully');
        
        // Add event listeners
        const backToSigninBtn = authWrapper.querySelector('#back-to-signin');
        const resendBtn = authWrapper.querySelector('#resend-verification');
        
        if (backToSigninBtn) {
            backToSigninBtn.addEventListener('click', () => {
                this.showInlineAuthForm('login');
            });
        }
        
        if (resendBtn) {
            resendBtn.addEventListener('click', async () => {
                // TODO: Implement resend verification email functionality
                resendBtn.textContent = 'Sent!';
                resendBtn.disabled = true;
                setTimeout(() => {
                    resendBtn.textContent = 'Resend Email';
                    resendBtn.disabled = false;
                }, 3000);
            });
        }
    }
    
    // Handle successful authentication and update UI accordingly
    async handleSuccessfulAuthentication(user, provider = 'email') {
        try {
            console.log(`✅ Handling successful ${provider} authentication for:`, user?.email);

            // Store user info locally
            this.currentUser = user;

            // Check if we're currently showing an auth form and hide it
            const authWrapper = this.embeddedContainer?.querySelector('#auth-wrapper');
            if (authWrapper) {
                console.log('🔄 Hiding authentication form...');
                authWrapper.style.display = 'none';
            }

            // Restore the appropriate content based on where the login form was displayed
            console.log('🔄 Restoring UI after login from:', this.currentAuthTarget || 'unknown');

            if (this.currentAuthTarget === '#menu-content') {
                // User logged in from the menu - restore menu content
                console.log('🔄 Restoring menu content...');
                this.restoreMenuContent();
            } else {
                // User logged in from summary tab (default) - restore summary content
                console.log('🔄 Restoring summary tab content...');
                this.restoreSummaryTabContent();

                // Re-bind summary events after restoring content
                this.bindSummaryEvents();
            }

            // Ensure proper summary content structure exists and show authenticated state
            const summaryContent = this.embeddedContainer?.querySelector('#summary-content');
            if (summaryContent) {
                // Re-query the elements after restoration
                const summaryAuthRequired = summaryContent.querySelector('#summary-auth-required');
                const summaryReady = summaryContent.querySelector('#summary-ready');

                // Switch to authenticated view
                if (summaryAuthRequired) {
                    summaryAuthRequired.classList.add('hidden');
                    console.log('🔄 Hidden auth-required section');
                }
                if (summaryReady) {
                    summaryReady.classList.remove('hidden');
                    console.log('🔄 Shown summary-ready section');
                }

                console.log('🎯 Switched to authenticated summary view');
            } else {
                console.warn('⚠️ Summary content element not found');
            }

            // Force refresh authentication status for menu and other UI elements
            await this.updateEmbeddedAuthUI();

            // Show success message to user
            this.showSuccess('Successfully signed in!');

            console.log('🔄 Authentication UI updated successfully');

        } catch (error) {
            console.error('❌ Error handling successful authentication:', error);
            // Show error to user instead of swallowing it
            this.showError('Login succeeded but failed to update UI: ' + error.message);
        }
    }

    // Authenticate user using the existing system via background script
    async authenticateUser(type, formData) {
        try {
            const messageType = type === 'login' ? 'USER_LOGIN' : 'USER_SIGNUP';
            // Send authentication request to background script
            const response = await chrome.runtime.sendMessage({
                type: messageType,
                data: formData
            });
            if (!response.success) {
                throw new Error(response.error || type + ' failed');
            }
            
            // Don't call handleSuccessfulAuthentication here - let the handleAuthSubmit flow handle it
            // to avoid conflicts with restoreSummaryTabContent()
            
            return true;
        } catch (error) {
            console.error('❌ ' + type + ' error:', error);
            throw error;
        }
    }
    // Restore the original summary tab content after successful authentication
    restoreSummaryTabContent() {
        const summaryContent = this.embeddedContainer?.querySelector('#summary-content');
        if (!summaryContent) return;
        // Restore the original summary tab content structure
        this.safeSetHTML(summaryContent, `
            <!-- Authentication Required State -->
            <div id="summary-auth-required" class="simply-empty-state">
                <div class="simply-empty-state__icon">
                    <svg width="48" height="48" viewBox="0 0 24 24" fill="currentColor" style="color: #ff0000;">
                        <path d="M12,1A11,11 0 0,0 1,12A11,11 0 0,0 12,23A11,11 0 0,0 23,12A11,11 0 0,0 12,1M12,3A9,9 0 0,1 21,12A9,9 0 0,1 12,21A9,9 0 0,1 3,12A9,9 0 0,1 12,3M12,17A1,1 0 0,1 13,18A1,1 0 0,1 12,19A1,1 0 0,1 11,18A1,1 0 0,1 12,17M12,7A1,1 0 0,1 13,8V14A1,1 0 0,1 12,15A1,1 0 0,1 11,14V8A1,1 0 0,1 12,7Z"/>
                    </svg>
                </div>
                <h3 class="simply-empty-state__title">Authentication Required</h3>
                <p class="simply-empty-state__description">Sign in to generate AI summaries of video content with advanced features.</p>
                <div class="simply-flex simply-flex-col simply-gap-3 simply-mb-4">
                    <button id="summary-signin-btn" class="simply-btn simply-btn--primary simply-w-full">
                        <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor" class="simply-mr-1">
                            <path d="M12,4A4,4 0 0,1 16,8A4,4 0 0,1 12,12A4,4 0 0,1 8,8A4,4 0 0,1 12,4M12,14C16.42,14 20,15.79 20,18V20H4V18C4,15.79 7.58,14 12,14Z"/>
                        </svg>
                        Sign In
                    </button>
                    <button id="summary-signup-btn" class="simply-btn simply-btn--secondary simply-w-full">
                        <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor" class="simply-mr-1">
                            <path d="M15,14C12.33,14 7,15.33 7,18V20H23V18C23,15.33 17.67,14 15,14M6,10V7H4V10H1V12H4V15H6V12H9V10M15,12A4,4 0 0,0 19,8A4,4 0 0,0 15,4A4,4 0 0,0 11,8A4,4 0 0,0 15,12Z"/>
                        </svg>
                        Sign Up
                    </button>
                </div>
                <div style="margin-top: 16px; padding: 12px; background: rgba(255, 0, 0, 0.05); border-radius: 6px; border: 1px solid rgba(255, 0, 0, 0.1);">
                    <div style="font-size: 11px; color: #666; text-align: center;">
                        <strong>Free Account Benefits:</strong><br>
                        • 1 video summary per week<br>
                        • AI-powered content analysis<br>
                        • Save transcripts and summaries
                    </div>
                </div>
            </div>
            <!-- Summary Ready State (for authenticated users) -->
            <div id="summary-ready" class="simply-empty-state hidden">
                <div class="simply-empty-state__icon">
                    <svg width="48" height="48" viewBox="0 0 24 24" fill="currentColor">
                        <path d="M14,2H6A2,2 0 0,0 4,4V20A2,2 0 0,0 6,22H18A2,2 0 0,0 20,20V8L14,2M18,20H6V4H13V9H18V20Z"/>
                    </svg>
                </div>
                <h3 class="simply-empty-state__title">Generate Summary</h3>
                <p class="simply-empty-state__description">Extract the transcript first, then generate an AI summary of the video content.</p>
                <div class="simply-flex simply-flex-col simply-gap-3 simply-mb-4">
                    <button id="generate-summary-btn" class="simply-btn simply-btn--primary simply-w-full">
                        <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor" class="simply-mr-1">
                            <path d="M14,2H6A2,2 0 0,0 4,4V20A2,2 0 0,0 6,22H18A2,2 0 0,0 20,20V8L14,2M18,20H6V4H13V9H18V20Z"/>
                        </svg>
                        Generate Summary
                    </button>
                </div>
            </div>
            <!-- Summary Display -->
            <div id="summary-display" class="simply-summary-viewer hidden">
                <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px; padding-bottom: 8px; border-bottom: 1px solid rgba(0, 0, 0, 0.08);">
                    <h4 style="margin: 0; font-size: 15px; color: #333; font-weight: 600;">AI Summary</h4>
                    <div style="font-size: 11px; color: #666; display: flex; align-items: center; gap: 4px;">
                        <svg width="12" height="12" viewBox="0 0 24 24" fill="currentColor" style="opacity: 0.7;">
                            <path d="M9 11H7v6h2v-6zm4 0h-2v6h2v-6zm4 0h-2v6h2v-6zm2.5-9H19V1h-2v1H7V1H5v1H3.5C2.67 2 2 2.67 2 3.5v15C2 19.33 2.67 20 3.5 20h17c.83 0 1.5-.67 1.5-1.5v-15C22 2.67 21.33 2 20.5 2zM20.5 18.5h-17v-13h17v13z"/>
                        </svg>
                        Generated with AI
                    </div>
                </div>
                <div id="summary-content-area" class="summary-content-area">
                    <!-- Summary content will be populated here -->
                </div>
                <div class="summary-actions">
                    <button id="copy-summary-btn" class="simply-btn simply-btn--secondary simply-btn--sm">
                        <svg width="12" height="12" viewBox="0 0 24 24" fill="currentColor" class="simply-mr-1">
                            <path d="M16 1H4C2.9 1 2 1.9 2 3V17H4V3H16V1ZM19 5H8C6.9 5 6 5.9 6 7V21C6 22.1 6.9 23 8 23H19C20.1 23 21 22.1 21 21V7C21 5.9 20.1 5 19 5ZM19 21H8V7H19V21Z"/>
                        </svg>
                        Copy
                    </button>
                    <button id="download-summary-btn" class="simply-btn simply-btn--secondary simply-btn--sm">
                        <svg width="12" height="12" viewBox="0 0 24 24" fill="currentColor" class="simply-mr-1">
                            <path d="M19 9h-4V3H9v6H5l7 7 7-7zM5 18v2h14v-2H5z"/>
                        </svg>
                        Download
                    </button>
                    <button id="email-summary-btn" class="simply-btn simply-btn--secondary simply-btn--sm">
                        <svg width="12" height="12" viewBox="0 0 24 24" fill="currentColor" class="simply-mr-1">
                            <path d="M20 4H4c-1.1 0-1.99.9-1.99 2L2 18c0 1.1.9 2 2 2h16c1.1 0 2-.9 2-2V6c0-1.1-.9-2-2-2zm0 4l-8 5-8-5V6l8 5 8-5v2z"/>
                        </svg>
                        Email
                    </button>
                    <button id="regenerate-summary-btn" class="simply-btn simply-btn--secondary simply-btn--sm">
                        <svg width="12" height="12" viewBox="0 0 24 24" fill="currentColor" class="simply-mr-1">
                            <path d="M17.65,6.35C16.2,4.9 14.21,4 12,4A8,8 0 0,0 4,12A8,8 0 0,0 12,20C15.73,20 18.84,17.45 19.73,14H17.65C16.83,16.33 14.61,18 12,18A6,6 0 0,1 6,12A6,6 0 0,1 12,6C13.66,6 15.14,6.69 16.22,7.78L13,11H20V4L17.65,6.35Z"/>
                        </svg>
                        Regenerate
                    </button>
                </div>
            </div>
        `);
        // Re-bind event listeners for the summary tab
        this.bindSummaryEvents();
    }
    // Bind event listeners specifically for summary tab elements
    bindSummaryEvents() {
        // Summary authentication buttons
        const summarySigninBtn = this.embeddedContainer.querySelector('#summary-signin-btn');
        if (summarySigninBtn) {
            summarySigninBtn.addEventListener('click', (e) => {
                e.preventDefault();
                this.handleSummarySignin();
            });
        }
        const summarySignupBtn = this.embeddedContainer.querySelector('#summary-signup-btn');
        if (summarySignupBtn) {
            summarySignupBtn.addEventListener('click', (e) => {
                e.preventDefault();
                this.handleSummarySignup();
            });
        }
        // Generate summary button
        const generateSummaryBtn = this.embeddedContainer.querySelector('#generate-summary-btn');
        if (generateSummaryBtn) {
            generateSummaryBtn.addEventListener('click', (e) => {
                e.preventDefault();
                this.handleGenerateSummary();
            });
        }
        // Regenerate summary button
        const regenerateSummaryBtn = this.embeddedContainer.querySelector('#regenerate-summary-btn');
        if (regenerateSummaryBtn) {
            regenerateSummaryBtn.addEventListener('click', (e) => {
                e.preventDefault();
                this.handleGenerateSummary();
            });
        }
        
        // Copy summary button
        const copySummaryBtn = this.embeddedContainer.querySelector('#copy-summary-btn');
        if (copySummaryBtn) {
            copySummaryBtn.addEventListener('click', (e) => {
                e.preventDefault();
                this.copySummaryToClipboard();
            });
        }
        
        // Download summary button
        const downloadSummaryBtn = this.embeddedContainer.querySelector('#download-summary-btn');
        if (downloadSummaryBtn) {
            downloadSummaryBtn.addEventListener('click', (e) => {
                e.preventDefault();
                this.downloadSummaryAsFile();
            });
        }

        // Email summary button
        const emailSummaryBtn = this.embeddedContainer.querySelector('#email-summary-btn');
        if (emailSummaryBtn) {
            emailSummaryBtn.addEventListener('click', (e) => {
                e.preventDefault();
                this.emailSummary();
            });
        }
    }
    // Show authentication modal
    showAuthModal(type) {
        // Since TubeVibeAuth is not available in embedded context, show inline forms
            if (type === 'login') {
            this.showInlineAuthForm('login');
            } else if (type === 'signup') {
            this.showInlineAuthForm('signup');
        }
    }
    // Handle logout directly without TubeVibeAuth
    async handleLogout() {
        try {
            // Send logout request to background script
            const response = await chrome.runtime.sendMessage({
                type: 'USER_LOGOUT'
            });
            if (response && response.success) {
                // Clear stored tokens locally as well
                if (this.tokenManagerLoaded && window.TokenManager && typeof window.TokenManager.clearTokenData === 'function') {
                    await window.TokenManager.clearTokenData();
                }
                await chrome.storage.local.remove(['simply_token_data', 'access_token', 'refresh_token', 'user_info', 'token_expires_at']);
                // Update the UI to show logged out state
                await this.updateEmbeddedAuthUI();
                // Show success message
                this.showSuccess('Successfully signed out!');
                // Switch to transcript tab
                this.switchTab('transcript');
        } else {
                console.error('❌ Logout failed:', response?.error || 'Unknown error');
                this.showError('Failed to sign out. Please try again.');
            }
        } catch (error) {
            console.error('❌ Logout error:', error);
            // Even if backend logout fails, clear local tokens
            try {
                if (this.tokenManagerLoaded && window.TokenManager && typeof window.TokenManager.clearTokenData === 'function') {
                    await window.TokenManager.clearTokenData();
                }
                await chrome.storage.local.remove(['simply_token_data', 'access_token', 'refresh_token', 'user_info', 'token_expires_at']);
                // Update UI
                await this.updateEmbeddedAuthUI();
                this.showSuccess('Signed out locally.');
            } catch (clearError) {
                console.error('❌ Failed to clear local tokens:', clearError);
                this.showError('Authentication system not available. Please refresh the page.');
            }
        }
    }
    // Show settings modal
    async showSettingsModal() {
        // Load current settings from storage
        const stored = await chrome.storage.local.get(['tubevibe_settings']);
        const settings = stored.tubevibe_settings || {
            autoExtract: false,
            defaultTab: 'transcript'
        };

        // Create modal overlay
        const overlay = document.createElement('div');
        overlay.className = 'settings-modal-overlay';
        overlay.innerHTML = `
            <div class="settings-modal">
                <div class="settings-modal-header">
                    <h3>Extension Settings</h3>
                    <button class="settings-modal-close">
                        <svg width="20" height="20" viewBox="0 0 24 24" fill="currentColor">
                            <path d="M19,6.41L17.59,5L12,10.59L6.41,5L5,6.41L10.59,12L5,17.59L6.41,19L12,13.41L17.59,19L19,17.59L13.41,12L19,6.41Z"/>
                        </svg>
                    </button>
                </div>
                <div class="settings-modal-content">
                    <div class="settings-item">
                        <div>
                            <div class="settings-item-label">Auto-extract Transcript</div>
                            <div class="settings-item-desc">Automatically extract when video loads</div>
                        </div>
                        <div class="settings-toggle ${settings.autoExtract ? 'active' : ''}" data-setting="autoExtract"></div>
                    </div>
                    <div class="settings-item">
                        <div>
                            <div class="settings-item-label">Default Tab</div>
                            <div class="settings-item-desc">Tab to show when opening extension</div>
                        </div>
                        <select id="settings-default-tab" style="padding: 6px 10px; border: 1px solid #e5e7eb; border-radius: 6px; font-size: 13px;">
                            <option value="transcript" ${settings.defaultTab === 'transcript' ? 'selected' : ''}>Transcript</option>
                            <option value="summary" ${settings.defaultTab === 'summary' ? 'selected' : ''}>Summary</option>
                            <option value="chat" ${settings.defaultTab === 'chat' ? 'selected' : ''}>Chat</option>
                        </select>
                    </div>
                </div>
                <div class="settings-modal-footer">
                    <button class="settings-clear-cache-btn">Clear Local Cache</button>
                </div>
            </div>
        `;

        this.embeddedContainer.appendChild(overlay);

        // Event listeners
        overlay.querySelector('.settings-modal-close').addEventListener('click', () => {
            overlay.remove();
        });

        overlay.addEventListener('click', (e) => {
            if (e.target === overlay) overlay.remove();
        });

        // Toggle switches
        overlay.querySelectorAll('.settings-toggle').forEach(toggle => {
            toggle.addEventListener('click', async () => {
                const settingKey = toggle.dataset.setting;
                toggle.classList.toggle('active');
                settings[settingKey] = toggle.classList.contains('active');
                await chrome.storage.local.set({ tubevibe_settings: settings });
            });
        });

        // Default tab select
        overlay.querySelector('#settings-default-tab').addEventListener('change', async (e) => {
            settings.defaultTab = e.target.value;
            await chrome.storage.local.set({ tubevibe_settings: settings });
        });

        // Clear cache button
        overlay.querySelector('.settings-clear-cache-btn').addEventListener('click', async () => {
            // Clear video cache entries
            const allStorage = await chrome.storage.local.get(null);
            const keysToRemove = Object.keys(allStorage).filter(key => key.startsWith('saved_video_'));
            if (keysToRemove.length > 0) {
                await chrome.storage.local.remove(keysToRemove);
            }
            this.showSuccess(`Cleared ${keysToRemove.length} cached videos`);
            overlay.remove();
        });
    }

    // Show history modal
    async showHistoryModal() {
        // Create modal overlay with loading state
        const overlay = document.createElement('div');
        overlay.className = 'history-modal-overlay';
        overlay.innerHTML = `
            <div class="history-modal">
                <div class="history-modal-header">
                    <h3>Recent Videos</h3>
                    <button class="history-modal-close">
                        <svg width="20" height="20" viewBox="0 0 24 24" fill="currentColor">
                            <path d="M19,6.41L17.59,5L12,10.59L6.41,5L5,6.41L10.59,12L5,17.59L6.41,19L12,13.41L17.59,19L19,17.59L13.41,12L19,6.41Z"/>
                        </svg>
                    </button>
                </div>
                <div class="history-modal-content">
                    <div style="text-align: center; padding: 20px; color: #6b7280;">
                        Loading...
                    </div>
                </div>
            </div>
        `;

        this.embeddedContainer.appendChild(overlay);

        // Close event listeners
        overlay.querySelector('.history-modal-close').addEventListener('click', () => {
            overlay.remove();
        });

        overlay.addEventListener('click', (e) => {
            if (e.target === overlay) overlay.remove();
        });

        // Fetch videos from backend
        try {
            const response = await chrome.runtime.sendMessage({
                type: 'GET_USER_VIDEOS',
                data: { limit: 10 }
            });

            const contentDiv = overlay.querySelector('.history-modal-content');

            if (!response || !response.success) {
                contentDiv.innerHTML = `
                    <div class="history-empty">
                        <svg viewBox="0 0 24 24" fill="currentColor">
                            <path d="M12,2A10,10 0 0,0 2,12A10,10 0 0,0 12,22A10,10 0 0,0 22,12A10,10 0 0,0 12,2M12,20A8,8 0 0,1 4,12A8,8 0 0,1 12,4A8,8 0 0,1 20,12A8,8 0 0,1 12,20M12,6A6,6 0 0,0 6,12A6,6 0 0,0 12,18A6,6 0 0,0 18,12A6,6 0 0,0 12,6M12,8A4,4 0 0,1 16,12A4,4 0 0,1 12,16A4,4 0 0,1 8,12A4,4 0 0,1 12,8"/>
                        </svg>
                        <div>${response?.error || 'Sign in to view your saved videos'}</div>
                    </div>
                `;
                return;
            }

            const videos = response.videos || [];
            if (videos.length === 0) {
                contentDiv.innerHTML = `
                    <div class="history-empty">
                        <svg viewBox="0 0 24 24" fill="currentColor">
                            <path d="M13.5,8H12V13L16.28,15.54L17,14.33L13.5,12.25V8M13,3A9,9 0 0,0 4,12H1L4.96,16.03L9,12H6A7,7 0 0,1 13,5A7,7 0 0,1 20,12A7,7 0 0,1 13,19C11.07,19 9.32,18.21 8.06,16.94L6.64,18.36C8.27,20 10.5,21 13,21A9,9 0 0,0 22,12A9,9 0 0,0 13,3"/>
                        </svg>
                        <div>No videos saved yet</div>
                        <div style="font-size: 12px; margin-top: 8px;">Extract a transcript to save it to your library</div>
                    </div>
                `;
                return;
            }

            // Render video list
            let html = '';
            videos.forEach(video => {
                const date = new Date(video.created_at);
                const dateStr = date.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
                const thumbUrl = video.thumbnail_url || `https://img.youtube.com/vi/${video.youtube_id}/mqdefault.jpg`;

                html += `
                    <div class="history-item" data-youtube-id="${video.youtube_id}">
                        <img class="history-item-thumb" src="${thumbUrl}" alt="" onerror="this.style.background='#e5e7eb'"/>
                        <div class="history-item-info">
                            <div class="history-item-title">${this.escapeHtml(video.title || 'Untitled Video')}</div>
                            <div class="history-item-date">${dateStr}</div>
                        </div>
                    </div>
                `;
            });
            contentDiv.innerHTML = html;

            // Add click handlers to navigate to videos
            contentDiv.querySelectorAll('.history-item').forEach(item => {
                item.addEventListener('click', () => {
                    const youtubeId = item.dataset.youtubeId;
                    if (youtubeId) {
                        window.location.href = `https://www.youtube.com/watch?v=${youtubeId}`;
                        overlay.remove();
                    }
                });
            });

        } catch (error) {
            console.error('Error loading history:', error);
            const contentDiv = overlay.querySelector('.history-modal-content');
            contentDiv.innerHTML = `
                <div class="history-empty">
                    <svg viewBox="0 0 24 24" fill="currentColor">
                        <path d="M12,2L1,21H23M12,6L19.53,19H4.47M11,10V14H13V10M11,16V18H13V16"/>
                    </svg>
                    <div>Failed to load videos</div>
                </div>
            `;
        }
    }

    // Handle opening the dashboard
    handleOpenDashboard() {
        // Open dashboard in new tab
        const dashboardUrl = 'https://simply-backend-production.up.railway.app/';
        window.open(dashboardUrl, '_blank');
    }

    // Handle opening help/feedback
    handleOpenHelp() {
        // Open help page or mailto link
        const helpUrl = 'mailto:support@tubevibe.app?subject=TubeVibe%20Extension%20Feedback';
        window.open(helpUrl, '_blank');
    }

    // Handle upgrade button click - redirects to pricing page
    handleUpgrade() {
        // Open the TubeVibe pricing page directly
        // Paddle checkout will happen there, and webhook will update subscription
        const pricingUrl = 'https://tubevibe.app/pricing';
        window.open(pricingUrl, '_blank');
    }

    // Update upgrade banner visibility based on subscription status
    async updateUpgradeBannerVisibility() {
        try {
            const banner = this.embeddedContainer?.querySelector('#menu-upgrade-banner');
            if (!banner) return;

            // Check auth status first
            const authResult = await chrome.storage.local.get(['user_info']);
            if (!authResult.user_info) {
                // Not logged in, hide banner
                banner.classList.add('hidden');
                return;
            }

            // Check subscription status
            const response = await chrome.runtime.sendMessage({ type: 'GET_SUBSCRIPTION_STATUS' });

            if (response && response.success) {
                const plan = response.subscription?.plan || response.plan || 'free';
                if (plan === 'free') {
                    banner.classList.remove('hidden');
                } else {
                    banner.classList.add('hidden');
                }
            } else {
                // Default to showing banner if we can't determine status
                banner.classList.remove('hidden');
            }
        } catch (error) {
            console.error('Error checking subscription status:', error);
        }
    }

    // Escape HTML to prevent XSS
    escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }
    // Restore menu content after auth form is dismissed
    restoreMenuContent() {
        const menuContent = this.embeddedContainer?.querySelector('#menu-content');
        if (!menuContent) return;

        let html = '<div style="padding: 0;">';
        html += '<!-- User Status Card -->';
        html += '<div id="auth-section">';
        html += '<div id="logged-out-menu" class="user-status-card user-status-card--logged-out">';
        html += '<div class="user-status-card__info">';
        html += '<div class="user-status-card__label">Not signed in</div>';
        html += '<div class="user-status-card__email" style="color: var(--simply-text-secondary); font-size: var(--simply-text-xs);">Sign in to sync your data</div>';
        html += '</div>';
        html += '</div>';
        html += '<div id="logged-in-menu" class="user-status-card user-status-card--logged-in hidden">';
        html += '<div class="user-status-card__info">';
        html += '<div class="user-status-card__label">Signed in as</div>';
        html += '<div id="menu-user-email" class="user-status-card__email">Loading...</div>';
        html += '<div id="menu-user-plan" class="user-status-card__plan">Loading...</div>';
        html += '</div>';
        html += '</div>';
        html += '</div>';
        html += '<!-- Auth Buttons -->';
        html += '<div id="auth-buttons-logged-out" style="display: flex; gap: var(--simply-space-2); margin-bottom: var(--simply-space-4);">';
        html += '<button id="menu-login-btn" class="simply-btn simply-btn--primary" style="flex: 1;">';
        html += 'Sign In';
        html += '</button>';
        html += '<button id="menu-signup-btn" class="simply-btn simply-btn--secondary" style="flex: 1;">';
        html += 'Sign Up';
        html += '</button>';
        html += '</div>';
        html += '<div id="auth-buttons-logged-in" class="hidden" style="margin-bottom: var(--simply-space-4);">';
        html += '<button id="menu-logout-btn" class="simply-btn simply-btn--danger simply-w-full">';
        html += 'Sign Out';
        html += '</button>';
        html += '</div>';
        html += '<!-- Upgrade Banner (shown only for free users) -->';
        html += '<div id="menu-upgrade-banner" class="menu-upgrade-banner hidden">';
        html += '<div class="upgrade-banner-content">';
        html += '<svg width="20" height="20" viewBox="0 0 24 24" fill="currentColor" style="color: #f59e0b;">';
        html += '<path d="M12,17.27L18.18,21L16.54,13.97L22,9.24L14.81,8.62L12,2L9.19,8.62L2,9.24L7.45,13.97L5.82,21L12,17.27Z"/>';
        html += '</svg>';
        html += '<div class="upgrade-banner-text">';
        html += '<div class="upgrade-banner-title">Upgrade to Premium</div>';
        html += '<div class="upgrade-banner-desc">Unlimited summaries, priority support</div>';
        html += '</div>';
        html += '</div>';
        html += '<button id="menu-upgrade-btn" class="simply-btn simply-btn--primary" style="font-size: 12px; padding: 6px 12px;">Upgrade</button>';
        html += '</div>';
        html += '<!-- Quick Actions Section -->';
        html += '<div class="menu-section">';
        html += '<h5>Quick Actions</h5>';
        html += '<button id="menu-dashboard-btn" class="menu-item">';
        html += '<svg width="18" height="18" viewBox="0 0 24 24" fill="currentColor">';
        html += '<path d="M13,3V9H21V3M13,21H21V11H13M3,21H11V15H3M3,13H11V3H3V13Z"/>';
        html += '</svg>';
        html += 'Open Dashboard';
        html += '</button>';
        html += '<button id="menu-history-btn" class="menu-item">';
        html += '<svg width="18" height="18" viewBox="0 0 24 24" fill="currentColor">';
        html += '<path d="M13.5,8H12V13L16.28,15.54L17,14.33L13.5,12.25V8M13,3A9,9 0 0,0 4,12H1L4.96,16.03L9,12H6A7,7 0 0,1 13,5A7,7 0 0,1 20,12A7,7 0 0,1 13,19C11.07,19 9.32,18.21 8.06,16.94L6.64,18.36C8.27,20 10.5,21 13,21A9,9 0 0,0 22,12A9,9 0 0,0 13,3"/>';
        html += '</svg>';
        html += 'Recent Videos';
        html += '</button>';
        html += '</div>';
        html += '<!-- Settings & Support Section -->';
        html += '<div class="menu-section">';
        html += '<h5>Settings & Support</h5>';
        html += '<button id="menu-settings-btn" class="menu-item">';
        html += '<svg width="18" height="18" viewBox="0 0 24 24" fill="currentColor">';
        html += '<path d="M12,15.5A3.5,3.5 0 0,1 8.5,12A3.5,3.5 0 0,1 12,8.5A3.5,3.5 0 0,1 15.5,12A3.5,3.5 0 0,1 12,15.5M19.43,12.97C19.47,12.65 19.5,12.33 19.5,12C19.5,11.67 19.47,11.34 19.43,11L21.54,9.37C21.73,9.22 21.78,8.95 21.66,8.73L19.66,5.27C19.54,5.05 19.27,4.96 19.05,5.05L16.56,6.05C16.04,5.66 15.5,5.32 14.87,5.07L14.5,2.42C14.46,2.18 14.25,2 14,2H10C9.75,2 9.54,2.18 9.5,2.42L9.13,5.07C8.5,5.32 7.96,5.66 7.44,6.05L4.95,5.05C4.73,4.96 4.46,5.05 4.34,5.27L2.34,8.73C2.21,8.95 2.27,9.22 2.46,9.37L4.57,11C4.53,11.34 4.5,11.67 4.5,12C4.5,12.33 4.53,12.65 4.57,12.97L2.46,14.63C2.27,14.78 2.21,15.05 2.34,15.27L4.34,18.73C4.46,18.95 4.73,19.03 4.95,18.95L7.44,17.94C7.96,18.34 8.5,18.68 9.13,18.93L9.5,21.58C9.54,21.82 9.75,22 10,22H14C14.25,22 14.46,21.82 14.5,21.58L14.87,18.93C15.5,18.68 16.04,18.34 16.56,17.94L19.05,18.95C19.27,19.03 19.54,18.95 19.66,18.73L21.66,15.27C21.78,15.05 21.73,14.78 21.54,14.63L19.43,12.97Z"/>';
        html += '</svg>';
        html += 'Extension Settings';
        html += '</button>';
        html += '<button id="menu-help-btn" class="menu-item">';
        html += '<svg width="18" height="18" viewBox="0 0 24 24" fill="currentColor">';
        html += '<path d="M15.07,11.25L14.17,12.17C13.45,12.89 13,13.5 13,15H11V14.5C11,13.39 11.45,12.39 12.17,11.67L13.41,10.41C13.78,10.05 14,9.55 14,9C14,7.89 13.1,7 12,7A2,2 0 0,0 10,9H8A4,4 0 0,1 12,5A4,4 0 0,1 16,9C16,9.88 15.64,10.67 15.07,11.25M13,19H11V17H13M12,2A10,10 0 0,0 2,12A10,10 0 0,0 12,22A10,10 0 0,0 22,12C22,6.47 17.5,2 12,2Z"/>';
        html += '</svg>';
        html += 'Help & Feedback';
        html += '</button>';
        html += '</div>';
        html += '<!-- Info Section -->';
        html += '<div style="padding: var(--simply-space-3); background: var(--simply-bg-secondary); border-radius: var(--simply-radius-lg); text-align: center;">';
        html += '<div style="font-size: var(--simply-text-xs); color: var(--simply-text-tertiary);">TubeVibe Extension</div>';
        html += '<div style="font-size: 10px; color: var(--simply-text-tertiary); margin-top: 2px;">Version 1.0.6 - AI Video Summaries</div>';
        html += '</div>';
        html += '</div>';

        this.safeSetHTML(menuContent, html);

        // Re-bind menu event listeners
        this.bindMenuEventListeners();

        // Update auth UI state
        this.updateEmbeddedAuthUI();
    }
    // Simple tab switching without TubeVibeUI
    switchTab(tabName) {
        if (!this.embeddedContainer) {
            console.error('❌ Embedded container not found, cannot switch tabs');
            return;
        }
        // Update tab buttons (scope to embedded container)
        this.embeddedContainer.querySelectorAll('.simply-tab').forEach(tab => {
            tab.classList.remove('simply-tab--active');
        });
        const activeTab = this.embeddedContainer.querySelector('[data-tab="' + tabName + '"]');
        if (activeTab) {
            activeTab.classList.add('simply-tab--active');
        }
        // Update content visibility (scope to embedded container)
        this.embeddedContainer.querySelectorAll('.simply-tab-content').forEach(content => {
            content.classList.add('hidden');
        });
        const activeContent = this.embeddedContainer.querySelector('#' + tabName + '-content');
        if (activeContent) {
            activeContent.classList.remove('hidden');
        }
    }
    async handleExtractTranscript() {
        // Use the working DOM-based method like Scripsy
        try {
            this.showLoading();
            // Use the working extractFromYouTubeDOMTranscript method
            const transcript = await this.extractFromYouTubeDOMTranscript();
            if (transcript && transcript.length > 50) {
                this.showTranscript(transcript);
            } else {
                console.error('❌ Transcript extraction failed or too short');
                this.showError('No transcript found or transcript too short');
            }
        } catch (error) {
            console.error('❌ Error in transcript extraction:', error);
            this.showError('An error occurred while extracting transcript');
        }
    }
    async handleGenerateSummary() {
        try {
            // Quick token check FIRST - fail fast if no token exists (bypass in TEST_MODE)
            if (!TEST_MODE) {
                // Quick check for token existence in storage
                const tokenData = await chrome.storage.local.get(['access_token']);
                if (!tokenData.access_token) {
                    console.log('🔐 No access token found, showing auth prompt immediately');
                    this.showSummaryAuthPrompt();
                    return;
                }

                // Full authentication status check
                const authState = await this.checkAuthenticationStatus();
                if (!authState.isAuthenticated) {
                    console.log('🔐 User not authenticated, showing auth prompt');
                    this.showSummaryAuthPrompt();
                    return;
                }
            } else {
                console.log('🧪 TEST_MODE: Bypassing authentication check');
            }

            // === Immediate UI feedback (only after auth check passes) ===
            const generateBtn = this.embeddedContainer?.querySelector('#generate-summary-btn');
            if (generateBtn) {
                generateBtn.disabled = true;
                generateBtn.dataset.originalText = generateBtn.textContent;
                generateBtn.textContent = 'Starting…';
                generateBtn.classList.add('simply-loading');
            }

            // Check quota limits before processing (if PaymentManager is loaded) - skip in TEST_MODE
            if (!TEST_MODE && this.paymentManagerLoaded && window.PaymentManager && typeof window.PaymentManager === 'function') {
                try {
                    const paymentManager = new window.PaymentManager();
                    const quotaCheck = await paymentManager.checkWeeklyQuota();
                    
                    if (!quotaCheck.canProcess) {
                        // Show upgrade modal for quota exceeded
                        if (quotaCheck.plan === 'free') {
                            paymentManager.showUpgradePrompt('quota_exceeded');
                        } else {
                            this.showSummaryError('Unable to process video at this time. Please try again later.');
                        }
                        return;
                    }
                } catch (quotaError) {
                    console.warn('⚠️ Could not check quota limits:', quotaError);
                    // Continue with processing if quota check fails
                }
            }
            const transcriptData = await this.getCurrentVideoData();
            if (!transcriptData) {
                this.showSummaryError('Could not extract video data. Please refresh the page and try again.');
                    return;
            }
            // Show loading state
            this.showLoadingState('Generating AI summary...');
            // Clean the transcript text for backend processing
            const cleanedTranscript = this.cleanTranscriptForBackend(transcriptData.transcript);
            // Update transcript data with cleaned version
            transcriptData.transcript = cleanedTranscript;

            // Send to NEW TubeVibe Library summary endpoint
            console.log('🚀 Sending GENERATE_VIDEO_SUMMARY message to background script...');
            console.log('📊 Transcript data being sent:', {
                video_id: transcriptData.video_id,
                title: transcriptData.title,
                transcript_length: transcriptData.transcript?.length
            });

            const response = await chrome.runtime.sendMessage({
                type: 'GENERATE_VIDEO_SUMMARY',
                data: transcriptData
            });

            console.log('📨 Background script response received:', response);

            // Check for Chrome runtime errors
            if (chrome.runtime.lastError) {
                console.error('❌ Chrome runtime error:', chrome.runtime.lastError);
                throw new Error(`Chrome runtime error: ${chrome.runtime.lastError.message}`);
            }

            // Handle the response
            if (response && response.success) {
                // Success - display the formatted summary
                console.log('✅ Summary generated successfully');
                this.showSummary(response.summary);
                this.showSuccess('Summary generated successfully!');
            } else {
                // Check if it's a token expiration error
                if (response && response.error && response.error.includes('expired')) {
                    console.log('🔐 Session expired, clearing tokens and showing sign-in UI');
                    // Clear stored tokens to force re-authentication
                    try {
                        if (this.tokenManagerLoaded && window.TokenManager && typeof window.TokenManager.clearTokenData === 'function') {
                            await window.TokenManager.clearTokenData();
                        }
                        await chrome.storage.local.remove(['simply_token_data', 'access_token', 'refresh_token', 'user_info', 'token_expires_at']);
                    } catch (error) {
                        console.error('❌ Error clearing tokens:', error);
                    }
                    // Show authentication required UI after clearing tokens
                    await this.updateEmbeddedAuthUI();
                    return;
            } else {
                    console.error('❌ Background script error:', response ? response.error : 'Unknown error');
                    
                    // Handle 404 Not Found errors - for testing upgrade flow
                    if (response && response.error && response.error.includes('Not Found')) {
                        // For testing: Show upgrade modal if PaymentManager is available
                        if (this.paymentManagerLoaded && window.PaymentManager) {
                            try {
                                console.log('🧪 Testing: Showing upgrade modal due to API error');
                                const paymentManager = new window.PaymentManager();
                                paymentManager.showUpgradePrompt('quota_exceeded');
                            } catch (error) {
                                console.error('❌ PaymentManager constructor error:', error);
                                console.log('PaymentManager type:', typeof window.PaymentManager);
                                console.log('PaymentManager loaded flag:', this.paymentManagerLoaded);
                                this.showSummaryError('Service temporarily unavailable. Please try again later.');
                            }
                        } else {
                            console.log('❌ PaymentManager not available:', {
                                loaded: this.paymentManagerLoaded,
                                exists: !!window.PaymentManager,
                                type: typeof window.PaymentManager
                            });
                            this.showSummaryError('Service temporarily unavailable. Please try again later.');
                        }
                    } else {
                        // Check if error is authentication-related
                        const errorMsg = response ? response.error : 'Unknown error';
                        if (/authentication|unauthorized|not authenticated|sign in|login required/i.test(errorMsg)) {
                            console.log('🔐 Authentication error detected, showing auth prompt');
                            this.showSummaryAuthPrompt();
                        } else {
                            this.showSummaryError('Failed to generate summary: ' + errorMsg);
                        }
                    }
            }
            }
        } catch (error) {
            console.error('❌ Error:', error.message);
            // Check if error is authentication-related
            if (/authentication|unauthorized|not authenticated|sign in|login required/i.test(error.message)) {
                console.log('🔐 Authentication error detected, showing auth prompt');
                this.showSummaryAuthPrompt();
            } else {
                this.showSummaryError('Error: ' + error.message);
            }
        } finally {
            // Always clear loading state
            this.clearLoadingState();
        }
    }
    // Working DOM-based transcript extraction method like Scripsy
    async extractFromYouTubeDOMTranscript() {
        try {
            // First, check if transcript segments are already loaded
            const existingSegmentSelectors = [
                'ytd-transcript-renderer .segment-text',
                'ytd-transcript-segment-list-renderer .segment-text', 
                '.ytd-transcript-segment-renderer .segment-text',
                '#panels .segment-text',
                '[data-target-id="engagement-panel-structured-description"] .segment-text'
            ];
            // Check if transcript is already visible
            for (const selector of existingSegmentSelectors) {
                const segments = document.querySelectorAll(selector);
                if (segments.length > 0) {
                    return this.parseTranscriptSegments(segments);
                }
            }
            // If not already loaded, open transcript panel
            const transcriptButton = this.findTranscriptButton();
            if (!transcriptButton) {
                console.error('❌ No transcript button found');
                return null;
            }
            // Check if transcript panel is already open
            const isTranscriptOpen = transcriptButton.getAttribute('aria-pressed') === 'true' ||
                                    !!document.querySelector('#panels ytd-transcript-renderer');
            if (!isTranscriptOpen) {
                // Need to click the button to open transcript
            transcriptButton.click();
                // Wait a bit for panel to open
                await new Promise(resolve => setTimeout(resolve, 500));
            }
            // Wait for content to load without interference
            await this.waitForTranscriptContent();
            // Now hide the panel after content is loaded - DISABLED to prevent YouTube UI interference
            // const hideStyle = document.createElement('style');
            // hideStyle.id = 'tubevibe-transcript-hide';
            // hideStyle.textContent = `
            //     /* Hide only specific transcript panels - VERY SPECIFIC to avoid affecting YouTube header */
            //     #panels ytd-transcript-renderer,
            //     #panels ytd-engagement-panel-section-list-renderer[target-id*="transcript"],
            //     #panels [data-target-id="engagement-panel-structured-description"],
            //     #panels [aria-label*="transcript" i][role="dialog"],
            //     #panels #structured-description,
            //     /* More specific selectors for transcript panels ONLY within #panels */
            //     #panels ytd-engagement-panel-section-list-renderer ytd-transcript-renderer { 
            //         opacity: 0 !important; 
            //         visibility: hidden !important;
            //         position: absolute !important;
            //         top: -9999px !important;
            //         left: -9999px !important;
            //         z-index: -1000 !important;
            //         pointer-events: none !important;
            //     }
            // `;
            // document.head.appendChild(hideStyle);
            // Extract transcript segments
            let transcript = null;
            for (const selector of existingSegmentSelectors) {
                const segments = document.querySelectorAll(selector);
                if (segments.length > 0) {
                    transcript = this.parseTranscriptSegments(segments);
                    break;
                }
            }
            // Close panel immediately with SAFE approach only
            this.safeCloseTranscriptPanel(transcriptButton);
            // Clean up almost immediately to minimize impact on YouTube UI
            setTimeout(() => {
                // Remove hide style to restore normal YouTube functionality
                const hideStyleEl = document.getElementById('tubevibe-transcript-hide');
                if (hideStyleEl) {
                    hideStyleEl.remove();
                }
            }, 100); // Reduced from 1000ms to 100ms
            return transcript;
        } catch (error) {
            console.error('❌ Error in DOM transcript extraction:', error);
            return null;
        }
    }
    // Find transcript button using multiple selectors
    findTranscriptButton() {
        const transcriptButtonSelectors = [
            'button[aria-label*="transcript" i]',
            'button[aria-label*="Show transcript"]',
            '#description button[aria-label*="transcript" i]',
            'ytd-video-description-transcript-section-renderer button',
            'button[aria-label*="Transcript"]',
            'ytd-video-description-transcript-section-renderer yt-button-renderer button'
        ];
        for (const selector of transcriptButtonSelectors) {
            const buttons = document.querySelectorAll(selector);
            for (const button of buttons) {
                const text = button.textContent?.toLowerCase() || '';
                const ariaLabel = button.getAttribute('aria-label')?.toLowerCase() || '';
                if (text.includes('transcript') || ariaLabel.includes('transcript')) {
                    return button;
                }
            }
        }
        return null;
    }
    // Wait for transcript content to load (simplified)
    async waitForTranscriptContent() {
        const maxWait = 3000; // 3 seconds max
        const checkInterval = 200; // Check every 200ms
        const startTime = Date.now();
        while (Date.now() - startTime < maxWait) {
            // Check multiple selectors for transcript segments
            const segmentSelectors = [
                'ytd-transcript-renderer .segment-text',
                'ytd-transcript-segment-list-renderer .segment-text',
                '.ytd-transcript-segment-renderer .segment-text',
                '#panels .segment-text',
                'ytd-transcript-segment-renderer .segment-text'
            ];
            for (const selector of segmentSelectors) {
                const segments = document.querySelectorAll(selector);
                if (segments.length > 0) {
                    return;
                }
            }
            await new Promise(resolve => setTimeout(resolve, checkInterval));
        }
        console.warn('⚠️ Timeout waiting for transcript content');
    }
    // Parse transcript segments from DOM elements with enhanced artifact removal
    parseTranscriptSegments(segments) {
        const transcriptText = Array.from(segments)
            .map((segment, index) => {
                // Debug first few segments
                if (index < 3) {
                    console.log('Segment ' + index + ':', segment);
                }
                // Extract clean text from the segment, handling nested elements
                let text = this.extractCleanTextFromSegment(segment);
                // Debug the extracted text
                if (index < 3) {
                    console.log('Extracted text:', text);
                }
                // Additional cleanup for any remaining artifacts
                text = this.cleanTextArtifacts(text);
                // Debug after cleanup
                if (index < 3) {
                    console.log('Cleaned text:', text);
                }
                // Remove timestamps at the beginning
                text = text
                    .replace(/^\d{1,2}:\d{2}:\d{2}\s*/, '') // Remove timestamps like "1:23:45"
                    .replace(/^\d{1,2}:\d{2}\s*/, '') // Remove short timestamps like "1:23"
                    .replace(/^\d+\s*/, ''); // Remove plain numbers at start
                return text.trim();
            })
            .filter(text => text.length > 0)
            .join(' ');
        return transcriptText.trim();
    }
    // Extract clean text from a segment element, handling nested structures
    extractCleanTextFromSegment(element) {
        // Get the raw HTML content to check for confidence tags
        const innerHTML = element.innerHTML || '';
        // If the element contains YouTube's confidence markup tags, extract text properly
        if (innerHTML.includes('<c') || innerHTML.includes('confidence=')) {
            // YouTube uses <c confidence="0.85" style="font-style: italic;">word</c> format
            console.log('Found confidence markup in segment');
            // Extract just the text content from these tags - enhanced approach
            let cleanedHTML = innerHTML
                // Remove complete <c> tags with all attributes including style
                .replace(/<c\s+[^>]*?>/gi, '')
                .replace(/<\/c>/gi, '')
                // Remove <v> voice tags if present
                .replace(/<v\s+[^>]*?>/gi, '')
                .replace(/<\/v>/gi, '')
                // Remove any partial tag fragments that might remain
                .replace(/confidence="[^"]*"/gi, '')
                .replace(/style="[^"]*"/gi, '')
                // Remove any remaining CSS fragments
                .replace(/\d+\.\d+;\s*font-style:\s*\w+;?\s*"?>/gi, '')
                .replace(/\d+\.\d+;\s*[^>]*"?>/gi, '')
                // Remove any other tags
                .replace(/<[^>]+>/g, '');
            // Clean up HTML entities
            cleanedHTML = this.decodeHTMLEntities(cleanedHTML);
            console.log('After HTML decode:', cleanedHTML);
            // Final cleanup with enhanced pattern matching
            let finalText = cleanedHTML
                .replace(/\d+\.\d+;\s*font-style:\s*\w+;?\s*"?>/g, '') // Remove remaining CSS fragments
                .replace(/\s+/g, ' ')
                .trim();
            console.log('Final text:', finalText);
            return finalText;
        }
        // First try innerText for cleaner extraction
        if (element.innerText && !this.containsStyleArtifacts(element.innerText)) {
            return element.innerText;
        }
        // If innerText has artifacts or is unavailable, do manual extraction
        let cleanText = '';
        // Recursively extract text from child nodes
        const extractFromNode = (node) => {
            if (node.nodeType === Node.TEXT_NODE) {
                // Direct text node
                const text = node.textContent.trim();
                if (text && !this.isStyleArtifact(text)) {
                    cleanText += ' ' + text;
                }
            } else if (node.nodeType === Node.ELEMENT_NODE) {
                // Skip style and script elements
                if (node.tagName === 'STYLE' || node.tagName === 'SCRIPT') {
                    return;
                }
                // Skip confidence tags but process their content
                if (node.tagName === 'C' || node.hasAttribute('confidence')) {
                    // Process child nodes of confidence tags
                    for (const child of node.childNodes) {
                        extractFromNode(child);
                    }
                    return;
                }
                // Check if this element contains style artifacts in its text
                const elementText = node.textContent.trim();
                if (this.isStyleArtifact(elementText)) {
                    return;
                }
                // Process child nodes
                for (const child of node.childNodes) {
                    extractFromNode(child);
                }
            }
        };
        extractFromNode(element);
        return cleanText.trim();
    }
    // Decode HTML entities
    decodeHTMLEntities(text) {
        return text
            .replace(/&amp;/g, '&')
            .replace(/&lt;/g, '<')
            .replace(/&gt;/g, '>')
            .replace(/&#39;/g, "'")
            .replace(/&quot;/g, '"')
            .replace(/&nbsp;/g, ' ');
    }
    // Check if text contains style artifacts
    containsStyleArtifacts(text) {
        const artifactPatterns = [
            /\d+\.\d+;.*?>/, // Patterns like "0.85;>"
            /\bopacity:\s*[\d.]+/, // Opacity declarations
            /\bfont-style:\s*\w+/, // Font style declarations
            /style="[^"]*"/, // Style attributes
            /^\d+\.\d+;/, // Decimal number with semicolon at start
        ];
        return artifactPatterns.some(pattern => pattern.test(text));
    }
    // Check if a text fragment is likely a style artifact
    isStyleArtifact(text) {
        const trimmed = text.trim();
        // Check for common style artifact patterns
        if (/^\d+\.\d+;?$/.test(trimmed)) return true; // Just a decimal number
        if (/^[\d.]+%$/.test(trimmed)) return true; // Percentage
        if (/^#[0-9a-fA-F]{3,6}$/.test(trimmed)) return true; // Hex color
        if (/^(rgb|rgba|hsl|hsla)\(/.test(trimmed)) return true; // Color functions
        if (/^[;:,<>"]$/.test(trimmed)) return true; // Single punctuation
        if (/^\d+\.\d+;.*?>$/.test(trimmed)) return true; // Pattern like "0.85;>"
        return false;
    }
    // Clean text artifacts from a string
    cleanTextArtifacts(text) {
        if (!text) return '';
        return text
            // Remove confidence-related patterns first
            .replace(/confidence="[\d.]+"/g, '') // Remove confidence attributes
            .replace(/\d+\.\d+;">|"\>/g, '') // Remove patterns like 0.85;"> or ">
            .replace(/\d+\.\d+;"/g, '') // Remove patterns like 0.85;"
            .replace(/\b\d+\.\d+;>/g, '') // Remove patterns like 0.85;>
            .replace(/\b\d+\.\d+;/g, '') // Decimal with semicolon
            // Enhanced patterns to catch combined confidence + style fragments
            .replace(/\d+\.\d+;\s*font-style:\s*\w+;?\s*"?>/g, '') // Catches "0.6; font-style: italic;">"
            .replace(/\d+\.\d+;\s*[^>]*"?>/g, '') // Catches any "0.6; [CSS properties]">"
            .replace(/\d+\.\d+;\s*[^"]*">/g, '') // Catches variations like "0.85; style stuff">"
            .replace(/;\s*font-style:\s*\w+;?\s*"?>/g, '') // Catches remaining "; font-style: italic;">"
            // Remove any remaining tag fragments
            .replace(/<c\s+[^>]*>/g, '') // Remove <c confidence> tags
            .replace(/<\/c>/g, '') // Remove closing </c> tags
            .replace(/<v\s+[^>]*>/g, '') // Remove voice tags
            .replace(/<\/v>/g, '') // Remove closing voice tags
            // Remove style properties
            .replace(/\bopacity:\s*[\d.]+;?/g, '')
            .replace(/\bfont-style:\s*\w+;?/g, '')
            .replace(/style="[^"]*"/g, '')
            // Remove HTML entities and tags
            .replace(/<[^>]+>/g, '')
            .replace(/&nbsp;/g, ' ')
            .replace(/&amp;/g, '&')
            .replace(/&lt;/g, '<')
            .replace(/&gt;/g, '>')
            .replace(/&quot;/g, '"')
            .replace(/&#39;/g, "'")
            // Clean up whitespace
            .replace(/\s+/g, ' ')
            .replace(/\s+([.,!?])/g, '$1')
            .trim();
    }
    // Additional cleanup method for already extracted transcript
    cleanupTranscriptText(text) {
        if (!text || typeof text !== 'string') {
            return text;
        }
        // Use the enhanced artifact cleaning method
        let cleanedText = this.cleanTextArtifacts(text);
        return cleanedText;
    }
    // Safe close transcript panel - minimal YouTube UI interference
    safeCloseTranscriptPanel(transcriptButton) {
        // Strategy 1: Try specific transcript close buttons only
        const closeButtonSelectors = [
            '#panels button[aria-label*="Hide transcript"]',
            '#panels button[aria-label*="Close transcript"]',
            'ytd-engagement-panel-title-header-renderer button[aria-label*="Close"]'
        ];
        for (const selector of closeButtonSelectors) {
            const closeButton = document.querySelector(selector);
            if (closeButton) {
                closeButton.click();
                break;
            }
        }
        // Strategy 2: Toggle transcript button (safe) - DISABLED to prevent YouTube UI interference
        // if (transcriptButton) {
        //     setTimeout(() => {
        //         transcriptButton.click();
        //     }, 100);
        // }
        // Strategy 3: Send single Escape key (safe)
        setTimeout(() => {
            const escapeEvent = new KeyboardEvent('keydown', {
                key: 'Escape',
                keyCode: 27,
                which: 27,
                bubbles: true
            });
            document.dispatchEvent(escapeEvent);
        }, 200);
    }
    // OLD Close transcript panel aggressively - KEPT FOR REFERENCE BUT NOT USED
    closeTranscriptPanel(transcriptButton) {
        // Strategy 1: Try all close buttons
        const closeButtonSelectors = [
            '#panels button[aria-label*="Close"]',
            '#panels button[aria-label*="close"]', 
            'ytd-engagement-panel-title-header-renderer button',
            '#panels .top-level-buttons button:last-child',
            'button[aria-label*="Hide transcript"]',
            '#panels yt-icon-button[aria-label*="Close"]',
            '#panels button[title*="Close"]',
            '#panels .close-button',
            'ytd-engagement-panel-section-list-renderer button[aria-label*="Close"]'
        ];
        for (const selector of closeButtonSelectors) {
            const closeButton = document.querySelector(selector);
            if (closeButton) {
                closeButton.click();
                break;
            }
        }
        // Strategy 2: Toggle transcript button off - DISABLED to prevent YouTube UI interference
        // setTimeout(() => {
        //     transcriptButton.click();
        // }, 50);
        // Strategy 3: Hide panels via CSS temporarily - DISABLED to prevent YouTube UI interference
        // setTimeout(() => {
        //     const panels = document.querySelector('#panels');
        //     if (panels) {
        //         panels.style.display = 'none';
        //         setTimeout(() => {
        //             panels.style.display = '';
        //         }, 200);
        //     }
        // }, 100);
        // Strategy 4: Send Escape key event
        setTimeout(() => {
            const escapeEvent = new KeyboardEvent('keydown', {
                key: 'Escape',
                keyCode: 27,
                which: 27,
                bubbles: true
            });
            document.dispatchEvent(escapeEvent);
        }, 150);
    }
    // Force close transcript panel with additional strategies - DISABLED to prevent YouTube UI interference
    forceCloseTranscriptPanel(transcriptButton) {
        // DISABLED: Strategy 1: Hide all panels with direct CSS manipulation
        // const panels = document.querySelector('#panels');
        // if (panels) {
        //     panels.style.cssText = 'display: none !important; opacity: 0 !important; visibility: hidden !important;';
        // }
        // DISABLED: Strategy 2: Remove panel elements temporarily
        // const panelElements = document.querySelectorAll('ytd-engagement-panel-section-list-renderer, ytd-transcript-renderer');
        // panelElements.forEach(el => {
        //     el.style.display = 'none';
        // });
        // Strategy 3: Click transcript button again to toggle off (this is safe) - DISABLED to prevent YouTube UI interference
        // if (transcriptButton) {
        //     transcriptButton.click();
        // }
        // Strategy 4: Multiple escape key events
        for (let i = 0; i < 3; i++) {
            setTimeout(() => {
                const escapeEvent = new KeyboardEvent('keydown', {
                    key: 'Escape',
                    keyCode: 27,
                    which: 27,
                    bubbles: true
                });
                document.dispatchEvent(escapeEvent);
            }, i * 50);
        }
        // Strategy 5: Try to collapse the panel - DISABLED to prevent YouTube UI interference
        // const collapseButtons = document.querySelectorAll('#panels button[aria-expanded="true"]');
        // collapseButtons.forEach(btn => btn.click());
    }
    // Working video ID extraction from content.ts
    getVideoId() {
        try {
            // Method 1: From URL parameter
            const urlParams = new URLSearchParams(window.location.search);
            const videoId = urlParams.get('v');
            if (videoId) {
                return videoId;
            }
            // Method 2: From page URL
            const match = window.location.href.match(/[?&]v=([^&]+)/);
            if (match) {
                return match[1];
            }
            return null;
        } catch (error) {
            console.warn('TubeVibe: Error getting video ID:', error);
            return null;
        }
    }
    // Working transcript extraction method from content.ts
    async extractFromPlayerResponseFast(videoId) {
        try {
            let playerResponse = null;
            // Try to get player response from window.ytInitialPlayerResponse
            if (window.ytInitialPlayerResponse) {
                playerResponse = window.ytInitialPlayerResponse;
            } else {
                // Try to find player response in script tags
                const scripts = document.querySelectorAll('script');
                for (const script of scripts) {
                    const content = script.textContent || script.innerHTML;
                    if (content.includes('ytInitialPlayerResponse')) {
                        try {
                            const match = content.match(/ytInitialPlayerResponse\s*=\s*({.+?});/);
                            if (match) {
                                playerResponse = JSON.parse(match[1]);
                                break;
                            }
                        } catch (e) {
                            console.warn('Error parsing script content:', e);
                        }
                    }
                }
            }
            if (!playerResponse) {
                return { success: false, error: 'Could not find ytInitialPlayerResponse' };
            }
            // Extract caption tracks
            const captionTracks = playerResponse?.captions?.playerCaptionsTracklistRenderer?.captionTracks;
            if (!captionTracks || captionTracks.length === 0) {
                return { success: false, error: 'No caption tracks found' };
            }
            // Get the best caption track (prefer auto-generated English)
            let bestTrack = null;
            // First try to find auto-generated English captions
            for (const track of captionTracks) {
                if (track.languageCode === 'en' && track.kind === 'asr') {
                    bestTrack = track;
                    break;
                }
            }
            // If no auto-generated English, try manual English captions
            if (!bestTrack) {
                for (const track of captionTracks) {
                    if (track.languageCode === 'en') {
                        bestTrack = track;
                        break;
                    }
                }
            }
            // If still no English, use the first available track
            if (!bestTrack) {
                bestTrack = captionTracks[0];
            }
            // Use authenticated fetch like content.ts does (Scripsy-like method)
            const transcript = await this.fetchCaptionsWithAuthentication(bestTrack.baseUrl, bestTrack.kind === 'asr');
            if (!transcript || transcript.length === 0) {
                return { success: false, error: 'No transcript could be extracted from caption track' };
            }
            return { success: true, transcript };
        } catch (error) {
            console.error('Error in extractFromPlayerResponseFast:', error);
            return { success: false, error: error.message };
        }
    }
    // Process caption data from YouTube's JSON3 format
    processCaptionData(captionData) {
        try {
            const events = captionData.events || [];
            let transcript = '';
            for (const event of events) {
                if (event.segs) {
                    for (const seg of event.segs) {
                        if (seg.utf8) {
                            transcript += seg.utf8;
                        }
                    }
                }
            }
            // Clean up the transcript
            transcript = transcript.replace(/\n/g, ' ').replace(/\s+/g, ' ').trim();
            return transcript;
        } catch (error) {
            console.error('Error processing caption data:', error);
            return '';
        }
    }
    // Fetch captions with authentication like content.ts does (Scripsy-like method)
    async fetchCaptionsWithAuthentication(baseUrl, isAutoGenerated) {
        try {
            // Try different formats in order of preference
            const formats = [
                { fmt: 'json3', processor: 'processJSON3Captions' },
                { fmt: 'srv3', processor: 'processXMLCaptions' },
                { fmt: 'srv1', processor: 'processXMLCaptions' },
                { fmt: 'vtt', processor: 'processVTTCaptions' }
            ];
            for (const format of formats) {
                try {
                    const captionUrl = baseUrl + '&fmt=' + format.fmt;
                    // Use authenticated fetch with proper headers and cookies
                    const response = await fetch(captionUrl, {
                        method: 'GET',
                        headers: {
                            'Accept': 'text/vtt, application/json, text/xml, */*',
                            'Accept-Language': 'en-US,en;q=0.9',
                            'Cache-Control': 'no-cache',
                            'User-Agent': navigator.userAgent,
                            'Referer': window.location.href,
                            'Origin': window.location.origin
                        },
                        credentials: 'include',
                        mode: 'cors'
                    });
                    if (!response.ok) {
                        continue;
                    }
                    const responseText = await response.text();
                    if (responseText.length === 0) {
                        continue;
                    }
                    console.log('Processing caption format: ' + format.fmt + '...');
                    // Process the response based on format
                    let transcript = '';
                    if (format.processor === 'processJSON3Captions') {
                        transcript = this.processJSON3Captions(responseText);
                    } else if (format.processor === 'processXMLCaptions') {
                        transcript = this.processXMLCaptions(responseText);
                    } else if (format.processor === 'processVTTCaptions') {
                        transcript = this.processVTTCaptions(responseText);
                    }
                    if (transcript && transcript.length > 0) {
                        return transcript;
                    }
                } catch (error) {
                    continue;
                }
            }
            return null;
        } catch (error) {
            console.error('Error in fetchCaptionsWithAuthentication:', error);
            return null;
        }
    }
    // Process JSON3 caption format
    processJSON3Captions(jsonText) {
        try {
            const captionData = JSON.parse(jsonText);
            return this.processCaptionData(captionData);
        } catch (error) {
            console.error('Error processing JSON3 captions:', error);
            return '';
        }
    }
    // Process VTT caption format
    processVTTCaptions(vttText) {
        try {
            const lines = vttText.split('\n');
            let transcript = '';
            for (let i = 0; i < lines.length; i++) {
                const line = lines[i].trim();
                // Skip VTT headers, timestamps, and empty lines
                if (line.startsWith('WEBVTT') || 
                    line.includes('-->') || 
                    line === '' || 
                    line.match(/^\d+$/)) {
                    continue;
                }
                // Add text content
                if (line) {
                    transcript += line + ' ';
                }
            }
            // Clean up the transcript
            transcript = transcript
                .replace(/<[^>]*>/g, '') // Remove HTML tags
                .replace(/&amp;/g, '&')
                .replace(/&lt;/g, '<')
                .replace(/&gt;/g, '>')
                .replace(/&quot;/g, '"')
                .replace(/&#39;/g, "'")
                .replace(/\s+/g, ' ')
                .trim();
            return transcript;
        } catch (error) {
            console.error('Error processing VTT captions:', error);
            return '';
        }
    }
    // Process XML caption data (srv3, srv1 formats)
    processXMLCaptions(xmlText) {
        try {
            const parser = new DOMParser();
            const xmlDoc = parser.parseFromString(xmlText, 'text/xml');
            // Check for parsing errors
            const parserError = xmlDoc.getElementsByTagName('parsererror')[0];
            if (parserError) {
                console.error('XML parsing error:', parserError.textContent);
                return '';
            }
            const textElements = xmlDoc.getElementsByTagName('text');
            let transcript = '';
            for (let i = 0; i < textElements.length; i++) {
                const textElement = textElements[i];
                const text = textElement.textContent || textElement.innerText || '';
                if (text.trim()) {
                    transcript += text.trim() + ' ';
                }
            }
            // Clean up the transcript
            transcript = transcript
                .replace(/&amp;/g, '&')
                .replace(/&lt;/g, '<')
                .replace(/&gt;/g, '>')
                .replace(/&quot;/g, '"')
                .replace(/&#39;/g, "'")
                .replace(/\s+/g, ' ')
                .trim();
            return transcript;
        } catch (error) {
            console.error('Error processing XML captions:', error);
            return '';
        }
    }
    // Show loading state
    showLoading() {
        const transcriptContent = this.embeddedContainer?.querySelector('#transcript-content');
        if (transcriptContent) {
            this.safeSetHTML(transcriptContent, `
                <div style="text-align: center; padding: 20px; color: #666;">
                    <div style="margin-bottom: 10px;">🎬 Extracting transcript...</div>
                    <div style="font-size: 12px;">This may take a moment</div>
                </div>
            `);
        }
    }
    // Show error message
    showError(message) {
        const transcriptContent = this.embeddedContainer?.querySelector('#transcript-content');
        if (transcriptContent) {
            // Use SafeDOM if available, otherwise fall back to safe text content
            if (window.SafeDOM && window.FeatureFlags?.isEnabled('SAFE_DOM_ENABLED')) {
                window.SafeDOM.setHTML(transcriptContent, `
                    <div style="text-align: center; padding: 20px; color: #d93025; background: rgba(217, 48, 37, 0.1); border-radius: 6px; margin: 10px;">
                        <div style="margin-bottom: 10px;">❌ Error</div>
                        <div style="font-size: 14px;" class="error-message"></div>
                    </div>
                `);
                // Safely set the error message text
                const errorMessageEl = transcriptContent.querySelector('.error-message');
                if (errorMessageEl) {
                    window.SafeDOM.setText(errorMessageEl, message);
                }
            } else {
                // Fallback: create elements safely without innerHTML for message
            this.safeSetHTML(transcriptContent, `
                <div style="text-align: center; padding: 20px; color: #d93025; background: rgba(217, 48, 37, 0.1); border-radius: 6px; margin: 10px;">
                    <div style="margin-bottom: 10px;">❌ Error</div>
                        <div style="font-size: 14px;" class="error-message"></div>
                </div>
            `);
                const errorMessageEl = transcriptContent.querySelector('.error-message');
                if (errorMessageEl) {
                    errorMessageEl.textContent = message;
                }
            }
        }
    }
    // Show authentication prompt for summary generation
    showSummaryAuthPrompt() {
        const summaryContent = this.embeddedContainer?.querySelector('#summary-content');
        if (summaryContent) {
            // Clear existing content and show auth prompt
            this.safeSetHTML(summaryContent, `
                <div style="text-align: center; padding: 20px 16px;">
                    <div style="width: 48px; height: 48px; margin: 0 auto 12px; background: #eef2ff; border-radius: 50%; display: flex; align-items: center; justify-content: center;">
                        <svg width="24" height="24" viewBox="0 0 24 24" fill="#4f46e5">
                            <path d="M12,4A4,4 0 0,1 16,8A4,4 0 0,1 12,12A4,4 0 0,1 8,8A4,4 0 0,1 12,4M12,14C16.42,14 20,15.79 20,18V20H4V18C4,15.79 7.58,14 12,14Z"/>
                        </svg>
                    </div>
                    <h3 style="margin: 0 0 6px; font-size: 15px; font-weight: 600; color: #1f2937;">Sign In Required</h3>
                    <p style="margin: 0 0 16px; font-size: 13px; color: #6b7280; line-height: 1.4;">
                        Please sign in or create an account to generate AI-powered video summaries.
                    </p>
                    <div style="display: flex; gap: 8px; justify-content: center;">
                        <button id="summary-auth-signin-btn" style="display: inline-flex; align-items: center; gap: 4px; padding: 7px 14px; font-size: 12px; font-weight: 500; background: #1e40af; border: none; border-radius: 5px; cursor: pointer; color: white; transition: all 0.15s ease;">
                            <svg width="12" height="12" viewBox="0 0 24 24" fill="currentColor">
                                <path d="M12,4A4,4 0 0,1 16,8A4,4 0 0,1 12,12A4,4 0 0,1 8,8A4,4 0 0,1 12,4M12,14C16.42,14 20,15.79 20,18V20H4V18C4,15.79 7.58,14 12,14Z"/>
                            </svg>
                            Sign In
                        </button>
                        <button id="summary-auth-signup-btn" style="display: inline-flex; align-items: center; gap: 4px; padding: 7px 14px; font-size: 12px; font-weight: 500; background: #f9fafb; border: 1px solid #d1d5db; border-radius: 5px; cursor: pointer; color: #374151; transition: all 0.15s ease;">
                            <svg width="12" height="12" viewBox="0 0 24 24" fill="currentColor">
                                <path d="M15,14C12.33,14 7,15.33 7,18V20H23V18C23,15.33 17.67,14 15,14M6,10V7H4V10H1V12H4V15H6V12H9V10M15,12A4,4 0 0,0 19,8A4,4 0 0,0 15,4A4,4 0 0,0 11,8A4,4 0 0,0 15,12Z"/>
                            </svg>
                            Sign Up
                        </button>
                    </div>
                </div>
            `);

            // Bind event listeners
            setTimeout(() => {
                const signinBtn = summaryContent.querySelector('#summary-auth-signin-btn');
                const signupBtn = summaryContent.querySelector('#summary-auth-signup-btn');

                if (signinBtn) {
                    signinBtn.addEventListener('click', () => {
                        this.showInlineAuthForm('login', '#summary-content');
                    });
                }
                if (signupBtn) {
                    signupBtn.addEventListener('click', () => {
                        this.showInlineAuthForm('signup', '#summary-content');
                    });
                }
            }, 0);
        }
    }

    // Show summary error with retry option
    showSummaryError(message) {
        const summaryContent = this.embeddedContainer?.querySelector('#summary-content');
        if (summaryContent) {
            // Clear all content and show error display
            this.safeSetHTML(summaryContent, `
                <div id="summary-error-container" style="text-align: center; padding: 24px; background: rgba(239, 68, 68, 0.05); border: 1px solid rgba(239, 68, 68, 0.2); border-radius: 8px; margin: 16px;">
                    <div style="color: #dc2626; margin-bottom: 16px;">
                        <svg width="24" height="24" viewBox="0 0 24 24" fill="currentColor" style="display: inline-block; vertical-align: middle; margin-bottom: 4px;">
                            <path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm1 15h-2v-2h2v2zm0-4h-2V7h2v6z"/>
                        </svg>
                        <div style="font-size: 16px; font-weight: 600; margin-top: 8px;">Summary Generation Failed</div>
                    </div>
                    <div style="font-size: 14px; color: #666; margin-bottom: 20px; line-height: 1.5;">${message}</div>
                    <div style="display: flex; gap: 12px; justify-content: center;">
                        <button id="retry-summary-btn" style="display: inline-flex; align-items: center; gap: 6px; padding: 8px 16px; font-size: 13px; background: #1e40af; color: white; border: none; border-radius: 6px; cursor: pointer; font-weight: 500;">
                            <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor">
                                <path d="M17.65 6.35C16.2 4.9 14.21 4 12 4c-4.42 0-7.99 3.58-7.99 8s3.57 8 7.99 8c3.73 0 6.84-2.55 7.73-6h-2.08c-.82 2.33-3.04 4-5.65 4-3.31 0-6-2.69-6-6s2.69-6 6-6c1.66 0 3.14.69 4.22 1.78L13 11h7V4l-2.35 2.35z"/>
                            </svg>
                            Retry
                        </button>
                        <button id="upgrade-summary-btn" style="display: none; padding: 8px 16px; font-size: 13px; background: #1e40af; color: white; border: none; border-radius: 6px; cursor: pointer; font-weight: 500;">
                            Upgrade
                        </button>
                        <button id="cancel-summary-btn" style="padding: 8px 16px; font-size: 13px; background: #f3f4f6; color: #666; border: 1px solid #d1d5db; border-radius: 6px; cursor: pointer; font-weight: 500;">
                            Cancel
                        </button>
                    </div>
                </div>
            `);
            const errorContainer = summaryContent.querySelector('#summary-error-container');
            // Determine if this error qualifies for upgrade prompt
            const isLimitError = /weekly video limit/i.test(message);
            if (isLimitError) {
                const upgradeBtnInline = errorContainer.querySelector('#upgrade-summary-btn');
                if (upgradeBtnInline) upgradeBtnInline.style.display = 'inline-block';
            }
            // Add event listeners for retry, cancel, and upgrade
            setTimeout(() => {
                const retryBtn = errorContainer.querySelector('#retry-summary-btn');
                const cancelBtn = errorContainer.querySelector('#cancel-summary-btn');
                const upgradeBtn = errorContainer.querySelector('#upgrade-summary-btn');
                if (retryBtn) {
                    retryBtn.addEventListener('click', () => {
                        errorContainer.remove();
                        this.handleGenerateSummary();
                    });
                }
                if (cancelBtn) {
                    cancelBtn.addEventListener('click', () => {
                        errorContainer.remove();
                    });
                }
                if (upgradeBtn) {
                    upgradeBtn.addEventListener('click', () => {
                        // Use PaymentManager modal if available, otherwise fallback to URL
                        if (this.paymentManagerLoaded && window.PaymentManager) {
                            try {
                                console.log('🔧 Creating PaymentManager for upgrade button');
                                const paymentManager = new window.PaymentManager();
                                paymentManager.showUpgradePrompt('weekly_limit');
                            } catch (error) {
                                console.error('❌ PaymentManager constructor error on upgrade button:', error);
                                console.log('PaymentManager details:', {
                                    loaded: this.paymentManagerLoaded,
                                    exists: !!window.PaymentManager,
                                    type: typeof window.PaymentManager,
                                    constructor: window.PaymentManager
                                });
                                // Fallback: Open pricing page directly
                                window.open('https://tubevibe.app/pricing', '_blank');
                            }
                        } else {
                            window.open(PREMIUM_UPGRADE_URL, '_blank');
                        }
                    });
                }
            }, 100);
        }
    }
    // Show success message
    showSuccess(message) {
        // Use the non-destructive feedback method
        this.showFeedback(message, 'success');
    }
    // Show transcript content with smart segmentation
    showTranscript(transcript) {
        // Clean up and store transcript for summary generation
        this.lastExtractedTranscript = this.cleanupTranscriptText(transcript);
        const transcriptContent = this.embeddedContainer?.querySelector('#transcript-content');
        if (transcriptContent) {
            // Parse transcript into intelligent segments
            const segments = this.parseTranscriptIntoSmartSegments(transcript);
            this.safeSetHTML(transcriptContent, `
                <div style="padding: 14px;">
                    <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 14px; padding-bottom: 10px; border-bottom: 1px solid rgba(0, 0, 0, 0.08);">
                        <h4 style="margin: 0; font-size: 15px; color: #333; font-weight: 600; letter-spacing: -0.01em;">Transcript</h4>
                        <div style="display: flex; gap: 6px;">
                            <button id="tubevibe-copy-btn" style="display: inline-flex; align-items: center; gap: 4px; padding: 5px 10px; font-size: 11px; font-weight: 500; background: #f9fafb; border: 1px solid #e5e7eb; border-radius: 5px; cursor: pointer; transition: all 0.15s ease; color: #4b5563;">
                                <svg width="11" height="11" viewBox="0 0 24 24" fill="currentColor">
                                    <path d="M16 1H4C2.9 1 2 1.9 2 3V17H4V3H16V1ZM19 5H8C6.9 5 6 5.9 6 7V21C6 22.1 6.9 23 8 23H19C20.1 23 21 22.1 21 21V7C21 5.9 20.1 5 19 5ZM19 21H8V7H19V21Z"/>
                                </svg>
                                Copy
                            </button>
                            <button id="tubevibe-download-btn" style="display: inline-flex; align-items: center; gap: 4px; padding: 5px 10px; font-size: 11px; font-weight: 500; background: #f9fafb; border: 1px solid #e5e7eb; border-radius: 5px; cursor: pointer; transition: all 0.15s ease; color: #4b5563;">
                                <svg width="11" height="11" viewBox="0 0 24 24" fill="currentColor">
                                    <path d="M19 9h-4V3H9v6H5l7 7 7-7zM5 18v2h14v-2H5z"/>
                                </svg>
                                Download
                            </button>
                            <button id="tubevibe-save-library-btn" style="display: inline-flex; align-items: center; gap: 4px; padding: 5px 10px; font-size: 11px; font-weight: 500; background: #f9fafb; border: 1px solid #e5e7eb; border-radius: 5px; cursor: pointer; transition: all 0.15s ease; color: #4b5563;">
                                <svg width="11" height="11" viewBox="0 0 24 24" fill="currentColor">
                                    <path d="M19 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11l5 5v11a2 2 0 0 1-2 2z M17 21v-8H7v8 M7 3v5h8"/>
                                </svg>
                                Save
                            </button>
                        </div>
                    </div>
                    <div style="margin-bottom: 14px; padding: 10px; background: linear-gradient(135deg, #f8f9fa 0%, #f1f3f4 100%); border-radius: 8px; border: 1px solid rgba(0, 0, 0, 0.04);">
                        <div style="font-size: 11px; color: #666; display: flex; align-items: center; gap: 8px;">
                            <span style="display: flex; align-items: center; gap: 4px;">
                                <svg width="12" height="12" viewBox="0 0 24 24" fill="currentColor" style="opacity: 0.7;">
                                    <path d="M9 11H7v6h2v-6zm4 0h-2v6h2v-6zm4 0h-2v6h2v-6zm2.5-9H19V1h-2v1H7V1H5v1H3.5C2.67 2 2 2.67 2 3.5v15C2 19.33 2.67 20 3.5 20h17c.83 0 1.5-.67 1.5-1.5v-15C22 2.67 21.33 2 20.5 2zM20.5 18.5h-17v-13h17v13z"/>
                                </svg>
                                ${segments.length} segments
                            </span>
                            <span style="display: flex; align-items: center; gap: 4px;">
                                <svg width="12" height="12" viewBox="0 0 24 24" fill="currentColor" style="opacity: 0.7;">
                                    <path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm-2 15l-5-5 1.41-1.41L10 14.17l7.59-7.59L19 8l-9 9z"/>
                                </svg>
                                Timestamped
                            </span>
                        </div>
                    </div>
                    <div style="max-height: 320px; overflow-y: auto; scrollbar-width: none; -ms-overflow-style: none; border-radius: 8px;" class="tubevibe-transcript-scroll">
                        ${segments.map((segment, index) => `
                            <div style="display: flex; gap: 8px; padding: 8px 12px; margin-bottom: 1px; border-left: 3px solid transparent; background: ${index % 2 === 0 ? 'rgba(248, 249, 250, 0.6)' : 'rgba(255, 255, 255, 0.8)'}; transition: all 0.2s ease; cursor: pointer;" 
                                 data-time="${segment.startTime}"
                                 onmouseover="this.style.borderLeftColor='#ff0000'; this.style.backgroundColor='rgba(255, 0, 0, 0.02)'"
                                 onmouseout="this.style.borderLeftColor='transparent'; this.style.backgroundColor='${index % 2 === 0 ? 'rgba(248, 249, 250, 0.6)' : 'rgba(255, 255, 255, 0.8)'}'">
                                <div style="flex-shrink: 0; width: 48px; display: flex; flex-direction: column; align-items: flex-start;">
                                    <button class="tubevibe-seek-btn" data-time="${segment.startTime}" style="background: linear-gradient(135deg, #f8f9fa 0%, #e9ecef 100%); border: 1px solid rgba(0, 0, 0, 0.08); border-radius: 4px; padding: 2px 6px; font-size: 10px; color: #666; cursor: pointer; transition: all 0.2s ease; font-weight: 500; font-family: 'SF Mono', Monaco, monospace;"
                                            title="Jump to ${this.formatTime(segment.startTime)}">
                                        ${this.formatTime(segment.startTime)}
                                    </button>
                                    ${segment.isAutoGenerated ? '<div style="font-size: 8px; color: #999; margin-top: 2px; font-style: italic;">(auto)</div>' : ''}
                                </div>
                                <div class="transcript-segment-text" style="flex: 1; line-height: 1.4; color: #2d3748; font-size: 12px; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; letter-spacing: 0.01em;">
                                    ${this.enhanceTextFormatting(segment.text)}
                                </div>
                            </div>
                        `).join('')}
                    </div>
                </div>
            `);
            // Add event listeners for copy and download buttons
            setTimeout(() => {
                const copyBtn = transcriptContent.querySelector('#tubevibe-copy-btn');
                const downloadBtn = transcriptContent.querySelector('#tubevibe-download-btn');
                const seekBtns = transcriptContent.querySelectorAll('.tubevibe-seek-btn');
                if (copyBtn) {
                    copyBtn.addEventListener('click', () => this.handleCopyTranscript(transcript));
                }
                if (downloadBtn) {
                    downloadBtn.addEventListener('click', () => this.handleDownloadTranscript(transcript));
                }
                const saveLibraryBtn = transcriptContent.querySelector('#tubevibe-save-library-btn');
                if (saveLibraryBtn) {
                    saveLibraryBtn.addEventListener('click', () => this.handleSaveToLibrary(transcript));
                }
                // Add event listeners for seek buttons
                seekBtns.forEach(btn => {
                    btn.addEventListener('click', (e) => {
                        const time = parseFloat(e.target.getAttribute('data-time'));
                        this.seekToTime(time);
                    });
                });
            }, 100);
        }
    }
    // Parse transcript into intelligent segments
    parseTranscriptIntoSmartSegments(transcript) {
        console.log('Parsing transcript into smart segments');
        // Clean transcript from UI elements
        const cleanedTranscript = this.cleanTranscriptFromUIElements(transcript);
        const workingTranscript = cleanedTranscript.length > 20 ? cleanedTranscript : transcript;
        const segments = [];
        // Check if transcript has timestamp format like [00:00] or 00:00
        const timestampRegex = /(?:\[(\d{1,2}:\d{2})\]|\b(\d{1,2}:\d{2})\b)/g;
        const timestampMatchesAll = Array.from(workingTranscript.matchAll(timestampRegex));
        const hasTimestamps = timestampMatchesAll.length >= 2;
        if (hasTimestamps) {
            // Parse transcript with real timestamps
            let lines = workingTranscript.split('\n').filter(line => line.trim());
            if (lines.length === 1) {
                // Single line transcript - split by timestamp patterns
                const patterns = [
                    /(?=\[\d{1,2}:\d{2}\])/g,  // [00:00] format
                    /(?=\d{1,2}:\d{2}\s)/g,    // 00:00 format with space
                    /(?=\d{1,2}:\d{2}[^\d])/g  // 00:00 format with non-digit
                ];
                for (const pattern of patterns) {
                    const testSplit = workingTranscript.split(pattern).filter(part => part.trim());
                    if (testSplit.length > 1) {
                        lines = testSplit;
                        break;
                    }
                }
            }
            let currentText = '';
            let currentStartTime = 0;
            lines.forEach((line, index) => {
                const cleanLine = line.trim();
                if (!cleanLine) return;
                // Extract timestamp from line
                const timestampMatch = cleanLine.match(/(?:\[(\d{1,2}:\d{2})\]|^(\d{1,2}:\d{2}))/);
                if (timestampMatch) {
                    // Found a new timestamp - save previous segment if exists
                    if (currentText.trim()) {
                        const isAutoGenerated = this.detectAutoGeneratedCaption(currentText);
                        const nextTime = this.parseTimeToSeconds(timestampMatch[1] || timestampMatch[2]);
                        segments.push({
                            startTime: currentStartTime,
                            endTime: nextTime,
                            text: this.cleanTranscriptText(currentText),
                            isAutoGenerated
                        });
                    }
                    // Start new segment
                    currentStartTime = this.parseTimeToSeconds(timestampMatch[1] || timestampMatch[2]);
                    currentText = cleanLine.replace(/(?:\[\d{1,2}:\d{2}\]|\d{1,2}:\d{2})/, '').trim();
                } else {
                    // Continue current segment
                    currentText += ' ' + cleanLine;
                }
            });
            // Add final segment
            if (currentText.trim()) {
                const isAutoGenerated = this.detectAutoGeneratedCaption(currentText);
                segments.push({
                    startTime: currentStartTime,
                    endTime: currentStartTime + 60, // Estimate 60s for final segment
                    text: this.cleanTranscriptText(currentText),
                    isAutoGenerated
                });
            }
        } else {
            // No timestamps - create segments by sentence/paragraph
            // Split by sentences and paragraphs
            const sentences = workingTranscript.split(/[.!?]+/).filter(s => s.trim().length > 10);
            const segmentSize = Math.max(1, Math.floor(sentences.length / 10)); // Aim for ~10 segments
            for (let i = 0; i < sentences.length; i += segmentSize) {
                const segmentSentences = sentences.slice(i, i + segmentSize);
                const text = segmentSentences.join('. ').trim();
                if (text) {
                    const startTime = Math.floor((i / sentences.length) * 300); // Estimate based on typical video length
                    const endTime = Math.floor(((i + segmentSize) / sentences.length) * 300);
                    segments.push({
                        startTime,
                        endTime,
                        text: this.cleanTranscriptText(text),
                        isAutoGenerated: true
                    });
                }
            }
        }
        return segments;
    }
    // Clean transcript from UI elements
    cleanTranscriptFromUIElements(transcript) {
        return transcript
            .replace(/\[(Music|Applause|Laughter|Inaudible)\]/gi, '')
            .replace(/\[.*?\]/g, '') // Remove other bracketed content
            .replace(/\s+/g, ' ')
            .trim();
    }
    // Detect auto-generated captions
    detectAutoGeneratedCaption(text) {
        // Auto-generated captions often have certain patterns
        const autoPatterns = [
            /\b(um|uh|ah|like|you know)\b/gi,
            /\b\w+\b\s+\b\w+\b\s+\b\w+\b/g // Very short phrases
        ];
        return autoPatterns.some(pattern => pattern.test(text));
    }
    // Parse time string to seconds
    parseTimeToSeconds(timeStr) {
        if (!timeStr) return 0;
        const parts = timeStr.split(':');
        if (parts.length === 2) {
            return parseInt(parts[0]) * 60 + parseInt(parts[1]);
        }
        return 0;
    }
    // Format seconds to time string
    formatTime(seconds) {
        const mins = Math.floor(seconds / 60);
        const secs = seconds % 60;
        return mins + ':' + secs.toString().padStart(2, '0');
    }
    // Clean transcript text
    cleanTranscriptText(text) {
        // First apply comprehensive artifact cleaning
        const cleanedText = this.cleanTextArtifacts(text);
        // Then apply formatting fixes
        return cleanedText
            .replace(/\s+/g, ' ')
            .replace(/([.!?])\s*([a-z])/g, '$1 $2') // Fix spacing after punctuation
            .trim();
    }
    // Enhance text formatting (without HTML to avoid artifacts)
    enhanceTextFormatting(text) {
        // For now, just return the text as-is to avoid HTML artifacts
        // The formatting can be applied via CSS classes if needed
        return text
            .replace(/([.!?])\s+/g, '$1 ') // Clean up spacing after punctuation
            .replace(/\s+/g, ' ') // Normalize whitespace
            .replace(/\.\.\./g, '…') // Replace three dots with ellipsis
            .trim();
    }
    // Handle copy transcript
    async handleCopyTranscript(transcript) {
        try {
            await navigator.clipboard.writeText(transcript);
            this.showSuccess('Transcript copied to clipboard!');
        } catch (error) {
            console.error('Failed to copy transcript:', error);
            this.showFeedback('Failed to copy transcript. Please try again.', 'error');
        }
    }
    // Handle download transcript
    handleDownloadTranscript(transcript) {
        try {
            // Get video title if available
            const titleElement = document.querySelector('h1.ytd-video-primary-info-renderer, h1.title');
            const videoTitle = titleElement ? titleElement.textContent.trim() : 'transcript';
            // Create filename
            const filename = videoTitle.replace(/[^a-z0-9]/gi, '_').toLowerCase() + '_transcript.txt';
            // Create blob and download
            const blob = new Blob([transcript], { type: 'text/plain;charset=utf-8' });
            const url = URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = filename;
            document.body.appendChild(a);
            a.click();
            document.body.removeChild(a);
            URL.revokeObjectURL(url);
            this.showSuccess('Transcript downloaded successfully!');
        } catch (error) {
            console.error('Failed to download transcript:', error);
            this.showFeedback('Failed to download transcript. Please try again.', 'error');
        }
    }
    // Handle save to library - saves video transcript to TubeVibe Library (Pinecone)
    async handleSaveToLibrary(transcript) {
        try {
            // Get save button and show loading state
            const saveBtn = this.embeddedContainer?.querySelector('#tubevibe-save-library-btn');
            if (saveBtn) {
                saveBtn.disabled = true;
                saveBtn.innerHTML = `
                    <svg width="10" height="10" viewBox="0 0 24 24" fill="currentColor" style="margin-right: 4px; vertical-align: middle; animation: spin 1s linear infinite;">
                        <path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm-2 15l-5-5 1.41-1.41L10 14.17l7.59-7.59L19 8l-9 9z"/>
                    </svg>
                    Saving...
                `;
            }

            // Get video metadata
            const videoId = this.getVideoId();
            const title = this.getVideoTitle();
            const channelName = this.getChannelName();
            const duration = this.getVideoDuration();

            if (!videoId) {
                throw new Error('Could not get video ID');
            }

            console.log('📚 Saving video to library:', { videoId, title, channelName });

            // Send to background script
            const response = await chrome.runtime.sendMessage({
                type: 'SAVE_TO_LIBRARY',
                data: {
                    video_id: videoId,
                    title: title || 'Untitled Video',
                    channel_name: channelName || 'Unknown Channel',
                    duration: duration,
                    transcript: this.cleanupTranscriptText(transcript),
                    thumbnail_url: `https://i.ytimg.com/vi/${videoId}/maxresdefault.jpg`,
                    url: window.location.href
                }
            });

            if (response && response.success) {
                this.showSuccess('Video saved to library! You can now chat and search across your saved videos.');
                // Update button to show saved state
                if (saveBtn) {
                    saveBtn.disabled = false;
                    saveBtn.innerHTML = `
                        <svg width="10" height="10" viewBox="0 0 24 24" fill="currentColor" style="margin-right: 4px; vertical-align: middle;">
                            <path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm-2 15l-5-5 1.41-1.41L10 14.17l7.59-7.59L19 8l-9 9z"/>
                        </svg>
                        Saved ✓
                    `;
                    saveBtn.style.background = 'linear-gradient(135deg, #28a745 0%, #20c997 100%)';
                }
                // Store that this video is saved for Chat tab integration
                this.currentVideoSaved = true;
                this.currentVideoId = videoId;
                // Also update the new saved state properties
                this.isVideoSaved = true;
                this.savedVideoInfo = {
                    id: response.video?.id,
                    title: title,
                    channel_name: channelName,
                    youtube_id: videoId,
                    created_at: new Date().toISOString()
                };
                // Enable chat interface
                this.showChatInterface();
            } else {
                throw new Error(response?.error || 'Failed to save video');
            }
        } catch (error) {
            console.error('❌ Failed to save to library:', error);
            this.showFeedback('Failed to save to library: ' + error.message, 'error');
            // Reset button
            const saveBtn = this.embeddedContainer?.querySelector('#tubevibe-save-library-btn');
            if (saveBtn) {
                saveBtn.disabled = false;
                saveBtn.innerHTML = `
                    <svg width="10" height="10" viewBox="0 0 24 24" fill="currentColor" style="margin-right: 4px; vertical-align: middle;">
                        <path d="M19 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11l5 5v11a2 2 0 0 1-2 2z M17 21v-8H7v8 M7 3v5h8"/>
                    </svg>
                    Save to Library
                `;
            }
        }
    }
    // Seek to specific time in video
    seekToTime(time) {
        const video = document.querySelector('video');
        if (video) {
            video.currentTime = time;
            video.play();
        }
    }
    // Show loading state for summary generation
    showLoadingState(message = 'Generating AI summary...') {
        // Prevent multiple overlays – reuse existing if present
        const existing = this.embeddedContainer?.querySelector('#summary-loading-overlay');
        if (existing) {
            const msg = existing.querySelector('.loading-message');
            if (msg) msg.textContent = message;
            return;
        }
        const summaryContent = this.embeddedContainer?.querySelector('#summary-content');
        const generateBtn = this.embeddedContainer?.querySelector('#generate-summary-btn');
        if (summaryContent) {
            // Create loading overlay without clearing existing content
            const loadingOverlay = document.createElement('div');
            loadingOverlay.id = 'summary-loading-overlay';
            loadingOverlay.style.cssText = `
                position: absolute;
                top: 0;
                left: 0;
                right: 0;
                bottom: 0;
                background: rgba(255, 255, 255, 0.95);
                display: flex;
                flex-direction: column;
                align-items: center;
                justify-content: center;
                z-index: 100;
                border-radius: 12px;
            `;
            // Use SafeDOM if available, otherwise fall back to safe text content
            if (window.SafeDOM && window.FeatureFlags?.isEnabled('SAFE_DOM_ENABLED')) {
                window.SafeDOM.setHTML(loadingOverlay, `
                    <div style="display: inline-block; width: 32px; height: 32px; border: 3px solid #f3f3f3; border-top: 3px solid #ff0000; border-radius: 50%; animation: spin 1s linear infinite; margin-bottom: 16px;"></div>
                    <div style="font-size: 14px; color: #666; font-weight: 500;" class="loading-message"></div>
                    <div style="font-size: 12px; color: #999; margin-top: 8px;">This may take a few moments</div>
                    <style>
                        @keyframes spin {
                            0% { transform: rotate(0deg); }
                            100% { transform: rotate(360deg); }
                        }
                    </style>
                `);
                // Safely set the loading message text
                const loadingMessageEl = loadingOverlay.querySelector('.loading-message');
                if (loadingMessageEl) {
                    window.SafeDOM.setText(loadingMessageEl, message);
                }
            } else {
                // Fallback: create elements safely without innerHTML for message
                this.safeSetHTML(loadingOverlay, `
                    <div style="display: inline-block; width: 32px; height: 32px; border: 3px solid #f3f3f3; border-top: 3px solid #ff0000; border-radius: 50%; animation: spin 1s linear infinite; margin-bottom: 16px;"></div>
                    <div style="font-size: 14px; color: #666; font-weight: 500;" class="loading-message"></div>
                    <div style="font-size: 12px; color: #999; margin-top: 8px;">This may take a few moments</div>
                    <style>
                        @keyframes spin {
                            0% { transform: rotate(0deg); }
                            100% { transform: rotate(360deg); }
                        }
                    </style>
                `);
                const loadingMessageEl = loadingOverlay.querySelector('.loading-message');
                if (loadingMessageEl) {
                    loadingMessageEl.textContent = message;
                }
            }
            // Make summary content relative positioned for overlay
            summaryContent.style.position = 'relative';
            summaryContent.appendChild(loadingOverlay);
        }
        // Disable the generate button
        if (generateBtn) {
            generateBtn.disabled = true;
            generateBtn.style.opacity = '0.5';
            generateBtn.style.cursor = 'not-allowed';
        }
    }
    // Show feedback message
    showFeedback(message, type = 'info') {
        // Remove any existing feedback
        const existingFeedback = this.embeddedContainer?.querySelector('#tubevibe-feedback');
        if (existingFeedback) {
            existingFeedback.remove();
        }
        // Create feedback element
        const feedback = document.createElement('div');
        feedback.id = 'tubevibe-feedback';
        feedback.style.cssText = `
            position: absolute;
            top: 60px;
            right: 20px;
            padding: 12px 20px;
            border-radius: 6px;
            font-size: 14px;
            font-weight: 500;
            z-index: 10000;
            animation: slideIn 0.3s ease-out;
            box-shadow: 0 2px 8px rgba(0, 0, 0, 0.15);
        `;
        // Style based on type
        if (type === 'success') {
            feedback.style.background = '#10b981';
            feedback.style.color = 'white';
        } else if (type === 'error') {
            feedback.style.background = '#ef4444';
            feedback.style.color = 'white';
        } else {
            feedback.style.background = '#3b82f6';
            feedback.style.color = 'white';
        }
        feedback.textContent = message;
        // Add animation style
        const style = document.createElement('style');
        style.textContent = `
            @keyframes slideIn {
                from { transform: translateX(100%); opacity: 0; }
                to { transform: translateX(0); opacity: 1; }
            }
            @keyframes slideOut {
                from { transform: translateX(0); opacity: 1; }
                to { transform: translateX(100%); opacity: 0; }
            }
        `;
        document.head.appendChild(style);
        // Add to embedded container
        if (this.embeddedContainer) {
            this.embeddedContainer.appendChild(feedback);
        } else {
            document.body.appendChild(feedback);
        }
        // Auto-remove after 3 seconds
        setTimeout(() => {
            feedback.style.animation = 'slideOut 0.3s ease-in forwards';
            setTimeout(() => {
                feedback.remove();
                style.remove();
            }, 300);
        }, 3000);
    }
    // Summary generation methods moved to use background script integration
    async getAuthToken() {
        // 🔧 ENHANCED: Use TokenManager for reliable token management
        try {
            // Wait a bit for TokenManager to initialize if needed
            let retryCount = 0;
            while (!this.tokenManagerLoaded && retryCount < 5) {
                await new Promise(resolve => setTimeout(resolve, 100));
                retryCount++;
            }
            
            if (this.tokenManagerLoaded && window.TokenManager) {
                console.log('🔍 [EmbeddedPopup] Using TokenManager for getAuthToken');
                return await window.TokenManager.getValidAccessToken();
            } else {
                console.log('⚠️ [EmbeddedPopup] TokenManager not loaded, falling back to direct storage');
                // Fallback to direct storage access
                return new Promise((resolve) => {
                    chrome.storage.local.get(['access_token'], (result) => {
                        resolve(result.access_token || null);
                    });
                });
            }
        } catch (error) {
            console.error('❌ [EmbeddedPopup] Error in getAuthToken:', error);
            // Fallback to direct storage access
            return new Promise((resolve) => {
                chrome.storage.local.get(['access_token'], (result) => {
                    resolve(result.access_token || null);
                });
            });
        }
    }
    async getUserId() {
        // Use Chrome storage directly - simpler approach
        return new Promise((resolve) => {
            chrome.storage.local.get(['user_info'], (result) => {
                const userInfo = result.user_info || {};
                resolve(userInfo.id || null);
            });
        });
    }
    getVideoTitle() {
        // Get video title from DOM
        const titleSelectors = [
            'h1.ytd-video-primary-info-renderer',
            'h1.ytd-videoPrimaryInfoRenderer',
            'h1 yt-formatted-string',
            '.ytp-title-text',
            'title'
        ];
        for (const selector of titleSelectors) {
            const element = document.querySelector(selector);
            if (element && element.textContent) {
                return element.textContent.trim();
            }
        }
        return 'Unknown Video Title';
    }
    getChannelName() {
        // Get channel name from DOM
        const channelSelectors = [
            'ytd-video-owner-renderer .ytd-channel-name a',
            'ytd-video-owner-renderer yt-formatted-string',
            '#owner-text a',
            '#channel-name',
            '.ytd-channel-name'
        ];
        for (const selector of channelSelectors) {
            const element = document.querySelector(selector);
            if (element && element.textContent) {
                return element.textContent.trim();
            }
        }
        return 'Unknown Channel';
    }
    getVideoDuration() {
        // Get video duration from DOM
        const durationSelectors = [
            '.ytp-time-duration',
            '.ytd-thumbnail-overlay-time-status-renderer',
            '.ytp-bound-time-right'
        ];
        for (const selector of durationSelectors) {
            const element = document.querySelector(selector);
            if (element && element.textContent) {
                const timeText = element.textContent.trim();
                return this.parseTimeToSeconds(timeText);
            }
        }
        // Try to get from video element
        const videoElement = document.querySelector('video');
        if (videoElement && videoElement.duration) {
            return videoElement.duration;
        }
        return 0; // Default duration
    }
    parseTimeToSeconds(timeString) {
        // Parse time string like "12:34" or "1:23:45" to seconds
        const parts = timeString.split(':').map(Number);
        let seconds = 0;
        if (parts.length === 3) {
            // Hours:minutes:seconds
            seconds = parts[0] * 3600 + parts[1] * 60 + parts[2];
        } else if (parts.length === 2) {
            // Minutes:seconds
            seconds = parts[0] * 60 + parts[1];
        } else if (parts.length === 1) {
            // Just seconds
            seconds = parts[0];
        }
        return seconds;
    }
    // Polling method removed - now using background script integration
    showSummaryLoading() {
        const summaryContent = this.embeddedContainer?.querySelector('#summary-content');
        if (summaryContent) {
            this.safeSetHTML(summaryContent, `
                <div style="padding: 16px; text-align: center;">
                    <div style="display: inline-block; width: 32px; height: 32px; border: 3px solid #f3f3f3; border-top: 3px solid #ff0000; border-radius: 50%; animation: spin 1s linear infinite; margin-bottom: 16px;"></div>
                    <div style="font-size: 14px; color: #666;">Generating AI summary...</div>
                    <div style="font-size: 12px; color: #999; margin-top: 8px;">This may take a few moments</div>
                </div>
                <style>
                    @keyframes spin {
                        0% { transform: rotate(0deg); }
                        100% { transform: rotate(360deg); }
                    }
                </style>
            `);
        }
    }
    clearLoadingState() {
        // Remove loading overlay only
        const loadingOverlay = this.embeddedContainer?.querySelector('#summary-loading-overlay');
        if (loadingOverlay) {
            loadingOverlay.remove();
        }
        // Re-enable the generate button
        const generateBtn = this.embeddedContainer?.querySelector('#generate-summary-btn');
        if (generateBtn) {
            generateBtn.disabled = false;
            generateBtn.style.opacity = '1';
            generateBtn.style.cursor = 'pointer';
        }
        // Reset summary content positioning
        const summaryContent = this.embeddedContainer?.querySelector('#summary-content');
        if (summaryContent) {
            summaryContent.style.position = '';
        }
    }
    async fetchAndDisplaySummary(transcriptId) {
        console.log(`🔍 fetchAndDisplaySummary called with transcriptId: "${transcriptId}"`);
        const maxRetries = 5;
        let retryDelay = 2000; // Start with 2 seconds
        for (let attempt = 1; attempt <= maxRetries; attempt++) {
            try {
                // Add delay before retry (except first attempt)
                if (attempt > 1) {
                    console.log(`⏳ Waiting ${retryDelay}ms before retry attempt ${attempt}...`);
                    await new Promise(resolve => setTimeout(resolve, retryDelay));
                }
                
                const url = 'https://simply-backend-production.up.railway.app/api/yt_summary/' + transcriptId;
                console.log(`🌐 Attempt ${attempt}/${maxRetries}: Fetching summary from: ${url}`);
                
                const response = await fetch(url, {
                    method: 'GET',
                    headers: {
                        'Content-Type': 'application/json',
                        'X-Extension-Request': 'true'
                    }
                });
                
                console.log(`📡 Response status: ${response.status} ${response.statusText}`);
                
                if (!response.ok) {
                    const errorText = await response.text();
                    console.error(`❌ API Error (${response.status}): ${errorText}`);
                    throw new Error('HTTP ' + response.status + ': ' + response.statusText + ' - ' + errorText);
                }
                const result = await response.json();
                console.log(`📋 API Response for attempt ${attempt}:`, result);
                
                if (result.success && result.summary && result.summary.length > 10) {
                    console.log(`✅ Summary loaded successfully: ${result.summary.length} characters`);
                    this.showSummary(result.summary);
                    return; // Success, exit the retry loop
                } else {
                    console.log(`⚠️ Summary not ready yet, attempt ${attempt}:`, result);
                    console.log(`🔍 Result details: success=${result.success}, summary=${result.summary ? result.summary.length + ' chars' : 'null'}`);
                    
                    // If it's the last attempt, show REAL error instead of fake success
                    if (attempt === maxRetries) {
                        console.error(`❌ REAL ERROR: Failed to get summary after ${maxRetries} attempts for transcript: ${transcriptId}`);
                        this.showSummaryError(`Summary not available yet. Please try again in a few moments. (Transcript ID: ${transcriptId})`);
                        return;
                    }
                    // Otherwise, continue to next retry
                    retryDelay *= 1.5; // Increase delay: 2s, 3s, 4.5s, 6.75s, 10s
                    continue;
                }
            } catch (error) {
                console.error(`❌ Error fetching summary (attempt ${attempt}/${maxRetries}):`, error);
                if (attempt === maxRetries) {
                    console.error(`❌ REAL ERROR: All ${maxRetries} attempts failed for transcript: ${transcriptId}`);
                    this.showSummaryError(`Failed to load summary: ${error.message}. Please try again later or contact support. (Transcript ID: ${transcriptId})`);
                    return;
                } else {
                    retryDelay *= 1.5;
                    continue;
                }
            }
        }
    }
    showSummary(summary) {
        // Ensure loading overlay is removed
        this.hideLoadingState();
        const summaryContent = this.embeddedContainer?.querySelector('#summary-content');
        if (summaryContent) {
            // Hide all empty states and loading states
            const summaryEmpty = this.embeddedContainer?.querySelector('#summary-empty');
            const summaryAuthRequired = this.embeddedContainer?.querySelector('#summary-auth-required');
            const summaryReady = this.embeddedContainer?.querySelector('#summary-ready');
            const summaryDisplay = this.embeddedContainer?.querySelector('#summary-display');
            
            // Hide the generate summary prompt and auth prompts
            if (summaryEmpty) summaryEmpty.classList.add('hidden');
            if (summaryAuthRequired) summaryAuthRequired.classList.add('hidden');
            if (summaryReady) summaryReady.classList.add('hidden');
            
            // Show the summary display container
            if (summaryDisplay) summaryDisplay.classList.remove('hidden');
            
            // Update summary content with properly formatted HTML
            const summaryContentArea = this.embeddedContainer?.querySelector('#summary-content-area');
            if (summaryContentArea) {
                // Clean up markdown code fences that may be present in the summary
                let cleanedSummary = summary;
                
                // Remove ```html at the beginning
                cleanedSummary = cleanedSummary.replace(/^```html\s*/i, '');
                
                // Remove ``` at the end
                cleanedSummary = cleanedSummary.replace(/\s*```\s*$/, '');
                
                // Remove any other code block indicators
                cleanedSummary = cleanedSummary.replace(/```[a-zA-Z]*\s*/g, '');
                
                // Check if summary is already formatted HTML or needs formatting
                const isHTML = cleanedSummary.trim().startsWith('<');
                const formattedSummary = isHTML ? cleanedSummary : this.formatSummaryText(cleanedSummary);
                
                this.safeSetHTML(summaryContentArea, `
                    <div style="font-size: 11px; line-height: 1.5; color: #333; text-align: justify;">
                        ${formattedSummary}
                    </div>
                `);
            }
            
            // Ensure action buttons are properly bound
            const regenerateBtn = this.embeddedContainer?.querySelector('#regenerate-summary-btn');
            const copyBtn = this.embeddedContainer?.querySelector('#copy-summary-btn');
            const downloadBtn = this.embeddedContainer?.querySelector('#download-summary-btn');
            
            if (regenerateBtn) {
                // Remove any existing listeners to prevent duplicates
                regenerateBtn.replaceWith(regenerateBtn.cloneNode(true));
                
                // Re-get the element and add fresh listener
                const newRegenerateBtn = this.embeddedContainer?.querySelector('#regenerate-summary-btn');
                if (newRegenerateBtn) {
                    newRegenerateBtn.addEventListener('click', (e) => {
                        e.preventDefault();
                        this.handleGenerateSummary();
                    });
                }
            }
            
            if (copyBtn) {
                // Remove any existing listeners to prevent duplicates
                copyBtn.replaceWith(copyBtn.cloneNode(true));
                
                // Re-get the element and add fresh listener
                const newCopyBtn = this.embeddedContainer?.querySelector('#copy-summary-btn');
                if (newCopyBtn) {
                    newCopyBtn.addEventListener('click', (e) => {
                        e.preventDefault();
                        this.copySummaryToClipboard();
                    });
                }
            }
            
            if (downloadBtn) {
                // Remove any existing listeners to prevent duplicates
                downloadBtn.replaceWith(downloadBtn.cloneNode(true));
                
                // Re-get the element and add fresh listener
                const newDownloadBtn = this.embeddedContainer?.querySelector('#download-summary-btn');
                if (newDownloadBtn) {
                    newDownloadBtn.addEventListener('click', (e) => {
                        e.preventDefault();
                        this.downloadSummaryAsFile();
                    });
                }
            }
        }
    }
    
    async copySummaryToClipboard() {
        try {
            const summaryContentArea = this.embeddedContainer?.querySelector('#summary-content-area');
            if (!summaryContentArea) {
                throw new Error('No summary content found to copy');
            }
            
            // Extract text content from the summary, removing HTML tags
            let summaryText = summaryContentArea.textContent || summaryContentArea.innerText || '';
            
            if (!summaryText.trim()) {
                throw new Error('Summary content is empty');
            }
            
            // Clean up any remaining markdown artifacts in the copied text
            summaryText = summaryText.replace(/^```html\s*/i, '');
            summaryText = summaryText.replace(/\s*```\s*$/, '');
            summaryText = summaryText.replace(/```[a-zA-Z]*\s*/g, '');
            
            // Use the modern clipboard API
            await navigator.clipboard.writeText(summaryText);
            
            // Show success feedback
            const copyBtn = this.embeddedContainer?.querySelector('#copy-summary-btn');
            if (copyBtn) {
                const originalText = copyBtn.innerHTML;
                copyBtn.innerHTML = `
                    <svg width="12" height="12" viewBox="0 0 24 24" fill="currentColor" class="simply-mr-1" style="color: #10b981;">
                        <path d="M9 16.17L4.83 12l-1.42 1.41L9 19 21 7l-1.41-1.41z"/>
                    </svg>
                    Copied!
                `;
                copyBtn.style.color = '#10b981';
                
                // Reset after 2 seconds
                setTimeout(() => {
                    copyBtn.innerHTML = originalText;
                    copyBtn.style.color = '';
                }, 2000);
            }
            
            console.log('✅ Summary copied to clipboard');
            
        } catch (error) {
            console.error('❌ Failed to copy summary:', error);
            
            // Show error feedback
            const copyBtn = this.embeddedContainer?.querySelector('#copy-summary-btn');
            if (copyBtn) {
                const originalText = copyBtn.innerHTML;
                copyBtn.innerHTML = `
                    <svg width="12" height="12" viewBox="0 0 24 24" fill="currentColor" class="simply-mr-1" style="color: #ef4444;">
                        <path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm1 15h-2v-2h2v2zm0-4h-2V7h2v6z"/>
                    </svg>
                    Failed
                `;
                copyBtn.style.color = '#ef4444';
                
                // Reset after 2 seconds
                setTimeout(() => {
                    copyBtn.innerHTML = originalText;
                    copyBtn.style.color = '';
                }, 2000);
            }
        }
    }
    
    async downloadSummaryAsFile() {
        try {
            const summaryContentArea = this.embeddedContainer?.querySelector('#summary-content-area');
            if (!summaryContentArea) {
                throw new Error('No summary content found to download');
            }
            
            // Extract text content from the summary, removing HTML tags
            let summaryText = summaryContentArea.textContent || summaryContentArea.innerText || '';
            
            if (!summaryText.trim()) {
                throw new Error('Summary content is empty');
            }
            
            // Clean up any remaining markdown artifacts
            summaryText = summaryText.replace(/^```html\s*/i, '');
            summaryText = summaryText.replace(/\s*```\s*$/, '');
            summaryText = summaryText.replace(/```[a-zA-Z]*\s*/g, '');
            
            // Get video metadata for filename
            const videoData = await this.getCurrentVideoData();
            const videoTitle = videoData?.title || 'YouTube Video';
            const videoId = videoData?.video_id || 'unknown';
            
            // Create a clean filename
            const sanitizedTitle = videoTitle.replace(/[^a-zA-Z0-9\s\-_]/g, '').replace(/\s+/g, '_').substring(0, 50);
            const timestamp = new Date().toISOString().split('T')[0]; // YYYY-MM-DD format
            const filename = `TubeVibe_Summary_${sanitizedTitle}_${videoId}_${timestamp}.txt`;
            
            // Add header information to the download
            const downloadContent = `TubeVibe AI Summary
Generated: ${new Date().toLocaleString()}
Video: ${videoTitle}
Video ID: ${videoId}
URL: https://youtube.com/watch?v=${videoId}

=====================================

${summaryText}

=====================================
Generated by TubeVibe Chrome Extension
Visit: TubeVibe.app
`;
            
            // Create blob and download
            const blob = new Blob([downloadContent], { type: 'text/plain;charset=utf-8' });
            const url = URL.createObjectURL(blob);
            
            // Create temporary download link
            const downloadLink = document.createElement('a');
            downloadLink.href = url;
            downloadLink.download = filename;
            downloadLink.style.display = 'none';
            
            // Append to document, click, and remove
            document.body.appendChild(downloadLink);
            downloadLink.click();
            document.body.removeChild(downloadLink);
            
            // Clean up the URL object
            URL.revokeObjectURL(url);
            
            // Show success feedback
            const downloadBtn = this.embeddedContainer?.querySelector('#download-summary-btn');
            if (downloadBtn) {
                const originalText = downloadBtn.innerHTML;
                downloadBtn.innerHTML = `
                    <svg width="12" height="12" viewBox="0 0 24 24" fill="currentColor" class="simply-mr-1" style="color: #10b981;">
                        <path d="M9 16.17L4.83 12l-1.42 1.41L9 19 21 7l-1.41-1.41z"/>
                    </svg>
                    Downloaded!
                `;
                downloadBtn.style.color = '#10b981';
                
                // Reset after 2 seconds
                setTimeout(() => {
                    downloadBtn.innerHTML = originalText;
                    downloadBtn.style.color = '';
                }, 2000);
            }
            
            console.log('✅ Summary downloaded as file:', filename);
            
        } catch (error) {
            console.error('❌ Failed to download summary:', error);
            
            // Show error feedback
            const downloadBtn = this.embeddedContainer?.querySelector('#download-summary-btn');
            if (downloadBtn) {
                const originalText = downloadBtn.innerHTML;
                downloadBtn.innerHTML = `
                    <svg width="12" height="12" viewBox="0 0 24 24" fill="currentColor" class="simply-mr-1" style="color: #ef4444;">
                        <path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm1 15h-2v-2h2v2zm0-4h-2V7h2v6z"/>
                    </svg>
                    Failed
                `;
                downloadBtn.style.color = '#ef4444';
                
                // Reset after 2 seconds
                setTimeout(() => {
                    downloadBtn.innerHTML = originalText;
                    downloadBtn.style.color = '';
                }, 2000);
            }
        }
    }

    async emailSummary() {
        try {
            const summaryContentArea = this.embeddedContainer?.querySelector('#summary-content-area');
            if (!summaryContentArea) {
                throw new Error('No summary content found to email');
            }

            // Get the HTML content of the summary
            let summaryHtml = summaryContentArea.innerHTML || '';

            if (!summaryHtml.trim()) {
                throw new Error('Summary content is empty');
            }

            // Get video metadata
            const videoData = await this.getCurrentVideoData();
            const videoTitle = videoData?.title || 'YouTube Video';
            const videoId = videoData?.video_id || 'unknown';
            const channelName = videoData?.channel_name || '';
            const durationSeconds = videoData?.duration_seconds || 0;

            // Show email input dialog
            const email = await this.showEmailInputDialog();
            if (!email) {
                console.log('Email sending cancelled by user');
                return;
            }

            // Show sending state
            const emailBtn = this.embeddedContainer?.querySelector('#email-summary-btn');
            let originalBtnText = '';
            if (emailBtn) {
                originalBtnText = emailBtn.innerHTML;
                emailBtn.innerHTML = `
                    <svg width="12" height="12" viewBox="0 0 24 24" fill="currentColor" class="simply-mr-1 animate-spin">
                        <path d="M12 2V6M12 18V22M4.93 4.93L7.76 7.76M16.24 16.24L19.07 19.07M2 12H6M18 12H22M4.93 19.07L7.76 16.24M16.24 7.76L19.07 4.93"/>
                    </svg>
                    Sending...
                `;
                emailBtn.disabled = true;
            }

            // Send email via background script
            const response = await chrome.runtime.sendMessage({
                type: 'EMAIL_VIDEO_SUMMARY',
                data: {
                    video_id: videoId,
                    recipient_email: email,
                    summary_html: summaryHtml,
                    video_title: videoTitle,
                    channel_name: channelName,
                    duration_seconds: durationSeconds,
                    transcript_length: summaryHtml.length
                }
            });

            if (response && response.success) {
                // Show success
                if (emailBtn) {
                    emailBtn.innerHTML = `
                        <svg width="12" height="12" viewBox="0 0 24 24" fill="currentColor" class="simply-mr-1" style="color: #10b981;">
                            <path d="M9 16.17L4.83 12l-1.42 1.41L9 19 21 7l-1.41-1.41z"/>
                        </svg>
                        Sent!
                    `;
                    emailBtn.style.color = '#10b981';
                    emailBtn.disabled = false;

                    setTimeout(() => {
                        emailBtn.innerHTML = originalBtnText;
                        emailBtn.style.color = '';
                    }, 3000);
                }
                console.log('✅ Summary emailed successfully to:', email);
            } else {
                throw new Error(response?.error || 'Failed to send email');
            }

        } catch (error) {
            console.error('❌ Failed to email summary:', error);

            // Show error feedback
            const emailBtn = this.embeddedContainer?.querySelector('#email-summary-btn');
            if (emailBtn) {
                const originalText = emailBtn.innerHTML;
                emailBtn.innerHTML = `
                    <svg width="12" height="12" viewBox="0 0 24 24" fill="currentColor" class="simply-mr-1" style="color: #ef4444;">
                        <path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm1 15h-2v-2h2v2zm0-4h-2V7h2v6z"/>
                    </svg>
                    Failed
                `;
                emailBtn.style.color = '#ef4444';
                emailBtn.disabled = false;

                setTimeout(() => {
                    emailBtn.innerHTML = `
                        <svg width="12" height="12" viewBox="0 0 24 24" fill="currentColor" class="simply-mr-1">
                            <path d="M20 4H4c-1.1 0-1.99.9-1.99 2L2 18c0 1.1.9 2 2 2h16c1.1 0 2-.9 2-2V6c0-1.1-.9-2-2-2zm0 4l-8 5-8-5V6l8 5 8-5v2z"/>
                        </svg>
                        Email
                    `;
                    emailBtn.style.color = '';
                }, 3000);
            }
        }
    }

    async showEmailInputDialog() {
        return new Promise((resolve) => {
            // Create overlay
            const overlay = document.createElement('div');
            overlay.style.cssText = `
                position: fixed;
                top: 0;
                left: 0;
                right: 0;
                bottom: 0;
                background: rgba(0, 0, 0, 0.5);
                z-index: 10000;
                display: flex;
                align-items: center;
                justify-content: center;
            `;

            // Create dialog
            const dialog = document.createElement('div');
            dialog.style.cssText = `
                background: white;
                border-radius: 12px;
                padding: 20px;
                width: 320px;
                box-shadow: 0 10px 25px rgba(0, 0, 0, 0.2);
            `;

            dialog.innerHTML = `
                <h3 style="margin: 0 0 16px 0; font-size: 16px; color: #333;">Email Summary</h3>
                <p style="margin: 0 0 12px 0; font-size: 12px; color: #666;">Enter the email address to send this summary to:</p>
                <input type="email" id="email-input" placeholder="email@example.com"
                    style="width: 100%; padding: 10px 12px; border: 1px solid #ddd; border-radius: 8px; font-size: 14px; box-sizing: border-box; margin-bottom: 16px;" />
                <div style="display: flex; gap: 8px; justify-content: flex-end;">
                    <button id="email-cancel-btn" style="padding: 8px 16px; background: #f3f4f6; color: #666; border: none; border-radius: 6px; cursor: pointer; font-size: 13px;">Cancel</button>
                    <button id="email-send-btn" style="padding: 8px 16px; background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; border: none; border-radius: 6px; cursor: pointer; font-size: 13px; font-weight: 500;">Send</button>
                </div>
            `;

            overlay.appendChild(dialog);
            document.body.appendChild(overlay);

            const emailInput = dialog.querySelector('#email-input');
            const cancelBtn = dialog.querySelector('#email-cancel-btn');
            const sendBtn = dialog.querySelector('#email-send-btn');

            emailInput.focus();

            const cleanup = () => {
                document.body.removeChild(overlay);
            };

            cancelBtn.addEventListener('click', () => {
                cleanup();
                resolve(null);
            });

            overlay.addEventListener('click', (e) => {
                if (e.target === overlay) {
                    cleanup();
                    resolve(null);
                }
            });

            sendBtn.addEventListener('click', () => {
                const email = emailInput.value.trim();
                if (email && email.includes('@')) {
                    cleanup();
                    resolve(email);
                } else {
                    emailInput.style.borderColor = '#ef4444';
                    emailInput.focus();
                }
            });

            emailInput.addEventListener('keypress', (e) => {
                if (e.key === 'Enter') {
                    const email = emailInput.value.trim();
                    if (email && email.includes('@')) {
                        cleanup();
                        resolve(email);
                    } else {
                        emailInput.style.borderColor = '#ef4444';
                    }
                }
            });
        });
    }

    formatSummaryText(summary) {
        // --- Pre-processing -------------------------------------------------
        let text = summary.replace(/\r\n/g, '\n').trim();
        // If the summary already contains <p> tags, assume it is HTML and return unchanged
        if (/<p[\s>]/i.test(text)) {
            return text;
        }
        // Add blank line after headings of the form "Title:" to help paragraph detection
        text = text.replace(/(^|\n)([A-Z][^\n:]{3,}:)(\s*)/g, '$1$2$3\n');
        // Convert markdown headings (###) to plain lines followed by blank line
        text = text.replace(/(^|\n)#+\s([^\n]+)/g, '$1$2\n');
        // Collapse 3+ newlines → 2 newlines
        text = text.replace(/\n{3,}/g, '\n\n');

        // --- Paragraph detection ------------------------------------------
        let paragraphs = [];
        if (text.includes('\n\n')) {
            paragraphs = text.split(/\n\s*\n/).filter(p => p.trim());
        } else {
            const lines = text.split('\n').filter(l => l.trim());
            let current = '';
            for (let i = 0; i < lines.length; i++) {
                const line = lines[i].trim();
                const next = lines[i + 1]?.trim();
                current += (current ? ' ' : '') + line;
                const end = (
                    line.endsWith('.') && next && /^[A-Z]/.test(next) ||
                    line.length < 60 && next && next.length > 60 ||
                    i === lines.length - 1
                );
                if (end) {
                    paragraphs.push(current.trim());
                    current = '';
                }
            }
        }

        // --- HTML formatting ----------------------------------------------
        const htmlParagraphs = paragraphs.map(p => {
            const isHeading = p.length < 70 && !/[.!?]$/.test(p);
            const cleaned = p
                .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
                .replace(/\*(.*?)\*/g, '<em>$1</em>');
            if (isHeading) {
                return `<p class="summary-heading" style="font-weight:600; margin:0 0 16px 0; line-height:1.4;">${cleaned}</p>`;
            }
            return `<p style="margin-bottom: 16px; line-height: 1.6;">${cleaned}</p>`;
        });

        const styleBlock = '<style>.summary-heading + p { margin-top:0; }</style>';
        return styleBlock + htmlParagraphs.join('');
    }

    showError(message) {
        const errorDisplay = this.embeddedContainer?.querySelector('#error-display');
        const errorMessage = this.embeddedContainer?.querySelector('#error-message');
        if (errorDisplay && errorMessage) {
            errorMessage.textContent = message;
            errorDisplay.classList.remove('hidden');
            // Auto-hide after 5 seconds
            setTimeout(() => {
                errorDisplay.classList.add('hidden');
            }, 5000);
        }
        console.error('❌ Error:', message);
    }
    showLoading() {
        // Show loading state in transcript tab
        const transcriptContent = this.embeddedContainer?.querySelector('#transcript-content');
        if (transcriptContent) {
            this.safeSetHTML(transcriptContent, `
                <div style="padding: 16px; text-align: center;">
                    <div style="display: inline-block; width: 32px; height: 32px; border: 3px solid #f3f3f3; border-top: 3px solid #ff0000; border-radius: 50%; animation: spin 1s linear infinite; margin-bottom: 16px;"></div>
                    <div style="font-size: 14px; color: #666;">Extracting transcript...</div>
                    <div style="font-size: 12px; color: #999; margin-top: 8px;">Please wait while we process the video</div>
                </div>
                <style>
                    @keyframes spin {
                        0% { transform: rotate(0deg); }
                        100% { transform: rotate(360deg); }
                    }
                </style>
            `);
        }
    }
    // Update authentication UI in embedded popup
    async updateEmbeddedAuthUI() {
        try {
            // Debug: Check all stored data
            const allStorageData = await new Promise((resolve) => {
                chrome.storage.local.get(null, (result) => {
                    resolve(result);
                });
            });
            // Secure logging for storage data
            if (window.SecureLogger) {
                window.SecureLogger.log('🔐 All storage data:', allStorageData);
            } else {
                console.log('Storage keys:', Object.keys(allStorageData).join(', '));
            }
            // Get current authentication status from Chrome storage
            const authToken = await this.getAuthToken();
            const isAuthenticated = !!authToken;
            // Secure logging - only show token in dev mode
            if (window.FeatureFlags?.isEnabled('VERBOSE_ERROR_LOGGING')) {
            } else if (window.SecureLogger) {
                window.SecureLogger.log('🔐 Auth token:', authToken);
            } else {
            }
            // Get user info from Chrome storage (with fresh data fetch)
            let userInfo = null;
            if (isAuthenticated) {
                // 🔧 ENHANCED: Force refresh user info to ensure latest plan data
                try {
                    console.log('🔄 [EmbeddedPopup] Force refreshing user info for UI update...');
                    console.log('🔍 [DEBUG] Sending GET_SUBSCRIPTION_STATUS message to background...');
                    
                    const refreshResponse = await chrome.runtime.sendMessage({
                        type: 'GET_SUBSCRIPTION_STATUS'
                    });
                    
                    console.log('🔍 [DEBUG] Background response received:', JSON.stringify(refreshResponse, null, 2));
                    
                    if (refreshResponse?.success && refreshResponse?.userInfo) {
                        userInfo = refreshResponse.userInfo;
                        console.log('✅ [EmbeddedPopup] Fresh user info for UI:', userInfo?.email, userInfo?.plan);
                        console.log('🔍 [DEBUG] Fresh userInfo object:', JSON.stringify(userInfo, null, 2));
                    } else {
                        console.warn('⚠️ [EmbeddedPopup] Could not get fresh user info, falling back to cache');
                        console.warn('🔍 [DEBUG] Failed response details:', refreshResponse);
                        // Fallback to cached data
                        userInfo = await new Promise((resolve) => {
                            chrome.storage.local.get(['user_info'], (result) => {
                                resolve(result.user_info || null);
                            });
                        });
                    }
                } catch (error) {
                    console.warn('⚠️ [EmbeddedPopup] Error refreshing user info, using cache:', error);
                    // Fallback to cached data
                    userInfo = await new Promise((resolve) => {
                        chrome.storage.local.get(['user_info'], (result) => {
                            resolve(result.user_info || null);
                        });
                    });
                }
            }
            // Secure logging for user info
            if (window.SecureLogger) {
                window.SecureLogger.log('🔐 User info:', userInfo);
            } else if (userInfo) {
                console.log('User:', userInfo.email ? userInfo.email.split('@')[0] : 'Unknown');
            }
            // Update menu UI
            const loggedOutMenu = this.embeddedContainer?.querySelector('#logged-out-menu');
            const loggedInMenu = this.embeddedContainer?.querySelector('#logged-in-menu');
            const menuUserEmail = this.embeddedContainer?.querySelector('#menu-user-email');
            const menuUserPlan = this.embeddedContainer?.querySelector('#menu-user-plan');
            // Auth button containers
            const authButtonsLoggedOut = this.embeddedContainer?.querySelector('#auth-buttons-logged-out');
            const authButtonsLoggedIn = this.embeddedContainer?.querySelector('#auth-buttons-logged-in');
            const upgradeButton = this.embeddedContainer?.querySelector('#menu-upgrade-banner');
            // Update summary tab UI
            const summaryAuthRequired = this.embeddedContainer?.querySelector('#summary-auth-required');
            const summaryReady = this.embeddedContainer?.querySelector('#summary-ready');
            if (isAuthenticated && userInfo) {
                // Show authenticated state
                if (loggedOutMenu) loggedOutMenu.classList.add('hidden');
                if (loggedInMenu) loggedInMenu.classList.remove('hidden');
                // Toggle auth buttons
                if (authButtonsLoggedOut) authButtonsLoggedOut.classList.add('hidden');
                if (authButtonsLoggedIn) authButtonsLoggedIn.classList.remove('hidden');
                if (menuUserEmail) menuUserEmail.textContent = userInfo.email || 'user@example.com';
                const userPlan = userInfo.plan || 'free';
                if (menuUserPlan) menuUserPlan.textContent = userPlan.charAt(0).toUpperCase() + userPlan.slice(1) + ' Plan';
                // Show/hide upgrade banner based on plan
                if (upgradeButton) {
                    if (userPlan === 'free') {
                        upgradeButton.classList.remove('hidden');
                    } else {
                        upgradeButton.classList.add('hidden');
                    }
                }
                // Show summary ready state
                if (summaryAuthRequired) summaryAuthRequired.classList.add('hidden');
                if (summaryReady) summaryReady.classList.remove('hidden');
            } else {
                // Show unauthenticated state
                if (loggedOutMenu) loggedOutMenu.classList.remove('hidden');
                if (loggedInMenu) loggedInMenu.classList.add('hidden');
                // Toggle auth buttons
                if (authButtonsLoggedOut) authButtonsLoggedOut.classList.remove('hidden');
                if (authButtonsLoggedIn) authButtonsLoggedIn.classList.add('hidden');
                // Hide upgrade banner when not logged in
                if (upgradeButton) upgradeButton.classList.add('hidden');
                // Show summary auth required state - BUT RESPECT TEST_MODE
                if (!TEST_MODE) {
                    if (summaryAuthRequired) summaryAuthRequired.classList.remove('hidden');
                    if (summaryReady) summaryReady.classList.add('hidden');
                } else {
                    // In TEST_MODE, show ready state even when not authenticated
                    if (summaryAuthRequired) summaryAuthRequired.classList.add('hidden');
                    if (summaryReady) summaryReady.classList.remove('hidden');
                    console.log('🧪 TEST_MODE: Showing summary ready state despite no auth');
                }
                // Ensure authentication buttons are properly bound
                this.bindSummaryEvents();
            }
        } catch (error) {
            console.error('❌ Error updating authentication UI:', error);
        }
    }
    // Check authentication status on initialization
    async checkAuthenticationStatus() {
        try {
            // Wait a bit for TokenManager to initialize if needed
            let retryCount = 0;
            while (!this.tokenManagerLoaded && retryCount < 10) {
                await new Promise(resolve => setTimeout(resolve, 100));
                retryCount++;
            }
            
            // 🔧 ENHANCED: Use TokenManager for authentication validation
            if (this.tokenManagerLoaded && window.TokenManager) {
                console.log('🔍 [EmbeddedPopup] Using TokenManager for authentication check');
                const authState = await window.TokenManager.validateAuthState();
                
                // If authenticated, refresh user info to get latest plan
                if (authState.hasToken && !authState.isExpired) {
                    try {
                        console.log('🔄 Refreshing user info to get latest plan...');
                        const subscriptionResponse = await chrome.runtime.sendMessage({
                            type: 'GET_SUBSCRIPTION_STATUS'
                        });
                        
                        if (subscriptionResponse?.success && subscriptionResponse?.userInfo) {
                            console.log('✅ User info refreshed:', subscriptionResponse.userInfo.email, subscriptionResponse.userInfo.plan);
                        }
                    } catch (error) {
                        console.warn('⚠️ Could not refresh user info during auth check:', error);
                    }
                }
                
                // Get user info from storage (now potentially refreshed)
                const result = await chrome.storage.local.get(['user_info']);
                
                // Update UI based on authentication status
                await this.updateEmbeddedAuthUI();
                
                return {
                    isAuthenticated: authState.hasToken && !authState.isExpired,
                    hasToken: authState.hasToken,
                    isTokenExpired: authState.isExpired,
                    user: result.user_info,
                    accessToken: authState.hasAccessToken ? 'present' : null, // Don't expose token
                    timeToExpiry: authState.timeToExpiry
                };
            } else {
                console.log('⚠️ [EmbeddedPopup] TokenManager not loaded, using legacy auth check');
                // Fallback to legacy authentication check
                const result = await chrome.storage.local.get(['access_token', 'refresh_token', 'user_info', 'token_expires_at']);
                const hasToken = !!result.access_token;
                const tokenExpiresAt = result.token_expires_at;
                const now = Date.now();
                const isTokenExpired = tokenExpiresAt && (now >= (tokenExpiresAt - 5 * 60 * 1000));
                const isAuthenticated = hasToken && !isTokenExpired;
                
                // If authenticated, refresh user info to get latest plan
                if (isAuthenticated) {
                    try {
                        console.log('🔄 Refreshing user info to get latest plan...');
                        const subscriptionResponse = await chrome.runtime.sendMessage({
                            type: 'GET_SUBSCRIPTION_STATUS'
                        });
                        
                        if (subscriptionResponse?.success && subscriptionResponse?.userInfo) {
                            console.log('✅ User info refreshed:', subscriptionResponse.userInfo.email, subscriptionResponse.userInfo.plan);
                        }
                    } catch (error) {
                        console.warn('⚠️ Could not refresh user info during auth check:', error);
                    }
                }
                
                await this.updateEmbeddedAuthUI();
                
                return {
                    isAuthenticated,
                    hasToken,
                    isTokenExpired,
                    user: result.user_info,
                    accessToken: result.access_token
                };
            }
        } catch (error) {
            console.error('❌ Error checking authentication status:', error);
            // Return default unauthenticated state on error
            return {
                isAuthenticated: false,
                hasToken: false,
                isTokenExpired: true,
                user: null,
                accessToken: null,
                error: error.message
            };
        }
    }
    insertIntoSidebar() {
        const sidebar = this.findSidebar();
        if (sidebar) {
            // Insert at the top of the sidebar
            if (sidebar.firstChild) {
                sidebar.insertBefore(this.embeddedContainer, sidebar.firstChild);
            } else {
                sidebar.appendChild(this.embeddedContainer);
            }
        } else {
            // Fallback: append to body
            console.warn('⚠️ Sidebar not found, appending to body');
            document.body.appendChild(this.embeddedContainer);
        }
    }
    // Clean transcript text for backend processing (remove embedded CSS/HTML artifacts)
    cleanTranscriptForBackend(transcript) {
        if (!transcript) return '';
        let cleanedText = transcript;
        // Remove embedded CSS content (styles between [css] and [/css] or similar patterns)
        cleanedText = cleanedText.replace(/\[css\][\s\S]*?\[\/css\]/gi, '');
        cleanedText = cleanedText.replace(/\<style[\s\S]*?\<\/style\>/gi, '');
        // Remove HTML tags but preserve text content
        cleanedText = cleanedText.replace(/<[^>]*>/g, ' ');
        // Remove CSS properties and selectors (more comprehensive regex)
        cleanedText = cleanedText.replace(/[\w\-\.#]+\s*\{\s*[^}]*\}/g, '');
        cleanedText = cleanedText.replace(/[\w\-]+\s*:\s*[^;]+;?/g, '');
        // Remove common CSS units and values
        cleanedText = cleanedText.replace(/\b\d+px\b|\b\d+em\b|\b\d+%\b|\b#[0-9a-fA-F]{3,6}\b/g, '');
        cleanedText = cleanedText.replace(/\brgb\([^)]+\)|\brgba\([^)]+\)/g, '');
        // Remove CSS keywords
        cleanedText = cleanedText.replace(/\b(absolute|relative|fixed|flex|grid|block|inline|none|auto|inherit|initial|unset)\b/g, '');
        // Remove multiple whitespace and normalize
        cleanedText = cleanedText.replace(/\s+/g, ' ');
        cleanedText = cleanedText.replace(/\n\s*\n/g, '\n');
        cleanedText = cleanedText.trim();
        return cleanedText;
    }
    // 🆕 NEW: Comprehensive video data extraction for summary generation
    async getCurrentVideoData() {
        try {
            // Get basic video metadata
            const videoId = this.getVideoId();
            if (!videoId) {
                throw new Error('Could not extract video ID from current page');
            }
            const title = this.getVideoTitle();
            const channelName = this.getChannelName();
            const duration = this.getVideoDuration();
            // Extract transcript
            const transcript = await this.extractFromYouTubeDOMTranscript();
            if (!transcript || transcript.trim().length === 0) {
                throw new Error('Could not extract transcript from video. Please make sure transcript/captions are available.');
            }
            // Construct video data object for backend processing
            const videoData = {
                video_id: videoId,
                title: title,
                channel_name: channelName,
                duration: duration,
                transcript: transcript,
                url: window.location.href,
                timestamp: new Date().toISOString()
            };
            console.log('📊 Video data extracted:', {
                ...videoData,
                transcript: videoData.transcript.substring(0, 100) + '...' // Log only first 100 chars of transcript
            });
            return videoData;
        } catch (error) {
            console.error('❌ Error extracting video data:', error);
            throw error;
        }
    }

    // Fallback upgrade modal when PaymentManager fails
    showUpgradeModalFallback() {
        console.log('🆘 Showing fallback upgrade modal');
        
        // Create modal overlay
        const overlay = document.createElement('div');
        overlay.style.cssText = `
            position: fixed; top: 0; left: 0; width: 100%; height: 100%;
            background: rgba(0,0,0,0.7); z-index: 10000; display: flex;
            align-items: center; justify-content: center;
        `;
        
        // Create modal content
        const modal = document.createElement('div');
        modal.style.cssText = `
            background: white; border-radius: 12px; padding: 24px;
            max-width: 400px; text-align: center; box-shadow: 0 8px 32px rgba(0,0,0,0.3);
        `;
        
        modal.innerHTML = `
            <h2 style="color: #333; margin: 0 0 16px 0;">Upgrade to Premium</h2>
            <p style="color: #666; margin: 0 0 24px 0;">
                You've reached your weekly limit. Upgrade for unlimited video summaries!
            </p>
            <div style="display: flex; gap: 12px; justify-content: center;">
                <button onclick="window.open('https://tubevibe.app/pricing', '_blank')" 
                        style="background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; border: none; padding: 16px 32px; border-radius: 8px; cursor: pointer; font-size: 16px; font-weight: 600;">
                    View Pricing Plans
                </button>
            </div>
            <button onclick="this.parentElement.parentElement.remove()" 
                    style="background: #6c757d; color: white; border: none; padding: 8px 16px; border-radius: 4px; cursor: pointer; margin-top: 16px;">
                Close
            </button>
        `;
        
        overlay.appendChild(modal);
        document.body.appendChild(overlay);
        
        // Auto-remove after 30 seconds
        setTimeout(() => {
            if (overlay.parentElement) overlay.remove();
        }, 30000);
    }
    
    // Start proactive token refresh to prevent session expiration
    startTokenRefreshInterval() {
        // Check token expiration every 10 minutes and refresh if needed
        setInterval(async () => {
            try {
                const result = await chrome.storage.local.get(['access_token', 'token_expires_at']);
                const expiresAt = result.token_expires_at;
                
                if (expiresAt) {
                    // Refresh token if it expires within the next 15 minutes
                    const fifteenMinutesFromNow = Date.now() + (15 * 60 * 1000);
                    
                    if (expiresAt <= fifteenMinutesFromNow) {
                        console.log('🔄 Proactively refreshing token (expires within 15 minutes)');
                        
                        try {
                            const refreshResponse = await chrome.runtime.sendMessage({
                                type: 'REFRESH_TOKEN'
                            });
                            
                            if (refreshResponse?.success) {
                                console.log('✅ Proactive token refresh successful');
                                // Update UI with fresh data
                                await this.updateEmbeddedAuthUI();
                            } else {
                                console.warn('⚠️ Proactive token refresh failed:', refreshResponse?.error);
                            }
                        } catch (error) {
                            console.warn('⚠️ Error during proactive token refresh:', error);
                        }
                    }
                }
            } catch (error) {
                console.warn('⚠️ Error checking token expiration:', error);
            }
        }, 10 * 60 * 1000); // Check every 10 minutes
        
        console.log('🔄 Started proactive token refresh interval (checks every 10 minutes)');
    }
    // Hide loading overlay (if present)
    hideLoadingState() {
        this.embeddedContainer?.querySelectorAll('#summary-loading-overlay').forEach(el=>el.remove());
        const generateBtn = this.embeddedContainer?.querySelector('#generate-summary-btn');
        if (generateBtn) {
            generateBtn.disabled = false;
            generateBtn.textContent = generateBtn.dataset.originalText || 'Generate Summary';
            generateBtn.classList.remove('simply-loading');
        }
    }
    sanitizeSummary(raw) {
        if (!raw) return '';
        let cleaned = raw.trim();
        if (cleaned.startsWith('```')) {
            const firstNl = cleaned.indexOf('\n');
            if (firstNl !== -1) cleaned = cleaned.slice(firstNl + 1);
        }
        if (cleaned.endsWith('```')) cleaned = cleaned.slice(0, -3);
        return cleaned.trim();
    }
}
// Initialize when the page loads with safe approach and LONGER delay
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', () => {
        setTimeout(() => {
            console.log('🎬 Initializing TubeVibe Embedded UI...');
            new EmbeddedPopupUI();
        }, 5000); // Wait 5 seconds for YouTube to fully load
    });
} else {
    setTimeout(() => {
        console.log('🎬 Initializing TubeVibe Embedded UI...');
        new EmbeddedPopupUI();
    }, 5000); // Wait 5 seconds for YouTube to fully load
}
