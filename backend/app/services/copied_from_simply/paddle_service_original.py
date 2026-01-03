"""
Paddle Payment Service
Handles Paddle Billing integration for subscription management
"""

import os
import json
import hmac
import hashlib
import base64
import logging
import httpx
from typing import Dict, Any, Optional, List
from datetime import datetime, timedelta
import uuid

from app.models.payment import (
    SubscriptionPlan, SubscriptionStatus, PaymentStatus,
    CheckoutRequest, CheckoutResponse, SubscriptionData, PaymentData,
    PaddleWebhookEvent, UpgradeRequest, UpgradeResponse,
    CancelSubscriptionRequest, CancelSubscriptionResponse,
    PADDLE_PRODUCTS
)
from app.services.supabase_client import get_supabase_client, SupabaseService

logger = logging.getLogger(__name__)

class PaddleService:
    """Service for handling Paddle Billing operations"""
    
    def __init__(self):
        """Initialize Paddle service with API credentials"""
        self.api_key = os.getenv("PADDLE_API_KEY")
        # Support multiple possible env var names and both environments
        # Collect possible secrets (order adjusted below based on environment)
        _candidates_all: List[tuple[str, str]] = [
            ("default", os.getenv("PADDLE_NOTIFICATION_SECRET", "")),
            ("prod", os.getenv("PADDLE_NOTIFICATION_SECRET_PROD", "")),
            ("sandbox", os.getenv("PADDLE_NOTIFICATION_SECRET_SANDBOX", "")),
            ("live", os.getenv("PADDLE_LIVE_NOTIFICATION_SECRET", "")),
            ("sandbox2", os.getenv("PADDLE_SANDBOX_NOTIFICATION_SECRET", "")),
        ]
        # Set environment first so we can prioritize ordering
        self.environment = os.getenv("PADDLE_ENVIRONMENT", "sandbox")  # sandbox or production
        # Prioritize secrets matching current environment
        if self.environment == "production":
            ordering = ["prod", "live", "default", "sandbox", "sandbox2"]
        else:
            ordering = ["sandbox", "sandbox2", "default", "prod", "live"]
        notification_secret_candidates: List[str] = [
            val for key in ordering for tag, val in _candidates_all if tag == key
        ]
        # Keep only non-empty, unique values while preserving order
        seen: set[str] = set()
        self.notification_secrets: List[str] = []
        for val in notification_secret_candidates:
            if val and val not in seen:
                self.notification_secrets.append(val)
                seen.add(val)
        # self.environment already set above
        
        # Set API base URL based on environment
        if self.environment == "production":
            self.api_base = "https://api.paddle.com"
        else:
            self.api_base = "https://sandbox-api.paddle.com"
            
        # Initialize Supabase client properly with better error handling
        self.supabase = None
        try:
            self.supabase = get_supabase_client()
            if not self.supabase:
                # Fallback: create a new SupabaseService instance if global client fails
                logger.warning("Global Supabase client not available, creating new instance")
                supabase_service = SupabaseService()
                if supabase_service.initialized:
                    self.supabase = supabase_service.client
                    logger.info("Successfully created fallback Supabase client")
                else:
                    logger.error("Failed to initialize fallback SupabaseService")
            else:
                logger.info("Successfully initialized Supabase client from global client")
        except Exception as e:
            logger.error(f"Error during Supabase client initialization: {e}")
            try:
                # Last resort: create new service directly
                logger.info("Attempting direct SupabaseService creation as last resort")
                supabase_service = SupabaseService()
                if supabase_service.initialized:
                    self.supabase = supabase_service.client
                    logger.info("Successfully created direct SupabaseService as last resort")
            except Exception as e2:
                logger.error(f"Final fallback failed: {e2}")
                
        if not self.supabase:
            logger.error("CRITICAL: Failed to initialize Supabase client for PaddleService - webhook handlers will fail")
        else:
            logger.info("✅ Supabase client successfully initialized in PaddleService")
        
        if not self.api_key:
            logger.warning("PADDLE_API_KEY not set - payment functionality will be disabled")
        
        logger.info(f"Paddle service initialized for {self.environment} environment")
    
    async def create_checkout_session(
        self, 
        user_id: str, 
        user_email: str, 
        request: CheckoutRequest
    ) -> CheckoutResponse:
        """Create a Paddle checkout session for subscription"""
        try:
            if not self.api_key:
                raise Exception("Paddle API key not configured")
            
            # Get product ID for the requested plan
            product_id = PADDLE_PRODUCTS.get(request.plan)
            if not product_id:
                raise Exception(f"No product ID configured for plan: {request.plan}")
            
            # Prepare checkout data with enhanced custom_data
            checkout_data = {
                "items": [
                    {
                        "price_id": product_id,
                        "quantity": 1
                    }
                ],
                "customer_email": user_email,
                "custom_data": {
                    "user_id": user_id,
                    "plan": request.plan.value,
                    "checkout_user_id": user_id,  # Redundant backup
                    "user_email": user_email,     # Additional backup for identification
                    "created_at": datetime.utcnow().isoformat()  # Timestamp for debugging
                },
                "return_url": request.success_url or f"https://tubevibe.app/success?plan={request.plan.value}",
                "locale": "en"
            }
            
            # Log checkout creation for debugging
            logger.info(f"🛒 Creating Paddle checkout for user {user_id} ({user_email}) with plan {request.plan.value}")
            logger.info(f"📝 Custom data being sent: {checkout_data['custom_data']}")
            
            # Add metadata if provided
            if request.metadata:
                checkout_data["custom_data"].update(request.metadata)
            
            # Make API request to Paddle
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{self.api_base}/transactions",
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type": "application/json"
                    },
                    json=checkout_data,
                    timeout=30.0
                )
                
                if response.status_code != 200:
                    error_data = response.json() if response.content else {}
                    logger.error(f"Paddle checkout creation failed: {response.status_code} - {error_data}")
                    raise Exception(f"Paddle API error: {error_data.get('error', {}).get('detail', 'Unknown error')}")
                
                result = response.json()
                
                # Extract checkout URL from response
                checkout_url = result.get("data", {}).get("checkout", {}).get("url")
                checkout_id = result.get("data", {}).get("id")
                
                if not checkout_url or not checkout_id:
                    logger.error(f"Invalid Paddle response: {result}")
                    raise Exception("Invalid response from Paddle API")
                
                logger.info(f"Created Paddle checkout for user {user_id}, plan {request.plan}")
                
                return CheckoutResponse(
                    checkout_url=checkout_url,
                    checkout_id=checkout_id,
                    expires_at=datetime.utcnow() + timedelta(hours=24)  # Paddle checkouts typically expire in 24h
                )
                
        except Exception as e:
            logger.error(f"Error creating Paddle checkout: {e}")
            raise
    
    async def get_subscription(self, subscription_id: str) -> Optional[SubscriptionData]:
        """Get subscription details from Paddle"""
        try:
            if not self.api_key:
                return None
            
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"{self.api_base}/subscriptions/{subscription_id}",
                    headers={
                        "Authorization": f"Bearer {self.api_key}"
                    },
                    timeout=30.0
                )
                
                if response.status_code == 404:
                    return None
                
                if response.status_code != 200:
                    logger.error(f"Error fetching subscription {subscription_id}: {response.status_code}")
                    return None
                
                result = response.json()
                subscription_data = result.get("data", {})
                
                # Convert Paddle subscription to our format
                return self._convert_paddle_subscription(subscription_data)
                
        except Exception as e:
            logger.error(f"Error fetching subscription {subscription_id}: {e}")
            return None
    
    async def cancel_subscription(
        self, 
        user_id: str, 
        request: CancelSubscriptionRequest
    ) -> CancelSubscriptionResponse:
        """Cancel a user's subscription"""
        try:
            # Get user's current subscription from database
            user_subscription = await self._get_user_subscription(user_id)
            if not user_subscription:
                return CancelSubscriptionResponse(
                    success=False,
                    message="No active subscription found"
                )
            
            paddle_subscription_id = user_subscription.get("paddle_subscription_id")
            if not paddle_subscription_id:
                return CancelSubscriptionResponse(
                    success=False,
                    message="No Paddle subscription ID found"
                )
            
            # Cancel with Paddle
            if request.cancel_immediately:
                effective_date = datetime.utcnow().isoformat()
            else:
                # Cancel at end of billing period
                effective_date = None
            
            cancel_data = {
                "effective_from": effective_date
            } if effective_date else {}
            
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{self.api_base}/subscriptions/{paddle_subscription_id}/cancel",
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type": "application/json"
                    },
                    json=cancel_data,
                    timeout=30.0
                )
                
                if response.status_code not in [200, 202]:
                    error_data = response.json() if response.content else {}
                    logger.error(f"Paddle cancellation failed: {response.status_code} - {error_data}")
                    return CancelSubscriptionResponse(
                        success=False,
                        message=f"Failed to cancel subscription: {error_data.get('error', {}).get('detail', 'Unknown error')}"
                    )
            
            # Update subscription in database
            await self._update_subscription_status(
                user_id, 
                SubscriptionStatus.CANCELLED,
                cancel_at_period_end=not request.cancel_immediately,
                cancelled_at=datetime.utcnow() if request.cancel_immediately else None
            )
            
            logger.info(f"Cancelled subscription for user {user_id}")
            
            return CancelSubscriptionResponse(
                success=True,
                message="Subscription cancelled successfully",
                cancelled_at=datetime.utcnow() if request.cancel_immediately else None,
                cancel_at_period_end=not request.cancel_immediately
            )
            
        except Exception as e:
            logger.error(f"Error cancelling subscription for user {user_id}: {e}")
            return CancelSubscriptionResponse(
                success=False,
                message=f"Error cancelling subscription: {str(e)}"
            )
    
    def verify_notification_signature(self, payload: bytes, signature_header: str) -> bool:
        """Verify Paddle Billing notification signature.

        Paddle Billing sends a header like:
          - "Paddle-Signature: t=TIMESTAMP; h1=SIGNATURE" (common)
          - or "Paddle-Signature: t=TIMESTAMP,v1=SIGNATURE"

        The signature is HMAC-SHA256 of either:
          - raw payload bytes
          - or f"{t}:{payload}" (some Paddle docs/examples include the timestamp)

        Encoding can be hex or base64 depending on examples/SDKs. We validate
        against both encodings to be robust across environments while still
        requiring knowledge of the shared secret(s).
        """
        try:
            if not self.notification_secrets:
                logger.warning("Paddle notification secret not configured")
                return False

            # Parse the header into key/value pairs
            def parse_header(header_value: str) -> dict[str, str]:
                parts: List[str] = []
                # Support both ';' and ',' as separators
                for chunk in header_value.split(";"):
                    parts.extend(chunk.split(","))
                kv: dict[str, str] = {}
                for part in parts:
                    if "=" in part:
                        k, v = part.strip().split("=", 1)
                        kv[k.strip().lower()] = v.strip()
                return kv

            header_map = parse_header(signature_header or "")
            try:
                logger.debug(
                    "Paddle signature header keys present: %s",
                    ",".join(sorted(header_map.keys())) or "<none>",
                )
            except Exception:
                pass
            provided_sig_values: List[str] = []
            # Common keys seen: 'h1', 'v1', sometimes just 'signature'
            for key in ("h1", "v1", "signature", "s", "sig"):
                if key in header_map:
                    provided_sig_values.append(header_map[key])
            # If header didn't include kv pairs, treat entire header as signature
            if not provided_sig_values and signature_header:
                provided_sig_values.append(signature_header.strip())

            timestamp = header_map.get("t") or header_map.get("ts")

            def matches_any(secret: str) -> bool:
                try:
                    # Compute HMAC over raw payload
                    digest_raw = hmac.new(secret.encode(), payload, hashlib.sha256).digest()
                    hex_raw = digest_raw.hex()
                    b64_raw = base64.b64encode(digest_raw).decode()

                    candidates = {hex_raw, b64_raw}

                    # Also try including timestamp prefix if present
                    if timestamp:
                        ts_payload = f"{timestamp}:{payload.decode(errors='ignore')}".encode()
                        digest_ts = hmac.new(secret.encode(), ts_payload, hashlib.sha256).digest()
                        candidates.add(digest_ts.hex())
                        candidates.add(base64.b64encode(digest_ts).decode())

                    # Constant-time compare against any provided value
                    for provided in provided_sig_values:
                        for expected in candidates:
                            if hmac.compare_digest(provided, expected):
                                return True
                    return False
                except Exception as inner_e:
                    logger.error(f"Signature match error: {inner_e}")
                    return False

            for secret in self.notification_secrets:
                if matches_any(secret):
                    return True

            logger.warning("Paddle webhook signature did not match any known secrets")
            return False

        except Exception as e:
            logger.error(f"Error verifying notification signature: {e}")
            return False
    
    async def process_notification(self, raw_body: bytes, signature: str) -> Dict[str, Any]:
        """Process Paddle Billing notification event"""
        try:
            # Verify signature using the *raw* body bytes received from FastAPI
            if not self.verify_notification_signature(raw_body, signature):
                logger.warning("Invalid notification signature")
                return {"success": False, "error": "Invalid signature"}
            
            # Parse JSON AFTER signature passes
            payload: Dict[str, Any] = json.loads(raw_body.decode())
            
            # CRITICAL DEBUG: Log the ENTIRE payload structure to understand Paddle's format
            logger.error(f"🔍 FULL PADDLE WEBHOOK PAYLOAD: {json.dumps(payload, indent=2)}")
            
            event_type = payload.get("event_type")
            event_data = payload.get("data", {})
            
            logger.info(f"Processing Paddle webhook: {event_type}")
            logger.debug(f"Paddle webhook payload keys: {list(payload.keys())}")
            logger.debug(f"Event data type: {type(event_data)}, keys: {list(event_data.keys()) if isinstance(event_data, dict) else 'not a dict'}")
            
            # Route to appropriate handler
            if event_type == "subscription.created":
                return await self._handle_subscription_created(event_data)
            elif event_type == "subscription.updated":
                return await self._handle_subscription_updated(event_data)
            elif event_type in ["subscription.cancelled", "subscription.canceled"]:
                return await self._handle_subscription_cancelled(event_data)
            elif event_type == "transaction.completed":
                return await self._handle_transaction_completed(event_data)
            elif event_type == "transaction.updated":
                return await self._handle_transaction_updated(event_data)
            else:
                logger.info(f"Unhandled webhook event type: {event_type}")
                return {"success": True, "message": "Event acknowledged but not processed"}
            
        except Exception as e:
            logger.error(f"Error processing webhook: {e}")
            return {"success": False, "error": str(e)}
    
    async def _handle_subscription_created(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Handle subscription.created webhook"""
        try:
            # Check if Supabase client is available
            if not self.supabase:
                logger.error("CRITICAL: Supabase client not initialized - cannot handle subscription created")
                # Try to reinitialize Supabase client
                try:
                    from app.services.supabase_client import SupabaseService
                    supabase_service = SupabaseService()
                    if supabase_service.initialized:
                        self.supabase = supabase_service.client
                        logger.info("✅ Emergency Supabase client reinitialization successful")
                    else:
                        logger.error("❌ Emergency Supabase client reinitialization failed")
                        return {"success": False, "error": "Database connection not available"}
                except Exception as e:
                    logger.error(f"❌ Emergency Supabase reinitialization error: {e}")
                    return {"success": False, "error": "Database connection not available"}
                
            # Check if data is valid
            if not data or not isinstance(data, dict):
                logger.error(f"Invalid subscription created data: {type(data)} - {data}")
                return {"success": False, "error": "Invalid webhook data"}
                
            subscription_id = data.get("id")
            custom_data = data.get("custom_data") or {}
            user_id = custom_data.get("user_id")
            plan = custom_data.get("plan", "premium")
            
            # Enhanced user identification for subscription creation
            if not user_id:
                logger.warning("No user_id in custom_data, attempting enhanced user identification")
                customer_id = data.get("customer_id")
                transaction_id = data.get("transaction_id")
                
                # Use the enhanced identification method
                user_id = await self._identify_transaction_user(custom_data, customer_id, subscription_id, transaction_id)
                
                # For subscriptions, we're more lenient - try additional strategies
                if not user_id and customer_id:
                    logger.info(f"🔍 Trying additional strategies for subscription creation with customer_id: {customer_id}")
                    
                    # Check if we can find a user by email from customer data (if available in future)
                    # For now, we'll create a "pending" subscription that can be linked later
                    logger.warning(f"💡 Could not identify user for subscription.created webhook")
                    logger.warning(f"Customer ID: {customer_id}, Transaction ID: {transaction_id}")
                    logger.warning(f"Creating subscription record without user_id for later linking")
                    
                    # Create subscription record without user_id for manual review/linking
                    subscription_data = {
                        "id": str(uuid.uuid4()),
                        "user_id": None,  # Will be updated when user is identified
                        "paddle_subscription_id": subscription_id,
                        "paddle_customer_id": customer_id,
                        "plan": plan,
                        "status": "pending_user_link",  # Special status for manual review
                        "current_period_start": data.get("current_billing_period", {}).get("starts_at"),
                        "current_period_end": data.get("current_billing_period", {}).get("ends_at"),
                        "created_at": datetime.utcnow().isoformat(),
                        "updated_at": datetime.utcnow().isoformat()
                    }
                    
                    try:
                        result = self.supabase.table("subscriptions").insert(subscription_data).execute()
                        if result.data:
                            logger.warning(f"⚠️ Created subscription record for manual linking: subscription_id={subscription_id}, customer_id={customer_id}")
                            return {"success": True, "message": "Subscription created but requires manual user linking"}
                        else:
                            logger.error(f"Failed to create pending subscription record: {result}")
                    except Exception as e:
                        logger.error(f"Error creating pending subscription: {e}")
                    
                    return {"success": True, "message": "Subscription webhook acknowledged but user identification failed"}
            
            # Create subscription record in database
            subscription_data = {
                "id": str(uuid.uuid4()),
                "user_id": user_id,
                "paddle_subscription_id": subscription_id,
                "paddle_customer_id": data.get("customer_id"),  # Store customer_id for future lookups
                "plan": plan,  # Use plan to match subscriptions table schema
                "status": SubscriptionStatus.ACTIVE.value,
                "current_period_start": data.get("current_billing_period", {}).get("starts_at"),
                "current_period_end": data.get("current_billing_period", {}).get("ends_at"),
                "created_at": datetime.utcnow().isoformat(),
                "updated_at": datetime.utcnow().isoformat()
            }
            
            # Store in database
            result = self.supabase.table("subscriptions").insert(subscription_data).execute()
            
            if result.data:
                logger.info(f"Created subscription record for user {user_id}")
                
                # Update user plan in user_profiles
                await self._update_user_plan(user_id, plan)
                
                return {"success": True, "message": "Subscription created"}
            else:
                logger.error(f"Failed to create subscription record: {result}")
                return {"success": False, "error": "Database error"}
            
        except Exception as e:
            logger.error(f"Error handling subscription created: {e}")
            return {"success": False, "error": str(e)}
    
    async def _handle_subscription_updated(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Handle subscription.updated webhook"""
        try:
            # Check if Supabase client is available
            if not self.supabase:
                logger.error("CRITICAL: Supabase client not initialized - cannot handle subscription updated")
                # Try to reinitialize Supabase client
                try:
                    from app.services.supabase_client import SupabaseService
                    supabase_service = SupabaseService()
                    if supabase_service.initialized:
                        self.supabase = supabase_service.client
                        logger.info("✅ Emergency Supabase client reinitialization successful")
                    else:
                        logger.error("❌ Emergency Supabase client reinitialization failed")
                        return {"success": False, "error": "Database connection not available"}
                except Exception as e:
                    logger.error(f"❌ Emergency Supabase reinitialization error: {e}")
                    return {"success": False, "error": "Database connection not available"}
                
            # Check if data is valid
            if not data or not isinstance(data, dict):
                logger.error(f"Invalid subscription updated data: {type(data)} - {data}")
                return {"success": False, "error": "Invalid webhook data"}
                
            subscription_id = data.get("id")
            status = data.get("status", "active")
            
            # Skip processing for cancelled subscriptions to avoid null field issues
            if status in ["canceled", "cancelled"]:
                logger.info(f"Subscription {subscription_id} is cancelled, skipping update")
                return {"success": True, "message": "Cancelled subscription acknowledged"}
            
            # Get billing period safely - it can be null for trialing/cancelled subscriptions
            billing_period = data.get("current_billing_period")
            if billing_period and isinstance(billing_period, dict):
                period_start = billing_period.get("starts_at")
                period_end = billing_period.get("ends_at")
            else:
                period_start = None
                period_end = None
                logger.info(f"No billing period for subscription {subscription_id} (status: {status})")
            
            # Update subscription in database
            update_data = {
                "status": status,
                "updated_at": datetime.utcnow().isoformat()
            }
            
            # Only add period dates if they exist
            if period_start:
                update_data["current_period_start"] = period_start
            if period_end:
                update_data["current_period_end"] = period_end
            
            # Store customer_id if available for future lookups
            customer_id = data.get("customer_id")
            if customer_id:
                update_data["paddle_customer_id"] = customer_id
            
            result = self.supabase.table("subscriptions").update(update_data).eq("paddle_subscription_id", subscription_id).execute()
            
            if result.data:
                logger.info(f"Updated subscription {subscription_id}")
                return {"success": True, "message": "Subscription updated"}
            else:
                logger.error(f"Failed to update subscription: {result}")
                return {"success": False, "error": "Database error"}
            
        except Exception as e:
            logger.error(f"Error handling subscription updated: {e}")
            return {"success": False, "error": str(e)}
    
    async def _handle_subscription_cancelled(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Handle subscription.cancelled webhook with immediate cancellation"""
        try:
            # Check if Supabase client is available
            if not self.supabase:
                logger.error("CRITICAL: Supabase client not initialized - cannot handle subscription cancelled")
                # Try to reinitialize Supabase client
                try:
                    from app.services.supabase_client import SupabaseService
                    supabase_service = SupabaseService()
                    if supabase_service.initialized:
                        self.supabase = supabase_service.client
                        logger.info("✅ Emergency Supabase client reinitialization successful")
                    else:
                        logger.error("❌ Emergency Supabase client reinitialization failed")
                        return {"success": False, "error": "Database connection not available"}
                except Exception as e:
                    logger.error(f"❌ Emergency Supabase reinitialization error: {e}")
                    return {"success": False, "error": "Database connection not available"}
                
            subscription_id = data.get("id")
            logger.info(f"⚡ Processing immediate cancellation for subscription {subscription_id}")
            
            # Prepare database update for immediate cancellation
            update_data = {
                "status": SubscriptionStatus.CANCELLED.value,
                "cancelled_at": datetime.utcnow().isoformat(),
                "updated_at": datetime.utcnow().isoformat(),
                "cancel_at_period_end": False,
                "metadata": {
                    "cancellation_type": "immediate",
                    "cancelled_via": "paddle_webhook"
                }
            }
            
            # Update subscription in database
            result = self.supabase.table("subscriptions").update(update_data).eq("paddle_subscription_id", subscription_id).execute()
            
            if result.data:
                # Get user_id to downgrade their plan immediately
                subscription = result.data[0]
                user_id = subscription.get("user_id")
                
                if user_id:
                    # Immediate cancellation: Downgrade to free immediately
                    downgrade_result = await self._update_user_plan(user_id, "free")
                    if downgrade_result.get("success"):
                        logger.info(f"⚡ Successfully cancelled and downgraded user {user_id} to free plan")
                        message = "Subscription cancelled immediately. User downgraded to free plan with 10 video limit."
                    else:
                        logger.error(f"❌ Failed to downgrade user {user_id} after cancellation")
                        message = "Subscription cancelled but user downgrade failed. Manual intervention required."
                else:
                    logger.warning(f"No user_id found for cancelled subscription {subscription_id}")
                    message = "Subscription cancelled but no user found"
                
                logger.info(f"✅ Successfully handled subscription cancellation for {subscription_id}")
                return {"success": True, "message": message, "is_immediate": True}
            else:
                logger.error(f"Failed to cancel subscription: {result}")
                return {"success": False, "error": "Database error"}
            
        except Exception as e:
            logger.error(f"Error handling subscription cancelled: {e}")
            return {"success": False, "error": str(e)}
    
    async def _handle_transaction_completed(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Handle transaction.completed webhook"""
        try:
            # Check if Supabase client is available
            if not self.supabase:
                logger.error("CRITICAL: Supabase client not initialized - cannot handle transaction completed")
                # Try to reinitialize Supabase client
                try:
                    from app.services.supabase_client import SupabaseService
                    supabase_service = SupabaseService()
                    if supabase_service.initialized:
                        self.supabase = supabase_service.client
                        logger.info("✅ Emergency Supabase client reinitialization successful")
                    else:
                        logger.error("❌ Emergency Supabase client reinitialization failed")
                        return {"success": False, "error": "Database connection not available"}
                except Exception as e:
                    logger.error(f"❌ Emergency Supabase reinitialization error: {e}")
                    return {"success": False, "error": "Database connection not available"}
                
            # Check if data is valid
            if not data or not isinstance(data, dict):
                logger.error(f"Invalid transaction completed data: {type(data)} - {data}")
                return {"success": False, "error": "Invalid webhook data"}
                
            transaction_id = data.get("id")
            custom_data = data.get("custom_data") or {}
            user_id = custom_data.get("user_id") or custom_data.get("checkout_user_id")
            customer_id = data.get("customer_id")
            subscription_id = data.get("subscription_id")
            plan = custom_data.get("plan")
            
            logger.info(f"Processing completed transaction for user_id: {user_id}, plan: {plan}")
            logger.info(f"Custom data: {custom_data}")
            logger.info(f"Customer ID: {customer_id}, Subscription ID: {subscription_id}")
            
            # Enhanced user identification with multiple fallback strategies
            user_id = await self._identify_transaction_user(custom_data, customer_id, subscription_id, transaction_id)
            
            if not user_id:
                logger.warning(f"🚨 CRITICAL: Could not identify user for transaction {transaction_id}")
                logger.warning(f"Custom data: {custom_data}, Customer ID: {customer_id}, Subscription ID: {subscription_id}")
                # Still return success to avoid webhook retries, but log for manual investigation
                return {"success": True, "message": "Transaction acknowledged but user identification failed - manual review required"}
            
            # Log transaction details
            amount = float(data.get("details", {}).get("totals", {}).get("grand_total", "0"))
            currency = data.get("currency_code", "USD")
            logger.info(f"Processing completed transaction for user {user_id}: {amount} {currency}")
            
            # Determine plan from subscription if not in custom_data
            if not plan and subscription_id:
                try:
                    # Get subscription details to determine plan
                    sub_result = self.supabase.table("subscriptions").select("*").eq("paddle_subscription_id", subscription_id).execute()
                    if sub_result.data:
                        # Update existing subscription
                        subscription_data = sub_result.data[0]
                        plan = subscription_data.get("plan", "premium")  # Default to premium if we got a payment
                        logger.info(f"Found existing subscription, plan: {plan}")
                    else:
                        # Create new subscription record
                        plan = "premium"  # Default to premium for completed transactions
                        subscription_data = {
                            "id": str(uuid.uuid4()),
                            "user_id": user_id,
                            "paddle_subscription_id": subscription_id,
                            "paddle_customer_id": customer_id,
                            "plan": plan,
                            "status": "active",
                            "created_at": datetime.utcnow().isoformat(),
                            "updated_at": datetime.utcnow().isoformat()
                        }
                        sub_create_result = self.supabase.table("subscriptions").insert(subscription_data).execute()
                        if sub_create_result.data:
                            logger.info(f"Created new subscription for user {user_id}")
                        else:
                            logger.error(f"Failed to create subscription: {sub_create_result}")
                except Exception as e:
                    logger.error(f"Error handling subscription: {e}")
                    plan = "premium"  # Fallback to premium
            
            # Update user plan in user_profiles table
            if plan:
                update_result = await self._update_user_plan(user_id, plan)
                if update_result.get("success"):
                    logger.info(f"✅ Successfully updated user {user_id} to {plan} plan")
                    return {"success": True, "message": f"User plan updated to {plan}"}
                else:
                    logger.error(f"❌ Failed to update user plan: {update_result.get('error')}")
                    return {"success": False, "error": f"Failed to update user plan: {update_result.get('error')}"}
            else:
                logger.warning(f"No plan determined for user {user_id}, transaction processed but plan not updated")
                return {"success": True, "message": "Transaction processed but plan not determined"}
            
        except Exception as e:
            logger.error(f"Error handling transaction completed: {e}")
            return {"success": False, "error": str(e)}
    
    async def _handle_transaction_updated(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Handle transaction.updated webhook - process when transaction status changes to completed"""
        try:
            # Check if Supabase client is available
            if not self.supabase:
                logger.error("CRITICAL: Supabase client not initialized - cannot handle transaction updated")
                # Try to reinitialize Supabase client
                try:
                    from app.services.supabase_client import SupabaseService
                    supabase_service = SupabaseService()
                    if supabase_service.initialized:
                        self.supabase = supabase_service.client
                        logger.info("✅ Emergency Supabase client reinitialization successful")
                    else:
                        logger.error("❌ Emergency Supabase client reinitialization failed")
                        return {"success": False, "error": "Database connection not available"}
                except Exception as e:
                    logger.error(f"❌ Emergency Supabase reinitialization error: {e}")
                    return {"success": False, "error": "Database connection not available"}
                
            # Check if data is valid
            if not data or not isinstance(data, dict):
                logger.error(f"Invalid transaction updated data: {type(data)} - {data}")
                return {"success": False, "error": "Invalid webhook data"}
                
            transaction_id = data.get("id")
            status = data.get("status")
            
            logger.info(f"Transaction updated: {transaction_id} - Status: {status}")
            
            # Only process if transaction is completed or paid
            if status not in ["completed", "paid"]:
                logger.info(f"Transaction {transaction_id} status is {status}, not processing yet")
                return {"success": True, "message": f"Transaction status {status} acknowledged"}
            
            # Get custom_data from the transaction
            custom_data = data.get("custom_data") or {}
            user_id = custom_data.get("user_id") or custom_data.get("checkout_user_id")
            plan = custom_data.get("plan")
            customer_id = data.get("customer_id")
            subscription_id = data.get("subscription_id")
            
            logger.info(f"Processing completed transaction for user_id: {user_id}, plan: {plan}")
            logger.info(f"Custom data: {custom_data}")
            logger.info(f"Customer ID: {customer_id}, Subscription ID: {subscription_id}")
            
            # Enhanced user identification with multiple fallback strategies
            user_id = await self._identify_transaction_user(custom_data, customer_id, subscription_id, transaction_id)
            
            if not user_id:
                logger.warning(f"🚨 CRITICAL: Could not identify user for transaction {transaction_id}")
                logger.warning(f"Custom data: {custom_data}, Customer ID: {customer_id}, Subscription ID: {subscription_id}")
                # Still return success to avoid webhook retries, but log for manual investigation
                return {"success": True, "message": "Transaction acknowledged but user identification failed - manual review required"}
            
            # Log transaction details
            amount = float(data.get("details", {}).get("totals", {}).get("grand_total", "0"))
            currency = data.get("currency_code", "USD")
            logger.info(f"💰 Processing completed transaction for user {user_id}: {amount} {currency}")
            
            # Determine plan from subscription if not in custom_data
            if not plan and subscription_id:
                try:
                    # Get subscription details to determine plan
                    sub_result = self.supabase.table("subscriptions").select("*").eq("paddle_subscription_id", subscription_id).execute()
                    if sub_result.data:
                        # Update existing subscription
                        subscription_data = sub_result.data[0]
                        plan = subscription_data.get("plan", "premium")  # Default to premium if we got a payment
                        logger.info(f"Found existing subscription, plan: {plan}")
                        
                        # Update the subscription with customer_id if missing
                        if customer_id and not subscription_data.get("paddle_customer_id"):
                            self.supabase.table("subscriptions").update({"paddle_customer_id": customer_id}).eq("paddle_subscription_id", subscription_id).execute()
                            logger.info(f"Updated subscription {subscription_id} with customer_id {customer_id}")
                    else:
                        # Create new subscription record
                        plan = "premium"  # Default to premium for completed transactions
                        subscription_data = {
                            "id": str(uuid.uuid4()),
                            "user_id": user_id,
                            "paddle_subscription_id": subscription_id,
                            "paddle_customer_id": customer_id,
                            "plan": plan,
                            "status": "active",
                            "created_at": datetime.utcnow().isoformat(),
                            "updated_at": datetime.utcnow().isoformat()
                        }
                        sub_create_result = self.supabase.table("subscriptions").insert(subscription_data).execute()
                        if sub_create_result.data:
                            logger.info(f"✅ Created new subscription for user {user_id}")
                        else:
                            logger.error(f"❌ Failed to create subscription: {sub_create_result}")
                except Exception as e:
                    logger.error(f"Error handling subscription: {e}")
                    plan = "premium"  # Fallback to premium
            
            # Update user plan in user_profiles table
            if plan:
                update_result = await self._update_user_plan(user_id, plan)
                if update_result.get("success"):
                    logger.info(f"✅ Successfully updated user {user_id} to {plan} plan")
                    return {"success": True, "message": f"User plan updated to {plan}"}
                else:
                    logger.error(f"❌ Failed to update user plan: {update_result.get('error')}")
                    return {"success": False, "error": f"Failed to update user plan: {update_result.get('error')}"}
            else:
                logger.warning(f"No plan determined for user {user_id}, transaction processed but plan not updated")
                return {"success": True, "message": "Transaction processed but plan not determined"}
            
        except Exception as e:
            logger.error(f"Error handling transaction updated: {e}")
            return {"success": False, "error": str(e)}
    
    async def _get_user_subscription(self, user_id: str) -> Optional[Dict[str, Any]]:
        """Get user's current subscription from database"""
        try:
            result = self.supabase.table("subscriptions").select("*").eq("user_id", user_id).eq("status", "active").execute()
            
            if result.data:
                return result.data[0]
            return None
            
        except Exception as e:
            logger.error(f"Error fetching user subscription: {e}")
            return None
    
    async def _update_subscription_status(
        self, 
        user_id: str, 
        status: SubscriptionStatus,
        cancel_at_period_end: bool = False,
        cancelled_at: Optional[datetime] = None
    ):
        """Update subscription status in database"""
        try:
            update_data = {
                "status": status.value,
                "cancel_at_period_end": cancel_at_period_end,
                "updated_at": datetime.utcnow().isoformat()
            }
            
            if cancelled_at:
                update_data["cancelled_at"] = cancelled_at.isoformat()
            
            result = self.supabase.table("subscriptions").update(update_data).eq("user_id", user_id).execute()
            
            if result.data:
                logger.info(f"Updated subscription status for user {user_id} to {status.value}")
            else:
                logger.error(f"Failed to update subscription status: {result}")
                
        except Exception as e:
            logger.error(f"Error updating subscription status: {e}")
    
    async def _identify_transaction_user(self, custom_data: Dict[str, Any], customer_id: str, subscription_id: str, transaction_id: str) -> Optional[str]:
        """Enhanced user identification with multiple fallback strategies"""
        try:
            # Strategy 1: Get from custom_data (primary method)
            if custom_data:
                user_id = custom_data.get("user_id") or custom_data.get("checkout_user_id")
                if user_id:
                    logger.info(f"✅ Found user_id from custom_data: {user_id}")
                    return user_id
            
            # Strategy 2: Look up by customer_id in subscriptions table
            if customer_id:
                logger.info(f"🔍 Attempting customer_id lookup for: {customer_id}")
                try:
                    sub_result = self.supabase.table("subscriptions").select("user_id").eq("paddle_customer_id", customer_id).limit(1).execute()
                    if sub_result.data:
                        user_id = sub_result.data[0]["user_id"]
                        logger.info(f"✅ Found user_id from customer_id lookup: {user_id}")
                        return user_id
                    else:
                        logger.info(f"❌ Customer ID {customer_id} not found in subscriptions table")
                except Exception as e:
                    logger.error(f"Error in customer_id lookup: {e}")
            
            # Strategy 3: Look up by subscription_id
            if subscription_id:
                logger.info(f"🔍 Attempting subscription_id lookup for: {subscription_id}")
                try:
                    sub_result = self.supabase.table("subscriptions").select("user_id").eq("paddle_subscription_id", subscription_id).limit(1).execute()
                    if sub_result.data:
                        user_id = sub_result.data[0]["user_id"]
                        logger.info(f"✅ Found user_id from subscription_id lookup: {user_id}")
                        
                        # Update subscription with customer_id if we have it and it's missing
                        if customer_id:
                            try:
                                self.supabase.table("subscriptions").update({"paddle_customer_id": customer_id}).eq("paddle_subscription_id", subscription_id).execute()
                                logger.info(f"🔄 Updated subscription {subscription_id} with customer_id {customer_id}")
                            except Exception as e:
                                logger.error(f"Error updating subscription with customer_id: {e}")
                        
                        return user_id
                    else:
                        logger.info(f"❌ Subscription ID {subscription_id} not found in subscriptions table")
                except Exception as e:
                    logger.error(f"Error in subscription_id lookup: {e}")
            
            # Strategy 4: Look up customer email from Paddle API and match with user profiles
            if customer_id:
                logger.info(f"🔍 Attempting customer email lookup from Paddle API for: {customer_id}")
                try:
                    customer_email = await self._get_customer_email_from_paddle(customer_id)
                    if customer_email:
                        logger.info(f"📧 Found customer email from Paddle: {customer_email}")
                        # Look up user by email in user_profiles
                        user_result = self.supabase.table("user_profiles").select("user_id").eq("email", customer_email).limit(1).execute()
                        if user_result.data:
                            user_id = user_result.data[0]["user_id"]
                            logger.info(f"✅ Found user_id from email lookup: {user_id} ({customer_email})")
                            return user_id
                        else:
                            logger.info(f"❌ No user found with email: {customer_email}")
                    else:
                        logger.info(f"❌ Could not get customer email from Paddle API")
                except Exception as e:
                    logger.error(f"Error in customer email lookup: {e}")
            
            # Strategy 5: Last resort - log for manual investigation
            logger.warning(f"🚨 All user identification strategies failed for transaction {transaction_id}")
            logger.warning(f"Available data: customer_id={customer_id}, subscription_id={subscription_id}, custom_data={custom_data}")
            
            return None
            
        except Exception as e:
            logger.error(f"Error in user identification: {e}")
            return None

    async def _get_customer_email_from_paddle(self, customer_id: str) -> Optional[str]:
        """Get customer email from Paddle API"""
        try:
            if not self.api_key:
                logger.error("Paddle API key not configured for customer lookup")
                return None
                
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"{self.api_base}/customers/{customer_id}",
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type": "application/json"
                    }
                )
                
                if response.status_code == 200:
                    customer_data = response.json()
                    customer_email = customer_data.get("data", {}).get("email")
                    if customer_email:
                        logger.info(f"📧 Retrieved customer email from Paddle: {customer_email}")
                        return customer_email
                    else:
                        logger.warning(f"No email found in Paddle customer data: {customer_data}")
                        return None
                else:
                    logger.error(f"Failed to get customer from Paddle API: {response.status_code} - {response.text}")
                    return None
                    
        except Exception as e:
            logger.error(f"Error fetching customer email from Paddle: {e}")
            return None

    async def _process_end_of_period_cancellations(self) -> Dict[str, Any]:
        """Check for and process end-of-period cancellations that are now effective"""
        try:
            if not self.supabase:
                logger.error("CRITICAL: Supabase client not initialized - cannot process end-of-period cancellations")
                return {"success": False, "error": "Database connection not available"}
            
            current_time = datetime.utcnow().isoformat()
            
            # Find subscriptions that are cancelled with cancel_at_period_end=True 
            # and have reached their effective cancellation date
            query = (
                self.supabase.table("subscriptions")
                .select("*")
                .eq("status", SubscriptionStatus.CANCELLED.value)
                .eq("cancel_at_period_end", True)
            )
            
            result = query.execute()
            
            if not result.data:
                logger.debug("No end-of-period cancellations to process")
                return {"success": True, "processed": 0}
            
            processed_count = 0
            for subscription in result.data:
                try:
                    # Check if cancellation should now be effective
                    metadata = subscription.get("metadata", {})
                    effective_date_str = metadata.get("cancellation_effective_date")
                    
                    if not effective_date_str:
                        # Fallback to current_period_end if no metadata
                        effective_date_str = subscription.get("current_period_end")
                    
                    if effective_date_str:
                        effective_date = datetime.fromisoformat(effective_date_str.replace("Z", "+00:00"))
                        current_dt = datetime.utcnow().replace(tzinfo=effective_date.tzinfo)
                        
                        # If the effective date has passed, downgrade the user
                        if current_dt >= effective_date:
                            user_id = subscription.get("user_id")
                            if user_id:
                                # Downgrade user to free plan
                                downgrade_result = await self._update_user_plan(user_id, "free")
                                
                                if downgrade_result.get("success", False):
                                    # Update subscription to mark as fully processed
                                    update_data = {
                                        "cancel_at_period_end": False,
                                        "updated_at": datetime.utcnow().isoformat(),
                                        "metadata": {
                                            **metadata,
                                            "end_of_period_processed": True,
                                            "processed_at": datetime.utcnow().isoformat()
                                        }
                                    }
                                    
                                    self.supabase.table("subscriptions").update(update_data).eq("id", subscription["id"]).execute()
                                    
                                    logger.info(f"✅ Processed end-of-period cancellation for user {user_id}, subscription {subscription['id']}")
                                    processed_count += 1
                                else:
                                    logger.error(f"Failed to downgrade user {user_id} for subscription {subscription['id']}")
                            else:
                                logger.warning(f"No user_id found for subscription {subscription['id']}")
                        else:
                            logger.debug(f"End-of-period cancellation for subscription {subscription['id']} not yet effective (until {effective_date_str})")
                    else:
                        logger.warning(f"No effective date found for end-of-period cancellation {subscription['id']}")
                        
                except Exception as e:
                    logger.error(f"Error processing end-of-period cancellation for subscription {subscription.get('id', 'unknown')}: {e}")
                    continue
            
            logger.info(f"Processed {processed_count} end-of-period cancellations")
            return {"success": True, "processed": processed_count}
            
        except Exception as e:
            logger.error(f"Error processing end-of-period cancellations: {e}")
            return {"success": False, "error": str(e)}

    async def _update_user_plan(self, user_id: str, plan: str):
        """Update user's plan and plan_limits in user_profiles table"""
        try:
            # Check if Supabase client is available
            if not self.supabase:
                logger.error("CRITICAL: Supabase client not initialized - cannot update user plan")
                # Try to reinitialize Supabase client
                try:
                    from app.services.supabase_client import SupabaseService
                    supabase_service = SupabaseService()
                    if supabase_service.initialized:
                        self.supabase = supabase_service.client
                        logger.info("✅ Emergency Supabase client reinitialization successful in _update_user_plan")
                    else:
                        logger.error("❌ Emergency Supabase client reinitialization failed in _update_user_plan")
                        return {"success": False, "error": "Database connection not available"}
                except Exception as e:
                    logger.error(f"❌ Emergency Supabase reinitialization error in _update_user_plan: {e}")
                    return {"success": False, "error": "Database connection not available"}
            
            # Get appropriate plan limits for the new plan
            plan_limits = self._get_plan_limits(plan)
            
            # Update user metadata with new plan and plan limits
            update_data = {
                "plan_type": plan,
                "plan_limits": plan_limits,
                "updated_at": datetime.utcnow().isoformat()
            }
            
            result = self.supabase.table("user_profiles").update(update_data).eq("user_id", user_id).execute()
            
            if result.data:
                logger.info(f"✅ Successfully updated user {user_id} plan to {plan} with appropriate limits")
                return {"success": True}
            else:
                logger.error(f"❌ Failed to update user plan: {result}")
                return {"success": False, "error": "Database update failed"}
                
        except Exception as e:
            logger.error(f"❌ Error updating user plan for user {user_id} to {plan}: {e}")
            return {"success": False, "error": str(e)}
    
    def _get_plan_limits(self, plan_type: str) -> dict:
        """Get plan limits for a specific plan type"""
        PLAN_LIMITS = {
            "free": {
                "total_videos": 10,           # 10 videos total (lifetime)
                "monthly_videos": -1,         # Not applicable for free
                "daily_requests": 100,
                "monthly_tokens": 50000,
                "concurrent_jobs": 2,
                "email_summaries": True,
                "max_video_duration": 3600,   # 1 hour
                "priority_processing": False
            },
            "premium": {
                "total_videos": -1,           # Not applicable (unlimited)
                "monthly_videos": -1,         # Unlimited per month
                "daily_requests": 1000,
                "monthly_tokens": 500000,
                "concurrent_jobs": 10,
                "email_summaries": True,
                "max_video_duration": 7200,   # 2 hours
                "priority_processing": True
            },
            "enterprise": {
                "total_videos": -1,           # Not applicable (unlimited)
                "monthly_videos": -1,         # Unlimited per month
                "daily_requests": 5000,
                "monthly_tokens": 1000000,
                "concurrent_jobs": 20,
                "email_summaries": True,
                "max_video_duration": 14400,  # 4 hours
                "priority_processing": True,
                "custom_integrations": True
            }
        }
        
        return PLAN_LIMITS.get(plan_type, PLAN_LIMITS["free"])
    
    def _convert_paddle_subscription(self, paddle_data: Dict[str, Any]) -> SubscriptionData:
        """Convert Paddle subscription data to our format"""
        return SubscriptionData(
            id=paddle_data.get("id"),
            user_id=paddle_data.get("custom_data", {}).get("user_id", ""),
            paddle_subscription_id=paddle_data.get("id"),
            plan=SubscriptionPlan(paddle_data.get("custom_data", {}).get("plan", "premium")),
            status=SubscriptionStatus(paddle_data.get("status", "active")),
            current_period_start=paddle_data.get("current_billing_period", {}).get("starts_at"),
            current_period_end=paddle_data.get("current_billing_period", {}).get("ends_at"),
            cancel_at_period_end=paddle_data.get("scheduled_change", {}).get("action") == "cancel",
            created_at=datetime.fromisoformat(paddle_data.get("created_at").replace("Z", "+00:00")),
            updated_at=datetime.fromisoformat(paddle_data.get("updated_at").replace("Z", "+00:00")),
            metadata=paddle_data.get("custom_data", {})
        )
