"""
Subscription Models - Adapted from existing Simply project
"""
from pydantic import BaseModel, Field, HttpUrl
from typing import Optional, Dict, Any
from datetime import datetime
from enum import Enum
import os


class SubscriptionPlan(str, Enum):
    """Subscription plan types"""
    FREE = "free"
    PREMIUM = "premium"
    ENTERPRISE = "enterprise"


class SubscriptionStatus(str, Enum):
    """Subscription status enum"""
    ACTIVE = "active"
    CANCELLED = "cancelled"
    EXPIRED = "expired"
    PAST_DUE = "past_due"
    TRIALING = "trialing"
    PAUSED = "paused"


class BillingCycle(str, Enum):
    """Billing cycle options"""
    MONTHLY = "monthly"
    ANNUAL = "annual"


# Paddle Product IDs (loaded from environment variables)
PADDLE_PRODUCTS = {
    SubscriptionPlan.PREMIUM: os.getenv("PADDLE_PREMIUM_PRICE_ID", "pri_default_premium"),
    SubscriptionPlan.ENTERPRISE: os.getenv("PADDLE_ENTERPRISE_PRICE_ID", "pri_default_enterprise")
}


class CheckoutRequest(BaseModel):
    """Request to create a Paddle checkout session"""
    plan: SubscriptionPlan
    billing_cycle: BillingCycle = BillingCycle.MONTHLY
    success_url: Optional[str] = None
    cancel_url: Optional[str] = None


class CheckoutResponse(BaseModel):
    """Response from Paddle checkout creation"""
    checkout_url: str
    checkout_id: str
    expires_at: Optional[datetime] = None


class Subscription(BaseModel):
    """User subscription information"""
    id: str
    user_id: str
    paddle_subscription_id: Optional[str] = None
    paddle_customer_id: Optional[str] = None
    plan: SubscriptionPlan
    status: SubscriptionStatus
    current_period_start: Optional[datetime] = None
    current_period_end: Optional[datetime] = None
    cancel_at_period_end: bool = False
    cancelled_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime
    metadata: Optional[Dict[str, Any]] = None

    class Config:
        from_attributes = True


class SubscriptionResponse(BaseModel):
    """Subscription info returned to client"""
    plan: SubscriptionPlan
    status: SubscriptionStatus
    current_period_end: Optional[datetime] = None
    cancel_at_period_end: bool = False
    limits: Dict[str, Any] = {}


class CancelSubscriptionRequest(BaseModel):
    """Request to cancel subscription"""
    reason: Optional[str] = None
    cancel_immediately: bool = False


class CancelSubscriptionResponse(BaseModel):
    """Response for subscription cancellation"""
    success: bool
    message: str
    cancelled_at: Optional[datetime] = None
    cancel_at_period_end: bool = False


class UpgradeRequest(BaseModel):
    """Request to initiate upgrade from extension"""
    plan: str = "premium"
    billing_cycle: str = "monthly"
    return_url: Optional[str] = None


class UpgradeResponse(BaseModel):
    """Response with Paddle checkout URL"""
    success: bool
    checkout_url: Optional[str] = None
    message: Optional[str] = None
    error: Optional[str] = None
