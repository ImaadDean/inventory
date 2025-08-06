"""
Initialize database indexes for product supplier pricing
"""
import asyncio
from app.database import get_database
from app.services.product_supplier_price_service import ProductSupplierPriceService


async def init_pricing_indexes():
    """Initialize database indexes for product supplier pricing"""
    try:
        print("🔄 Initializing product supplier pricing indexes...")
        
        db = await get_database()
        price_service = ProductSupplierPriceService(db)
        
        # Create indexes
        await price_service.create_index()
        
        print("✅ Product supplier pricing indexes initialized successfully!")
        
    except Exception as e:
        print(f"❌ Error initializing pricing indexes: {e}")


if __name__ == "__main__":
    asyncio.run(init_pricing_indexes())
