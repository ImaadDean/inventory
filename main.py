from fastapi import FastAPI, HTTPException, Request, Cookie
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from contextlib import asynccontextmanager
import logging
from typing import Optional
from app.middleware.activity_tracker import ActivityTrackingMiddleware

# Import configuration and database
from app.config.settings import settings
from app.config.database import connect_to_mongo, close_mongo_connection, get_database
from app.utils.expense_categories_init import initialize_default_expense_categories

# Import API routers
from app.routes.auth.api import router as auth_api_router
from app.routes.users.api import router as users_api_router
from app.routes.products.api import router as products_api_router
from app.routes.customers.api import router as customers_api_router
from app.routes.categories.api import router as categories_api_router
from app.routes.suppliers.api import router as suppliers_api_router
from app.routes.expenses.api import router as expenses_api_router
from app.routes.pos.api import router as pos_api_router
from app.routes.orders.api import router as orders_api_router
from app.routes.dashboard.api import router as dashboard_api_router

# Import HTML route routers
from app.routes.auth.route import auth_routes
from app.routes.dashboard.route import dashboard_routes
from app.routes.users.route import users_routes
from app.routes.products.route import products_routes
from app.routes.customers.route import customers_routes
from app.routes.categories.route import categories_routes
from app.routes.suppliers.route import suppliers_routes
from app.routes.expenses.route import expenses_routes
from app.routes.pos.route import pos_routes
from app.routes.orders.route import orders_routes
from app.routes.reports.route import reports_routes

# Import authentication utilities
from app.utils.auth import verify_token, get_user_by_username

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan events"""
    # Startup
    logger.info("Starting up Inventory Management System...")
    await connect_to_mongo()

    # Initialize default expense categories
    try:
        db = await get_database()
        await initialize_default_expense_categories(db)
    except Exception as e:
        logger.error(f"Failed to initialize expense categories: {e}")

    logger.info("Application startup complete")

    yield

    # Shutdown
    logger.info("Shutting down Inventory Management System...")
    await close_mongo_connection()
    logger.info("Application shutdown complete")


# Create FastAPI application
app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description="""
    ## Inventory Management System with POS

    A comprehensive inventory management system with Point of Sale functionality.

    ### Features:
    * **Authentication**: JWT-based authentication with role-based access control
    * **User Management**: Admin can manage users with different roles (Admin, Cashier, Inventory Manager)
    * **Inventory Management**: Complete product and category management with stock tracking
    * **Customer Management**: Customer database with purchase history tracking
    * **Point of Sale**: Full POS system with transaction processing and automatic stock updates
    * **Dashboard & Reports**: Analytics and reporting for sales and inventory

    ### User Roles:
    * **Admin**: Full system access
    * **Inventory Manager**: Can manage products, categories, and inventory
    * **Cashier**: Can process sales and view basic information

    ### Authentication:
    Use the `/api/auth/login` endpoint to get an access token, then include it in the Authorization header:
    ```
    Authorization: Bearer <your_access_token>
    ```

    ### Web Interface:
    Access the web interface at `/auth/login` for HTML-based interaction.
    """,
    lifespan=lifespan,
    debug=settings.DEBUG
)

# Setup templates with timezone filters
templates = Jinja2Templates(directory="app/templates")

# Register timezone template filters
from app.utils.template_filters import TEMPLATE_FILTERS
for filter_name, filter_func in TEMPLATE_FILTERS.items():
    templates.env.filters[filter_name] = filter_func

# Add activity tracking middleware
app.add_middleware(ActivityTrackingMiddleware)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Authentication middleware for HTML routes
async def get_current_user_from_cookie(request: Request):
    """Get current user from cookie for HTML routes"""
    access_token = request.cookies.get("access_token")
    if not access_token:
        return None

    if access_token.startswith("Bearer "):
        token = access_token[7:]
    else:
        token = access_token

    payload = verify_token(token)
    if not payload:
        return None

    username = payload.get("sub")
    if not username:
        return None

    user = await get_user_by_username(username)
    return user


# Global exception handler
@app.exception_handler(Exception)
async def global_exception_handler(request, exc):
    logger.error(f"Global exception: {exc}")
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error"}
    )


# Health check endpoint
@app.get("/health", tags=["Health"])
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "app_name": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "timestamp": "2024-01-20T10:00:00Z"
    }


# Include API routers
app.include_router(auth_api_router)
app.include_router(users_api_router)
app.include_router(products_api_router)
app.include_router(customers_api_router)
app.include_router(categories_api_router)
app.include_router(suppliers_api_router)
app.include_router(expenses_api_router)
app.include_router(pos_api_router)
app.include_router(orders_api_router)
app.include_router(dashboard_api_router)

# Include HTML route routers
app.include_router(auth_routes)
app.include_router(dashboard_routes)
app.include_router(users_routes)
app.include_router(products_routes)
app.include_router(customers_routes)
app.include_router(categories_routes)
app.include_router(suppliers_routes)
app.include_router(expenses_routes)
app.include_router(pos_routes)
app.include_router(orders_routes)
app.include_router(reports_routes, prefix="/reports")


# Root endpoint - redirect to dashboard if authenticated, otherwise to login
@app.get("/", tags=["Root"])
async def root(request: Request):
    """Root endpoint - redirect based on authentication status"""
    user = await get_current_user_from_cookie(request)
    if user:
        return RedirectResponse(url="/dashboard", status_code=302)
    else:
        return RedirectResponse(url="/auth/login", status_code=302)


# API root endpoint
@app.get("/api", tags=["API Root"])
async def api_root():
    """API root endpoint with information"""
    return {
        "message": f"Welcome to {settings.APP_NAME} API",
        "version": settings.APP_VERSION,
        "docs_url": "/docs",
        "redoc_url": "/redoc",
        "health_check": "/health",
        "web_interface": "/auth/login"
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=settings.DEBUG,
        log_level="info"
    )