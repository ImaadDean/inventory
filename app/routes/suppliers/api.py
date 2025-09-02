from fastapi import APIRouter, HTTPException, Depends, Query, Request
from typing import List, Optional
from app.utils.auth import get_current_user, get_current_user_hybrid, get_current_user_hybrid_dependency, verify_token, get_user_by_username
from app.models.user import User
from app.models.supplier import Supplier
from app.schemas.supplier import SupplierCreate, SupplierUpdate, SupplierResponse
from app.config.database import get_database
from app.utils.timezone import now_kampala, kampala_to_utc
from bson import ObjectId
from datetime import datetime
import logging

logger = logging.getLogger(__name__)
router = APIRouter()



@router.get("/api/suppliers/", response_model=dict)
async def get_suppliers(
    page: int = Query(1, ge=1),
    size: int = Query(10, ge=1, le=100),
    search: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    user: User = Depends(get_current_user_hybrid_dependency())
):
    """Get suppliers with pagination and filtering"""
    try:
        db = await get_database()
        suppliers_collection = db.suppliers
        products_collection = db.products
        expenses_collection = db.expenses
        
        # Build query
        query = {}
        
        if search:
            query["$or"] = [
                {"name": {"$regex": search, "$options": "i"}},
                {"contact_person": {"$regex": search, "$options": "i"}},
                {"email": {"$regex": search, "$options": "i"}},
                {"phone": {"$regex": search, "$options": "i"}}
            ]
        
        if status:
            if status == "active":
                query["is_active"] = True
            elif status == "inactive":
                query["is_active"] = False
        
        # Get total count
        total = await suppliers_collection.count_documents(query)
        
        # Get suppliers with pagination
        skip = (page - 1) * size
        cursor = suppliers_collection.find(query).skip(skip).limit(size).sort("name", 1)
        suppliers = await cursor.to_list(length=size)
        
        # Convert ObjectId to string and format data
        for supplier in suppliers:
            supplier["id"] = str(supplier["_id"])
            del supplier["_id"]
            
            # Add computed fields
            supplier_name = supplier.get("name", "")

            # Get product count from both old method (supplier field) and new method (products array)
            # Use case-insensitive matching for supplier name
            product_count_old = await products_collection.count_documents({
                "supplier": {"$regex": f"^{supplier_name}$", "$options": "i"}
            })
            product_count_new = len(supplier.get("products", []))

            # Use the higher count (for backward compatibility)
            supplier["products_count"] = max(product_count_old, product_count_new)

            # Get last order date from supplier record or restock history
            last_order_date = supplier.get("last_order_date")
            if not last_order_date:
                # Fallback: check restock history for this supplier
                restock_history = db.restock_history
                last_restock = await restock_history.find_one(
                    {"supplier_name": {"$regex": f"^{supplier_name}$", "$options": "i"}},
                    sort=[("restocked_at", -1)]
                )
                if last_restock:
                    last_order_date = last_restock.get("restocked_at")

            supplier["last_order_date"] = last_order_date

            # Calculate unpaid balance
            unpaid_expenses = await expenses_collection.find({
                "vendor": supplier_name,
                "status": "not_paid"
            }).to_list(length=None)
            
            unpaid_balance = sum(expense.get("amount", 0) for expense in unpaid_expenses)
            supplier["unpaid_balance"] = unpaid_balance
        
        # Calculate stats
        products_collection = db.products
        total_products = await products_collection.count_documents({})

        stats = {
            "total": await suppliers_collection.count_documents({}),
            "active": await suppliers_collection.count_documents({"is_active": True}),
            "products": total_products,
            "total_value": 0  # TODO: Calculate total inventory value
        }
        
        return {
            "suppliers": suppliers,
            "total": total,
            "page": page,
            "size": size,
            "total_pages": (total + size - 1) // size,
            "stats": stats
        }
        
    except Exception as e:
        logger.error(f"Error fetching suppliers: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch suppliers")

@router.post("/api/suppliers/", response_model=dict)
async def create_supplier(
    request: Request,
    supplier_data: SupplierCreate,
    user: User = Depends(get_current_user_hybrid_dependency())
):
    """Create a new supplier"""
    try:
        db = await get_database()
        suppliers_collection = db.suppliers
        
        # Check if supplier already exists
        existing = await suppliers_collection.find_one({
            "name": {"$regex": f"^{supplier_data.name}$", "$options": "i"}
        })
        
        if existing:
            raise HTTPException(status_code=400, detail="Supplier with this company name already exists")
        
        # Create supplier document
        supplier_doc = {
            "name": supplier_data.name,
            "contact_person": supplier_data.contact_person,
            "phone": supplier_data.phone,
            "email": supplier_data.email,
            "address": supplier_data.address,
            "notes": supplier_data.notes,
            "is_active": supplier_data.is_active,
            "created_at": kampala_to_utc(now_kampala()),
            "updated_at": kampala_to_utc(now_kampala()),
            "created_by": user.username
        }
        
        result = await suppliers_collection.insert_one(supplier_doc)
        
        if result.inserted_id:
            return {
                "message": "Supplier created successfully",
                "supplier_id": str(result.inserted_id)
            }
        else:
            raise HTTPException(status_code=500, detail="Failed to create supplier")
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating supplier: {e}")
        raise HTTPException(status_code=500, detail="Failed to create supplier")

@router.get("/api/suppliers/{supplier_id}", response_model=dict)
async def get_supplier(
    request: Request,
    supplier_id: str,
    user: User = Depends(get_current_user_hybrid_dependency())
):
    """Get a specific supplier by ID"""
    try:
        db = await get_database()
        suppliers_collection = db.suppliers
        
        supplier = await suppliers_collection.find_one({"_id": ObjectId(supplier_id)})
        
        if not supplier:
            raise HTTPException(status_code=404, detail="Supplier not found")
        
        # Convert ObjectId to string
        supplier["id"] = str(supplier["_id"])
        del supplier["_id"]
        
        return supplier
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching supplier: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch supplier")

@router.put("/api/suppliers/{supplier_id}", response_model=dict)
async def update_supplier(
    request: Request,
    supplier_id: str,
    supplier_data: SupplierUpdate,
    user: User = Depends(get_current_user_hybrid_dependency())
):
    """Update a supplier and update related products if name changes"""
    try:
        db = await get_database()
        suppliers_collection = db.suppliers
        products_collection = db.products

        # Check if supplier exists
        existing = await suppliers_collection.find_one({"_id": ObjectId(supplier_id)})
        if not existing:
            raise HTTPException(status_code=404, detail="Supplier not found")

        old_name = existing.get("name")

        # Build update document
        update_doc = {
            "updated_at": kampala_to_utc(now_kampala()),
            "updated_by": user.username
        }

        # Add fields that are being updated
        update_data = supplier_data.dict(exclude_unset=True)
        update_doc.update(update_data)

        # Update supplier
        result = await suppliers_collection.update_one(
            {"_id": ObjectId(supplier_id)},
            {"$set": update_doc}
        )

        products_updated = 0

        # If supplier name changed, update products that reference this supplier
        if "name" in update_data and update_data["name"] != old_name:
            new_name = update_data["name"]

            # Update products with the old supplier name
            products_update_result = await products_collection.update_many(
                {"supplier": old_name},
                {
                    "$set": {
                        "supplier": new_name,
                        "updated_at": kampala_to_utc(now_kampala())
                    }
                }
            )
            products_updated = products_update_result.modified_count

            logger.info(f"Updated supplier name from '{old_name}' to '{new_name}' in {products_updated} products")

        if result.modified_count > 0:
            message = "Supplier updated successfully"
            if products_updated > 0:
                message += f". {products_updated} products were updated with the new supplier name."
            return {
                "message": message,
                "products_updated": products_updated
            }
        else:
            return {"message": "No changes made to supplier"}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating supplier: {e}")
        raise HTTPException(status_code=500, detail="Failed to update supplier")

@router.delete("/api/suppliers/{supplier_id}", response_model=dict)
async def delete_supplier(
    request: Request,
    supplier_id: str,
    user: User = Depends(get_current_user_hybrid_dependency())
):
    """Delete a supplier while keeping products they supplied"""
    try:
        db = await get_database()
        suppliers_collection = db.suppliers
        products_collection = db.products

        # Check if supplier exists
        existing = await suppliers_collection.find_one({"_id": ObjectId(supplier_id)})
        if not existing:
            raise HTTPException(status_code=404, detail="Supplier not found")

        supplier_name = existing.get("name", "Unknown Supplier")

        # Check for products supplied by this supplier
        products_count = await products_collection.count_documents({"supplier": supplier_name})

        # Update products to remove supplier reference but keep the products
        if products_count > 0:
            update_result = await products_collection.update_many(
                {"supplier": supplier_name},
                {
                    "$set": {
                        "supplier": f"[DELETED] {supplier_name}",
                        "updated_at": kampala_to_utc(now_kampala())
                    }
                }
            )
            logger.info(f"Updated {update_result.modified_count} products for deleted supplier: {supplier_name}")

        # Delete the supplier
        result = await suppliers_collection.delete_one({"_id": ObjectId(supplier_id)})

        if result.deleted_count > 0:
            message = f"Supplier '{supplier_name}' deleted successfully"
            if products_count > 0:
                message += f". {products_count} products were updated to preserve their history."

            return {
                "message": message,
                "products_updated": products_count
            }
        else:
            raise HTTPException(status_code=500, detail="Failed to delete supplier")

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting supplier: {e}")
        raise HTTPException(status_code=500, detail="Failed to delete supplier")


@router.patch("/api/suppliers/{supplier_id}/deactivate", response_model=dict)
async def deactivate_supplier(
    request: Request,
    supplier_id: str,
    user: User = Depends(get_current_user_hybrid_dependency())
):
    """Deactivate a supplier (soft delete) while keeping all data intact"""
    try:
        db = await get_database()
        suppliers_collection = db.suppliers

        # Check if supplier exists
        existing = await suppliers_collection.find_one({"_id": ObjectId(supplier_id)})
        if not existing:
            raise HTTPException(status_code=404, detail="Supplier not found")

        supplier_name = existing.get("name", "Unknown Supplier")

        # Update supplier to inactive
        result = await suppliers_collection.update_one(
            {"_id": ObjectId(supplier_id)},
            {
                "$set": {
                    "is_active": False,
                    "updated_at": kampala_to_utc(now_kampala()),
                    "updated_by": user.username
                }
            }
        )

        if result.modified_count > 0:
            return {
                "message": f"Supplier '{supplier_name}' deactivated successfully. All products and history preserved.",
                "action": "deactivated"
            }
        else:
            raise HTTPException(status_code=500, detail="Failed to deactivate supplier")

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deactivating supplier: {e}")
        raise HTTPException(status_code=500, detail="Failed to deactivate supplier")


@router.patch("/api/suppliers/{supplier_id}/activate", response_model=dict)
async def activate_supplier(
    request: Request,
    supplier_id: str,
    user: User = Depends(get_current_user_hybrid_dependency())
):
    """Reactivate a supplier"""
    try:
        db = await get_database()
        suppliers_collection = db.suppliers

        # Check if supplier exists
        existing = await suppliers_collection.find_one({"_id": ObjectId(supplier_id)})
        if not existing:
            raise HTTPException(status_code=404, detail="Supplier not found")

        supplier_name = existing.get("name", "Unknown Supplier")

        # Update supplier to active
        result = await suppliers_collection.update_one(
            {"_id": ObjectId(supplier_id)},
            {
                "$set": {
                    "is_active": True,
                    "updated_at": kampala_to_utc(now_kampala()),
                    "updated_by": user.username
                }
            }
        )

        if result.modified_count > 0:
            return {
                "message": f"Supplier '{supplier_name}' activated successfully.",
                "action": "activated"
            }
        else:
            raise HTTPException(status_code=500, detail="Failed to activate supplier")

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error activating supplier: {e}")
        raise HTTPException(status_code=500, detail="Failed to activate supplier")


@router.get("/dropdown", response_model=dict)
async def get_suppliers_dropdown():
    """Get simple list of active suppliers for dropdowns - no auth required"""
    try:
        db = await get_database()
        suppliers_collection = db.suppliers

        # Get only active suppliers with basic info
        cursor = suppliers_collection.find(
            {"is_active": True},
            {"name": 1, "_id": 1}
        ).sort("name", 1)

        suppliers = await cursor.to_list(length=None)

        # Format for dropdown
        suppliers_list = []
        for supplier in suppliers:
            suppliers_list.append({
                "id": str(supplier["_id"]),
                "name": supplier["name"]
            })

        return {
            "suppliers": suppliers_list,
            "total": len(suppliers_list)
        }

    except Exception as e:
        logger.error(f"Error fetching simple suppliers: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch suppliers")


@router.post("/sync-products", response_model=dict)
async def sync_supplier_products(
    request: Request,
    user: User = Depends(get_current_user_hybrid_dependency())
):
    """Sync existing products with suppliers - one-time migration"""
    try:
        db = await get_database()
        suppliers_collection = db.suppliers
        products_collection = db.products

        # Get all suppliers
        suppliers = await suppliers_collection.find({}).to_list(length=None)
        updated_count = 0

        for supplier in suppliers:
            supplier_name = supplier["name"]
            supplier_id = supplier["_id"]

            # Find all products for this supplier
            products = await products_collection.find({"supplier": supplier_name}).to_list(length=None)
            product_ids = [str(product["_id"]) for product in products]

            # Update supplier with product list
            if product_ids:
                update_doc = {
                    "products": product_ids,
                    "updated_at": kampala_to_utc(now_kampala())
                }

                # Set last_order_date if not exists
                if not supplier.get("last_order_date") and product_ids:
                    update_doc["last_order_date"] = kampala_to_utc(now_kampala())

                await suppliers_collection.update_one(
                    {"_id": supplier_id},
                    {"$set": update_doc}
                )
                updated_count += 1

        return {
            "message": f"Successfully synced {updated_count} suppliers with their products",
            "updated_suppliers": updated_count
        }

    except Exception as e:
        logger.error(f"Error syncing supplier products: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to sync supplier products: {str(e)}"
        )
