#!/usr/bin/env python3
"""
Migration script to convert orders to sales
"""
import asyncio
from motor.motor_asyncio import AsyncIOMotorClient
from app.config.settings import settings
from bson import ObjectId
from datetime import datetime
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Map order payment methods to sale payment methods
PAYMENT_METHOD_MAP = {
    "cash": "cash",
    "card": "card",
    "mobile_money": "mobile_money",
    "bank_transfer": "bank_transfer",
    "installment": "not_paid",  # Installments are not fully paid yet
    "pending": "not_paid",
    "partially_paid": "not_paid",
    "paid": "cash"  # Default to cash for fully paid orders
}

# Map order statuses to sale statuses
STATUS_MAP = {
    "pending": "pending",
    "active": "pending",
    "completed": "completed",
    "cancelled": "cancelled",
    "refunded": "refunded",
    "paid": "completed",
    "partially_paid": "pending"
}


async def migrate_orders_to_sales():
    """Migrate all orders to sales collection"""
    try:
        logger.info("Starting migration of orders to sales...")
        
        client = AsyncIOMotorClient(settings.mongodb_url)
        db = client[settings.MONGO_DATABASE]
        
        orders_collection = db.orders
        sales_collection = db.sales
        
        sales_count = await sales_collection.count_documents({})
        if sales_count > 0:
            logger.warning(f"Sales collection already contains {sales_count} documents. Skipping migration.")
            return
        
        orders_cursor = orders_collection.find({})
        orders = await orders_cursor.to_list(length=None)
        
        logger.info(f"Found {len(orders)} orders to migrate")
        
        migrated_count = 0
        failed_count = 0
        
        for i, order in enumerate(orders):
            try:
                if order.get("payment_method") == "installment":
                    logger.info(f"Skipping installment order {order.get('order_number')}")
                    continue
                
                sale_data = await convert_order_to_sale(order, db, i)
                
                if sale_data:
                    result = await sales_collection.insert_one(sale_data)
                    if result.inserted_id:
                        migrated_count += 1
                        logger.info(f"Migrated order {order.get('order_number')} to sale {sale_data.get('sale_number')}")
                    else:
                        failed_count += 1
                        logger.error(f"Failed to migrate order {order.get('order_number')}")
                else:
                    failed_count += 1
                    logger.error(f"Failed to convert order {order.get('order_number')} to sale")
                    
            except Exception as e:
                failed_count += 1
                logger.error(f"Error migrating order {order.get('order_number')}: {e}")
        
        logger.info(f"Migration completed. Successfully migrated: {migrated_count}, Failed: {failed_count}")
        
        client.close()
        
    except Exception as e:
        logger.error(f"Error during migration: {e}")


async def convert_order_to_sale(order, db, sale_index):
    """Convert an order document to a sale document"""
    try:
        sale_number = f"SALE-{sale_index + 1:06d}"
        
        sale_data = {
            "sale_number": sale_number,
            "customer_id": order.get("client_id"),
            "customer_name": order.get("client_name", ""),
            "cashier_id": order.get("created_by", ObjectId()),
            "cashier_name": "System",
            "items": [],
            "subtotal": order.get("subtotal", 0),
            "tax_amount": order.get("tax", 0),
            "discount_amount": order.get("discount", 0),
            "total_amount": order.get("total", 0),
            "payment_method": PAYMENT_METHOD_MAP.get(order.get("payment_method", "cash"), "cash"),
            "payment_received": order.get("total", 0) if order.get("payment_status") == "paid" else 0,
            "change_given": 0,
            "status": STATUS_MAP.get(order.get("status", "completed"), "completed"),
            "notes": order.get("notes", ""),
            "created_at": order.get("created_at", datetime.utcnow()),
            "updated_at": order.get("updated_at", datetime.utcnow())
        }
        
        order_items = order.get("items", [])
        sale_items = []
        
        for item in order_items:
            sale_item = {
                "product_id": item.get("product_id", ""),
                "product_name": item.get("product_name", ""),
                "sku": "",
                "quantity": item.get("quantity", 0),
                "unit_price": item.get("unit_price", 0),
                "cost_price": item.get("unit_price", 0),
                "total_price": item.get("total_price", 0),
                "discount_amount": item.get("discount_amount", 0)
            }
            
            try:
                product_id = item.get("product_id")
                if product_id:
                    product = await db.products.find_one({"_id": ObjectId(product_id)})
                    if product:
                        if product.get("is_decant", False):
                            if product.get("original_cost") and product.get("original_volume") and product.get("decant_volume"):
                                calculated_cost = (product["original_cost"] / product["original_volume"]) * product["decant_volume"]
                                sale_item["cost_price"] = calculated_cost
                        else:
                            sale_item["cost_price"] = product.get("cost_price", product.get("price", 0))
                        sale_item["sku"] = product.get("sku", "")
            except Exception as e:
                logger.warning(f"Could not fetch product info for item: {e}")
            
            unit_profit = sale_item["unit_price"] - sale_item["cost_price"]
            total_profit = (unit_profit * sale_item["quantity"]) - sale_item["discount_amount"]
            sale_item["profit"] = max(0, total_profit)
            
            sale_items.append(sale_item)
        
        sale_data["items"] = sale_items
        
        total_profit = sum(item["profit"] for item in sale_items)
        sale_data["total_profit"] = total_profit
        
        try:
            cashier_id = order.get("created_by")
            if cashier_id:
                user = await db.users.find_one({"_id": ObjectId(cashier_id)})
                if user:
                    sale_data["cashier_name"] = user.get("full_name", "System")
        except Exception:
            pass
        
        if not sale_data["sale_number"]:
            logger.error("Order missing sale_number")
            return None
            
        if not sale_data["items"] or len(sale_data["items"]) == 0:
            logger.error(f"Order {sale_data['sale_number']} has no items")
            return None
            
        return sale_data
        
    except Exception as e:
        logger.error(f"Error converting order to sale: {e}")
        return None


if __name__ == "__main__":
    asyncio.run(migrate_orders_to_sales())