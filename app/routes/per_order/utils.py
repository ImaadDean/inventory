from ...config.database import get_database

async def generate_per_order_number() -> str:
    """Generate a new unique per order number"""
    db = await get_database()
    # Count existing orders to generate next sequential number
    order_count = await db.per_orders.count_documents({})
    return f"PO-{order_count + 1:06d}"
