from fastapi import APIRouter, Depends, HTTPException, status
from bson import ObjectId
from ...config.database import get_database
from ...models.user import User
from ...schemas.payment import PaymentUpdate
from ...utils.auth import get_current_user_hybrid_dependency

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

    if payment_data.payment_type == "full":
        await db.orders.update_one(
            {"_id": ObjectId(order_id)},
            {"$set": {"payment_status": "paid"}}
        )
    elif payment_data.payment_type == "partial":
        # You can add more complex logic here for partial payments if needed
        await db.orders.update_one(
            {"_id": ObjectId(order_id)},
            {"$set": {"payment_status": "partially_paid"}}
        )
    else:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid payment type")

    return {"success": True, "message": "Payment status updated successfully"}
