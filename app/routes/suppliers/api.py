from fastapi import APIRouter, HTTPException, Depends, Query, Request, status
from typing import List, Optional
from app.utils.auth import get_current_user, get_current_user_hybrid, get_current_user_hybrid_dependency, verify_token, get_user_by_username
from app.models.user import User
from app.models.supplier import Supplier
from app.schemas.supplier import SupplierCreate, SupplierUpdate, SupplierResponse, SupplierPayment
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
        
        # --- Optimizations: Fetch aggregated data in bulk ---

        # 1. Get product counts for all suppliers (case-insensitive)
        product_count_pipeline = [
            {"$group": {"_id": {"$toLower": "$supplier"}, "count": {"$sum": 1}}}
        ]
        product_counts_cursor = products_collection.aggregate(product_count_pipeline)
        product_counts = {item["_id"]: item["count"] async for item in product_counts_cursor}

        # 2. Get last order dates from restock history for all suppliers (case-insensitive)
        restock_history_collection = db.restock_history
        last_restock_pipeline = [
            {"$sort": {"restocked_at": -1}},
            {"$group": {
                "_id": {"$toLower": "$supplier_name"},
                "last_restock_date": {"$first": "$restocked_at"}
            }}
        ]
        last_restocks_cursor = restock_history_collection.aggregate(last_restock_pipeline)
        last_restocks = {item["_id"]: item["last_restock_date"] async for item in last_restocks_cursor}

        # 3. Get unpaid balances for all suppliers (case-insensitive on vendor)
        unpaid_balance_pipeline = [
            {"$match": {"status": {"$in": ["not_paid", "partially_paid"]}}},
            {"$group": {
                "_id": {"$toLower": "$vendor"},
                "total_due": {"$sum": "$amount"},
                "total_paid": {"$sum": "$amount_paid"}
            }},
            {"$project": {
                "unpaid_balance": {"$subtract": ["$total_due", "$total_paid"]}
            }}
        ]
        unpaid_balances_cursor = expenses_collection.aggregate(unpaid_balance_pipeline)
        unpaid_balances = {item["_id"]: item["unpaid_balance"] async for item in unpaid_balances_cursor}

        # --- End Optimizations ---
        
        # Convert ObjectId to string and format data
        for supplier in suppliers:
            supplier["id"] = str(supplier["_id"])
            del supplier["_id"]
            
            supplier_name = supplier.get("name", "")
            supplier_name_lower = supplier_name.lower()
            
            # Add computed fields using pre-fetched data
            
            # Product count
            product_count_old = product_counts.get(supplier_name_lower, 0)
            product_count_new = len(supplier.get("products", []))
            supplier["products_count"] = max(product_count_old, product_count_new)

            # Last order date
            last_order_date = supplier.get("last_order_date")
            if not last_order_date:
                last_order_date = last_restocks.get(supplier_name_lower)
            supplier["last_order_date"] = last_order_date

            # Unpaid balance
            supplier["unpaid_balance"] = unpaid_balances.get(supplier_name_lower, 0)
        
        # Calculate stats efficiently
        stats_pipeline = [
            {"$facet": {
                "total": [{"$count": "count"}],
                "active": [{"$match": {"is_active": True}}, {"$count": "count"}]
            }}
        ]
        stats_result_cursor = suppliers_collection.aggregate(stats_pipeline)
        stats_result = await stats_result_cursor.to_list(length=1)
        
        total_suppliers = stats_result[0]['total'][0]['count'] if stats_result and stats_result[0]['total'] else 0
        active_suppliers = stats_result[0]['active'][0]['count'] if stats_result and stats_result[0]['active'] else 0

        total_products = await products_collection.count_documents({})

        # Calculate total unpaid balance for stats
        total_unpaid_balance = sum(unpaid_balances.values())
        
        stats = {
            "total": total_suppliers,
            "active": active_suppliers,
            "products": total_products,
            "total_value": total_unpaid_balance  # Changed from 0 to total unpaid balance
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

@router.post("/api/suppliers/{supplier_name}/pay", response_model=dict)
async def pay_supplier_expenses(
    supplier_name: str,
    payment: SupplierPayment,
    user: User = Depends(get_current_user_hybrid_dependency())
):
    """Pay off unpaid expenses for a supplier"""
    try:
        db = await get_database()
        expenses_collection = db.expenses
        installments_collection = db.installments
        
        # Get all unpaid expenses for the supplier, oldest first
        unpaid_expenses = await expenses_collection.find({
            "vendor": supplier_name,
            "status": {"$in": ["not_paid", "partially_paid"]}
        }).sort("expense_date", 1).to_list(length=None)
        
        if not unpaid_expenses:
            raise HTTPException(status_code=404, detail="No unpaid expenses found for this supplier.")

        payment_amount = payment.amount
        paid_expenses_ids = []
        partially_paid_expense_id = None

        for expense in unpaid_expenses:
            if payment_amount <= 0:
                break

            expense_id = expense["_id"]
            expense_amount = expense["amount"]
            amount_paid = expense.get("amount_paid", 0)
            remaining_due = expense_amount - amount_paid
            
            amount_to_pay_for_this_expense = min(payment_amount, remaining_due)

            if amount_to_pay_for_this_expense <= 0:
                continue

            # Update expense
            new_amount_paid = amount_paid + amount_to_pay_for_this_expense
            new_status = "paid" if new_amount_paid >= expense_amount else "partially_paid"

            await expenses_collection.update_one(
                {"_id": expense_id},
                {"$set": {
                    "status": new_status,
                    "amount_paid": new_amount_paid,
                    "payment_method": payment.payment_method,
                    "updated_at": kampala_to_utc(now_kampala()),
                    "updated_by": user.username
                }}
            )

            # Create installment record
            await installments_collection.insert_one({
                "expense_id": expense_id,
                "amount": amount_to_pay_for_this_expense,
                "payment_date": kampala_to_utc(now_kampala()),
                "payment_method": payment.payment_method,
                "notes": f"Paid via supplier payment page.",
                "created_by": user.username
            })

            if new_status == "paid":
                paid_expenses_ids.append(str(expense_id))
            else:
                partially_paid_expense_id = str(expense_id)

            payment_amount -= amount_to_pay_for_this_expense
        
        return {
            "message": "Payment processed successfully.",
            "paid_expenses": paid_expenses_ids,
            "partially_paid_expense": partially_paid_expense_id
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error paying supplier expenses: {e}")
        raise HTTPException(status_code=500, detail="Failed to pay supplier expenses")

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
