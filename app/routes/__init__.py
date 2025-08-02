# API Routers
from .auth.api import router as auth_api_router
from .users.api import router as users_api_router
from .products.api import router as products_api_router
from .customers.api import router as customers_api_router
from .pos.api import router as pos_api_router
from .dashboard.api import router as dashboard_api_router

# HTML Route Routers
from .auth.route import auth_routes
from .dashboard.route import dashboard_routes

__all__ = [
    # API routers
    "auth_api_router",
    "users_api_router",
    "products_api_router",
    "customers_api_router",
    "pos_api_router",
    "dashboard_api_router",

    # HTML route routers
    "auth_routes",
    "dashboard_routes"
]