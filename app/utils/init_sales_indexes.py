"""
Initialize database indexes for sales collection
"""
import asyncio
from app.config.database import get_database


async def init_sales_indexes():
    """Initialize database indexes for sales collection"""
    try:
        db = await get_database()
        sales_collection = db.sales
        
        # Create indexes for better query performance
        # Index on sale_number for unique constraint
        await sales_collection.create_index("sale_number", unique=True)
        
        # Index on created_at for date-based queries
        await sales_collection.create_index("created_at")
        
        # Index on status for filtering
        await sales_collection.create_index("status")
        
        # Index on customer_id for customer-based queries
        await sales_collection.create_index("customer_id")
        
        # Index on cashier_id for cashier-based queries
        await sales_collection.create_index("cashier_id")
        
        # Compound index for common query patterns
        await sales_collection.create_index([
            ("status", 1),
            ("created_at", 1)
        ])
        
        await sales_collection.create_index([
            ("customer_id", 1),
            ("created_at", 1)
        ])
        
        await sales_collection.create_index([
            ("cashier_id", 1),
            ("created_at", 1)
        ])
        
    except Exception as e:
        pass


if __name__ == "__main__":
    asyncio.run(init_sales_indexes())