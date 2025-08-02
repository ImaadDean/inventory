"""
Middleware to track user activity automatically
"""

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response as StarletteResponse
from ..utils.user_activity import update_user_activity
from ..utils.auth import verify_token
import asyncio


class ActivityTrackingMiddleware(BaseHTTPMiddleware):
    """
    Middleware to automatically track user activity on each authenticated request
    """
    
    def __init__(self, app, excluded_paths: list = None):
        super().__init__(app)
        # Paths to exclude from activity tracking (to avoid too frequent updates)
        self.excluded_paths = excluded_paths or [
            "/static/",
            "/favicon.ico",
            "/api/auth/ping",
            "/api/users/activity",  # Avoid recursive calls
        ]
    
    async def dispatch(self, request: Request, call_next) -> StarletteResponse:
        """Process request and track user activity if authenticated"""
        
        # Skip activity tracking for excluded paths
        if any(request.url.path.startswith(path) for path in self.excluded_paths):
            return await call_next(request)
        
        # Process the request first
        response = await call_next(request)
        
        # Track activity after successful request (don't block the response)
        asyncio.create_task(self._track_user_activity(request))
        
        return response
    
    async def _track_user_activity(self, request: Request):
        """Track user activity in background"""
        try:
            # Extract token from Authorization header
            auth_header = request.headers.get("Authorization")
            if not auth_header or not auth_header.startswith("Bearer "):
                return
            
            token = auth_header.split(" ")[1]
            payload = verify_token(token)
            
            if not payload:
                return
            
            username = payload.get("sub")
            if not username:
                return
            
            # Get user ID from username
            from ..utils.auth import get_user_by_username
            user = await get_user_by_username(username)
            
            if user and user.is_active:
                # Update activity in background (don't wait for completion)
                await update_user_activity(str(user.id))
                
        except Exception as e:
            # Log error but don't affect the main request
            print(f"Activity tracking error: {e}")


class SessionActivityTracker:
    """
    Alternative session-based activity tracker for web interface
    """
    
    @staticmethod
    async def track_web_activity(request: Request):
        """
        Track activity for web interface users (using session/cookies)
        This can be called manually from routes that need activity tracking
        """
        try:
            # This would be used for session-based tracking
            # For now, we'll rely on the JWT middleware
            pass
        except Exception as e:
            print(f"Web activity tracking error: {e}")


def should_track_activity(request: Request) -> bool:
    """
    Determine if we should track activity for this request
    """
    # Skip static files and health checks
    excluded_patterns = [
        "/static/",
        "/favicon.ico",
        "/health",
        "/ping",
        "/api/auth/ping"
    ]
    
    path = request.url.path.lower()
    
    # Skip excluded patterns
    if any(pattern in path for pattern in excluded_patterns):
        return False
    
    # Skip OPTIONS requests
    if request.method == "OPTIONS":
        return False
    
    # Only track GET, POST, PUT, DELETE requests
    if request.method not in ["GET", "POST", "PUT", "DELETE", "PATCH"]:
        return False
    
    return True


async def manual_activity_update(request: Request):
    """
    Manually update user activity - can be called from specific routes
    """
    if not should_track_activity(request):
        return
    
    try:
        # Extract token from Authorization header
        auth_header = request.headers.get("Authorization")
        if not auth_header or not auth_header.startswith("Bearer "):
            return
        
        token = auth_header.split(" ")[1]
        payload = verify_token(token)
        
        if not payload:
            return
        
        username = payload.get("sub")
        if not username:
            return
        
        # Get user and update activity
        from ..utils.auth import get_user_by_username
        user = await get_user_by_username(username)
        
        if user and user.is_active:
            await update_user_activity(str(user.id))
            
    except Exception as e:
        print(f"Manual activity update error: {e}")
