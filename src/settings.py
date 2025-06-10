import os
from pathlib import Path
from typing import List
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import BaseModel, field_validator

class Settings(BaseSettings):
    # Database settings
    DB_URL: str
    
    # JWT settings
    AUTHJWT_SECRET_KEY: str
    AUTHJWT_ACCESS_TOKEN_EXPIRES: int = 36000  # 1 hour
    AUTHJWT_REFRESH_TOKEN_EXPIRES: int = 604800  # 7 days
        
    # Server settings
    HOST: str = "127.0.0.1"
    PORT: int = 8000
    DEBUG_MODE: bool = True
    LOG_LEVEL: str = "debug"
    
    # CORS settings
    CORS_ORIGINS: List[str] = ["http://localhost:3000", "http://localhost:8000"]
    
    # Security settings
    MIN_PASSWORD_LENGTH: int = 8
    MAX_PASSWORD_LENGTH: int = 32
    PASSWORD_REGEX: str = r"^(?=.*[A-Za-z])(?=.*\d)[A-Za-z\d]{8,}$"
    
    @field_validator("CORS_ORIGINS", mode="before")
    def assemble_cors_origins(cls, v):
        if isinstance(v, str):
            return [i.strip() for i in v.split(",")]
        return v

    model_config = SettingsConfigDict(
        env_file=Path(__file__).parent / "../.env",
        case_sensitive=True,
        env_file_encoding="utf-8"
    )

settings = Settings()

class SettingsJWT(BaseModel):
    """JWT specific settings."""
    authjwt_secret_key: str = settings.AUTHJWT_SECRET_KEY
    authjwt_access_token_expires: int = settings.AUTHJWT_ACCESS_TOKEN_EXPIRES
    authjwt_refresh_token_expires: int = settings.AUTHJWT_REFRESH_TOKEN_EXPIRES
    authjwt_token_location: set = {"headers"}
    authjwt_cookie_csrf_protect: bool = True
    authjwt_cookie_samesite: str = "lax"
    authjwt_cookie_secure: bool = False  # Set to True in production with HTTPS
    authjwt_denylist_enabled: bool = False
    authjwt_denylist_token_checks: set = {"access", "refresh"}

