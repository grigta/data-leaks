"""Admin routers package."""
from .auth import router as auth_router
from .users import router as users_router
from .coupons import router as coupons_router
from .analytics import router as analytics_router
from .news import router as news_router
from .workers import router as workers_router
from .workers import workers_router as workers_mgmt_router
from .tickets import router as tickets_router
from .stats import router as stats_router
from .transactions import router as transactions_router
from .orders import router as orders_router
from . import maintenance
from . import custom_pricing
from . import internal
from . import errors
from . import settings
from . import test_polygon

__all__ = ['auth_router', 'users_router', 'coupons_router', 'analytics_router', 'news_router', 'workers_router', 'workers_mgmt_router', 'tickets_router', 'stats_router', 'transactions_router', 'orders_router', 'maintenance', 'custom_pricing', 'internal', 'errors', 'settings', 'test_polygon']
