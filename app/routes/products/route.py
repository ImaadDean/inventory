from fastapi import APIRouter, Request, Depends, Form, HTTPException, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from datetime import datetime
from decimal import Decimal
from bson import ObjectId
from typing import Optional
from ...models import User
from ...utils.auth import get_current_user, verify_token, get_user_by_username
from ...config.database import get_database
from ...utils.expense_categories_init import create_stocking_expense
from ...utils.timezone import now_kampala, kampala_to_utc

templates = Jinja2Templates(directory="app/templates")
products_routes = APIRouter(prefix="/products", tags=["Product Management Web"])


async def get_current_user_from_cookie(request: Request):
    """Get current user from cookie for HTML routes"""
    access_token = request.cookies.get("access_token")
    if not access_token:
        return None

    if access_token.startswith("Bearer "):
        token = access_token[7:]
    else:
        token = access_token

    payload = verify_token(token)
    if not payload:
        return None

    username = payload.get("sub")
    if not username:
        return None

    user = await get_user_by_username(username)
    return user


@products_routes.get("/", response_class=HTMLResponse)
async def products_page(request: Request):
    """Display products management page"""
    current_user = await get_current_user_from_cookie(request)
    if not current_user:
        return RedirectResponse(url="/auth/login", status_code=302)

    return templates.TemplateResponse(
        "products/index.html",
        {"request": request, "user": current_user}
    )


@products_routes.post("/", response_class=HTMLResponse)
async def create_product(
    request: Request,
    name: str = Form(...),
    category_id: str = Form(...),
    sku: str = Form(...),
    cost_price: str = Form(None),
    price: str = Form(...),
    stock_quantity: str = Form(...),
    description: str = Form(None),
    min_stock_level: str = Form("10"),
    max_stock_level: str = Form(None),
    unit: str = Form("pcs"),
    barcode: str = Form(None),
    supplier: str = Form(None),
    location: str = Form(None),
    is_active: bool = Form(True),
    payment_method: str = Form(None)
):
    """Handle product creation from form submission"""
    current_user = await get_current_user_from_cookie(request)
    if not current_user:
        return RedirectResponse(url="/auth/login", status_code=302)

    db = await get_database()

    # Parse and validate numeric fields
    try:
        parsed_cost_price = float(cost_price) if cost_price and cost_price.strip() else None
        parsed_price = float(price) if price and price.strip() else 0.0
        parsed_stock_quantity = int(stock_quantity) if stock_quantity and stock_quantity.strip() else 0
        parsed_min_stock_level = int(min_stock_level) if min_stock_level and min_stock_level.strip() else 10
        parsed_max_stock_level = int(max_stock_level) if max_stock_level and max_stock_level.strip() else None
    except (ValueError, TypeError) as e:
        return RedirectResponse(
            url="/products/?error=Invalid numeric values provided",
            status_code=302
        )

    try:
        # Check if product with same SKU already exists
        existing_product = await db.products.find_one({"sku": sku.strip()})
        if existing_product:
            return RedirectResponse(
                url="/products/?error=Product with this SKU already exists",
                status_code=302
            )

        # Validate category exists
        try:
            category_object_id = ObjectId(category_id)
            category = await db.categories.find_one({"_id": category_object_id})
            if not category:
                return RedirectResponse(
                    url="/products/?error=Selected category not found",
                    status_code=302
                )
        except Exception:
            return RedirectResponse(
                url="/products/?error=Invalid category selected",
                status_code=302
            )

        # Create product document
        product_doc = {
            "name": name.strip(),
            "category_id": category_object_id,
            "category_name": category["name"],  # Store category name for easy access
            "sku": sku.strip().upper(),  # Store SKU in uppercase
            "price": parsed_price,  # Store as float for MongoDB compatibility
            "stock_quantity": parsed_stock_quantity,
            "description": description.strip() if description else None,
            "min_stock_level": parsed_min_stock_level,
            "max_stock_level": parsed_max_stock_level,
            "unit": unit.strip() if unit else "pcs",
            "barcode": barcode.strip() if barcode else None,
            "supplier": supplier.strip() if supplier else None,
            "location": location.strip() if location else None,
            "is_active": is_active,
            "created_at": kampala_to_utc(now_kampala()),
            "updated_at": kampala_to_utc(now_kampala()),
            "created_by": current_user.id,  # Store user ObjectId instead of username
            "total_sold": 0,
            "last_restocked": None,
            "cost_price": parsed_cost_price,
            "payment_method": payment_method.strip() if payment_method else None,
            "profit_margin": None  # Can be calculated later
        }

        # Insert product
        result = await db.products.insert_one(product_doc)

        # Update supplier information if supplier is provided
        if supplier and supplier.strip():
            await update_supplier_on_product_creation(
                db=db,
                supplier_name=supplier.strip(),
                product_id=str(result.inserted_id),
                product_name=name,
                product_sku=sku.strip().upper()
            )

        # Create stocking expense (mandatory for all new products with cost price)
        expense_message = ""
        if parsed_cost_price and parsed_cost_price > 0 and parsed_stock_quantity > 0:
            total_cost = parsed_cost_price * parsed_stock_quantity
            expense_id = await create_stocking_expense(
                db=db,
                product_name=name,
                quantity=parsed_stock_quantity,
                unit_cost=parsed_cost_price,  # Use parsed_cost_price as unit_cost
                total_cost=total_cost,
                supplier_name=supplier,
                user_username=current_user.username,
                payment_method=payment_method
            )

            if expense_id:
                expense_message = f" and stocking expense created (UGX {total_cost:,.2f})"

        # Redirect with success message
        success_msg = f"Product created successfully{expense_message}"
        return RedirectResponse(
            url=f"/products/?success={success_msg}",
            status_code=302
        )

    except ValueError as e:
        # Handle invalid price or quantity
        return RedirectResponse(
            url="/products/?error=Invalid price or quantity format",
            status_code=302
        )
    except Exception as e:
        print(f"Error creating product: {e}")
        return RedirectResponse(
            url="/products/?error=Failed to create product",
            status_code=302
        )


async def update_supplier_on_product_creation(db, supplier_name: str, product_id: str, product_name: str, product_sku: str):
    """Update supplier information when a new product is created"""
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
                "notes": f"Auto-created from product creation",
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
        else:
            # Update existing supplier
            supplier_id = supplier["_id"]
            current_products = supplier.get("products", [])

            # Add product to supplier's product list if not already there
            if product_id not in current_products:
                current_products.append(product_id)

            # Update supplier with new product
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

            print(f"Updated supplier {supplier_name} with new product {product_name}")

    except Exception as e:
        print(f"Error updating supplier on product creation: {e}")
        # Don't raise exception as this is supplementary functionality