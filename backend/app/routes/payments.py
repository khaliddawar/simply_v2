"""
Payment Routes - Paddle Billing Integration

Adapted from the existing Simply project's payment implementation.
"""
from fastapi import APIRouter, HTTPException, Depends, Request, Header
from typing import Optional

from app.models.subscription import (
    CheckoutRequest, CheckoutResponse,
    SubscriptionResponse, CancelSubscriptionRequest, CancelSubscriptionResponse
)
from app.routes.auth import get_current_user_id

router = APIRouter()


@router.post("/checkout", response_model=CheckoutResponse)
async def create_checkout(
    request: CheckoutRequest,
    user_id: str = Depends(get_current_user_id)
):
    """
    Create a Paddle checkout session for subscription.

    Returns a checkout URL to redirect the user to.
    """
    # TODO: Implement Paddle checkout
    # Copy logic from existing paddle_service.py

    raise HTTPException(status_code=501, detail="Payment integration not yet implemented")


@router.get("/subscription", response_model=SubscriptionResponse)
async def get_subscription(user_id: str = Depends(get_current_user_id)):
    """
    Get current user's subscription status.
    """
    # TODO: Get subscription from database

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
    # TODO: Implement subscription cancellation

    raise HTTPException(status_code=501, detail="Payment integration not yet implemented")


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
    # Get raw body for signature verification
    body = await request.body()

    # TODO: Implement webhook handling
    # Copy logic from existing paddle_service.py

    return {"status": "received"}


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
                    "10 videos total",
                    "2 groups",
                    "50 searches/month",
                    "Basic transcript storage"
                ],
                "limits": {
                    "max_videos": 10,
                    "max_groups": 2,
                    "monthly_searches": 50,
                    "summary_enabled": False
                }
            },
            {
                "id": "premium",
                "name": "Premium",
                "price": 9.99,
                "billing_cycle": "monthly",
                "features": [
                    "Unlimited videos",
                    "Unlimited groups",
                    "Unlimited searches",
                    "AI-powered summaries",
                    "Priority support"
                ],
                "limits": {
                    "max_videos": -1,
                    "max_groups": -1,
                    "monthly_searches": -1,
                    "summary_enabled": True
                }
            },
            {
                "id": "enterprise",
                "name": "Enterprise",
                "price": 29.99,
                "billing_cycle": "monthly",
                "features": [
                    "Everything in Premium",
                    "API access",
                    "Team collaboration",
                    "Custom integrations",
                    "Dedicated support"
                ],
                "limits": {
                    "max_videos": -1,
                    "max_groups": -1,
                    "monthly_searches": -1,
                    "summary_enabled": True,
                    "api_access": True
                }
            }
        ]
    }
