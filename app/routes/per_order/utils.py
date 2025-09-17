from ...config.database import get_database

async def generate_per_order_number() -> str:
    """Generate a new unique per order number"""
    db = await get_database()
    last_order = await db.per_orders.find_one({}, sort=[("order_number", -1)])
    if last_order and last_order.get("order_number"):
        try:
            last_number = int(last_order["order_number"].split("-")[-1])
            new_number = last_number + 1
            return f"PO-{new_number:06d}"
        except (ValueError, IndexError):
            # Fallback in case of unexpected format
            count = await db.per_orders.count_documents({})
            return f"PO-{count + 1:06d}"
    return "PO-000001"
