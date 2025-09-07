from fastapi import APIRouter

# Import routers from routes and api modules
from .routes import router as routes_router
from .api import router as api_router

# Create main HR router
hr_router = APIRouter()

# Include sub-routers
hr_router.include_router(routes_router)
hr_router.include_router(api_router)
