import logging
from fastapi.responses import JSONResponse
from fastapi_jwt_auth import AuthJWT
from fastapi import Depends, HTTPException, Request, status
from starlette.middleware.base import BaseHTTPMiddleware

logger = logging.getLogger(__name__)

EXEMPT_PATHS = [
    "/api/v1/registration",
    "/api/v1/authorization",
    "/api/docs",
    "/api/redoc",
    "/api/openapi.json"
]

class AuthenticateMiddleware(BaseHTTPMiddleware):
    """Middleware for JWT authentication."""
    
    async def dispatch(self, request: Request, call_next):
        # Skip authentication for exempted paths
        if any(request.url.path.startswith(path) for path in EXEMPT_PATHS):
            return await call_next(request)

        try:
            auth_jwt = AuthJWT(request) 
            auth_jwt.jwt_required()
            logger.debug(f"Authenticated request to {request.url.path}")
        except Exception as e:
            logger.warning(f"Authentication failed: {str(e)}")
            return JSONResponse(
                status_code=status.HTTP_401_UNAUTHORIZED,
                content={"detail": "Not authenticated"},
                headers={"Authenticate": "Bearer"}
            )

        return await call_next(request)

async def authenticate(Authorize: AuthJWT = Depends()):
    """
    Dependency for JWT authentication.
    Can be used in route dependencies.
    """
    try:
        Authorize.jwt_required()

    except Exception as e:
        logger.warning(f"Authentication failed: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authorization": "Bearer"}
        )
