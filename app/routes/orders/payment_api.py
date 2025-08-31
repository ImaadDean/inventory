from fastapi import APIRouter, Depends, HTTPException, status
from bson import ObjectId
from ...config.database import get_database
from ...models.user import User
from ...schemas.payment import PaymentUpdate
from ...utils.auth import get_current_user_hybrid_dependency
from datetime import datetime

router = APIRouter(
    prefix="/api/orders/{order_id}/payment",
    tags=["Orders Payment API"],
    dependencies=[Depends(get_current_user_hybrid_dependency())]
)

@router.post("", response_model=dict)
async def update_payment(order_id: str, payment_data: PaymentUpdate):
    db = await get_database()
    order = await db.orders.find_one({"_id": ObjectId(order_id)})

    if not order:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found")

    paid_amount = order.get("paid_amount", 0) + payment_data.amount
    balance = order["total"] - paid_amount

    if balance < 0:
        balance = 0

    order_update_data = {
        "paid_amount": paid_amount,
        "balance": balance,
        "updated_at": datetime.utcnow()
    }

    if balance == 0:
        order_update_data["payment_status"] = "paid"
        order_update_data["status"] = "completed"
    else:
        order_update_data["payment_status"] = "partially_paid"

    await db.orders.update_one(
        {"_id": ObjectId(order_id)},
        {"$set": order_update_data}
    )

    # Update the corresponding sale record
    if order.get("sale_id"):
        sale_update_data = {
            "payment_received": paid_amount,
            "updated_at": datetime.utcnow()
        }

        # Update status based on payment
        if balance == 0:
            sale_update_data["status"] = "completed"
            # Also update payment method on full payment
            if payment_data.method:
                sale_update_data["payment_method"] = payment_data.method
            else:
                sale = await db.sales.find_one({"_id": order["sale_id"]})
                if sale and sale.get("payment_method") == "not_paid":
                    sale_update_data["payment_method"] = "cash"
        elif paid_amount > 0:
            sale_update_data["status"] = "partially_paid"

        await db.sales.update_one(
            {"_id": order["sale_id"]},
            {"$set": sale_update_data}
        )

    return {"success": True, "message": "Payment status updated successfully"}
