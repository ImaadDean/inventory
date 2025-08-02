from fastapi import APIRouter, HTTPException, status, Depends, Query, Request
from typing import List, Optional
from datetime import datetime
from bson import ObjectId
from ...config.database import get_database
from ...schemas.category import CategoryCreate, CategoryUpdate, CategoryResponse, CategoryStats, CategoryWithChildren
from ...models import Category
from ...utils.auth import get_current_user, verify_token, get_user_by_username
from ...models import User

router = APIRouter(prefix="/api/categories", tags=["Categories API"])


async def get_current_user_hybrid(request: Request) -> User:
    """Get current user from either JWT token or cookie"""

    # Try cookie authentication first (for web interface)
    access_token = request.cookies.get("access_token")
    if access_token:
        try:
            # Handle Bearer prefix in cookie value
            token = access_token
            if access_token.startswith("Bearer "):
                token = access_token[7:]  # Remove "Bearer " prefix

            payload = verify_token(token)
            if payload:
                username = payload.get("sub")
                if username:
                    user = await get_user_by_username(username)
                    if user and user.is_active:
                        return user
        except Exception as e:
            print(f"Cookie auth failed: {e}")

    # Try JWT token authentication (for API clients)
    auth_header = request.headers.get("Authorization")
    if auth_header and auth_header.startswith("Bearer "):
        try:
            token = auth_header.split(" ")[1]
            payload = verify_token(token)
            if payload:
                username = payload.get("sub")
                if username:
                    user = await get_user_by_username(username)
                    if user and user.is_active:
                        return user
        except Exception as e:
            print(f"JWT auth failed: {e}")

    # If both methods fail, raise authentication error
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )


@router.get("/simple", response_model=dict)
async def get_categories_simple():
    """Get simple list of categories for dropdowns"""
    try:
        db = await get_database()

        # Get all active categories
        categories = await db.categories.find(
            {"is_active": True},
            {"name": 1, "_id": 1}
        ).sort("name", 1).to_list(length=None)

        # Convert to simple format
        category_list = []
        for category in categories:
            category_list.append({
                "id": str(category["_id"]),
                "name": category["name"]
            })

        return {
            "categories": category_list,
            "total": len(category_list)
        }

    except Exception as e:
        return {
            "categories": [],
            "total": 0,
            "error": str(e)
        }


@router.get("/stats", response_model=dict)
async def get_category_stats():
    """Get category statistics for dashboard cards"""
    try:
        db = await get_database()

        # Get total categories count
        total_categories = await db.categories.count_documents({})

        # Get active categories count
        active_categories = await db.categories.count_documents({"is_active": True})

        # Get parent categories count (categories without parent_id)
        parent_categories = await db.categories.count_documents({
            "$or": [
                {"parent_id": {"$exists": False}},
                {"parent_id": None}
            ]
        })

        # Get subcategories count (categories with parent_id)
        subcategories = await db.categories.count_documents({
            "parent_id": {"$exists": True, "$ne": None}
        })

        # Get total products count across all categories
        total_products = await db.products.count_documents({"is_active": True})

        # Calculate categories with products
        categories_with_products = await db.categories.aggregate([
            {
                "$lookup": {
                    "from": "products",
                    "localField": "_id",
                    "foreignField": "category_id",
                    "as": "products"
                }
            },
            {
                "$match": {
                    "products": {"$ne": []}  # Categories that have at least one product
                }
            },
            {
                "$count": "categories_with_products"
            }
        ]).to_list(length=1)

        categories_with_products_count = categories_with_products[0]["categories_with_products"] if categories_with_products else 0

        return {
            "total_categories": total_categories,
            "active_categories": active_categories,
            "parent_categories": parent_categories,
            "subcategories": subcategories,
            "total_products": total_products,
            "categories_with_products": categories_with_products_count,
            "empty_categories": total_categories - categories_with_products_count
        }

    except Exception as e:
        print(f"Error getting category stats: {e}")
        return {
            "total_categories": 0,
            "active_categories": 0,
            "parent_categories": 0,
            "subcategories": 0,
            "error": str(e)
        }


async def get_current_user_hybrid(request: Request) -> User:
    """Get current user from either JWT token or cookie"""

    # Try cookie authentication first (for web interface)
    access_token = request.cookies.get("access_token")
    if access_token:
        try:
            # Handle Bearer prefix in cookie value
            token = access_token
            if access_token.startswith("Bearer "):
                token = access_token[7:]  # Remove "Bearer " prefix

            payload = verify_token(token)
            if payload:
                username = payload.get("sub")
                if username:
                    user = await get_user_by_username(username)
                    if user and user.is_active:
                        return user
        except Exception as e:
            print(f"Cookie auth failed: {e}")

    # Try JWT token authentication (for API clients)
    auth_header = request.headers.get("Authorization")
    if auth_header and auth_header.startswith("Bearer "):
        try:
            token = auth_header.split(" ")[1]
            payload = verify_token(token)
            if payload:
                username = payload.get("sub")
                if username:
                    user = await get_user_by_username(username)
                    if user and user.is_active:
                        return user
        except Exception as e:
            print(f"JWT auth failed: {e}")

    # If both methods fail, raise authentication error
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )


@router.get("/auth-test", response_model=dict)
async def test_authentication(request: Request, current_user: User = Depends(get_current_user_hybrid)):
    """Test endpoint to verify authentication is working"""
    return {
        "authenticated": True,
        "user": {
            "username": current_user.username,
            "email": current_user.email,
            "role": current_user.role,
            "is_active": current_user.is_active
        },
        "message": "Authentication successful!"
    }


@router.post("/", response_model=CategoryResponse, status_code=status.HTTP_201_CREATED)
async def create_category(
    category_data: CategoryCreate,
    request: Request,
    current_user: User = Depends(get_current_user_hybrid)
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


@router.put("/{category_id}", response_model=dict)
async def update_category(
    category_id: str,
    category_update: CategoryUpdate,
    request: Request,
    current_user: User = Depends(get_current_user_hybrid)
):
    """Update a category"""
    try:
        db = await get_database()

        # Validate category ID
        if not ObjectId.is_valid(category_id):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid category ID"
            )

        # Check if category exists
        existing_category = await db.categories.find_one({"_id": ObjectId(category_id)})
        if not existing_category:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Category not found"
            )

        # Prepare update data
        update_data = {}
        if category_update.name is not None:
            # Check if name already exists (excluding current category)
            existing_name = await db.categories.find_one({
                "name": category_update.name,
                "_id": {"$ne": ObjectId(category_id)}
            })
            if existing_name:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Category name already exists"
                )
            update_data["name"] = category_update.name

        if category_update.description is not None:
            update_data["description"] = category_update.description

        if category_update.parent_id is not None:
            # Validate parent category exists
            if category_update.parent_id:
                parent_exists = await db.categories.find_one({"_id": ObjectId(category_update.parent_id)})
                if not parent_exists:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail="Parent category not found"
                    )
                # Prevent circular reference
                if str(category_update.parent_id) == category_id:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail="Category cannot be its own parent"
                    )
            update_data["parent_id"] = ObjectId(category_update.parent_id) if category_update.parent_id else None

        if category_update.is_active is not None:
            update_data["is_active"] = category_update.is_active

        # Add updated timestamp
        update_data["updated_at"] = datetime.utcnow()

        # Update the category
        result = await db.categories.update_one(
            {"_id": ObjectId(category_id)},
            {"$set": update_data}
        )

        if result.modified_count == 0:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to update category"
            )

        # Get updated category
        updated_category = await db.categories.find_one({"_id": ObjectId(category_id)})

        return {
            "success": True,
            "message": "Category updated successfully",
            "category": {
                "id": str(updated_category["_id"]),
                "name": updated_category["name"],
                "description": updated_category.get("description"),
                "parent_id": str(updated_category["parent_id"]) if updated_category.get("parent_id") else None,
                "is_active": updated_category["is_active"],
                "updated_at": updated_category["updated_at"].isoformat()
            }
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update category: {str(e)}"
        )


@router.delete("/{category_id}", response_model=dict)
async def delete_category(
    category_id: str,
    request: Request,
    current_user: User = Depends(get_current_user_hybrid)
):
    """Delete a category"""
    try:
        db = await get_database()

        # Validate category ID
        if not ObjectId.is_valid(category_id):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid category ID"
            )

        # Check if category exists
        category = await db.categories.find_one({"_id": ObjectId(category_id)})
        if not category:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Category not found"
            )

        # Check if category has products
        products_count = await db.products.count_documents({"category_id": ObjectId(category_id)})
        if products_count > 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Cannot delete category. It has {products_count} products assigned to it. Please reassign or delete the products first."
            )

        # Check if category has subcategories
        subcategories_count = await db.categories.count_documents({"parent_id": ObjectId(category_id)})
        if subcategories_count > 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Cannot delete category. It has {subcategories_count} subcategories. Please delete or reassign the subcategories first."
            )

        # Delete the category
        result = await db.categories.delete_one({"_id": ObjectId(category_id)})

        if result.deleted_count == 0:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to delete category"
            )

        return {
            "success": True,
            "message": f"Category '{category['name']}' deleted successfully",
            "deleted_category": {
                "id": category_id,
                "name": category["name"]
            }
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete category: {str(e)}"
        )


@router.get("/", response_model=dict)
async def get_categories(
    request: Request,
    skip: int = Query(0, ge=0, description="Number of categories to skip"),
    limit: int = Query(100, ge=1, le=1000, description="Number of categories to return"),
    active_only: bool = Query(True, description="Return only active categories"),
    parent_id: Optional[str] = Query(None, description="Filter by parent category ID"),
    search: Optional[str] = Query(None, description="Search term for category name or description"),
    status: Optional[str] = Query(None, description="Filter by status: active, inactive"),
    type: Optional[str] = Query(None, description="Filter by type: parent, child")
):
    """Get all categories with optional filtering"""
    try:
        # TODO: Add proper authentication
        # For now, skip authentication since web interface handles it

        db = await get_database()

        # Build filter
        filter_dict = {}

        # Handle status filter
        if status == "active":
            filter_dict["is_active"] = True
        elif status == "inactive":
            filter_dict["is_active"] = False
        elif active_only and not status:
            filter_dict["is_active"] = True

        # Handle type filter
        if type == "parent":
            filter_dict["$or"] = [
                {"parent_id": {"$exists": False}},
                {"parent_id": None}
            ]
        elif type == "child":
            filter_dict["parent_id"] = {"$exists": True, "$ne": None}

        # Handle parent_id filter (for hierarchical filtering)
        if parent_id:
            filter_dict["parent_id"] = parent_id

        # Handle search filter
        if search:
            search_regex = {"$regex": search, "$options": "i"}
            filter_dict["$or"] = [
                {"name": search_regex},
                {"description": search_regex}
            ]

        # Get categories with product counts using aggregation
        pipeline = [
            {"$match": filter_dict},
            {"$sort": {"name": 1}},
            {"$skip": skip},
            {"$limit": limit},
            {
                "$lookup": {
                    "from": "products",
                    "localField": "_id",
                    "foreignField": "category_id",
                    "as": "products"
                }
            },
            {
                "$addFields": {
                    "product_count": {"$size": "$products"}
                }
            },
            {
                "$project": {
                    "products": 0  # Remove the products array, keep only the count
                }
            }
        ]

        categories = await db.categories.aggregate(pipeline).to_list(length=limit)
        total = await db.categories.count_documents(filter_dict)

        # Convert to response format
        category_responses = []
        for category in categories:
            category_responses.append({
                "id": str(category["_id"]),
                "name": category["name"],
                "description": category.get("description"),
                "parent_id": str(category["parent_id"]) if category.get("parent_id") else None,
                "parent_name": None,  # TODO: Implement parent name lookup
                "product_count": category.get("product_count", 0),
                "is_active": category["is_active"],
                "created_at": category["created_at"].isoformat(),
                "updated_at": category.get("updated_at", category["created_at"]).isoformat(),
                "created_by": category.get("created_by")
            })

        return {
            "categories": category_responses,
            "total": total,
            "skip": skip,
            "limit": limit
        }

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve categories: {str(e)}"
        )


@router.get("/{category_id}", response_model=dict)
async def get_category(category_id: str):
    """Get a single category by ID"""
    try:
        db = await get_database()

        # Validate category ID
        if not ObjectId.is_valid(category_id):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid category ID"
            )

        # Get category with product count
        pipeline = [
            {"$match": {"_id": ObjectId(category_id)}},
            {
                "$lookup": {
                    "from": "products",
                    "localField": "_id",
                    "foreignField": "category_id",
                    "as": "products"
                }
            },
            {
                "$addFields": {
                    "product_count": {"$size": "$products"}
                }
            },
            {
                "$project": {
                    "products": 0  # Remove the products array, keep only the count
                }
            }
        ]

        categories = await db.categories.aggregate(pipeline).to_list(length=1)

        if not categories:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Category not found"
            )

        category = categories[0]

        return {
            "id": str(category["_id"]),
            "name": category["name"],
            "description": category.get("description"),
            "parent_id": str(category["parent_id"]) if category.get("parent_id") else None,
            "product_count": category.get("product_count", 0),
            "is_active": category["is_active"],
            "created_at": category["created_at"].isoformat(),
            "updated_at": category.get("updated_at", category["created_at"]).isoformat(),
            "created_by": category.get("created_by")
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve category: {str(e)}"
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


