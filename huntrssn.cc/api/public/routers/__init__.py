"""
Public API routers.
"""
from api.public.routers.auth import router as auth_router
from api.public.routers.search import router as search_router
from api.public.routers.ecommerce import router as ecommerce_router
from api.public.routers.stats import router as stats_router
from api.public.routers.billing import router as billing_router
from api.public.routers.news import router as news_router
from api.public.routers.tickets import router as tickets_router
from api.public.routers.internal import router as internal_router
from api.public.routers.maintenance import router as maintenance_router
from api.public.routers.admin import router as admin_router
from api.public.routers.subscriptions import router as subscriptions_router
from api.public.routers.sms import router as sms_router

__all__ = ["auth_router", "search_router", "ecommerce_router", "stats_router", "billing_router", "news_router", "tickets_router", "internal_router", "maintenance_router", "admin_router", "subscriptions_router", "sms_router"]
