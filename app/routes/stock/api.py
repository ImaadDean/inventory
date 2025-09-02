from fastapi import APIRouter, Depends, HTTPException, status
from ...models import User
from ...schemas.stock import RestockCreate
from ...utils.auth import require_admin_or_inventory
from ...config.database import get_database, db
from bson import ObjectId
from datetime import datetime
from ...utils.timezone import now_kampala, kampala_to_utc
from ...routes.products.api import update_supplier_on_restock
from ...models.product_supplier_price import ProductSupplierPriceCreate
from ...services.product_supplier_price_service import ProductSupplierPriceService

router = APIRouter(prefix="/api/stock", tags=["Stock Management API"])

@router.post("/restock", response_model=dict)
async def restock_products(
    restock_data: RestockCreate,
    current_user: User = Depends(require_admin_or_inventory)
):
    db = await get_database()
    client = db.client
    
    async with await client.start_session() as session:
        async with session.start_transaction():
            try:
                # 1. Create the expense document
                expense_products = []
                for item in restock_data.products:
                    product = await db.products.find_one({"_id": ObjectId(item.product_id)}, session=session)
                    if not product:
                        raise HTTPException(status_code=404, detail=f"Product with id {item.product_id} not found")
                    
                    expense_products.append({
                        "product_id": item.product_id,
                        "name": product["name"],
                        "quantity": item.quantity,
                        "cost_price": item.cost_price
                    })

                # Determine status based on payment method
                is_paid = restock_data.payment_method in ['cash', 'mobile_money']
                status = 'paid' if is_paid else 'not_paid'

                expense_doc = {
                    "description": restock_data.description,
                    "category": restock_data.category,
                    "amount": restock_data.amount,
                    "expense_date": datetime.strptime(str(restock_data.expense_date), '%Y-%m-%d'),
                    "payment_method": restock_data.payment_method,
                    "vendor": restock_data.vendor,
                    "notes": restock_data.notes,
                    "products": expense_products,
                    "created_by": str(current_user.id),
                    "status": status,
                    "is_paid": is_paid,
                    "created_at": kampala_to_utc(now_kampala()),
                    "updated_at": kampala_to_utc(now_kampala())
                }
                
                result = await db.expenses.insert_one(expense_doc, session=session)
                expense_id = result.inserted_id

                # 2. Update stock and supplier for each product
                for item in restock_data.products:
                    # Get product again to have the full document
                    product = await db.products.find_one({"_id": ObjectId(item.product_id)}, session=session)
                    supplier_id = None

                    # Update supplier information if a vendor is provided
                    if restock_data.vendor:
                        supplier_id = await update_supplier_on_restock(
                            db=db,
                            supplier_name=restock_data.vendor,
                            product_id=item.product_id,
                            product_name=product["name"]
                        )

                    # Create price record if we have cost and supplier information
                    if item.cost_price and item.cost_price > 0 and supplier_id:
                        try:
                            price_service = ProductSupplierPriceService(db)
                            total_cost = item.cost_price * item.quantity

                            price_record = ProductSupplierPriceCreate(
                                product_id=item.product_id,
                                supplier_id=str(supplier_id),
                                unit_cost=item.cost_price,
                                quantity_restocked=item.quantity,
                                total_cost=total_cost,
                                restock_date=kampala_to_utc(now_kampala()),
                                expense_id=str(expense_id),
                                notes=restock_data.notes
                            )

                            await price_service.create_price_record(price_record)
                            print(f"✅ Created price record: {restock_data.vendor} - UGX {item.cost_price}")

                        except Exception as e:
                            print(f"❌ Error creating price record: {e}")

                    # Update product stock and cost price
                    await db.products.update_one(
                        {"_id": ObjectId(item.product_id)},
                        {
                            "$inc": {"stock_quantity": item.quantity},
                            "$set": {
                                "cost_price": item.cost_price,
                                "supplier": restock_data.vendor, # Also update the supplier field on the product
                                "updated_at": kampala_to_utc(now_kampala())
                            }
                        },
                        session=session
                    )
                
                return {"success": True, "message": "Products restocked successfully", "expense_id": str(expense_id)}

            except Exception as e:
                await session.abort_transaction()
                raise HTTPException(status_code=500, detail=str(e))