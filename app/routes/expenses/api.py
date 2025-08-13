from fastapi import APIRouter, HTTPException, Depends, Query, Request
from typing import List, Optional
from app.utils.auth import get_current_user, get_current_user_hybrid, get_current_user_hybrid_dependency, verify_token, get_user_by_username
from app.utils.timezone import now_kampala, kampala_to_utc, get_month_start
from app.models.user import User
from app.models.expense import Expense
from app.models.expense_category import ExpenseCategory
from app.schemas.expense import ExpenseCreate, ExpenseUpdate, ExpenseResponse
from app.schemas.expense_category import ExpenseCategoryCreate, ExpenseCategoryUpdate, ExpenseCategoryResponse
from app.config.database import get_database
from app.utils.timezone import now_kampala, kampala_to_utc
from bson import ObjectId
from datetime import datetime, date
import logging

logger = logging.getLogger(__name__)
router = APIRouter()



@router.get("/api/expenses/", response_model=dict)
async def get_expenses(
    page: int = Query(1, ge=1),
    size: int = Query(10, ge=1, le=100),
    search: Optional[str] = Query(None),
    category: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    date_from: Optional[str] = Query(None),
    date_to: Optional[str] = Query(None),
    user: User = Depends(get_current_user_hybrid_dependency())
):
    """Get expenses with pagination and filtering"""
    try:
        db = await get_database()
        expenses_collection = db.expenses
        
        # Build query
        query = {}
        
        if search:
            query["$or"] = [
                {"description": {"$regex": search, "$options": "i"}},
                {"vendor": {"$regex": search, "$options": "i"}},
                {"notes": {"$regex": search, "$options": "i"}}
            ]
        
        if category:
            query["category"] = category
            
        if status:
            query["status"] = status
            
        # Enhanced date filtering to handle different date storage formats
        if date_from or date_to:
            date_conditions = []

            # Method 1: Try datetime object comparison
            if date_from and date_to:
                try:
                    start_date = datetime.strptime(date_from, "%Y-%m-%d")
                    end_date = datetime.strptime(date_to, "%Y-%m-%d").replace(hour=23, minute=59, second=59)
                    date_conditions.append({
                        "expense_date": {
                            "$gte": start_date,
                            "$lte": end_date
                        }
                    })
                except ValueError:
                    pass
            elif date_from:
                try:
                    start_date = datetime.strptime(date_from, "%Y-%m-%d")
                    date_conditions.append({"expense_date": {"$gte": start_date}})
                except ValueError:
                    pass
            elif date_to:
                try:
                    end_date = datetime.strptime(date_to, "%Y-%m-%d").replace(hour=23, minute=59, second=59)
                    date_conditions.append({"expense_date": {"$lte": end_date}})
                except ValueError:
                    pass

            # Method 2: Try string-based date comparison (for dates stored as strings)
            if date_from and date_to:
                # Convert YYYY-MM-DD to M/D/YYYY format for string comparison
                try:
                    from_parts = date_from.split('-')
                    to_parts = date_to.split('-')
                    from_str = f"{int(from_parts[1])}/{int(from_parts[2])}/{from_parts[0]}"
                    to_str = f"{int(to_parts[1])}/{int(to_parts[2])}/{to_parts[0]}"

                    date_conditions.append({
                        "$expr": {
                            "$and": [
                                {"$gte": [{"$dateFromString": {"dateString": "$expense_date", "onError": None}},
                                         {"$dateFromString": {"dateString": from_str, "onError": None}}]},
                                {"$lte": [{"$dateFromString": {"dateString": "$expense_date", "onError": None}},
                                         {"$dateFromString": {"dateString": to_str, "onError": None}}]}
                            ]
                        }
                    })
                except:
                    pass

            # Method 3: Simple string pattern matching for common date formats
            if date_from:
                try:
                    # Convert 2025-08-03 to match patterns like "8/3/2025"
                    year, month, day = date_from.split('-')
                    patterns = [
                        f"{int(month)}/{int(day)}/{year}",  # 8/3/2025
                        f"{month}/{day}/{year}",            # 08/03/2025
                        f"{int(month)}/{day}/{year}",       # 8/03/2025
                        f"{month}/{int(day)}/{year}",       # 08/3/2025
                        date_from                           # 2025-08-03
                    ]

                    pattern_conditions = []
                    for pattern in patterns:
                        escaped_pattern = pattern.replace('/', '\\/')
                        pattern_conditions.append({"expense_date": {"$regex": f"^{escaped_pattern}"}})

                    if pattern_conditions:
                        date_conditions.append({"$or": pattern_conditions})
                except:
                    pass

            # Apply date conditions
            if date_conditions:
                if len(date_conditions) == 1:
                    query.update(date_conditions[0])
                else:
                    query["$or"] = date_conditions
        
        # Get total count
        total = await expenses_collection.count_documents(query)
        
        # Get expenses with pagination
        skip = (page - 1) * size
        cursor = expenses_collection.find(query).skip(skip).limit(size).sort("expense_date", -1)
        expenses = await cursor.to_list(length=size)
        
        # Convert ObjectId to string and format data
        for expense in expenses:
            expense["id"] = str(expense["_id"])
            del expense["_id"]
            
            # Format date
            if expense.get("expense_date"):
                if isinstance(expense["expense_date"], str):
                    # Already a string, keep as is
                    pass
                else:
                    # Convert datetime to string
                    expense["expense_date"] = expense["expense_date"].isoformat()
        
        # Calculate stats
        total_pipeline = [
            {"$group": {"_id": None, "total": {"$sum": "$amount"}}}
        ]
        total_result = await expenses_collection.aggregate(total_pipeline).to_list(1)
        total_amount = total_result[0]["total"] if total_result else 0
        
        # This month stats
        current_month = get_month_start()
        month_pipeline = [
            {"$match": {"expense_date": {"$gte": current_month}}},
            {"$group": {"_id": None, "total": {"$sum": "$amount"}}}
        ]
        month_result = await expenses_collection.aggregate(month_pipeline).to_list(1)
        month_amount = month_result[0]["total"] if month_result else 0
        
        # Pending expenses
        pending_pipeline = [
            {"$match": {"status": "pending"}},
            {"$group": {"_id": None, "total": {"$sum": "$amount"}}}
        ]
        pending_result = await expenses_collection.aggregate(pending_pipeline).to_list(1)
        pending_amount = pending_result[0]["total"] if pending_result else 0
        
        # Categories count
        categories_count = len(await expenses_collection.distinct("category"))
        
        stats = {
            "total": total_amount,
            "month": month_amount,
            "pending": pending_amount,
            "categories": categories_count
        }
        
        return {
            "expenses": expenses,
            "total": total,
            "page": page,
            "size": size,
            "total_pages": (total + size - 1) // size,
            "stats": stats
        }
        
    except Exception as e:
        logger.error(f"Error fetching expenses: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch expenses")

@router.post("/api/expenses/", response_model=dict)
async def create_expense(
    request: Request,
    expense_data: ExpenseCreate,
    user: User = Depends(get_current_user_hybrid)
):
    """Create a new expense"""
    try:
        db = await get_database()
        expenses_collection = db.expenses
        
        # Create expense document
        expense_doc = {
            "description": expense_data.description,
            "category": expense_data.category,
            "amount": expense_data.amount,
            "expense_date": expense_data.expense_date,
            "payment_method": expense_data.payment_method,
            "vendor": expense_data.vendor,
            "notes": expense_data.notes,
            "status": expense_data.status,
            "created_at": kampala_to_utc(now_kampala()),
            "updated_at": kampala_to_utc(now_kampala()),
            "created_by": user.username
        }
        
        result = await expenses_collection.insert_one(expense_doc)
        
        if result.inserted_id:
            return {
                "message": "Expense created successfully",
                "expense_id": str(result.inserted_id)
            }
        else:
            raise HTTPException(status_code=500, detail="Failed to create expense")
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating expense: {e}")
        raise HTTPException(status_code=500, detail="Failed to create expense")

@router.get("/api/expenses/{expense_id}", response_model=dict)
async def get_expense(
    request: Request,
    expense_id: str,
    user: User = Depends(get_current_user_hybrid)
):
    """Get a specific expense by ID"""
    try:
        db = await get_database()
        expenses_collection = db.expenses
        
        expense = await expenses_collection.find_one({"_id": ObjectId(expense_id)})
        
        if not expense:
            raise HTTPException(status_code=404, detail="Expense not found")
        
        # Convert ObjectId to string
        expense["id"] = str(expense["_id"])
        del expense["_id"]
        
        # Format date
        if expense.get("expense_date"):
            if isinstance(expense["expense_date"], str):
                # Already a string, keep as is
                pass
            else:
                # Convert datetime to string
                expense["expense_date"] = expense["expense_date"].isoformat()
        
        return expense
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching expense: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch expense")

@router.put("/api/expenses/{expense_id}", response_model=dict)
async def update_expense(
    request: Request,
    expense_id: str,
    expense_data: ExpenseUpdate,
    user: User = Depends(get_current_user_hybrid)
):
    """Update an expense"""
    try:
        db = await get_database()
        expenses_collection = db.expenses
        
        # Check if expense exists
        existing = await expenses_collection.find_one({"_id": ObjectId(expense_id)})
        if not existing:
            raise HTTPException(status_code=404, detail="Expense not found")
        
        # Build update document
        update_doc = {
            "updated_at": kampala_to_utc(now_kampala()),
            "updated_by": user.username
        }
        
        # Add fields that are being updated
        update_data = expense_data.dict(exclude_unset=True)
        update_doc.update(update_data)
        
        result = await expenses_collection.update_one(
            {"_id": ObjectId(expense_id)},
            {"$set": update_doc}
        )
        
        if result.modified_count > 0:
            return {"message": "Expense updated successfully"}
        else:
            return {"message": "No changes made to expense"}
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating expense: {e}")
        raise HTTPException(status_code=500, detail="Failed to update expense")

@router.delete("/api/expenses/{expense_id}", response_model=dict)
async def delete_expense(
    request: Request,
    expense_id: str,
    user: User = Depends(get_current_user_hybrid)
):
    """Delete an expense"""
    try:
        db = await get_database()
        expenses_collection = db.expenses
        
        # Check if expense exists
        existing = await expenses_collection.find_one({"_id": ObjectId(expense_id)})
        if not existing:
            raise HTTPException(status_code=404, detail="Expense not found")
        
        result = await expenses_collection.delete_one({"_id": ObjectId(expense_id)})
        
        if result.deleted_count > 0:
            return {"message": "Expense deleted successfully"}
        else:
            raise HTTPException(status_code=500, detail="Failed to delete expense")
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting expense: {e}")
        raise HTTPException(status_code=500, detail="Failed to delete expense")

# Expense Categories Endpoints

@router.get("/api/expense-categories/", response_model=dict)
async def get_expense_categories(
    user: User = Depends(get_current_user_hybrid_dependency())
):
    """Get all expense categories"""
    try:
        db = await get_database()
        categories_collection = db.expense_categories

        # Get all active categories
        cursor = categories_collection.find({"is_active": True}).sort("name", 1)
        categories = await cursor.to_list(length=None)

        # Convert ObjectId to string
        for category in categories:
            category["id"] = str(category["_id"])
            del category["_id"]

        return {"categories": categories}

    except Exception as e:
        logger.error(f"Error fetching expense categories: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch expense categories")

@router.post("/api/expense-categories/", response_model=dict)
async def create_expense_category(
    request: Request,
    category_data: ExpenseCategoryCreate,
    user: User = Depends(get_current_user_hybrid)
):
    """Create a new expense category"""
    try:
        db = await get_database()
        categories_collection = db.expense_categories

        # Check if category name already exists
        existing = await categories_collection.find_one({"name": {"$regex": f"^{category_data.name}$", "$options": "i"}})
        if existing:
            raise HTTPException(status_code=400, detail="Category name already exists")

        # Create category document
        category_doc = {
            "name": category_data.name,
            "icon": category_data.icon,
            "is_default": False,
            "is_active": True,
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow(),
            "created_by": user.username
        }

        result = await categories_collection.insert_one(category_doc)

        if result.inserted_id:
            return {
                "message": "Expense category created successfully",
                "category_id": str(result.inserted_id)
            }
        else:
            raise HTTPException(status_code=500, detail="Failed to create expense category")

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating expense category: {e}")
        raise HTTPException(status_code=500, detail="Failed to create expense category")

@router.put("/api/expense-categories/{category_id}", response_model=dict)
async def update_expense_category(
    request: Request,
    category_id: str,
    category_data: ExpenseCategoryUpdate,
    user: User = Depends(get_current_user_hybrid)
):
    """Update an expense category"""
    try:
        db = await get_database()
        categories_collection = db.expense_categories

        # Check if category exists
        existing = await categories_collection.find_one({"_id": ObjectId(category_id)})
        if not existing:
            raise HTTPException(status_code=404, detail="Expense category not found")

        # Don't allow updating default categories
        if existing.get("is_default", False):
            raise HTTPException(status_code=400, detail="Cannot update default categories")

        # Check if new name already exists (if name is being updated)
        if category_data.name and category_data.name != existing["name"]:
            name_exists = await categories_collection.find_one({
                "name": {"$regex": f"^{category_data.name}$", "$options": "i"},
                "_id": {"$ne": ObjectId(category_id)}
            })
            if name_exists:
                raise HTTPException(status_code=400, detail="Category name already exists")

        # Build update document
        update_doc = {
            "updated_at": datetime.utcnow(),
            "updated_by": user.username
        }

        # Add fields that are being updated
        update_data = category_data.dict(exclude_unset=True)
        update_doc.update(update_data)

        result = await categories_collection.update_one(
            {"_id": ObjectId(category_id)},
            {"$set": update_doc}
        )

        if result.modified_count > 0:
            return {"message": "Expense category updated successfully"}
        else:
            return {"message": "No changes made to expense category"}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating expense category: {e}")
        raise HTTPException(status_code=500, detail="Failed to update expense category")

@router.delete("/api/expense-categories/{category_id}", response_model=dict)
async def delete_expense_category(
    request: Request,
    category_id: str,
    user: User = Depends(get_current_user_hybrid)
):
    """Delete an expense category"""
    try:
        db = await get_database()
        categories_collection = db.expense_categories
        expenses_collection = db.expenses

        # Check if category exists
        existing = await categories_collection.find_one({"_id": ObjectId(category_id)})
        if not existing:
            raise HTTPException(status_code=404, detail="Expense category not found")

        # Don't allow deleting default categories
        if existing.get("is_default", False):
            raise HTTPException(status_code=400, detail="Cannot delete default categories")

        # Check if category is being used by any expenses
        expenses_using_category = await expenses_collection.count_documents({"category": existing["name"]})
        if expenses_using_category > 0:
            raise HTTPException(
                status_code=400,
                detail=f"Cannot delete category. It is being used by {expenses_using_category} expense(s)"
            )

        result = await categories_collection.delete_one({"_id": ObjectId(category_id)})

        if result.deleted_count > 0:
            return {"message": "Expense category deleted successfully"}
        else:
            raise HTTPException(status_code=500, detail="Failed to delete expense category")

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting expense category: {e}")
        raise HTTPException(status_code=500, detail="Failed to delete expense category")

@router.get("/debug-dates", response_model=dict)
async def debug_expense_dates(
    request: Request,
    user: User = Depends(get_current_user_hybrid)
):
    """Debug endpoint to check how dates are stored in expenses"""
    try:
        db = await get_database()
        expenses_collection = db.expenses

        # Get a few sample expenses to see date formats
        sample_expenses = await expenses_collection.find({}).limit(5).to_list(length=5)

        date_info = []
        for expense in sample_expenses:
            date_info.append({
                "id": str(expense["_id"]),
                "description": expense.get("description", ""),
                "expense_date": expense.get("expense_date"),
                "expense_date_type": type(expense.get("expense_date")).__name__,
                "expense_date_str": str(expense.get("expense_date"))
            })

        return {
            "sample_expenses": date_info,
            "total_expenses": await expenses_collection.count_documents({})
        }

    except Exception as e:
        return {
            "error": str(e)
        }
