from fastapi import APIRouter, HTTPException, status, Depends, Query, Request, UploadFile, File
from typing import Optional
from datetime import datetime
from bson import ObjectId
from ...config.database import get_database
from ...config.cloudinary_config import CloudinaryService
from ...schemas.product import (
    CategoryCreate, CategoryUpdate, CategoryResponse,
    ProductCreate, ProductUpdate, ProductResponse, ProductList, StockUpdate
)
from ...models import Product, Category, User
from ...models.product_supplier_price import ProductSupplierPriceCreate
from ...services.product_supplier_price_service import ProductSupplierPriceService
from ...utils.auth import require_admin_or_inventory, get_current_user, get_current_user_hybrid, get_current_user_hybrid_dependency, verify_token, get_user_by_username
from ...utils.expense_categories_init import create_restocking_expense, create_stocking_expense
from ...utils.timezone import now_kampala, kampala_to_utc
from ...utils.decant_handler import calculate_decant_availability, open_new_bottle_for_decants

router = APIRouter(prefix="/api/products", tags=["Product Management API"])


async def get_product_scents(db, product):
    """Helper function to get scent information for a product"""
    scents_info = []
    if product.get("scent_ids"):
        # Get scent details for multiple scents
        scent_ids = product["scent_ids"]
        if scent_ids:
            scents = await db.scents.find({"_id": {"$in": scent_ids}}).to_list(length=None)
            scents_info = [{"id": str(scent["_id"]), "name": scent["name"]} for scent in scents]
    elif product.get("scent_id"):
        # Handle single scent for backward compatibility
        scent = await db.scents.find_one({"_id": product["scent_id"]})
        if scent:
            scents_info = [{"id": str(scent["_id"]), "name": scent["name"]}]

    return scents_info





@router.get("/stats", response_model=dict)
async def get_product_stats(
    current_user: User = Depends(get_current_user_hybrid_dependency())
):
    """Get product statistics for dashboard cards"""
    db = await get_database()

    # Get total products count
    total_products = await db.products.count_documents({"is_active": True})

    # Get in stock products (stock > 0)
    in_stock = await db.products.count_documents({
        "is_active": True,
        "stock_quantity": {"$gt": 0}
    })

    # Get low stock products using proper MongoDB query
    low_stock = await db.products.count_documents({
        "is_active": True,
        "stock_quantity": {"$gt": 0},
        "$expr": {"$lte": ["$stock_quantity", {"$ifNull": ["$min_stock_level", 10]}]}
    })

    # Get out of stock products (stock = 0)
    out_of_stock = await db.products.count_documents({
        "is_active": True,
        "stock_quantity": 0
    })

    return {
        "total_products": total_products,
        "in_stock": in_stock,
        "low_stock": low_stock,
        "out_of_stock": out_of_stock
    }


@router.get("/suppliers/dropdown", response_model=dict)
async def get_suppliers_dropdown():
    """Get simple list of active suppliers for dropdowns - no auth required"""
    try:
        db = await get_database()
        suppliers_collection = db.suppliers

        # Get all suppliers first to see what we have
        all_suppliers = await suppliers_collection.find({}).to_list(length=None)

        # If no suppliers exist, return empty list
        if not all_suppliers:
            return {
                "suppliers": [],
                "total": 0
            }

        # Get only active suppliers with basic info
        cursor = suppliers_collection.find(
            {"is_active": True}
        ).sort("name", 1)

        suppliers = await cursor.to_list(length=None)

        # Format for dropdown
        suppliers_list = []
        for supplier in suppliers:
            suppliers_list.append({
                "id": str(supplier["_id"]),
                "name": supplier.get("name", "Unknown Supplier")
            })

        return {
            "suppliers": suppliers_list,
            "total": len(suppliers_list)
        }

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch suppliers: {str(e)}"
        )


async def update_supplier_on_restock(db, supplier_name: str, product_id: str, product_name: str):
    """Update supplier information when a product is restocked and return supplier ID"""
    try:
        suppliers_collection = db.suppliers

        # Find the supplier by name (case-insensitive)
        supplier = await suppliers_collection.find_one({
            "name": {"$regex": f"^{supplier_name}$", "$options": "i"}
        })

        if not supplier:
            # If supplier doesn't exist, create a basic supplier record
            supplier_doc = {
                "name": supplier_name,
                "contact_person": None,
                "phone": None,
                "email": None,
                "address": None,
                "notes": f"Auto-created from product restocking",
                "is_active": True,
                "created_at": kampala_to_utc(now_kampala()),
                "updated_at": kampala_to_utc(now_kampala()),
                "created_by": "system",
                "products": [product_id],
                "last_order_date": kampala_to_utc(now_kampala()),
                "total_orders": 1
            }

            result = await suppliers_collection.insert_one(supplier_doc)
            if result.inserted_id:
                print(f"Created new supplier: {supplier_name}")
                return result.inserted_id
        else:
            # Update existing supplier
            supplier_id = supplier["_id"]
            current_products = supplier.get("products", [])

            # Add product to supplier's product list if not already there
            if product_id not in current_products:
                current_products.append(product_id)

            # Update supplier with new product and last order date
            update_doc = {
                "products": current_products,
                "last_order_date": kampala_to_utc(now_kampala()),
                "total_orders": supplier.get("total_orders", 0) + 1,
                "updated_at": kampala_to_utc(now_kampala())
            }

            await suppliers_collection.update_one(
                {"_id": supplier_id},
                {"$set": update_doc}
            )

            print(f"Updated supplier {supplier_name} with product {product_name}")
            return supplier_id

    except Exception as e:
        print(f"Error updating supplier on restock: {e}")
        # Don't raise exception as this is supplementary functionality
        return None


@router.get("/check-name/{name}", response_model=dict)
async def check_product_name(name: str):
    """Check if a product name already exists"""
    db = await get_database()
    product = await db.products.find_one({"name": {"$regex": f"^{name}$", "$options": "i"}})
    return {"exists": product is not None}


@router.post("/", response_model=dict)
async def create_product_api(
    product_data: ProductCreate,
    request: Request = None,
    current_user: User = Depends(get_current_user_hybrid_dependency())
):
    """Create a new product via API"""
    try:
        db = await get_database()

        # Check if product with the same name already exists
        if not product_data.force:
            existing_product = await db.products.find_one({"name": {"$regex": f"^{product_data.name}$", "$options": "i"}})
            if existing_product:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=f"Product with name '{product_data.name}' already exists. Do you want to create it anyway?"
                )

        # Validate category exists if provided
        if product_data.category_id:
            if not ObjectId.is_valid(product_data.category_id):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Invalid category ID"
                )

            category = await db.categories.find_one({"_id": ObjectId(product_data.category_id)})
            if not category:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Category not found"
                )



        # Create product document
        product_doc = {
            "name": product_data.name,
            "description": product_data.description,
            "barcode": product_data.barcode,
            "category_id": ObjectId(product_data.category_id) if product_data.category_id else None,
            "price": product_data.price,
            "cost_price": product_data.cost_price,
            "stock_quantity": product_data.stock_quantity,
            "min_stock_level": product_data.min_stock_level,
            "unit": product_data.unit,
            "supplier": product_data.supplier,
            "brand": product_data.brand,
            "is_active": True,
            "created_at": now_kampala(),
            "updated_at": None
        }

        # Handle perfume-specific fields
        if product_data.bottle_size_ml:
            product_doc["bottle_size_ml"] = product_data.bottle_size_ml

        # Handle decant information
        if product_data.decant:
            product_doc["decant"] = product_data.decant.model_dump()

        # Handle scent associations
        if product_data.scent_ids and len(product_data.scent_ids) > 0:
            # Filter out empty strings and validate scent IDs
            valid_scent_ids = [scent_id for scent_id in product_data.scent_ids if scent_id and scent_id.strip()]

            if valid_scent_ids:
                # Validate all scent IDs exist and convert to ObjectIds
                scent_object_ids = []
                for scent_id in valid_scent_ids:
                    if ObjectId.is_valid(scent_id):
                        scent_object_id = ObjectId(scent_id)
                        # Verify scent exists
                        scent = await db.scents.find_one({"_id": scent_object_id})
                        if scent:
                            scent_object_ids.append(scent_object_id)

                if scent_object_ids:
                    # Store scent IDs as ObjectIds
                    product_doc["scent_ids"] = scent_object_ids
                    # For backward compatibility, also store the first scent as scent_id
                    product_doc["scent_id"] = scent_object_ids[0]

        # Handle watch settings
        if any([product_data.material_id, product_data.movement_type_id, product_data.gender_id, product_data.color_id]):
            watch_data = {}
            
            # Handle material
            if product_data.material_id:
                if ObjectId.is_valid(product_data.material_id):
                    material = await db.watch_materials.find_one({"_id": ObjectId(product_data.material_id)})
                    if material:
                        watch_data["material"] = {
                            "_id": ObjectId(product_data.material_id),
                            "name": material["name"]
                        }
            
            # Handle movement type
            if product_data.movement_type_id:
                if ObjectId.is_valid(product_data.movement_type_id):
                    movement_type = await db.watch_movement_types.find_one({"_id": ObjectId(product_data.movement_type_id)})
                    if movement_type:
                        watch_data["movement_type"] = {
                            "_id": ObjectId(product_data.movement_type_id),
                            "name": movement_type["name"]
                        }
            
            # Handle gender
            if product_data.gender_id:
                if ObjectId.is_valid(product_data.gender_id):
                    gender = await db.watch_genders.find_one({"_id": ObjectId(product_data.gender_id)})
                    if gender:
                        watch_data["gender"] = {
                            "_id": ObjectId(product_data.gender_id),
                            "name": gender["name"]
                        }
            
            # Handle color
            if product_data.color_id:
                if ObjectId.is_valid(product_data.color_id):
                    color = await db.watch_colors.find_one({"_id": ObjectId(product_data.color_id)})
                    if color:
                        watch_data["color"] = {
                            "_id": ObjectId(product_data.color_id),
                            "name": color["name"]
                        }
            
            if watch_data:
                product_doc["watch"] = watch_data

        # Insert product
        result = await db.products.insert_one(product_doc)

        if not result.inserted_id:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to create product"
            )

        product_id = str(result.inserted_id)

        # Handle supplier and pricing information (similar to restocking)
        supplier_id = None
        expense_id = None

        if product_data.supplier and product_data.cost_price and product_data.cost_price > 0:
            # Update supplier information
            supplier_id = await update_supplier_on_restock(
        db=db,
        supplier_name=product_data.supplier,
        product_id=product_id,
        product_name=product_data.name
    )

            # Create expense record for initial stock
            if product_data.stock_quantity > 0:
                total_cost = product_data.cost_price * product_data.stock_quantity
                expense_id = await create_stocking_expense(
                    db=db,
                    product_name=product_data.name,
                    quantity=product_data.stock_quantity,
                    unit_cost=product_data.cost_price,
                    total_cost=total_cost,
                    supplier_name=product_data.supplier,
                    user_username=current_user.username,
                    payment_method=product_data.payment_method
                )

            # Create price record for supplier pricing history
            if supplier_id and product_data.stock_quantity > 0:
                try:
                    price_service = ProductSupplierPriceService(db)
                    total_cost = product_data.cost_price * product_data.stock_quantity

                    price_record = ProductSupplierPriceCreate(
                        product_id=product_id,
                        supplier_id=str(supplier_id),
                        unit_cost=product_data.cost_price,
                        quantity_restocked=product_data.stock_quantity,
                        total_cost=total_cost,
                        restock_date=kampala_to_utc(now_kampala()),
                        expense_id=expense_id,
                        notes="Initial stock - Product creation"
                    )

                    await price_service.create_price_record(price_record)
                    print(f"✅ Created initial price record: {product_data.supplier} - UGX {product_data.cost_price}")

                except Exception as e:
                    print(f"⚠️ Failed to create price record: {e}")
                    # Don't fail the entire product creation if price record fails

        return {
            "success": True,
            "message": "Product created successfully with supplier and pricing information",
            "product_id": product_id,
            "supplier_updated": supplier_id is not None,
            "expense_created": expense_id is not None
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create product: {str(e)}"
        )


@router.post("/{product_id}/upload-image", response_model=dict)
async def upload_product_image(
    product_id: str,
    file: UploadFile = File(...),
    request: Request = None,
    current_user: User = Depends(get_current_user_hybrid_dependency())
):
    """Upload an image for a product"""
    try:
        db = await get_database()

        # Validate product ID
        if not ObjectId.is_valid(product_id):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid product ID"
            )

        # Check if product exists
        product = await db.products.find_one({"_id": ObjectId(product_id)})
        if not product:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Product not found"
            )

        # Delete existing image if it exists
        if product.get("image_public_id"):
            CloudinaryService.delete_image(product["image_public_id"])

        # Upload new image
        image_data = await CloudinaryService.upload_product_image(file, product_id)

        # Update product with image information
        update_result = await db.products.update_one(
            {"_id": ObjectId(product_id)},
            {"$set": {
                "image_public_id": image_data["public_id"],
                "image_url": image_data["url"],
                "updated_at": now_kampala()
            }}
        )

        if update_result.modified_count == 0:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to update product with image information"
            )

        return {
            "success": True,
            "message": "Image uploaded successfully",
            "image_data": image_data
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to upload image: {str(e)}"
        )


@router.delete("/{product_id}/image", response_model=dict)
async def delete_product_image(
    product_id: str,
    request: Request = None,
    current_user: User = Depends(get_current_user_hybrid_dependency())
):
    """Delete a product's image"""
    try:
        db = await get_database()

        # Validate product ID
        if not ObjectId.is_valid(product_id):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid product ID"
            )

        # Get product
        product = await db.products.find_one({"_id": ObjectId(product_id)})
        if not product:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Product not found"
            )

        # Delete image from Cloudinary if it exists
        if product.get("image_public_id"):
            CloudinaryService.delete_image(product["image_public_id"])

        # Remove image information from product
        update_result = await db.products.update_one(
            {"_id": ObjectId(product_id)},
            {"$unset": {
                "image_public_id": "",
                "image_url": ""
            },
            "$set": {
                "updated_at": now_kampala()
            }}
        )

        if update_result.modified_count == 0:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to remove image information from product"
            )

        return {
            "success": True,
            "message": "Image deleted successfully"
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete image: {str(e)}"
        )


@router.get("/auth-test", response_model=dict)
async def test_authentication(request: Request, current_user: User = Depends(get_current_user_hybrid_dependency())):
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

@router.get("/debug-supplier", response_model=dict)
async def debug_supplier_products(
    request: Request,
    supplier: str = Query(...),
    current_user: User = Depends(get_current_user_hybrid_dependency())
):
    """Debug endpoint to check supplier product matching"""
    try:
        db = await get_database()

        # Get all products to see what suppliers exist
        all_products = await db.products.find({}).to_list(length=None)
        supplier_names = set()
        for product in all_products:
            if product.get('supplier'):
                supplier_names.add(product['supplier'])

        # Test the exact query that would be used
        filter_query = {"supplier": {"$regex": f"^{supplier}$", "$options": "i"}}
        matching_products = await db.products.find(filter_query).to_list(length=None)

        return {
            "requested_supplier": supplier,
            "all_supplier_names": list(supplier_names),
            "filter_query": filter_query,
            "matching_products_count": len(matching_products),
            "matching_products": [
                {
                    "name": p["name"],
                    "supplier": p.get("supplier", "None"),
                    "active": p.get("is_active", True)
                }
                for p in matching_products
            ]
        }
    except Exception as e:
        return {
            "error": str(e),
            "requested_supplier": supplier
        }

@router.post("/fix-supplier-links", response_model=dict)
async def fix_supplier_product_links(
    request: Request,
    current_user: User = Depends(get_current_user_hybrid_dependency())
):
    """Fix products that should be linked to suppliers but aren't"""
    try:
        db = await get_database()

        # Get all suppliers
        suppliers = await db.suppliers.find({}).to_list(length=None)
        fixed_count = 0

        for supplier in suppliers:
            supplier_name = supplier["name"]

            # Find products in restock_history that were restocked with this supplier
            # but don't have the supplier field set
            restock_records = await db.restock_history.find({
                "supplier_name": supplier_name
            }).to_list(length=None)

            product_ids_to_fix = set()
            for record in restock_records:
                product_id = record.get("product_id")
                if product_id:
                    # Check if the product exists and doesn't have supplier set
                    product = await db.products.find_one({"_id": product_id})
                    if product and not product.get("supplier"):
                        product_ids_to_fix.add(product_id)

            # Update products to set the supplier field
            if product_ids_to_fix:
                result = await db.products.update_many(
                    {"_id": {"$in": list(product_ids_to_fix)}},
                    {
                        "$set": {
                            "supplier": supplier_name,
                            "updated_at": kampala_to_utc(now_kampala())
                        }
                    }
                )
                fixed_count += result.modified_count

        return {
            "success": True,
            "message": f"Fixed {fixed_count} product-supplier links",
            "fixed_count": fixed_count
        }

    except Exception as e:
        return {
            "success": False,
            "error": str(e)
        }


@router.get("/", response_model=dict)
async def get_products(
    page: int = Query(1, ge=1),
    size: int = Query(10, ge=1, le=1000),
    search: Optional[str] = Query(None),
    category_id: Optional[str] = Query(None),
    stock_status: Optional[str] = Query(None),  # "in-stock", "low-stock", "out-of-stock"
    is_active: Optional[bool] = Query(None),
    low_stock_only: Optional[bool] = Query(False),
    supplier: Optional[str] = Query(None),  # Filter by supplier name
    current_user: User = Depends(get_current_user_hybrid_dependency())
):
    """Get all products with pagination and filtering"""
    try:
        db = await get_database()

        # Build filter query
        filter_query = {}
        if search:
            filter_query["$or"] = [
                {"name": {"$regex": search, "$options": "i"}},
                {"barcode": {"$regex": search, "$options": "i"}},
                {"supplier": {"$regex": search, "$options": "i"}}
            ]
        if category_id and ObjectId.is_valid(category_id):
            filter_query["category_id"] = ObjectId(category_id)
        if is_active is not None:
            filter_query["is_active"] = is_active
        if supplier:
            # Filter by supplier name (case-insensitive)
            filter_query["supplier"] = {"$regex": f"^{supplier}$", "$options": "i"}

        # Handle stock status filtering
        if stock_status == "in-stock":
            # Products with stock > min_stock_level
            filter_query["stock_quantity"] = {"$gt": 0}
            filter_query["$expr"] = {"$gt": ["$stock_quantity", {"$ifNull": ["$min_stock_level", 10]}]}
        elif stock_status == "low-stock":
            # Products with 0 < stock <= min_stock_level
            filter_query["stock_quantity"] = {"$gt": 0}
            filter_query["$expr"] = {"$lte": ["$stock_quantity", {"$ifNull": ["$min_stock_level", 10]}]}
        elif stock_status == "out-of-stock":
            filter_query["stock_quantity"] = 0

        # Legacy support for low_stock_only parameter
        if low_stock_only:
            filter_query["stock_quantity"] = {"$gt": 0}
            filter_query["$expr"] = {"$lte": ["$stock_quantity", {"$ifNull": ["$min_stock_level", 10]}]}

        # Get total count
        total = await db.products.count_documents(filter_query)

        # Get products with pagination
        skip = (page - 1) * size
        pipeline = [
            {"$match": filter_query},
            {"$lookup": {
                "from": "categories",
                "localField": "category_id",
                "foreignField": "_id",
                "as": "category"
            }},
            {"$sort": {"created_at": -1}},
            {"$skip": skip},
            {"$limit": size}
        ]

        cursor = db.products.aggregate(pipeline)
        products_data = await cursor.to_list(length=size)

        products = []
        for product in products_data:
            try:
                category_name = product["category"][0]["name"] if product.get("category") else "No Category"

                # Calculate profit margin
                profit_margin = None
                cost_price = product.get("cost_price")
                price = product.get("price")
                if cost_price and price and cost_price > 0:
                    profit_margin = ((price - cost_price) / cost_price) * 100

                # Determine stock status (Low stock if below min_stock_level)
                min_stock_level = product.get("min_stock_level", 10)  # Default to 10 if not set
                stock_quantity = product.get("stock_quantity", 0)
                is_low_stock = stock_quantity <= min_stock_level and stock_quantity > 0
                stock_status = "out-of-stock" if stock_quantity == 0 else ("low-stock" if is_low_stock else "in-stock")

                # Calculate perfume-specific fields
                decant_info = calculate_decant_availability(product)

                # Determine stock display format
                stock_display = str(stock_quantity)
                if decant_info.get("is_decantable"):
                    opened_ml = decant_info.get("opened_bottle_ml_left", 0)
                    stock_display = f"{stock_quantity} pcs & {opened_ml}mls"
                else:
                    stock_display = f"{stock_quantity} {product.get('unit', 'pcs')}"

                product_data = {
                    "id": str(product.get("_id")),
                    "name": product.get("name", "Unnamed Product"),
                    "description": product.get("description", ""),
                    "barcode": product.get("barcode", ""),
                    "category_id": str(product.get("category_id")) if product.get("category_id") else None,
                    "category_name": category_name,
                    "price": product.get("price") or 0,
                    "cost_price": cost_price,
                    "stock_quantity": stock_quantity,
                    "min_stock_level": product.get("min_stock_level"),
                    "unit": product.get("unit", "pcs"),
                    "supplier": product.get("supplier", ""),
                    "brand": product.get("brand", ""),
                    "is_active": product.get("is_active", True),
                    "is_low_stock": is_low_stock,
                    "stock_status": stock_status,
                    "profit_margin": profit_margin,
                    "created_at": product.get("created_at").isoformat() if product.get("created_at") else None,
                    "updated_at": (product.get("updated_at") or product.get("created_at")).isoformat() if (product.get("updated_at") or product.get("created_at")) else None,
                    "created_by": str(product.get("created_by", "")),
                    "stock_display": stock_display
                }

                # Add perfume-specific fields if applicable
                if product.get("bottle_size_ml"):
                    product_data["bottle_size_ml"] = product.get("bottle_size_ml")

                if product.get("decant"):
                    product_data["decant"] = product.get("decant")
                    product_data["is_perfume_with_decants"] = decant_info.get("is_decantable")
                    product_data["total_ml_available"] = decant_info.get("total_ml_available")
                    product_data["available_decants"] = decant_info.get("available_decants")

                # Add scent information
                product_data["scents"] = await get_product_scents(db, product)

                # Add image information
                if product.get("image_public_id"):
                    image_urls = CloudinaryService.get_image_urls(product.get("image_public_id"))
                    product_data["image"] = {
                        "public_id": product.get("image_public_id"),
                        "url": product.get("image_url", image_urls.get("url")),
                        "thumbnail_url": image_urls.get("thumbnail_url"),
                        "medium_url": image_urls.get("medium_url")
                    }
                else:
                    product_data["image"] = None

                products.append(product_data)
            except Exception as e:
                print(f"Error processing product {product.get('_id')}: {e}")
                products.append({
                    "id": str(product.get("_id")),
                    "name": f"Error processing this product: {product.get('name')}",
                    "error": str(e)
                })

        return {
            "products": products,
            "total": total,
            "page": page,
            "size": size,
            "total_pages": (total + size - 1) // size,
            "has_next": page * size < total,
            "has_prev": page > 1
        }
    except Exception as e:
        print(f"Error in get_products endpoint: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"An unexpected error occurred: {e}"
        )


@router.post("/{product_id}/restock", response_model=dict)
async def restock_product(
    product_id: str,
    stock_update: StockUpdate,
    request: Request,
    current_user: User = Depends(get_current_user_hybrid_dependency())
):
    """Restock a product by adding quantity"""
    try:
        db = await get_database()

        # Validate product ID
        if not ObjectId.is_valid(product_id):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid product ID"
            )

        # Find the product
        product = await db.products.find_one({"_id": ObjectId(product_id)})
        if not product:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Product not found"
            )

        # Validate quantity (must be positive for restocking)
        if stock_update.quantity <= 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Restock quantity must be positive"
            )

        # Calculate new stock quantity
        current_stock = product.get("stock_quantity", 0)
        new_stock = current_stock + stock_update.quantity

        # Update the product
        update_data = {
            "stock_quantity": new_stock,
            "updated_at": kampala_to_utc(now_kampala()),
            "last_restocked": kampala_to_utc(now_kampala())
        }

        # If supplier is provided, update the product's supplier field
        if stock_update.supplier_name:
            update_data["supplier"] = stock_update.supplier_name

        # If unit cost is provided, update the product's cost price
        if stock_update.unit_cost and stock_update.unit_cost > 0:
            update_data["cost_price"] = stock_update.unit_cost

        result = await db.products.update_one(
            {"_id": ObjectId(product_id)},
            {"$set": update_data}
        )

        if result.modified_count == 0:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to update product stock"
            )

        # Log the restock activity (optional - you can create a stock_history collection)
        restock_log = {
            "product_id": ObjectId(product_id),
            "product_name": product["name"],
            "quantity_added": stock_update.quantity,
            "previous_stock": current_stock,
            "new_stock": new_stock,
            "reason": stock_update.reason or "Manual restock",
            "restocked_by": current_user.id,
            "restocked_by_username": current_user.username,
            "restocked_at": kampala_to_utc(now_kampala())
        }

        # Insert restock log (create collection if it doesn't exist)
        await db.restock_history.insert_one(restock_log)

        # Update supplier information if supplier is provided
        supplier_id = None
        if stock_update.supplier_name:
            supplier_id = await update_supplier_on_restock(
                db=db,
                supplier_name=stock_update.supplier_name,
                product_id=product_id,
                product_name=product["name"]
            )

        # Create automatic expense if cost information is provided
        expense_id = None
        if stock_update.unit_cost and stock_update.unit_cost > 0:
            total_cost = stock_update.unit_cost * stock_update.quantity
            expense_id = await create_restocking_expense(
                db=db,
                product_name=product["name"],
                quantity=stock_update.quantity,
                unit_cost=stock_update.unit_cost,
                total_cost=total_cost,
                supplier_name=stock_update.supplier_name,
                user_username=current_user.username,
                payment_method=stock_update.payment_method
            )

        # Create price record if we have cost and supplier information
        if stock_update.unit_cost and stock_update.unit_cost > 0 and supplier_id:
            try:
                price_service = ProductSupplierPriceService(db)
                total_cost = stock_update.unit_cost * stock_update.quantity

                price_record = ProductSupplierPriceCreate(
                    product_id=product_id,
                    supplier_id=str(supplier_id),
                    unit_cost=stock_update.unit_cost,
                    quantity_restocked=stock_update.quantity,
                    total_cost=total_cost,
                    restock_date=kampala_to_utc(now_kampala()),
                    expense_id=expense_id,
                    notes=stock_update.reason
                )

                await price_service.create_price_record(price_record)
                print(f"✅ Created price record: {stock_update.supplier_name} - UGX {stock_update.unit_cost}")

            except Exception as e:
                print(f"❌ Error creating price record: {e}")
                # Don't fail the restock operation if price record creation fails

        response_data = {
            "success": True,
            "message": f"Successfully restocked {product['name']}",
            "product_id": product_id,
            "product_name": product["name"],
            "quantity_added": stock_update.quantity,
            "previous_stock": current_stock,
            "new_stock": new_stock,
            "reason": stock_update.reason or "Manual restock"
        }

        # Add cost price update information if cost was updated
        if stock_update.unit_cost and stock_update.unit_cost > 0:
            previous_cost = product.get("cost_price", 0)
            response_data["cost_price_updated"] = {
                "previous_cost": previous_cost,
                "new_cost": stock_update.unit_cost,
                "message": f"Product cost price updated to UGX {stock_update.unit_cost:,.2f}"
            }

        # Add expense information if created
        if expense_id:
            total_cost = stock_update.unit_cost * stock_update.quantity
            response_data["expense_created"] = {
                "expense_id": expense_id,
                "total_cost": total_cost,
                "message": f"Automatic expense created for UGX {total_cost:,.2f}"
            }

        return response_data

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to restock product: {str(e)}"
        )


@router.get("/{product_id}", response_model=dict)
async def get_product(
    product_id: str,
    request: Request,
    current_user: User = Depends(get_current_user_hybrid_dependency())
):
    """Get a single product by ID with detailed information including perfume details and supplier info"""
    try:
        db = await get_database()

        # Validate product ID
        if not ObjectId.is_valid(product_id):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid product ID"
            )

        # Get product
        product = await db.products.find_one({"_id": ObjectId(product_id)})
        if not product:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Product not found"
            )

        # Get category name
        category_name = "Uncategorized"
        if product.get("category_id"):
            category = await db.categories.find_one({"_id": product["category_id"]})
            if category:
                category_name = category["name"]

        # Calculate profit margin
        profit_margin = None
        cost_price = product.get("cost_price", 0)
        if cost_price and cost_price > 0:
            profit_margin = ((product["price"] - cost_price) / cost_price) * 100

        # Check if it's a perfume with decants
        decant_info = product.get("decant")
        is_perfume_with_decants = decant_info and decant_info.get("is_decantable", False)

        # Calculate perfume-specific details
        perfume_details = None
        if is_perfume_with_decants:
            bottle_size_ml = product.get("bottle_size_ml", 0)
            decant_size_ml = decant_info.get("decant_size_ml", 0)
            opened_bottle_ml_left = decant_info.get("opened_bottle_ml_left", 0)

            # Calculate total ml available (unopened bottles + opened bottle)
            unopened_ml = product["stock_quantity"] * bottle_size_ml
            total_ml_available = unopened_ml + opened_bottle_ml_left

            # Calculate available decants
            available_decants = int(total_ml_available // decant_size_ml) if decant_size_ml > 0 else 0

            perfume_details = {
                "available_decants": available_decants,
                "bottle_size_ml": bottle_size_ml,
                "total_ml_available": total_ml_available,
                "decant_size_ml": decant_size_ml,
                "decant_price": decant_info.get("decant_price", 0),
                "opened_bottle_ml_left": opened_bottle_ml_left
            }

        # Get suppliers and their pricing from the product_supplier_prices table
        suppliers_info = []
        try:
            # Query the product_supplier_prices collection directly
            pipeline = [
                {"$match": {"product_id": ObjectId(product_id)}},
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
                    "supplier_contact": {"$first": "$supplier_info.contact_person"},
                    "supplier_phone": {"$first": "$supplier_info.phone"},
                    "supplier_email": {"$first": "$supplier_info.email"},
                    "supplier_address": {"$first": "$supplier_info.address"},
                    "supplier_active": {"$first": "$supplier_info.is_active"},
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

            pricing_data = await db.product_supplier_prices.aggregate(pipeline).to_list(length=None)

            # Get current supplier ID for comparison
            current_supplier_id = None
            if product.get("supplier_id"):
                current_supplier_id = str(product["supplier_id"])
            elif product.get("supplier"):
                # Find supplier by name to get ID
                current_supplier = await db.suppliers.find_one({
                    "name": {"$regex": f"^{product['supplier']}$", "$options": "i"}
                })
                if current_supplier:
                    current_supplier_id = str(current_supplier["_id"])

            for supplier_data in pricing_data:
                supplier_id = str(supplier_data["_id"])
                is_current = (supplier_id == current_supplier_id)

                # Limit price history to last 5 records
                price_history = supplier_data["price_history"][:5]

                supplier_info = {
                    "name": supplier_data["supplier_name"],
                    "is_current": is_current,
                    "contact_person": supplier_data.get("supplier_contact"),
                    "phone": supplier_data.get("supplier_phone"),
                    "email": supplier_data.get("supplier_email"),
                    "address": supplier_data.get("supplier_address"),
                    "is_active": supplier_data.get("supplier_active", True),
                    "latest_price": supplier_data["latest_price"],
                    "latest_restock_date": supplier_data["latest_restock_date"].isoformat(),
                    "average_price": round(supplier_data["average_price"], 2),
                    "total_restocks": supplier_data["total_restocks"],
                    "total_quantity": supplier_data["total_quantity"],
                    "price_history": price_history,
                    # Add pricing object in the format the frontend expects
                    "pricing": {
                        "latest_price": supplier_data["latest_price"],
                        "lowest_price": supplier_data["latest_price"],  # We can enhance this later
                        "highest_price": supplier_data["latest_price"], # We can enhance this later
                        "average_price": round(supplier_data["average_price"], 2),
                        "price_count": supplier_data["total_restocks"],
                        "all_prices": [item["unit_cost"] for item in price_history],
                        "purchase_dates": [item["restock_date"].isoformat() for item in price_history]
                    }
                }
                suppliers_info.append(supplier_info)

        except Exception as e:
            print(f"Error getting pricing from product_supplier_prices table: {e}")
            suppliers_info = []

        # Fallback: If no pricing history found, add current supplier if available
        if not suppliers_info and product.get("supplier"):
            try:
                current_supplier = await db.suppliers.find_one({
                    "name": {"$regex": f"^{product['supplier']}$", "$options": "i"}
                })

                if current_supplier:
                    supplier_info = {
                        "name": current_supplier["name"],
                        "is_current": True,
                        "contact_person": current_supplier.get("contact_person"),
                        "phone": current_supplier.get("phone"),
                        "email": current_supplier.get("email"),
                        "address": current_supplier.get("address"),
                        "is_active": current_supplier.get("is_active", True),
                        "latest_price": product.get("cost_price", 0),
                        "latest_restock_date": product.get("updated_at", "").isoformat() if product.get("updated_at") else "",
                        "average_price": product.get("cost_price", 0),
                        "total_restocks": 0,
                        "total_quantity": 0,
                        "price_history": []
                    }
                    suppliers_info.append(supplier_info)

            except Exception as e:
                print(f"Error getting current supplier: {e}")



        # Determine stock status
        stock_status = "in-stock"
        if product["stock_quantity"] == 0:
            stock_status = "out-of-stock"
        elif product["stock_quantity"] <= product.get("min_stock_level", 0):
            stock_status = "low-stock"

        # Create stock display string
        stock_display = f"{product['stock_quantity']} {product.get('unit', 'pcs')}"
        if is_perfume_with_decants and opened_bottle_ml_left:
            stock_display = f"{product['stock_quantity']} pcs & {opened_bottle_ml_left}mls"

        return_data = {
            "id": str(product["_id"]),
            "name": product["name"],
            "description": product.get("description", ""),
            "barcode": product.get("barcode"),
            "price": float(product["price"]),
            "cost_price": float(cost_price) if cost_price else None,
            "profit_margin": profit_margin,
            "stock_quantity": product["stock_quantity"],
            "min_stock_level": product.get("min_stock_level", 0),
            "unit": product.get("unit", "pcs"),
            "stock_status": stock_status,
            "stock_display": stock_display,
            "category_id": str(product["category_id"]) if product.get("category_id") else None,
            "category_name": category_name,
            "supplier": product.get("supplier"),
            "brand": product.get("brand"),
            "is_active": product.get("is_active", True),
            "created_at": product["created_at"].isoformat() if product.get("created_at") else None,
            "updated_at": product["updated_at"].isoformat() if product.get("updated_at") else None,

            # Perfume-specific fields
            "is_perfume_with_decants": is_perfume_with_decants,
            "bottle_size_ml": product.get("bottle_size_ml"),
            "decant": decant_info,
            "perfume_details": perfume_details,

            # Supplier information - all suppliers that have supplied this product
            "suppliers_info": suppliers_info,

            # Scent information
            "scents": await get_product_scents(db, product)
        }

        # Add image information if available
        if product.get("image_public_id"):
            image_urls = CloudinaryService.get_image_urls(product["image_public_id"])
            return_data["image"] = {
                "public_id": product["image_public_id"],
                "url": product.get("image_url", image_urls.get("url")),
                "thumbnail_url": image_urls.get("thumbnail_url"),
                "medium_url": image_urls.get("medium_url"),
                "large_url": image_urls.get("large_url")
            }
        else:
            return_data["image"] = None

        return return_data

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve product: {str(e)}"
        )


@router.put("/{product_id}", response_model=dict)
async def update_product(
    product_id: str,
    product_data: ProductUpdate,
    request: Request,
    current_user: User = Depends(get_current_user_hybrid_dependency())
):
    """Update a product"""
    try:
        db = await get_database()

        # Validate product ID
        if not ObjectId.is_valid(product_id):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid product ID"
            )

        # Check if product exists
        existing_product = await db.products.find_one({"_id": ObjectId(product_id)})
        if not existing_product:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Product not found"
            )

        # Build update document with only provided fields
        update_doc = {"updated_at": now_kampala()}

        # Handle each field that can be updated
        if product_data.name is not None:
            update_doc["name"] = product_data.name.strip()

        if product_data.description is not None:
            update_doc["description"] = product_data.description.strip() if product_data.description else None

        if product_data.barcode is not None:
            update_doc["barcode"] = product_data.barcode.strip() if product_data.barcode else None

        if product_data.category_id is not None:
            # Validate category exists
            try:
                category_object_id = ObjectId(product_data.category_id)
                category = await db.categories.find_one({"_id": category_object_id})
                if not category:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail="Selected category not found"
                    )
                update_doc["category_id"] = category_object_id
                update_doc["category_name"] = category["name"]
            except Exception:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Invalid category selected"
                )

        if product_data.price is not None:
            update_doc["price"] = float(product_data.price)

        if product_data.cost_price is not None:
            update_doc["cost_price"] = float(product_data.cost_price) if product_data.cost_price > 0 else None

        if product_data.stock_quantity is not None:
            update_doc["stock_quantity"] = product_data.stock_quantity

        if product_data.min_stock_level is not None:
            update_doc["min_stock_level"] = product_data.min_stock_level



        if product_data.unit is not None:
            update_doc["unit"] = product_data.unit.strip() if product_data.unit else "pcs"

        if product_data.supplier is not None:
            update_doc["supplier"] = product_data.supplier.strip() if product_data.supplier else None

        if product_data.brand is not None:
            update_doc["brand"] = product_data.brand.strip() if product_data.brand else None

        if product_data.is_active is not None:
            update_doc["is_active"] = product_data.is_active

        # Handle perfume-specific fields
        if product_data.bottle_size_ml is not None:
            update_doc["bottle_size_ml"] = float(product_data.bottle_size_ml)

        # Handle scent associations
        if product_data.scent_ids is not None:
            if product_data.scent_ids:  # If scent_ids list is provided and not empty
                # Validate all scent IDs exist
                scent_object_ids = []
                for scent_id in product_data.scent_ids:
                    if not ObjectId.is_valid(scent_id):
                        raise HTTPException(
                            status_code=status.HTTP_400_BAD_REQUEST,
                            detail=f"Invalid scent ID: {scent_id}"
                        )

                    scent_object_id = ObjectId(scent_id)
                    scent = await db.scents.find_one({"_id": scent_object_id})
                    if not scent:
                        raise HTTPException(
                            status_code=status.HTTP_400_BAD_REQUEST,
                            detail=f"Scent not found: {scent_id}"
                        )
                    scent_object_ids.append(scent_object_id)

                # Store scent IDs as ObjectIds
                update_doc["scent_ids"] = scent_object_ids

                # For backward compatibility, also store the first scent as scent_id
                if scent_object_ids:
                    update_doc["scent_id"] = scent_object_ids[0]
                else:
                    update_doc["scent_id"] = None
            else:
                # Empty list means remove all scents
                update_doc["scent_ids"] = []
                update_doc["scent_id"] = None

        # Handle decant information
        if product_data.decant is not None:
            decant_data = product_data.decant.model_dump(exclude_unset=True)
            if decant_data:
                # Merge with existing decant data if it exists
                existing_decant = existing_product.get("decant", {})
                existing_decant.update(decant_data)
                update_doc["decant"] = existing_decant
            else:
                # Remove decant data if empty
                update_doc["decant"] = None

        # Update the product
        result = await db.products.update_one(
            {"_id": ObjectId(product_id)},
            {"$set": update_doc}
        )

        if result.modified_count == 0:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to update product"
            )

        return {
            "success": True,
            "message": "Product updated successfully",
            "product_id": product_id
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update product: {str(e)}"
        )


@router.delete("/{product_id}", response_model=dict)
async def delete_product(
    product_id: str,
    request: Request,
    current_user: User = Depends(get_current_user_hybrid_dependency())
):
    """Delete a product"""
    try:
        db = await get_database()

        # Validate product ID
        if not ObjectId.is_valid(product_id):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid product ID"
            )

        # Check if product exists
        product = await db.products.find_one({"_id": ObjectId(product_id)})
        if not product:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Product not found"
            )

        # Check if product is used in any orders (optional safety check)
        orders_with_product = await db.orders.count_documents({
            "items.product_id": ObjectId(product_id)
        })

        if orders_with_product > 0:
            # Instead of preventing deletion, we could mark as inactive
            # For now, let's allow deletion but warn about it
            pass

        # Delete the product
        result = await db.products.delete_one({"_id": ObjectId(product_id)})

        if result.deleted_count == 0:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to delete product"
            )

        # Also delete any restock history for this product
        await db.restock_history.delete_many({"product_id": ObjectId(product_id)})

        return {
            "success": True,
            "message": f"Product '{product['name']}' deleted successfully",
            "deleted_product": {
                "id": product_id,
                "name": product["name"],
                "barcode": product.get("barcode", ""),
                "orders_affected": orders_with_product
            }
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete product: {str(e)}"
        )


# Decant Management Endpoints

@router.post("/{product_id}/open-bottle", response_model=dict)
async def open_new_bottle(
    product_id: str,
    request: Request,
    current_user: User = Depends(get_current_user_hybrid_dependency())
):
    """Open a new bottle for decant fulfillment"""
    try:
        db = await get_database()

        # Validate product ID
        if not ObjectId.is_valid(product_id):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid product ID"
            )

        # Open new bottle
        success, message, updated_product = await open_new_bottle_for_decants(
            db, ObjectId(product_id)
        )

        if not success:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=message
            )

        return {
            "success": True,
            "message": message,
            "product": {
                "id": str(updated_product["_id"]),
                "name": updated_product["name"],
                "stock_quantity": updated_product["stock_quantity"],
                "opened_bottle_ml_left": updated_product.get("decant", {}).get("opened_bottle_ml_left", 0)
            }
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to open new bottle: {str(e)}"
        )


@router.get("/{product_id}/decant-info", response_model=dict)
async def get_decant_info(
    product_id: str,
    request: Request,
    current_user: User = Depends(get_current_user_hybrid_dependency())
):
    """Get decant availability information for a product"""
    try:
        db = await get_database()

        # Validate product ID
        if not ObjectId.is_valid(product_id):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid product ID"
            )

        # Find the product
        product = await db.products.find_one({"_id": ObjectId(product_id)})
        if not product:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Product not found"
            )

        # Calculate decant availability
        decant_info = calculate_decant_availability(product)

        return {
            "product_id": product_id,
            "product_name": product["name"],
            "bottle_size_ml": product.get("bottle_size_ml"),
            "stock_quantity": product["stock_quantity"],
            **decant_info
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get decant info: {str(e)}"
        )