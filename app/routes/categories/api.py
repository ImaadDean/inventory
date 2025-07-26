from fastapi import APIRouter, HTTPException, status, Depends, Query
from typing import List, Optional
from datetime import datetime
from ...config.database import get_database
from ...schemas.category import CategoryCreate, CategoryUpdate, CategoryResponse, CategoryStats, CategoryWithChildren
from ...models import Category
from ...utils.auth import get_current_user
from ...models import User

router = APIRouter(prefix="/api/categories", tags=["Categories API"])


@router.post("/", response_model=CategoryResponse, status_code=status.HTTP_201_CREATED)
async def create_category(
    category_data: CategoryCreate,
    current_user: User = Depends(get_current_user)
):
    """Create a new category"""
    try:
        db = await get_database()
        
        # Check if category name already exists
        existing_category = await db.categories.find_one({"name": category_data.name})
        if existing_category:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Category with this name already exists"
            )
        
        # If parent_id is provided, verify parent exists
        if category_data.parent_id:
            parent_category = await db.categories.find_one({"_id": category_data.parent_id})
            if not parent_category:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Parent category not found"
                )
        
        # Create category
        category = Category(**category_data.model_dump())
        result = await db.categories.insert_one(category.model_dump(by_alias=True, exclude={"id"}))
        
        # Retrieve created category
        created_category = await db.categories.find_one({"_id": result.inserted_id})
        return CategoryResponse(**created_category)
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create category: {str(e)}"
        )


@router.get("/", response_model=List[CategoryResponse])
async def get_categories(
    skip: int = Query(0, ge=0, description="Number of categories to skip"),
    limit: int = Query(100, ge=1, le=1000, description="Number of categories to return"),
    active_only: bool = Query(True, description="Return only active categories"),
    parent_id: Optional[str] = Query(None, description="Filter by parent category ID"),
    current_user: User = Depends(get_current_user)
):
    """Get all categories with optional filtering"""
    try:
        db = await get_database()
        
        # Build filter
        filter_dict = {}
        if active_only:
            filter_dict["is_active"] = True
        if parent_id:
            filter_dict["parent_id"] = parent_id
        
        # Get categories
        cursor = db.categories.find(filter_dict).skip(skip).limit(limit).sort("name", 1)
        categories = await cursor.to_list(length=limit)
        
        return [CategoryResponse(**category) for category in categories]
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve categories: {str(e)}"
        )


@router.get("/stats", response_model=CategoryStats)
async def get_category_stats(current_user: User = Depends(get_current_user)):
    """Get category statistics"""
    try:
        db = await get_database()
        
        # Get category counts
        total_categories = await db.categories.count_documents({})
        active_categories = await db.categories.count_documents({"is_active": True})
        inactive_categories = total_categories - active_categories
        
        # Get categories with products (this would require joining with products collection)
        # For now, we'll set it to 0 - this can be implemented later
        categories_with_products = 0
        
        return CategoryStats(
            total_categories=total_categories,
            active_categories=active_categories,
            inactive_categories=inactive_categories,
            categories_with_products=categories_with_products
        )
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve category statistics: {str(e)}"
        )


@router.get("/tree", response_model=List[CategoryWithChildren])
async def get_category_tree(current_user: User = Depends(get_current_user)):
    """Get categories in a hierarchical tree structure"""
    try:
        db = await get_database()
        
        # Get all active categories
        categories = await db.categories.find({"is_active": True}).sort("name", 1).to_list(length=None)
        
        # Build tree structure
        category_dict = {str(cat["_id"]): CategoryWithChildren(**cat) for cat in categories}
        root_categories = []
        
        for category in category_dict.values():
            if category.parent_id:
                parent_id = str(category.parent_id)
                if parent_id in category_dict:
                    category_dict[parent_id].children.append(category)
            else:
                root_categories.append(category)
        
        return root_categories
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve category tree: {str(e)}"
        )


@router.get("/{category_id}", response_model=CategoryResponse)
async def get_category(
    category_id: str,
    current_user: User = Depends(get_current_user)
):
    """Get a specific category by ID"""
    try:
        db = await get_database()
        
        category = await db.categories.find_one({"_id": category_id})
        if not category:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Category not found"
            )
        
        return CategoryResponse(**category)
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve category: {str(e)}"
        )


@router.put("/{category_id}", response_model=CategoryResponse)
async def update_category(
    category_id: str,
    category_data: CategoryUpdate,
    current_user: User = Depends(get_current_user)
):
    """Update a category"""
    try:
        db = await get_database()
        
        # Check if category exists
        existing_category = await db.categories.find_one({"_id": category_id})
        if not existing_category:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Category not found"
            )
        
        # Check if new name already exists (if name is being updated)
        if category_data.name and category_data.name != existing_category["name"]:
            name_exists = await db.categories.find_one({
                "name": category_data.name,
                "_id": {"$ne": category_id}
            })
            if name_exists:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Category with this name already exists"
                )
        
        # If parent_id is being updated, verify parent exists
        if category_data.parent_id:
            parent_category = await db.categories.find_one({"_id": category_data.parent_id})
            if not parent_category:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Parent category not found"
                )
        
        # Update category
        update_data = category_data.model_dump(exclude_unset=True)
        update_data["updated_at"] = datetime.utcnow()
        
        await db.categories.update_one(
            {"_id": category_id},
            {"$set": update_data}
        )
        
        # Return updated category
        updated_category = await db.categories.find_one({"_id": category_id})
        return CategoryResponse(**updated_category)
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update category: {str(e)}"
        )


@router.delete("/{category_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_category(
    category_id: str,
    current_user: User = Depends(get_current_user)
):
    """Delete a category (soft delete by setting is_active to False)"""
    try:
        db = await get_database()
        
        # Check if category exists
        category = await db.categories.find_one({"_id": category_id})
        if not category:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Category not found"
            )
        
        # Check if category has child categories
        child_categories = await db.categories.find_one({"parent_id": category_id, "is_active": True})
        if child_categories:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot delete category that has active child categories"
            )
        
        # Soft delete (set is_active to False)
        await db.categories.update_one(
            {"_id": category_id},
            {"$set": {"is_active": False, "updated_at": datetime.utcnow()}}
        )
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete category: {str(e)}"
        )
