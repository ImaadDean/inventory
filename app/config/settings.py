from pydantic_settings import BaseSettings
from typing import Optional


class Settings(BaseSettings):
    # MongoDB Configuration
    MONGODB_USERNAME: str = "imaad"
    MONGODB_PASSWORD: str = "Ertdfgxc"
    MONGODB_HOST: str = "144.21.56.184"
    MONGODB_PORT: int = 27017
    MONGODB_DATABASE: str = "inventory"
    MONGODB_MAX_CONNECTIONS: int = 20

    # JWT Configuration
    SECRET_KEY: str = "your-secret-key-change-this-in-production"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30

    # Application Configuration
    APP_NAME: str = "Inventory Management System"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = True

    # CORS Configuration
    ALLOWED_ORIGINS: list = ["*"]

    @property
    def mongodb_url(self) -> str:
        return f"mongodb://{self.MONGODB_USERNAME}:{self.MONGODB_PASSWORD}@{self.MONGODB_HOST}:{self.MONGODB_PORT}/{self.MONGODB_DATABASE}?authSource=admin&maxPoolSize={self.MONGODB_MAX_CONNECTIONS}"

    class Config:
        env_file = ".env"


settings = Settings()