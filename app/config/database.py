from motor.motor_asyncio import AsyncIOMotorClient
from fastapi import HTTPException
from .settings import settings
import logging

logger = logging.getLogger(__name__)


class Database:
    client: AsyncIOMotorClient = None
    database = None


db = Database()


async def get_database():
    if db.database is None:
        raise HTTPException(
            status_code=503,
            detail="Database connection not available. Please check MongoDB configuration."
        )
    return db.database


async def connect_to_mongo():
    """Create database connection"""
    try:
        db.client = AsyncIOMotorClient(settings.mongodb_url)
        db.database = db.client[settings.MONGO_DATABASE]

        # Test connection
        await db.client.admin.command('ping')
        logger.info(f"Successfully connected to MongoDB database '{settings.MONGO_DATABASE}' on Atlas")

    except Exception as e:
        logger.error(f"Error connecting to MongoDB: {e}")
        db.client = None
        db.database = None


async def close_mongo_connection():
    """Close database connection"""
    if db.client:
        db.client.close()
        logger.info("Disconnected from MongoDB")
