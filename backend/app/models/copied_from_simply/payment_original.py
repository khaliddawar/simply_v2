from pydantic import BaseModel, Field, HttpUrl
from typing import Optional, Dict, Any, List
from datetime import datetime
from enum import Enum

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

class PaymentStatus(str, Enum):
    """Payment status enum"""
    PENDING = "pending"
    COMPLETED = "completed"
    FAILED = "failed"
    REFUNDED = "refunded"
    CANCELLED = "cancelled"

# Paddle Product IDs (loaded from environment variables)
import os
PADDLE_PRODUCTS = {
    SubscriptionPlan.PREMIUM: os.getenv("PADDLE_PREMIUM_PRODUCT_ID", "pri_01234567890abcdef"),
    SubscriptionPlan.ENTERPRISE: os.getenv("PADDLE_ENTERPRISE_PRODUCT_ID", "pri_01234567890fedcba")
}

# Paddle Price IDs for different billing cycles
PADDLE_PRICES = {
    "premium_monthly": os.getenv("PADDLE_PREMIUM_MONTHLY_PRICE_ID", "pri_monthly_default"),
    "premium_annual": os.getenv("PADDLE_PREMIUM_ANNUAL_PRICE_ID", "pri_annual_default")
}

class BillingCycle(str, Enum):
    """Billing cycle options"""
    MONTHLY = "monthly"
    ANNUAL = "annual"

class CheckoutRequest(BaseModel):
    """Request to create a Paddle checkout session"""
    plan: SubscriptionPlan
    billing_cycle: BillingCycle = BillingCycle.MONTHLY
    success_url: Optional[HttpUrl] = None
    cancel_url: Optional[HttpUrl] = None
    customer_email: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None

class CheckoutResponse(BaseModel):
    """Response from Paddle checkout creation"""
    checkout_url: HttpUrl
    checkout_id: str
    expires_at: Optional[datetime] = None

class SubscriptionData(BaseModel):
    """User subscription information"""
    id: str
    user_id: str
    paddle_subscription_id: Optional[str] = None
    plan: SubscriptionPlan
    status: SubscriptionStatus
    current_period_start: Optional[datetime] = None
    current_period_end: Optional[datetime] = None
    cancel_at_period_end: bool = False
    cancelled_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime
    metadata: Optional[Dict[str, Any]] = None

class PaymentData(BaseModel):
    """Payment transaction information"""
    id: str
    user_id: str
    subscription_id: Optional[str] = None
    paddle_transaction_id: Optional[str] = None
    amount: float
    currency: str = "USD"
    status: PaymentStatus
    payment_method: Optional[str] = None
    created_at: datetime
    processed_at: Optional[datetime] = None
    metadata: Optional[Dict[str, Any]] = None

class PaddleWebhookEvent(BaseModel):
    """Paddle webhook event data"""
    event_id: str
    event_type: str
    occurred_at: datetime
    data: Dict[str, Any]
    
class SubscriptionCreatedEvent(BaseModel):
    """Paddle subscription.created webhook event"""
    subscription_id: str
    customer_id: str
    product_id: str
    status: str
    current_billing_period: Dict[str, Any]
    custom_data: Optional[Dict[str, Any]] = None

class SubscriptionUpdatedEvent(BaseModel):
    """Paddle subscription.updated webhook event"""
    subscription_id: str
    customer_id: str
    status: str
    current_billing_period: Dict[str, Any]
    custom_data: Optional[Dict[str, Any]] = None

class SubscriptionCancelledEvent(BaseModel):
    """Paddle subscription.cancelled webhook event"""
    subscription_id: str
    customer_id: str
    cancellation_effective_date: datetime
    custom_data: Optional[Dict[str, Any]] = None

class TransactionCompletedEvent(BaseModel):
    """Paddle transaction.completed webhook event"""
    transaction_id: str
    customer_id: str
    subscription_id: Optional[str] = None
    product_id: str
    amount: str
    currency: str
    status: str
    custom_data: Optional[Dict[str, Any]] = None

class UpgradeRequest(BaseModel):
    """Request to upgrade user subscription"""
    plan: SubscriptionPlan
    return_url: Optional[HttpUrl] = None

class UpgradeResponse(BaseModel):
    """Response for subscription upgrade"""
    success: bool
    message: str
    checkout_url: Optional[HttpUrl] = None
    subscription_id: Optional[str] = None

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

class UsageQuota(BaseModel):
    """User's current usage and quotas"""
    user_id: str
    plan: SubscriptionPlan
    videos_this_week: int
    weekly_limit: int
    unlimited_access: bool = False
    period_start: datetime
    period_end: datetime 