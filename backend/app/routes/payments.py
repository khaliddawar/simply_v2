"""
Payment Routes - Paddle Billing Integration

Handles subscription management, checkout, and webhook processing.
Adapted from the Simply project's payment implementation.
"""
from fastapi import APIRouter, HTTPException, Depends, Request, Header
from fastapi.responses import JSONResponse, HTMLResponse, RedirectResponse
from typing import Optional, Dict, Any
import json
import hmac
import hashlib
import logging
import httpx

from app.models.subscription import (
    CheckoutRequest, CheckoutResponse,
    SubscriptionResponse, CancelSubscriptionRequest, CancelSubscriptionResponse,
    UpgradeRequest, UpgradeResponse
)
from app.routes.auth import get_current_user_id, get_current_user_id_optional
from app.settings import get_settings
from app.services.database_service import get_database_service

logger = logging.getLogger(__name__)
router = APIRouter()


def verify_paddle_signature(raw_body: bytes, signature_header: str, webhook_secret: str) -> bool:
    """
    Verify Paddle webhook signature using HMAC-SHA256.

    Paddle signature format: t=timestamp;h1=signature or ts=timestamp;h1=signature
    """
    if not signature_header or not webhook_secret:
        return False

    try:
        # Parse signature header
        parts = {}
        for part in signature_header.split(';'):
            key_value = part.strip().split('=', 1)
            if len(key_value) == 2:
                parts[key_value[0].strip()] = key_value[1].strip()

        timestamp = parts.get('ts') or parts.get('t')
        signature = parts.get('h1')

        if not timestamp or not signature:
            logger.warning(f"Missing timestamp or signature in header: {signature_header}")
            return False

        # Build signed payload: timestamp:raw_body
        signed_payload = f"{timestamp}:{raw_body.decode('utf-8')}"

        # Calculate expected signature
        expected_signature = hmac.new(
            webhook_secret.encode('utf-8'),
            signed_payload.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()

        # Constant-time comparison
        return hmac.compare_digest(expected_signature, signature)

    except Exception as e:
        logger.error(f"Error verifying Paddle signature: {e}")
        return False


@router.post("/checkout", response_model=CheckoutResponse)
async def create_checkout(
    request: CheckoutRequest,
    user_id: str = Depends(get_current_user_id)
):
    """
    Create a Paddle checkout session for subscription.
    Returns a checkout URL to redirect the user to.
    """
    settings = get_settings()

    # For now, redirect to the pricing page
    # The pricing page handles Paddle checkout directly
    return CheckoutResponse(
        checkout_url="https://tubevibe.app/pricing",
        checkout_id=None
    )


@router.post("/upgrade", response_model=UpgradeResponse)
async def initiate_upgrade(
    request: UpgradeRequest,
    user_id: str = Depends(get_current_user_id)
):
    """
    Initiate subscription upgrade from extension.

    Creates a Paddle checkout session with the user's ID in custom_data
    so the webhook can identify which user to upgrade.
    """
    settings = get_settings()

    # Check if Paddle is configured
    if not settings.paddle_api_key or not settings.paddle_premium_price_id:
        logger.warning("Paddle not configured - returning pricing page URL")
        return UpgradeResponse(
            success=True,
            checkout_url="https://tubevibe.app/pricing",
            message="Redirecting to pricing page"
        )

    # Get user info from database
    db = await get_database_service()
    user = await db.get_user_by_id(user_id)

    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    user_email = user.get('email')

    # Determine price ID based on plan
    price_id = settings.paddle_premium_price_id
    if request.plan == "enterprise" and settings.paddle_enterprise_price_id:
        price_id = settings.paddle_enterprise_price_id

    # Paddle API base URL
    paddle_base_url = (
        "https://api.paddle.com"
        if settings.paddle_environment == "production"
        else "https://sandbox-api.paddle.com"
    )

    # Create transaction via Paddle API
    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{paddle_base_url}/transactions",
                headers={
                    "Authorization": f"Bearer {settings.paddle_api_key}",
                    "Content-Type": "application/json"
                },
                json={
                    "items": [
                        {
                            "price_id": price_id,
                            "quantity": 1
                        }
                    ],
                    "customer": {
                        "email": user_email
                    },
                    "custom_data": {
                        "user_id": user_id,
                        "user_email": user_email,
                        "source": "extension"
                    },
                    "checkout": {
                        "url": request.return_url or f"{settings.api_base_url}/api/payments/success"
                    }
                },
                timeout=30.0
            )

            if response.status_code == 201:
                data = response.json()
                checkout_url = data.get("data", {}).get("checkout", {}).get("url")

                if checkout_url:
                    logger.info(f"Created Paddle checkout for user {user_id}")
                    return UpgradeResponse(
                        success=True,
                        checkout_url=checkout_url,
                        message="Checkout session created"
                    )
                else:
                    logger.error(f"No checkout URL in Paddle response: {data}")
                    raise HTTPException(
                        status_code=500,
                        detail="Failed to get checkout URL from Paddle"
                    )
            else:
                error_data = response.json()
                logger.error(f"Paddle API error: {response.status_code} - {error_data}")
                raise HTTPException(
                    status_code=response.status_code,
                    detail=error_data.get("error", {}).get("detail", "Paddle API error")
                )

    except httpx.TimeoutException:
        logger.error("Paddle API timeout")
        raise HTTPException(status_code=504, detail="Payment service timeout")
    except httpx.RequestError as e:
        logger.error(f"Paddle API request error: {e}")
        raise HTTPException(status_code=502, detail="Payment service unavailable")


@router.get("/subscription", response_model=SubscriptionResponse)
async def get_subscription(user_id: str = Depends(get_current_user_id_optional)):
    """
    Get current user's subscription status.
    """
    if not user_id:
        return SubscriptionResponse(
            plan="free",
            status="active",
            limits={
                "max_videos": 10,
                "max_groups": 2,
                "monthly_searches": 50,
                "summary_enabled": False
            }
        )

    db = await get_database_service()

    # Get user's subscription from database
    try:
        user = await db.get_user_by_id(user_id)
        if user:
            # Check plan_type field (updated by webhook) or fall back to subscription_plan
            plan = user.get('plan_type') or user.get('subscription_plan') or 'free'
            settings = get_settings()
            limits = settings.get_plan_limits(plan)

            return SubscriptionResponse(
                plan=plan,
                status=user.get('subscription_status', 'active'),
                paddle_subscription_id=user.get('paddle_subscription_id'),
                current_period_end=user.get('subscription_end_date'),
                limits=limits
            )
    except Exception as e:
        logger.error(f"Error getting subscription: {e}")

    # Return free plan as default
    return SubscriptionResponse(
        plan="free",
        status="active",
        limits={
            "max_videos": 10,
            "max_groups": 2,
            "monthly_searches": 50,
            "summary_enabled": False
        }
    )


@router.post("/cancel", response_model=CancelSubscriptionResponse)
async def cancel_subscription(
    request: CancelSubscriptionRequest,
    user_id: str = Depends(get_current_user_id)
):
    """
    Cancel the user's subscription.
    """
    # TODO: Implement subscription cancellation via Paddle API
    raise HTTPException(status_code=501, detail="Subscription cancellation not yet implemented")


@router.post("/webhook")
async def paddle_webhook(
    request: Request,
    paddle_signature: Optional[str] = Header(None, alias="Paddle-Signature")
):
    """
    Handle Paddle webhook notifications.

    Paddle sends webhooks for:
    - subscription.created
    - subscription.updated
    - subscription.cancelled
    - transaction.completed
    """
    settings = get_settings()

    # Get raw body for signature verification
    body = await request.body()

    # Parse JSON payload
    try:
        payload = json.loads(body.decode())
    except json.JSONDecodeError as e:
        logger.error(f"Invalid JSON in webhook payload: {e}")
        return JSONResponse(status_code=400, content={"error": "Invalid JSON payload"})

    event_type = payload.get('event_type', 'unknown')
    logger.info(f"Received Paddle webhook: {event_type}")

    # Verify signature (skip in development if no secret configured)
    if settings.paddle_notification_secret:
        if not paddle_signature:
            logger.warning("Missing Paddle-Signature header")
            return JSONResponse(status_code=400, content={"error": "Missing signature"})

        if not verify_paddle_signature(body, paddle_signature, settings.paddle_notification_secret):
            logger.warning("Invalid Paddle signature")
            return JSONResponse(status_code=401, content={"error": "Invalid signature"})
    else:
        logger.warning("Paddle webhook secret not configured - skipping signature verification")

    # Process the webhook based on event type
    try:
        if event_type == 'transaction.completed':
            await handle_transaction_completed(payload)
        elif event_type == 'subscription.created':
            await handle_subscription_created(payload)
        elif event_type == 'subscription.updated':
            await handle_subscription_updated(payload)
        elif event_type == 'subscription.cancelled':
            await handle_subscription_cancelled(payload)
        else:
            logger.info(f"Unhandled webhook event type: {event_type}")

        return JSONResponse(status_code=200, content={"status": "received"})

    except Exception as e:
        logger.error(f"Error processing webhook: {e}")
        return JSONResponse(status_code=500, content={"error": str(e)})


async def handle_transaction_completed(payload: Dict[str, Any]):
    """
    Handle transaction.completed webhook - user has successfully paid.
    Updates user's subscription status in the database.
    """
    data = payload.get('data', {})

    # Extract user identification from custom_data
    custom_data = data.get('custom_data', {})
    user_id = custom_data.get('user_id') or custom_data.get('checkout_user_id')
    user_email = custom_data.get('user_email')

    # Get subscription details
    subscription_id = data.get('subscription_id')
    customer_id = data.get('customer_id')

    # Determine plan from price ID (default to premium for paid transactions)
    plan = 'premium'

    logger.info(f"Transaction completed - User: {user_id or user_email}, Subscription: {subscription_id}")

    db = await get_database_service()

    # Try to find user by various methods
    user = None
    if user_id:
        user = await db.get_user_by_id(user_id)
    elif user_email:
        user = await db.get_user_by_email(user_email)

    if not user:
        logger.warning(f"No user found for transaction - user_id: {user_id}, email: {user_email}")
        return

    user_id = user['id']

    # Create or update subscription in subscriptions table
    try:
        await db.create_or_update_subscription(
            user_id=user_id,
            plan=plan,
            status='active',
            paddle_subscription_id=subscription_id,
            paddle_customer_id=customer_id
        )
        logger.info(f"Updated subscription for user {user_id} to {plan}")

        # Also update user's plan_type in users table
        await db.update_user(user_id, {'plan_type': plan})

    except Exception as e:
        logger.error(f"Failed to update user subscription: {e}")
        raise


async def handle_subscription_created(payload: Dict[str, Any]):
    """
    Handle subscription.created webhook.
    """
    data = payload.get('data', {})
    subscription_id = data.get('id')
    customer_id = data.get('customer_id')
    status = data.get('status')

    custom_data = data.get('custom_data', {})
    user_id = custom_data.get('user_id')

    logger.info(f"Subscription created - ID: {subscription_id}, Status: {status}, User: {user_id}")

    if user_id:
        db = await get_database_service()
        try:
            await db.create_or_update_subscription(
                user_id=user_id,
                plan='premium',
                status=status or 'active',
                paddle_subscription_id=subscription_id,
                paddle_customer_id=customer_id
            )
            await db.update_user(user_id, {'plan_type': 'premium'})
            logger.info(f"Created subscription for user {user_id}")
        except Exception as e:
            logger.error(f"Error creating subscription: {e}")


async def handle_subscription_updated(payload: Dict[str, Any]):
    """
    Handle subscription.updated webhook.
    """
    data = payload.get('data', {})
    subscription_id = data.get('id')
    status = data.get('status')

    logger.info(f"Subscription updated - ID: {subscription_id}, Status: {status}")

    db = await get_database_service()
    try:
        # Update subscription status by paddle_subscription_id
        await db.update_subscription_by_paddle_id(subscription_id, {
            'status': status
        })
        logger.info(f"Updated subscription {subscription_id} status to {status}")
    except Exception as e:
        logger.error(f"Error updating subscription: {e}")


async def handle_subscription_cancelled(payload: Dict[str, Any]):
    """
    Handle subscription.cancelled webhook.
    Downgrades user to free plan.
    """
    data = payload.get('data', {})
    subscription_id = data.get('id')

    logger.info(f"Subscription cancelled - ID: {subscription_id}")

    db = await get_database_service()
    try:
        # Get the user associated with this subscription
        user = await db.get_user_by_paddle_subscription_id(subscription_id)
        if user:
            # Update subscription to cancelled
            await db.update_subscription_by_paddle_id(subscription_id, {
                'status': 'cancelled',
                'plan': 'free'
            })
            # Downgrade user to free plan
            await db.update_user(user['id'], {'plan_type': 'free'})
            logger.info(f"Downgraded user {user['id']} to free plan")
        else:
            logger.warning(f"No user found for cancelled subscription {subscription_id}")
    except Exception as e:
        logger.error(f"Error cancelling subscription: {e}")


@router.get("/success")
async def payment_success(plan: str = "premium"):
    """
    Handle successful payment redirect from Paddle.
    Shows a success message and redirects back to the extension.
    """
    html_content = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>Payment Successful - TubeVibe</title>
        <style>
            body {{
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
                display: flex;
                align-items: center;
                justify-content: center;
                min-height: 100vh;
                margin: 0;
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            }}
            .container {{
                text-align: center;
                background: white;
                padding: 48px;
                border-radius: 16px;
                box-shadow: 0 20px 40px rgba(0,0,0,0.2);
                max-width: 480px;
            }}
            .checkmark {{
                width: 80px;
                height: 80px;
                background: #10b981;
                border-radius: 50%;
                display: flex;
                align-items: center;
                justify-content: center;
                margin: 0 auto 24px;
            }}
            .checkmark svg {{
                width: 40px;
                height: 40px;
                color: white;
            }}
            h1 {{
                color: #1f2937;
                margin-bottom: 16px;
            }}
            p {{
                color: #6b7280;
                margin-bottom: 24px;
                line-height: 1.6;
            }}
            .plan-badge {{
                display: inline-block;
                background: #8b5cf6;
                color: white;
                padding: 8px 16px;
                border-radius: 20px;
                font-weight: 600;
                text-transform: capitalize;
                margin-bottom: 24px;
            }}
            .btn {{
                display: inline-block;
                background: #2563eb;
                color: white;
                padding: 12px 24px;
                border-radius: 8px;
                text-decoration: none;
                font-weight: 600;
                transition: background 0.2s;
            }}
            .btn:hover {{
                background: #1d4ed8;
            }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="checkmark">
                <svg fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="3" d="M5 13l4 4L19 7"></path>
                </svg>
            </div>
            <h1>Payment Successful!</h1>
            <div class="plan-badge">{plan} Plan</div>
            <p>
                Thank you for upgrading to TubeVibe {plan.title()}!
                Your subscription is now active and you can enjoy all premium features.
            </p>
            <p>
                Return to YouTube and refresh the page to start using your new features.
            </p>
            <a href="https://www.youtube.com" class="btn">Go to YouTube</a>
        </div>
    </body>
    </html>
    """
    return HTMLResponse(content=html_content)


@router.get("/plans")
async def get_available_plans():
    """
    Get available subscription plans and pricing.
    """
    return {
        "plans": [
            {
                "id": "free",
                "name": "Free",
                "price": 0,
                "features": [
                    "1 video summary per month",
                    "Complete transcript access",
                    "Email delivery included",
                    "Segmented summaries"
                ],
                "limits": {
                    "max_videos": 10,
                    "max_groups": 2,
                    "monthly_searches": 50,
                    "summary_enabled": True,
                    "summaries_per_month": 1
                }
            },
            {
                "id": "premium",
                "name": "Premium",
                "price": 7,
                "billing_cycle": "monthly",
                "features": [
                    "700k tokens per month",
                    "Unlimited summaries",
                    "Chat with any video",
                    "Priority processing",
                    "Advanced analytics",
                    "Email support"
                ],
                "limits": {
                    "max_videos": -1,
                    "max_groups": -1,
                    "monthly_searches": -1,
                    "summary_enabled": True,
                    "tokens_per_month": 700000
                }
            }
        ]
    }
