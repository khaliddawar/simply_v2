"""
Payment Routes for Paddle Integration
Handles subscription management, checkout creation, and webhook processing
"""

from fastapi import APIRouter, Depends, HTTPException, status, Request, Header
from fastapi.responses import JSONResponse, HTMLResponse, RedirectResponse
import logging
import json
from typing import Dict, Any, Optional

from app.services.paddle_service import PaddleService
from app.middleware.auth_middleware import get_current_user
from app.services.supabase_client import get_supabase_client
from app.models.payment import (
    CheckoutRequest, CheckoutResponse, UpgradeRequest, UpgradeResponse,
    CancelSubscriptionRequest, CancelSubscriptionResponse, UsageQuota,
    SubscriptionPlan, SubscriptionStatus
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/payments", tags=["payments"])

# Initialize Paddle service
paddle_service = PaddleService()

@router.post("/checkout", response_model=CheckoutResponse)
async def create_checkout_session(
    request: CheckoutRequest,
    current_user: Dict = Depends(get_current_user)
):
    """
    Create a Paddle checkout session for subscription upgrade
    """
    try:
        user_id = current_user["id"]
        user_email = current_user["email"]
        
        logger.info(f"Creating checkout session for user {user_email}, plan: {request.plan}")
        
        # Validate that user is not already on this plan
        current_plan = current_user.get("user_metadata", {}).get("plan", "free")
        if current_plan == request.plan.value:
            raise HTTPException(
                status_code=400,
                detail=f"User is already on {request.plan.value} plan"
            )
        
        # Create checkout session with Paddle
        checkout_response = await paddle_service.create_checkout_session(
            user_id=user_id,
            user_email=user_email,
            request=request
        )
        
        logger.info(f"Created checkout session: {checkout_response.checkout_id}")
        
        return checkout_response
        
    except Exception as e:
        logger.error(f"Error creating checkout session: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to create checkout session: {str(e)}"
        )

@router.post("/upgrade", response_model=UpgradeResponse)
async def upgrade_subscription(
    request: UpgradeRequest,
    current_user: Dict = Depends(get_current_user)
):
    """
    Initiate subscription upgrade process
    """
    try:
        user_id = current_user["id"]
        user_email = current_user["email"]
        current_plan = current_user.get("user_metadata", {}).get("plan", "free")
        
        logger.info(f"User {user_email} requesting upgrade from {current_plan} to {request.plan}")
        
        # Validate upgrade path
        if current_plan == request.plan.value:
            return UpgradeResponse(
                success=False,
                message=f"You are already on the {request.plan.value} plan"
            )
        
        # Create checkout for upgrade
        checkout_request = CheckoutRequest(
            plan=request.plan,
            success_url=request.return_url,
            customer_email=user_email,
            metadata={"upgrade_from": current_plan}
        )
        
        checkout_response = await paddle_service.create_checkout_session(
            user_id=user_id,
            user_email=user_email,
            request=checkout_request
        )
        
        return UpgradeResponse(
            success=True,
            message=f"Upgrade checkout created for {request.plan.value} plan",
            checkout_url=checkout_response.checkout_url
        )
        
    except Exception as e:
        logger.error(f"Error processing upgrade request: {e}")
        return UpgradeResponse(
            success=False,
            message=f"Failed to create upgrade checkout: {str(e)}"
        )

@router.post("/cancel", response_model=CancelSubscriptionResponse)
async def cancel_subscription(
    request: CancelSubscriptionRequest,
    current_user: Dict = Depends(get_current_user)
):
    """
    Cancel user's subscription
    """
    try:
        user_id = current_user["id"]
        user_email = current_user["email"]
        current_plan = current_user.get("user_metadata", {}).get("plan", "free")
        
        logger.info(f"User {user_email} requesting cancellation of {current_plan} plan")
        
        if current_plan == "free":
            return CancelSubscriptionResponse(
                success=False,
                message="You don't have an active subscription to cancel"
            )
        
        # Cancel subscription with Paddle
        response = await paddle_service.cancel_subscription(user_id, request)
        
        if response.success:
            logger.info(f"Successfully cancelled subscription for user {user_email}")
        
        return response
        
    except Exception as e:
        logger.error(f"Error cancelling subscription: {e}")
        return CancelSubscriptionResponse(
            success=False,
            message=f"Failed to cancel subscription: {str(e)}"
        )

@router.get("/subscription")
async def get_subscription_info(
    current_user: Dict = Depends(get_current_user)
):
    """
    Get current user's subscription information
    """
    try:
        user_id = current_user["id"]
        
        # Get user profile to get the actual plan_type from database
        supabase = get_supabase_client()
        profile_resp = supabase.table("user_profiles").select("plan_type").eq("user_id", user_id).single().execute()
        
        # Get the user's actual plan from user_profiles table 
        user_plan = "free"  # default
        if profile_resp.data:
            user_plan = profile_resp.data.get("plan_type", "free")
        
        # Get subscription details from database
        subscription = await paddle_service._get_user_subscription(user_id)
        
        if not subscription and user_plan != "free":
            # User has a plan but no subscription record - might be legacy
            return {
                "plan": user_plan,
                "status": "active",
                "legacy": True,
                "message": "Legacy subscription - contact support for details"
            }
        
        if subscription:
            return {
                "plan": subscription.get("plan", user_plan),
                "status": subscription.get("status"),
                "current_period_start": subscription.get("current_period_start"),
                "current_period_end": subscription.get("current_period_end"),
                "cancel_at_period_end": subscription.get("cancel_at_period_end", False),
                "cancelled_at": subscription.get("cancelled_at")
            }
        
        # Return the actual plan from user_profiles (not always "free")
        return {
            "plan": user_plan,
            "status": "active",
            "message": f"{user_plan.title()} plan" + (" - upgrade to get unlimited access" if user_plan == "free" else "")
        }
        
    except Exception as e:
        logger.error(f"Error fetching subscription info: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to fetch subscription info: {str(e)}"
        )

@router.get("/usage", response_model=UsageQuota)
async def get_usage_quota(
    current_user: Dict = Depends(get_current_user)
):
    """
    Get user's current usage and quota information
    """
    try:
        user_id = current_user["id"]
        user_plan = current_user.get("user_metadata", {}).get("plan", "free")
        
        # Get usage from the updated total video limit function
        from app.routes.youtube_routes import check_total_video_limit
        from app.services.supabase_client import get_supabase_client
        
        # Get user's plan details
        supabase = get_supabase_client()
        profile_resp = supabase.table("user_profiles").select("plan_type, plan_limits").eq("user_id", user_id).single().execute()
        actual_plan = profile_resp.data.get("plan_type", "free") if profile_resp.data else "free"
        plan_limits = profile_resp.data.get("plan_limits", {}) if profile_resp.data else {}
        
        # Check if user can process more videos
        can_process = await check_total_video_limit(user_id)
        
        if actual_plan == "free":
            # For free users, show total videos used vs total limit
            total_videos_limit = plan_limits.get("total_videos", 10)
            
            # Count total videos used
            usage_resp = supabase.table("usage_ledger").select("id").eq("user_id", user_id).eq("resource_type", "video_processing").execute()
            total_videos_used = len(usage_resp.data) if usage_resp.data else 0
            
            return UsageQuota(
                user_id=user_id,
                plan=SubscriptionPlan(actual_plan),
                videos_this_week=total_videos_used,  # Reuse field for total videos
                weekly_limit=total_videos_limit,     # Reuse field for total limit
                unlimited_access=False,
                period_start=None,  # Not applicable for total limits
                period_end=None     # Not applicable for total limits
            )
        else:
            # Premium/Enterprise users have unlimited access
            return UsageQuota(
                user_id=user_id,
                plan=SubscriptionPlan(actual_plan),
                videos_this_week=0,  # Don't track for unlimited users
                weekly_limit=-1,     # -1 indicates unlimited
                unlimited_access=True,
                period_start=None,
                period_end=None
            )
        
    except Exception as e:
        logger.error(f"Error fetching usage quota: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to fetch usage quota: {str(e)}"
        )

@router.get("/plans")
async def get_available_plans():
    """
    Get available subscription plans and pricing
    """
    return {
        "plans": [
            {
                "id": "free",
                "name": "Free",
                "price": 0,
                "currency": "USD",
                "interval": "month",
                "features": [
                    "10 video summaries total",
                    "Basic email delivery",
                    "YouTube transcript extraction"
                ],
                "limits": {
                    "total_videos": 10,
                    "email_delivery": True,
                    "priority_support": False
                }
            },
            {
                "id": "premium_monthly",
                "name": "Premium Monthly",
                "price": 7.00,
                "currency": "USD", 
                "interval": "month",
                "savings": None,
                "features": [
                    "Unlimited video summaries per month",
                    "Priority email delivery",
                    "Advanced summary features",
                    "Email support"
                ],
                "limits": {
                    "monthly_videos": -1,  # Unlimited
                    "email_delivery": True,
                    "priority_support": True
                }
            },
            {
                "id": "premium_annual",
                "name": "Premium Annual", 
                "price": 84.00,
                "currency": "USD",
                "interval": "year",
                "monthly_equivalent": 7.00,
                "savings": "20% off monthly pricing",
                "features": [
                    "Unlimited video summaries per month",
                    "Priority email delivery", 
                    "Advanced summary features",
                    "Email support",
                    "20% annual savings"
                ],
                "limits": {
                    "monthly_videos": -1,  # Unlimited
                    "email_delivery": True,
                    "priority_support": True
                }
            },
            {
                "id": "enterprise",
                "name": "Enterprise",
                "price": 29.99,
                "currency": "USD",
                "interval": "month", 
                "features": [
                    "Everything in Premium",
                    "Custom integrations",
                    "Priority support",
                    "Advanced analytics"
                ],
                "limits": {
                    "monthly_videos": -1,  # Unlimited
                    "email_delivery": True,
                    "priority_support": True,
                    "custom_integrations": True
                }
            }
        ]
    }

@router.get("/checkout", response_class=HTMLResponse)
async def checkout_landing(current_user: Dict = Depends(get_current_user)):
    """
    Main checkout landing page for tubevibe.app/checkout
    Professional pricing page with both monthly and annual options
    """
    from app.models.payment import PADDLE_PRICES
    import os
    
    paddle_environment = os.getenv("PADDLE_ENVIRONMENT", "sandbox")
    client_token = os.getenv("PADDLE_CLIENT_TOKEN", "test_")
    monthly_price_id = PADDLE_PRICES.get("premium_monthly")
    annual_price_id = PADDLE_PRICES.get("premium_annual")
    
    # Get user information for checkout
    user_id = current_user["id"]
    user_email = current_user["email"]
    
    return HTMLResponse(content=f"""
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>TubeVibe Premium - Choose Your Plan</title>
        <meta name="description" content="Upgrade to TubeVibe Premium for unlimited YouTube summaries and enhanced features">
        <style>
            * {{
                margin: 0;
                padding: 0;
                box-sizing: border-box;
            }}
            
            body {{
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                min-height: 100vh;
                display: flex;
                align-items: center;
                justify-content: center;
                padding: 20px;
            }}
            
            .container {{
                max-width: 900px;
                width: 100%;
                background: white;
                border-radius: 16px;
                box-shadow: 0 20px 40px rgba(0,0,0,0.1);
                overflow: hidden;
            }}
            
            .header {{
                text-align: center;
                padding: 40px 20px 20px;
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                color: white;
            }}
            
            .header h1 {{
                font-size: 2.5rem;
                font-weight: 700;
                margin-bottom: 10px;
            }}
            
            .header p {{
                font-size: 1.2rem;
                opacity: 0.9;
            }}
            
            .pricing-section {{
                padding: 40px 20px;
            }}
            
            .pricing-grid {{
                display: grid;
                grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
                gap: 30px;
                max-width: 800px;
                margin: 0 auto;
            }}
            
            .plan-card {{
                border: 2px solid #e1e5e9;
                border-radius: 12px;
                padding: 30px;
                text-align: center;
                position: relative;
                transition: all 0.3s ease;
                background: white;
            }}
            
            .plan-card:hover {{
                border-color: #667eea;
                transform: translateY(-5px);
                box-shadow: 0 10px 30px rgba(102, 126, 234, 0.2);
            }}
            
            .plan-card.recommended {{
                border-color: #28a745;
                background: linear-gradient(135deg, #f8f9fa 0%, #e9ecef 100%);
            }}
            
            .plan-card.recommended::before {{
                content: "🏆 Most Popular";
                position: absolute;
                top: -15px;
                left: 50%;
                transform: translateX(-50%);
                background: #28a745;
                color: white;
                padding: 8px 20px;
                border-radius: 20px;
                font-size: 0.875rem;
                font-weight: 600;
            }}
            
            .plan-title {{
                font-size: 1.5rem;
                font-weight: 700;
                margin-bottom: 10px;
                color: #333;
            }}
            
            .plan-price {{
                font-size: 3rem;
                font-weight: 800;
                color: #667eea;
                margin-bottom: 5px;
            }}
            
            .plan-period {{
                color: #666;
                margin-bottom: 20px;
            }}
            
            .plan-savings {{
                background: #28a745;
                color: white;
                padding: 4px 12px;
                border-radius: 20px;
                font-size: 0.875rem;
                font-weight: 600;
                display: inline-block;
                margin-bottom: 20px;
            }}
            
            .plan-features {{
                text-align: left;
                margin-bottom: 30px;
            }}
            
            .plan-features li {{
                list-style: none;
                padding: 8px 0;
                display: flex;
                align-items: center;
                color: #555;
            }}
            
            .plan-features li::before {{
                content: "✅";
                margin-right: 10px;
                font-size: 1.1rem;
            }}
            
            .checkout-btn {{
                width: 100%;
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                color: white;
                border: none;
                padding: 16px 24px;
                border-radius: 8px;
                font-size: 1.1rem;
                font-weight: 600;
                cursor: pointer;
                transition: all 0.3s ease;
            }}
            
            .checkout-btn:hover {{
                transform: translateY(-2px);
                box-shadow: 0 6px 20px rgba(102, 126, 234, 0.3);
            }}
            
            .checkout-btn.annual {{
                background: linear-gradient(135deg, #28a745 0%, #20c997 100%);
            }}
            
            .checkout-btn.annual:hover {{
                box-shadow: 0 6px 20px rgba(40, 167, 69, 0.3);
            }}
            
            .trust-indicators {{
                text-align: center;
                padding: 20px;
                border-top: 1px solid #e1e5e9;
                background: #f8f9fa;
            }}
            
            .trust-indicators p {{
                color: #666;
                font-size: 0.9rem;
                margin-bottom: 10px;
            }}
            
            .security-badges {{
                display: flex;
                justify-content: center;
                gap: 20px;
                flex-wrap: wrap;
            }}
            
            .security-badge {{
                display: flex;
                align-items: center;
                gap: 5px;
                color: #28a745;
                font-size: 0.875rem;
                font-weight: 500;
            }}
            
            @media (max-width: 768px) {{
                .header h1 {{
                    font-size: 2rem;
                }}
                
                .plan-price {{
                    font-size: 2.5rem;
                }}
                
                .pricing-grid {{
                    grid-template-columns: 1fr;
                }}
            }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <h1>TubeVibe Premium</h1>
                <p>Unlimited YouTube summaries and enhanced features</p>
            </div>
            
            <div class="pricing-section">
                <div class="pricing-grid">
                    <!-- Monthly Plan -->
                    <div class="plan-card">
                        <div class="plan-title">Monthly</div>
                        <div class="plan-price">$7</div>
                        <div class="plan-period">per month</div>
                        
                        <ul class="plan-features">
                            <li>Unlimited YouTube summaries</li>
                            <li>AI-powered insights</li>
                            <li>Email delivery</li>
                            <li>Priority support</li>
                            <li>Chrome extension</li>
                        </ul>
                        
                        <button class="checkout-btn" onclick="openCheckout('monthly')">
                            Start Monthly Plan
                        </button>
                    </div>
                    
                    <!-- Annual Plan -->
                    <div class="plan-card recommended">
                        <div class="plan-title">Annual</div>
                        <div class="plan-price">$84</div>
                        <div class="plan-period">per year</div>
                        <div class="plan-savings">Save 20% ($20 off)</div>
                        
                        <ul class="plan-features">
                            <li>Unlimited YouTube summaries</li>
                            <li>AI-powered insights</li>
                            <li>Email delivery</li>
                            <li>Priority support</li>
                            <li>Chrome extension</li>
                            <li>2 months free</li>
                        </ul>
                        
                        <button class="checkout-btn annual" onclick="openCheckout('annual')">
                            Start Annual Plan
                        </button>
                    </div>
                </div>
            </div>
            
            <div class="trust-indicators">
                <p>🔒 Secure payment powered by Paddle • Cancel anytime • 30-day money back guarantee</p>
                <div class="security-badges">
                    <div class="security-badge">
                        <span>🛡️</span>
                        <span>SSL Secured</span>
                    </div>
                    <div class="security-badge">
                        <span>💳</span>
                        <span>PCI Compliant</span>
                    </div>
                    <div class="security-badge">
                        <span>🌍</span>
                        <span>Global Payments</span>
                    </div>
                </div>
            </div>
        </div>
        
        <script src="https://cdn.paddle.com/paddle/v2/paddle.js"></script>
        <script>
            console.log('Initializing Paddle...');
            console.log('Environment: {paddle_environment}');
            console.log('Client Token: {client_token}');
            
            // Initialize Paddle
            Paddle.Environment.set('{paddle_environment}');
            Paddle.Initialize({{
                token: '{client_token}'
            }});
            
            function openCheckout(plan) {{
                console.log('Opening Paddle checkout for plan:', plan);
                
                let priceId;
                if (plan === 'annual') {{
                    priceId = '{annual_price_id}';
                }} else {{
                    priceId = '{monthly_price_id}';
                }}
                
                Paddle.Checkout.open({{
                    items: [{{
                        priceId: priceId,
                        quantity: 1
                    }}],
                    customer: {{
                        email: '{user_email}'
                    }},
                    customData: {{
                        user_id: '{user_id}',
                        plan: plan,
                        checkout_user_id: '{user_id}',
                        user_email: '{user_email}',
                        created_at: new Date().toISOString()
                    }},
                    settings: {{
                        displayMode: 'overlay',
                        theme: 'light',
                        locale: 'en',
                        allowLogout: false,
                        showAddTaxId: true,
                        showAddDiscounts: true
                    }},
                    successCallback: function(data) {{
                        console.log('Checkout success:', data);
                        // Redirect to success page
                        window.location.href = 'https://tubevibe.app/success?plan=' + plan;
                    }},
                    errorCallback: function(error) {{
                        console.error('Checkout error:', error);
                        alert('There was an issue with the checkout. Please try again or contact support.');
                    }}
                }});
            }}
        </script>
    </body>
    </html>
    """)

@router.get("/success", response_class=HTMLResponse)
async def checkout_success(plan: Optional[str] = None):
    """
    Success page after successful payment
    """
    return HTMLResponse(content=f"""
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Welcome to TubeVibe Premium!</title>
        <style>
            * {{
                margin: 0;
                padding: 0;
                box-sizing: border-box;
            }}
            
            body {{
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
                background: linear-gradient(135deg, #28a745 0%, #20c997 100%);
                min-height: 100vh;
                display: flex;
                align-items: center;
                justify-content: center;
                padding: 20px;
            }}
            
            .container {{
                max-width: 600px;
                width: 100%;
                background: white;
                border-radius: 16px;
                box-shadow: 0 20px 40px rgba(0,0,0,0.1);
                text-align: center;
                padding: 60px 40px;
            }}
            
            .success-icon {{
                font-size: 4rem;
                margin-bottom: 30px;
            }}
            
            .success-title {{
                font-size: 2.5rem;
                font-weight: 700;
                color: #333;
                margin-bottom: 20px;
            }}
            
            .success-message {{
                font-size: 1.2rem;
                color: #666;
                margin-bottom: 40px;
                line-height: 1.6;
            }}
            
            .plan-info {{
                background: linear-gradient(135deg, #f8f9fa 0%, #e9ecef 100%);
                border-radius: 12px;
                padding: 30px;
                margin-bottom: 40px;
            }}
            
            .plan-name {{
                font-size: 1.5rem;
                font-weight: 700;
                color: #28a745;
                margin-bottom: 10px;
            }}
            
            .next-steps {{
                text-align: left;
                margin-bottom: 40px;
            }}
            
            .next-steps h3 {{
                font-size: 1.3rem;
                font-weight: 600;
                color: #333;
                margin-bottom: 20px;
                text-align: center;
            }}
            
            .next-steps ul {{
                list-style: none;
                padding: 0;
            }}
            
            .next-steps li {{
                padding: 12px 0;
                display: flex;
                align-items: center;
                color: #555;
                border-bottom: 1px solid #eee;
            }}
            
            .next-steps li:last-child {{
                border-bottom: none;
            }}
            
            .next-steps li::before {{
                content: "✅";
                margin-right: 15px;
                font-size: 1.2rem;
            }}
            
            .cta-buttons {{
                display: flex;
                gap: 20px;
                justify-content: center;
                flex-wrap: wrap;
            }}
            
            .cta-btn {{
                padding: 14px 28px;
                border-radius: 8px;
                text-decoration: none;
                font-weight: 600;
                transition: all 0.3s ease;
                border: none;
                cursor: pointer;
                font-size: 1rem;
            }}
            
            .cta-btn.primary {{
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                color: white;
            }}
            
            .cta-btn.primary:hover {{
                transform: translateY(-2px);
                box-shadow: 0 6px 20px rgba(102, 126, 234, 0.3);
            }}
            
            .cta-btn.secondary {{
                background: #f8f9fa;
                color: #333;
                border: 2px solid #e9ecef;
            }}
            
            .cta-btn.secondary:hover {{
                background: #e9ecef;
            }}
            
            .support-info {{
                margin-top: 40px;
                padding-top: 30px;
                border-top: 1px solid #e9ecef;
                color: #666;
                font-size: 0.9rem;
            }}
            
            @media (max-width: 768px) {{
                .container {{
                    padding: 40px 20px;
                }}
                
                .success-title {{
                    font-size: 2rem;
                }}
                
                .cta-buttons {{
                    flex-direction: column;
                }}
                
                .cta-btn {{
                    width: 100%;
                }}
            }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="success-icon">🎉</div>
            <h1 class="success-title">Welcome to TubeVibe Premium!</h1>
            <p class="success-message">
                Thank you for upgrading! Your payment has been processed successfully and you now have access to all premium features.
            </p>
            
            <div class="plan-info">
                <div class="plan-name">
                    {plan.title() if plan else 'Premium'} Plan Activated
                </div>
                <p>You now have unlimited access to YouTube summaries and all premium features.</p>
            </div>
            
            <div class="next-steps">
                <h3>What's Next?</h3>
                <ul>
                    <li>Install or refresh the TubeVibe Chrome extension</li>
                    <li>Start getting unlimited YouTube summaries</li>
                    <li>Receive AI-powered insights via email</li>
                    <li>Access priority customer support</li>
                    <li>Manage your subscription anytime</li>
                </ul>
            </div>
            
            <div class="cta-buttons">
                <a href="https://chrome.google.com/webstore/detail/tubevibe" class="cta-btn primary">
                    Get Chrome Extension
                </a>
                <a href="https://tubevibe.app" class="cta-btn secondary">
                    Visit TubeVibe.app
                </a>
            </div>
            
            <div class="support-info">
                <p>
                    <strong>Need help?</strong> Contact our support team at 
                    <a href="mailto:support@tubevibe.app" style="color: #667eea;">support@tubevibe.app</a>
                </p>
                <p style="margin-top: 10px;">
                    You can manage your subscription, update payment methods, or cancel anytime from your account dashboard.
                </p>
            </div>
        </div>
    </body>
    </html>
    """)

@router.get("/checkout/monthly", response_class=HTMLResponse)
async def checkout_monthly(discount: Optional[str] = None):
    """
    Professional checkout page for monthly subscription
    """
    # Get Paddle product and price IDs for monthly subscription
    from app.models.payment import PADDLE_PRODUCTS, PADDLE_PRICES, SubscriptionPlan
    product_id = PADDLE_PRODUCTS.get(SubscriptionPlan.PREMIUM)
    price_id = PADDLE_PRICES.get("premium_monthly")
    
    # Environment for Paddle.js (sandbox or production)
    import os
    paddle_environment = os.getenv("PADDLE_ENVIRONMENT", "sandbox")
    client_token = os.getenv("PADDLE_CLIENT_TOKEN", "test_")  # You'll need to add this to .env
    
    # Professional checkout page HTML
    checkout_html = f"""
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>TubeVibe Premium - Monthly Subscription</title>
        <style>
            * {{
                margin: 0;
                padding: 0;
                box-sizing: border-box;
            }}
            
            body {{
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                min-height: 100vh;
                display: flex;
                align-items: center;
                justify-content: center;
                padding: 20px;
            }}
            
            .checkout-container {{
                background: white;
                border-radius: 16px;
                box-shadow: 0 20px 40px rgba(0,0,0,0.1);
                max-width: 480px;
                width: 100%;
                overflow: hidden;
            }}
            
            .header {{
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                color: white;
                padding: 32px;
                text-align: center;
            }}
            
            .header h1 {{
                font-size: 28px;
                font-weight: 700;
                margin-bottom: 8px;
            }}
            
            .header p {{
                opacity: 0.9;
                font-size: 16px;
            }}
            
            .content {{
                padding: 32px;
            }}
            
            .plan-details {{
                border: 2px solid #e5f3ff;
                border-radius: 12px;
                padding: 24px;
                margin-bottom: 24px;
                background: #f8fcff;
            }}
            
            .price {{
                font-size: 48px;
                font-weight: 700;
                color: #1a365d;
                margin-bottom: 8px;
            }}
            
            .price span {{
                font-size: 18px;
                color: #4a5568;
                font-weight: 400;
            }}
            
            .features {{
                list-style: none;
                margin: 20px 0;
            }}
            
            .features li {{
                display: flex;
                align-items: center;
                margin-bottom: 12px;
                font-size: 16px;
                color: #2d3748;
            }}
            
            .features li::before {{
                content: "✓";
                color: #48bb78;
                font-weight: bold;
                margin-right: 12px;
                font-size: 18px;
            }}
            
            .discount-section {{
                background: #f0fff4;
                border: 2px solid #9ae6b4;
                border-radius: 8px;
                padding: 16px;
                margin-bottom: 24px;
                text-align: center;
            }}
            
            .discount-input {{
                width: 100%;
                padding: 12px;
                border: 2px solid #e2e8f0;
                border-radius: 8px;
                font-size: 16px;
                margin-bottom: 12px;
            }}
            
            .apply-discount {{
                background: #4299e1;
                color: white;
                border: none;
                padding: 10px 20px;
                border-radius: 6px;
                font-size: 14px;
                cursor: pointer;
            }}
            
            .checkout-btn {{
                width: 100%;
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                color: white;
                border: none;
                padding: 18px;
                border-radius: 12px;
                font-size: 18px;
                font-weight: 600;
                cursor: pointer;
                transition: transform 0.2s;
                margin-bottom: 16px;
            }}
            
            .checkout-btn:hover {{
                transform: translateY(-2px);
            }}
            
            .security {{
                display: flex;
                align-items: center;
                justify-content: center;
                color: #718096;
                font-size: 14px;
                margin-bottom: 20px;
            }}
            
            .security::before {{
                content: "🔒";
                margin-right: 8px;
            }}
            
            .cancel-anytime {{
                text-align: center;
                color: #718096;
                font-size: 14px;
            }}
            
            @media (max-width: 480px) {{
                .checkout-container {{
                    margin: 10px;
                }}
                
                .header {{
                    padding: 24px 20px;
                }}
                
                .content {{
                    padding: 24px 20px;
                }}
                
                .price {{
                    font-size: 36px;
                }}
            }}
        </style>
    </head>
    <body>
        <div class="checkout-container">
            <div class="header">
                <h1>TubeVibe Premium</h1>
                <p>Unlimited YouTube summaries and priority support</p>
            </div>
            
            <div class="content">
                <div class="plan-details">
                    <div class="price">$7<span>/month</span></div>
                    
                    <ul class="features">
                        <li>Unlimited video summaries</li>
                        <li>Priority email delivery</li>
                        <li>Advanced summary features</li>
                        <li>Email support</li>
                        <li>Chrome extension access</li>
                    </ul>
                </div>
                
                <div class="discount-section">
                    <h3 style="margin-bottom: 12px; color: #22543d;">Have a discount code?</h3>
                    <input type="text" id="discountCode" class="discount-input" placeholder="Enter discount code" value="{discount or ''}">
                    <button class="apply-discount" onclick="applyDiscount()">Apply Code</button>
                </div>
                
                <button class="checkout-btn" onclick="window.location.href='{paddle_checkout_url}'">
                    Start Your Premium Subscription
                </button>
                
                <div class="security">
                    Secure payment powered by Paddle
                </div>
                
                <div class="cancel-anytime">
                    Cancel anytime, no commitments
                </div>
            </div>
        </div>
        
        <script>
            function applyDiscount() {{
                const code = document.getElementById('discountCode').value.trim();
                if (code) {{
                    const url = new URL(window.location);
                    url.searchParams.set('discount', code);
                    window.location.href = url.toString();
                }}
            }}
            
            // Allow Enter key to apply discount
            document.getElementById('discountCode').addEventListener('keypress', function(e) {{
                if (e.key === 'Enter') {{
                    applyDiscount();
                }}
            }});
        </script>
    </body>
    </html>
    """
    
    return HTMLResponse(content=checkout_html)

@router.get("/checkout/annual", response_class=HTMLResponse)
async def checkout_annual(discount: Optional[str] = None):
    """
    Professional checkout page for annual subscription
    """
    # Build Paddle checkout URL with annual price
    from app.models.payment import PADDLE_PRODUCTS, PADDLE_PRICES, SubscriptionPlan
    product_id = PADDLE_PRODUCTS.get(SubscriptionPlan.PREMIUM)
    price_id = PADDLE_PRICES.get("premium_annual")
    paddle_checkout_url = f"https://checkout.paddle.com/checkout?checkout[product_id]={product_id}&checkout[price_id]={price_id}"
    
    # Add discount code if provided
    if discount:
        paddle_checkout_url += f"&checkout[coupon]={discount}"
    
    # Professional checkout page HTML
    checkout_html = f"""
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>TubeVibe Premium - Annual Subscription</title>
        <style>
            * {{
                margin: 0;
                padding: 0;
                box-sizing: border-box;
            }}
            
            body {{
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                min-height: 100vh;
                display: flex;
                align-items: center;
                justify-content: center;
                padding: 20px;
            }}
            
            .checkout-container {{
                background: white;
                border-radius: 16px;
                box-shadow: 0 20px 40px rgba(0,0,0,0.1);
                max-width: 480px;
                width: 100%;
                overflow: hidden;
                position: relative;
            }}
            
            .popular-badge {{
                position: absolute;
                top: -8px;
                right: 24px;
                background: #48bb78;
                color: white;
                padding: 8px 16px;
                border-radius: 16px;
                font-size: 12px;
                font-weight: 600;
                text-transform: uppercase;
                letter-spacing: 0.5px;
            }}
            
            .header {{
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                color: white;
                padding: 32px;
                text-align: center;
            }}
            
            .header h1 {{
                font-size: 28px;
                font-weight: 700;
                margin-bottom: 8px;
            }}
            
            .header p {{
                opacity: 0.9;
                font-size: 16px;
            }}
            
            .content {{
                padding: 32px;
            }}
            
            .plan-details {{
                border: 2px solid #e5f3ff;
                border-radius: 12px;
                padding: 24px;
                margin-bottom: 24px;
                background: #f8fcff;
            }}
            
            .price-section {{
                text-align: center;
                margin-bottom: 20px;
            }}
            
            .price {{
                font-size: 48px;
                font-weight: 700;
                color: #1a365d;
                margin-bottom: 8px;
            }}
            
            .price span {{
                font-size: 18px;
                color: #4a5568;
                font-weight: 400;
            }}
            
            .savings {{
                background: #48bb78;
                color: white;
                padding: 6px 12px;
                border-radius: 20px;
                font-size: 14px;
                font-weight: 600;
                display: inline-block;
                margin-bottom: 8px;
            }}
            
            .monthly-equivalent {{
                color: #718096;
                font-size: 16px;
            }}
            
            .features {{
                list-style: none;
                margin: 20px 0;
            }}
            
            .features li {{
                display: flex;
                align-items: center;
                margin-bottom: 12px;
                font-size: 16px;
                color: #2d3748;
            }}
            
            .features li::before {{
                content: "✓";
                color: #48bb78;
                font-weight: bold;
                margin-right: 12px;
                font-size: 18px;
            }}
            
            .discount-section {{
                background: #f0fff4;
                border: 2px solid #9ae6b4;
                border-radius: 8px;
                padding: 16px;
                margin-bottom: 24px;
                text-align: center;
            }}
            
            .discount-input {{
                width: 100%;
                padding: 12px;
                border: 2px solid #e2e8f0;
                border-radius: 8px;
                font-size: 16px;
                margin-bottom: 12px;
            }}
            
            .apply-discount {{
                background: #4299e1;
                color: white;
                border: none;
                padding: 10px 20px;
                border-radius: 6px;
                font-size: 14px;
                cursor: pointer;
            }}
            
            .checkout-btn {{
                width: 100%;
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                color: white;
                border: none;
                padding: 18px;
                border-radius: 12px;
                font-size: 18px;
                font-weight: 600;
                cursor: pointer;
                transition: transform 0.2s;
                margin-bottom: 16px;
            }}
            
            .checkout-btn:hover {{
                transform: translateY(-2px);
            }}
            
            .security {{
                display: flex;
                align-items: center;
                justify-content: center;
                color: #718096;
                font-size: 14px;
                margin-bottom: 20px;
            }}
            
            .security::before {{
                content: "🔒";
                margin-right: 8px;
            }}
            
            .cancel-anytime {{
                text-align: center;
                color: #718096;
                font-size: 14px;
            }}
            
            @media (max-width: 480px) {{
                .checkout-container {{
                    margin: 10px;
                }}
                
                .header {{
                    padding: 24px 20px;
                }}
                
                .content {{
                    padding: 24px 20px;
                }}
                
                .price {{
                    font-size: 36px;
                }}
            }}
        </style>
    </head>
    <body>
        <div class="checkout-container">
            <div class="popular-badge">Most Popular</div>
            
            <div class="header">
                <h1>TubeVibe Premium</h1>
                <p>Annual plan with 20% savings</p>
            </div>
            
            <div class="content">
                <div class="plan-details">
                    <div class="price-section">
                        <div class="savings">Save 20%</div>
                        <div class="price">$84<span>/year</span></div>
                        <div class="monthly-equivalent">That's just $7/month</div>
                    </div>
                    
                    <ul class="features">
                        <li>Unlimited video summaries</li>
                        <li>Priority email delivery</li>
                        <li>Advanced summary features</li>
                        <li>Email support</li>
                        <li>Chrome extension access</li>
                        <li><strong>20% annual savings</strong></li>
                    </ul>
                </div>
                
                <div class="discount-section">
                    <h3 style="margin-bottom: 12px; color: #22543d;">Have a discount code?</h3>
                    <input type="text" id="discountCode" class="discount-input" placeholder="Enter discount code" value="{discount or ''}">
                    <button class="apply-discount" onclick="applyDiscount()">Apply Code</button>
                </div>
                
                <button class="checkout-btn" onclick="window.location.href='{paddle_checkout_url}'">
                    Start Your Premium Subscription
                </button>
                
                <div class="security">
                    Secure payment powered by Paddle
                </div>
                
                <div class="cancel-anytime">
                    Cancel anytime, no commitments
                </div>
            </div>
        </div>
        
        <script>
            function applyDiscount() {{
                const code = document.getElementById('discountCode').value.trim();
                if (code) {{
                    const url = new URL(window.location);
                    url.searchParams.set('discount', code);
                    window.location.href = url.toString();
                }}
            }}
            
            // Allow Enter key to apply discount
            document.getElementById('discountCode').addEventListener('keypress', function(e) {{
                if (e.key === 'Enter') {{
                    applyDiscount();
                }}
            }});
        </script>
    </body>
    </html>
    """
    
    return HTMLResponse(content=checkout_html)

@router.get("/upgrade")
async def upgrade_redirect(plan: str = "monthly"):
    """
    Redirect users to appropriate checkout page
    """
    if plan.lower() in ["annual", "yearly", "year"]:
        return RedirectResponse(url="/api/payments/checkout/annual", status_code=302)
    else:
        return RedirectResponse(url="/api/payments/checkout/monthly", status_code=302)

@router.get("/checkout-test", response_class=HTMLResponse)
async def checkout_test():
    """
    Test checkout page with proper Paddle.js integration
    """
    from app.models.payment import PADDLE_PRICES
    import os
    
    paddle_environment = os.getenv("PADDLE_ENVIRONMENT", "sandbox")
    client_token = os.getenv("PADDLE_CLIENT_TOKEN", "test_")
    monthly_price_id = PADDLE_PRICES.get("premium_monthly")
    
    return HTMLResponse(content=f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>TubeVibe Premium - Test Checkout</title>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <style>
            body {{
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
                max-width: 600px;
                margin: 50px auto;
                padding: 20px;
                background: #f5f5f5;
            }}
            .container {{
                background: white;
                padding: 40px;
                border-radius: 12px;
                box-shadow: 0 4px 12px rgba(0,0,0,0.1);
                text-align: center;
            }}
            .checkout-btn {{
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                color: white;
                border: none;
                padding: 16px 32px;
                border-radius: 8px;
                font-size: 18px;
                font-weight: 600;
                cursor: pointer;
                margin: 20px 0;
            }}
            .checkout-btn:hover {{
                transform: translateY(-2px);
                box-shadow: 0 6px 20px rgba(102, 126, 234, 0.3);
            }}
            .info {{
                background: #e8f4fd;
                padding: 16px;
                border-radius: 8px;
                margin: 20px 0;
                border-left: 4px solid #2196F3;
            }}
        </style>
    </head>
    <body>
        <div class="container">
            <h1>TubeVibe Premium</h1>
            <p>Unlimited YouTube summaries for just <strong>$7/month</strong></p>
            
            <div class="info">
                <strong>🔧 Test Environment</strong><br>
                Environment: {paddle_environment}<br>
                Price ID: {monthly_price_id}<br>
                Client Token: {client_token[:10]}...
            </div>
            
            <button class="checkout-btn" onclick="openCheckout()">
                Start Premium Subscription
            </button>
            
            <p><small>This will open a Paddle checkout overlay</small></p>
        </div>

        <script src="https://cdn.paddle.com/paddle/v2/paddle.js"></script>
        <script>
            console.log('Initializing Paddle...');
            console.log('Environment: {paddle_environment}');
            console.log('Client Token: {client_token}');
            console.log('Price ID: {monthly_price_id}');
            
            // Initialize Paddle
            Paddle.Environment.set('{paddle_environment}');
            Paddle.Initialize({{
                token: '{client_token}'
            }});
            
            function openCheckout() {{
                console.log('Opening Paddle checkout...');
                
                Paddle.Checkout.open({{
                    items: [{{
                        priceId: '{monthly_price_id}',
                        quantity: 1
                    }}],
                    settings: {{
                        displayMode: 'overlay',
                        theme: 'light',
                        locale: 'en'
                    }},
                    successCallback: function(data) {{
                        console.log('Checkout success:', data);
                        alert('Payment successful! Welcome to TubeVibe Premium!');
                    }},
                    errorCallback: function(error) {{
                        console.error('Checkout error:', error);
                        alert('Checkout error: ' + JSON.stringify(error));
                    }}
                }});
            }}
        </script>
    </body>
    </html>
    """)

@router.post("/notifications")
async def handle_paddle_notification(
    request: Request,
    paddle_signature: Optional[str] = Header(None, alias="Paddle-Signature")
):
    """
    Handle Paddle Billing notification events
    """
    try:
        # Get raw body for signature verification
        body = await request.body()
        
        # Parse JSON payload
        try:
            payload = json.loads(body.decode())
        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON in webhook payload: {e}")
            return JSONResponse(
                status_code=400,
                content={"error": "Invalid JSON payload"}
            )
        
        # Verify signature
        if not paddle_signature:
            logger.warning("Missing Paddle-Signature header")
            return JSONResponse(
                status_code=400,
                content={"error": "Missing signature"}
            )
        
        # Process notification
        # Pass raw body bytes for accurate signature verification
        result = await paddle_service.process_notification(body, paddle_signature)
        
        if result.get("success"):
            logger.info(f"Successfully processed notification: {payload.get('event_type')}")
            return JSONResponse(
                status_code=200,
                content={"message": "Notification processed successfully"}
            )
        else:
            logger.error(f"Failed to process notification: {result.get('error')}")
            return JSONResponse(
                status_code=400,
                content={"error": result.get("error", "Notification processing failed")}
            )
        
    except Exception as e:
        logger.error(f"Error handling notification: {e}")
        return JSONResponse(
            status_code=500,
            content={"error": "Internal server error"}
        )

@router.get("/health")
async def payment_health_check():
    """Health check for payment service"""
    try:
        # Check if Paddle is configured
        paddle_configured = bool(paddle_service.api_key)
        
        return {
            "service": "payment_service",
            "status": "healthy",
            "paddle_configured": paddle_configured,
            "environment": paddle_service.environment,
            "timestamp": "2024-01-01T00:00:00Z"  # Will be actual timestamp
        }
    except Exception as e:
        logger.error(f"Payment health check failed: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Payment service health check failed: {str(e)}"
        )

@router.post("/process-end-of-period-cancellations")
async def process_end_of_period_cancellations(
    current_user: Dict = Depends(get_current_user)
):
    """Manually trigger processing of end-of-period cancellations"""
    try:
        # Only allow admin users to trigger this (optional security check)
        user_email = current_user.get("email", "")
        logger.info(f"End-of-period processing requested by user: {user_email}")
        
        # Process end-of-period cancellations
        result = await paddle_service._process_end_of_period_cancellations()
        
        if result.get("success"):
            processed_count = result.get("processed", 0)
            return {
                "success": True,
                "message": f"Successfully processed {processed_count} end-of-period cancellations",
                "processed_count": processed_count,
                "timestamp": datetime.utcnow().isoformat()
            }
        else:
            logger.error(f"Failed to process end-of-period cancellations: {result.get('error')}")
            raise HTTPException(
                status_code=500,
                detail=f"Failed to process cancellations: {result.get('error')}"
            )
        
    except Exception as e:
        logger.error(f"Error processing end-of-period cancellations: {e}")
        raise HTTPException(
            status_code=500,
            detail="Internal server error"
        ) 