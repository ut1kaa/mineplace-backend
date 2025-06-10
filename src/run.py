import asyncio
import logging
from pydantic import BaseModel
import uvicorn
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi_jwt_auth import AuthJWT
from .settings import SettingsJWT, settings
from .middlewares import AuthenticateMiddleware, RedirectIfAuthenticatedMiddleware
from .api import AuthRouter, UsersRouter, AddonsRouter, UserLikesRouter, VersionRouter
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

# Configure logging
LOGGER = logging.getLogger(__name__)

@AuthJWT.load_config
def get_config():
    return SettingsJWT()

def configure_logging():
    """Configure logging with proper format and handlers."""
    LOGGER.setLevel(logging.INFO)
    
    # Console handler
    console_handler = logging.StreamHandler()
    console_formatter = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )
    console_handler.setFormatter(console_formatter)
    LOGGER.addHandler(console_handler)
    
    # File handler
    file_handler = logging.FileHandler("app.log")
    file_formatter = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )
    file_handler.setFormatter(file_formatter)
    LOGGER.addHandler(file_handler)
    
    LOGGER.info("Logger is configured successfully!")

def configure_app(app: FastAPI):
    """Configure FastAPI application with middleware and routes."""
    
    # Configure CORS
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.CORS_ORIGINS,
        allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
        allow_headers=["*"],
        allow_credentials=True,
        max_age=3600,
    )
    
    # Add authentication middleware
    # app.add_middleware(AuthenticateMiddleware)
    # app.add_middleware(RedirectIfAuthenticatedMiddleware)
    
    # Global exception handler
    @app.exception_handler(Exception)
    async def global_exception_handler(request: Request, exc: Exception):
        LOGGER.error(f"Global error handler caught: {exc}", exc_info=True)
        return JSONResponse(
            status_code=500,
            content={"detail": "Internal server error occurred"}
        )
    
    # Include routers with versioning
    app.include_router(AuthRouter, prefix="/api/v1", tags=["Authentication"])
    app.include_router(UsersRouter, prefix="/api/v1", tags=["Users"])
    app.include_router(AddonsRouter, prefix="/api/v1", tags=["Addons"])
    app.include_router(UserLikesRouter, prefix="/api/v1", tags=["User Likes"])
    app.include_router(VersionRouter, prefix="/api/v1", tags=["Version"])
    # app.state.limiter = AuthRouterLimiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)


# Create FastAPI app with metadata
app = FastAPI(
    title="MinePlace API",
    description="Backend API for MinePlace application",
    version="1.0.0",
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    openapi_url="/api/openapi.json"
)

configure_app(app)

def run_server():
    """Run the FastAPI server with uvicorn."""
    uvicorn.run(
        "src.run:app",
        host=settings.HOST,
        port=settings.PORT,
        log_level=settings.LOG_LEVEL,
        reload=settings.DEBUG_MODE
    )

def handle_exception(loop, context):
    """Handle uncaught exceptions in the event loop."""
    LOGGER.error("Uncaught exception", exc_info=context["exc_info"])
    loop.stop()

def main():
    """Main application entry point."""
    # Configure application
    configure_logging()
    # Run server
    try:
        run_server()
    except KeyboardInterrupt:
        LOGGER.info("Server stopped by user")
    except Exception as e:
        LOGGER.error(f"Server stopped due to error: {e}", exc_info=True)
        raise

if __name__ == '__main__':
    main()