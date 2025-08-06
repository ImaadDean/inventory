from datetime import datetime
from typing import List, Optional, Dict, Any
from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.models.product_supplier_price import (
    ProductSupplierPriceCreate,
    ProductSupplierPriceResponse,
    SupplierPricingSummary,
    ProductPricingHistory
)


class ProductSupplierPriceService:
    """Service for managing product supplier pricing data"""
    
    def __init__(self, db: AsyncIOMotorDatabase):
        self.db = db
        self.collection = db.product_supplier_prices
    
    async def create_price_record(self, price_data: ProductSupplierPriceCreate) -> str:
        """Create a new price record"""
        now = datetime.utcnow()
        
        record = {
            "product_id": ObjectId(price_data.product_id),
            "supplier_id": ObjectId(price_data.supplier_id),
            "unit_cost": price_data.unit_cost,
            "quantity_restocked": price_data.quantity_restocked,
            "total_cost": price_data.total_cost,
            "restock_date": price_data.restock_date,
            "expense_id": ObjectId(price_data.expense_id) if price_data.expense_id else None,
            "notes": price_data.notes,
            "created_at": now,
            "updated_at": now
        }
        
        result = await self.collection.insert_one(record)
        return str(result.inserted_id)
    
    async def get_product_pricing_history(self, product_id: str) -> Optional[ProductPricingHistory]:
        """Get complete pricing history for a product"""
        try:
            product_oid = ObjectId(product_id)
            
            # Get product info
            product = await self.db.products.find_one({"_id": product_oid})
            if not product:
                return None
            
            # Aggregate pricing data by supplier
            pipeline = [
                {"$match": {"product_id": product_oid}},
                {"$lookup": {
                    "from": "suppliers",
                    "localField": "supplier_id",
                    "foreignField": "_id",
                    "as": "supplier_info"
                }},
                {"$unwind": "$supplier_info"},
                {"$sort": {"restock_date": -1}},
                {"$group": {
                    "_id": "$supplier_id",
                    "supplier_name": {"$first": "$supplier_info.name"},
                    "latest_price": {"$first": "$unit_cost"},
                    "latest_restock_date": {"$first": "$restock_date"},
                    "average_price": {"$avg": "$unit_cost"},
                    "total_restocks": {"$sum": 1},
                    "total_quantity": {"$sum": "$quantity_restocked"},
                    "price_history": {
                        "$push": {
                            "unit_cost": "$unit_cost",
                            "quantity": "$quantity_restocked",
                            "restock_date": "$restock_date",
                            "total_cost": "$total_cost"
                        }
                    }
                }},
                {"$sort": {"latest_restock_date": -1}}
            ]
            
            suppliers_data = await self.collection.aggregate(pipeline).to_list(length=None)
            
            # Build supplier summaries
            suppliers = []
            current_supplier_id = str(product.get("supplier_id")) if product.get("supplier_id") else None
            
            for supplier_data in suppliers_data:
                supplier_id = str(supplier_data["_id"])
                
                # Limit price history to last 5 records
                price_history = supplier_data["price_history"][:5]
                
                supplier_summary = SupplierPricingSummary(
                    supplier_id=supplier_id,
                    supplier_name=supplier_data["supplier_name"],
                    is_current=(supplier_id == current_supplier_id),
                    latest_price=supplier_data["latest_price"],
                    latest_restock_date=supplier_data["latest_restock_date"],
                    average_price=round(supplier_data["average_price"], 2),
                    total_restocks=supplier_data["total_restocks"],
                    total_quantity=supplier_data["total_quantity"],
                    price_history=price_history
                )
                suppliers.append(supplier_summary)
            
            # Calculate price range
            all_prices = [s.latest_price for s in suppliers]
            price_range = {
                "min": min(all_prices) if all_prices else 0,
                "max": max(all_prices) if all_prices else 0
            }
            
            return ProductPricingHistory(
                product_id=product_id,
                product_name=product["name"],
                current_supplier_id=current_supplier_id,
                current_cost_price=product.get("cost_price", 0),
                suppliers=suppliers,
                total_suppliers=len(suppliers),
                price_range=price_range
            )
            
        except Exception as e:
            print(f"Error getting product pricing history: {e}")
            return None
    
    async def get_supplier_price_history(self, product_id: str, supplier_id: str, limit: int = 10) -> List[ProductSupplierPriceResponse]:
        """Get price history for a specific product-supplier combination"""
        try:
            pipeline = [
                {
                    "$match": {
                        "product_id": ObjectId(product_id),
                        "supplier_id": ObjectId(supplier_id)
                    }
                },
                {"$lookup": {
                    "from": "suppliers",
                    "localField": "supplier_id",
                    "foreignField": "_id",
                    "as": "supplier_info"
                }},
                {"$unwind": "$supplier_info"},
                {"$sort": {"restock_date": -1}},
                {"$limit": limit}
            ]
            
            records = await self.collection.aggregate(pipeline).to_list(length=None)
            
            result = []
            for record in records:
                price_record = ProductSupplierPriceResponse(
                    id=str(record["_id"]),
                    product_id=str(record["product_id"]),
                    supplier_id=str(record["supplier_id"]),
                    supplier_name=record["supplier_info"]["name"],
                    unit_cost=record["unit_cost"],
                    quantity_restocked=record["quantity_restocked"],
                    total_cost=record["total_cost"],
                    restock_date=record["restock_date"],
                    expense_id=str(record["expense_id"]) if record.get("expense_id") else None,
                    notes=record.get("notes"),
                    created_at=record["created_at"],
                    updated_at=record["updated_at"]
                )
                result.append(price_record)
            
            return result
            
        except Exception as e:
            print(f"Error getting supplier price history: {e}")
            return []
    
    async def get_latest_supplier_price(self, product_id: str, supplier_id: str) -> Optional[float]:
        """Get the latest price for a product from a specific supplier"""
        try:
            record = await self.collection.find_one(
                {
                    "product_id": ObjectId(product_id),
                    "supplier_id": ObjectId(supplier_id)
                },
                sort=[("restock_date", -1)]
            )
            
            return record["unit_cost"] if record else None
            
        except Exception as e:
            print(f"Error getting latest supplier price: {e}")
            return None
    
    async def create_index(self):
        """Create database indexes for better performance"""
        try:
            # Compound index for product-supplier queries
            await self.collection.create_index([
                ("product_id", 1),
                ("supplier_id", 1),
                ("restock_date", -1)
            ])
            
            # Index for product queries
            await self.collection.create_index([
                ("product_id", 1),
                ("restock_date", -1)
            ])
            
            print("✅ Product supplier price indexes created successfully")
            
        except Exception as e:
            print(f"❌ Error creating indexes: {e}")
