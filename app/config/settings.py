import os
from pydantic_settings import BaseSettings


def get_dynamic_base_url():
    """Get base URL using the robust configuration manager"""
    try:
        from ..utils.server_config import get_base_url
        return get_base_url()
    except ImportError:
        # Fallback if server_config is not available
        return os.getenv("BASE_URL", "http://localhost:8000")


class Settings(BaseSettings):
    # MongoDB Configuration
    MONGO_USERNAME: str = "imaad"
    MONGO_PASSWORD: str = "Ertdfgxc"
    MONGO_HOST: str = "144.21.56.184"
    MONGO_PORT: int = 27017
    
    MONGO_DATABASE: str = "inventory"
    MONGO_POOL_SIZE: int = 20

    # JWT Configuration
    SECRET_KEY: str = "your-secret-key-change-this-in-production"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30

    # Application Configuration
    APP_NAME: str = "Inventory Management System"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = True
    # Dynamic Base URL Configuration - Uses robust detection system
    # Priority: Environment Variable > Configuration File > Auto-detection > Fallback
    BASE_URL: str = get_dynamic_base_url()

    # CORS Configuration
    ALLOWED_ORIGINS: list = ["*"]

    # Timezone Configuration
    TIMEZONE: str = "Africa/Kampala"  # East Africa Time (UTC+3)
    TIMEZONE_NAME: str = "East Africa Time"
    TIMEZONE_ABBREVIATION: str = "EAT"

    # Email settings
    MAIL_USERNAME: str = "perfumesandmore.ug@gmail.com"
    MAIL_PASSWORD: str = "vlaj owhi pgvt bwij"
    MAIL_FROM: str = "perfumesandmore.ug@gmail.com"
    MAIL_FROM_NAME: str = "Perfumes & More"
    MAIL_PORT: int = 587
    MAIL_SERVER: str = "smtp.gmail.com"
    MAIL_TLS: bool = True
    MAIL_SSL: bool = False
    USE_CREDENTIALS: bool = True

    @property
    def mongodb_url(self) -> str:
        return f"mongodb://{self.MONGO_USERNAME}:{self.MONGO_PASSWORD}@{self.MONGO_HOST}:{self.MONGO_PORT}/{self.MONGO_DATABASE}?authSource=admin&maxPoolSize={self.MONGO_POOL_SIZE}"




settings = Settings()
