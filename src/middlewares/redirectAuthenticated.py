import logging
from fastapi_jwt_auth import AuthJWT
from fastapi import Depends, HTTPException, Request, status
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import RedirectResponse

logger = logging.getLogger(__name__)

class RedirectIfAuthenticatedMiddleware(BaseHTTPMiddleware):
    """Middleware to redirect authenticated users away from auth pages."""
    
    async def dispatch(self, request: Request, call_next):
        # Only check authentication for auth-related paths
        if request.url.path not in ["/api/v1/registration", "/api/v1/authorization"]:
            return await call_next(request)
            
        auth_jwt = AuthJWT()
        try:
            auth_jwt.jwt_required()
            # User is authenticated, redirect to home
            logger.debug(f"Redirecting authenticated user from {request.url.path}")
            return RedirectResponse(
                url="/api/v1/home",
                status_code=status.HTTP_302_FOUND
            )
        except Exception:
            # User is not authenticated, proceed with request
            logger.debug(f"Proceeding with unauthenticated request to {request.url.path}")
            return await call_next(request)
