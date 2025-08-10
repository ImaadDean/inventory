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
from ...utils.expense_categories_init import create_stocking_expense, create_restocking_expense
from ...utils.timezone import now_kampala, kampala_to_utc
from ...models.product_supplier_price import ProductSupplierPriceCreate
from ...services.product_supplier_price_service import ProductSupplierPriceService

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
    cost_price: str = Form(None),
    price: str = Form(...),
    stock_quantity: str = Form(...),
    description: str = Form(None),
    min_stock_level: str = Form("4"),
    unit: str = Form("pcs"),
    barcode: str = Form(None),
    supplier: str = Form(None),
    is_active: bool = Form(True),
    payment_method: str = Form(None),
    # Perfume-specific fields
    bottle_size_ml: str = Form(None),
    is_decantable: bool = Form(False),
    decant_size_ml: str = Form(None),
    decant_price: str = Form(None),
    # Scent fields
    scent_ids: list = Form(None)
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
        parsed_min_stock_level = int(min_stock_level) if min_stock_level and min_stock_level.strip() else 4

        # Parse perfume-specific fields
        parsed_bottle_size_ml = float(bottle_size_ml) if bottle_size_ml and bottle_size_ml.strip() else None
        parsed_decant_size_ml = float(decant_size_ml) if decant_size_ml and decant_size_ml.strip() else None
        parsed_decant_price = float(decant_price) if decant_price and decant_price.strip() else None

    except (ValueError, TypeError) as e:
        return RedirectResponse(
            url="/products/?error=Invalid numeric values provided",
            status_code=302
        )

    try:


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
            "price": parsed_price,  # Store as float for MongoDB compatibility
            "stock_quantity": parsed_stock_quantity,
            "description": description.strip() if description else None,
            "min_stock_level": parsed_min_stock_level,
            "unit": unit.strip() if unit else "pcs",
            "barcode": barcode.strip() if barcode else None,
            "supplier": supplier.strip() if supplier else None,
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

        # Add perfume-specific fields if provided
        if parsed_bottle_size_ml:
            product_doc["bottle_size_ml"] = parsed_bottle_size_ml

        if is_decantable and parsed_decant_size_ml and parsed_decant_price:
            product_doc["decant"] = {
                "is_decantable": True,
                "decant_size_ml": parsed_decant_size_ml,
                "decant_price": parsed_decant_price,
                "opened_bottle_ml_left": 0.0  # Start with no opened bottle
            }

        # Handle scent associations
        if scent_ids and isinstance(scent_ids, list) and len(scent_ids) > 0:
            # Filter out empty strings and validate scent IDs
            valid_scent_ids = [scent_id for scent_id in scent_ids if scent_id and scent_id.strip()]

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

        # Insert product
        result = await db.products.insert_one(product_doc)

        product_id = str(result.inserted_id)

        # Handle supplier and pricing information (same as API and restocking)
        supplier_id = None
        expense_id = None
        expense_message = ""

        if supplier and supplier.strip() and parsed_cost_price and parsed_cost_price > 0:
            # Import the restock function
            from ...routes.products.api import update_supplier_on_restock

            # Update supplier information
            supplier_id = await update_supplier_on_restock(
                db=db,
                supplier_name=supplier.strip(),
                product_id=product_id,
                product_name=name,
                product_sku=sku.strip().upper()
            )

            # Create expense record for initial stock
            if parsed_stock_quantity > 0:
                total_cost = parsed_cost_price * parsed_stock_quantity
                expense_id = await create_restocking_expense(
                    db=db,
                    product_name=name,
                    quantity=parsed_stock_quantity,
                    unit_cost=parsed_cost_price,
                    total_cost=total_cost,
                    supplier_name=supplier.strip(),
                    user_username=current_user.username,
                    payment_method=payment_method or "Initial Stock"
                )

                if expense_id:
                    expense_message = f" and expense created (UGX {total_cost:,.2f})"

            # Create price record for supplier pricing history
            if supplier_id and parsed_stock_quantity > 0:
                try:
                    price_service = ProductSupplierPriceService(db)
                    total_cost = parsed_cost_price * parsed_stock_quantity

                    price_record = ProductSupplierPriceCreate(
                        product_id=product_id,
                        supplier_id=str(supplier_id),
                        unit_cost=parsed_cost_price,
                        quantity_restocked=parsed_stock_quantity,
                        total_cost=total_cost,
                        restock_date=kampala_to_utc(now_kampala()),
                        expense_id=expense_id,
                        notes="Initial stock - Product creation"
                    )

                    await price_service.create_price_record(price_record)
                    print(f"✅ Created initial price record: {supplier.strip()} - UGX {parsed_cost_price}")

                except Exception as e:
                    print(f"⚠️ Failed to create price record: {e}")
                    # Don't fail the entire product creation if price record fails

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


