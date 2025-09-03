import asyncio
from pymongo import MongoClient
from bson import ObjectId
import urllib.parse

# --- Connection details ---
MONGO_USERNAME = "imaad"
MONGO_PASSWORD = "Ertdfgxc"
MONGO_CLUSTER = "cluster0.n5vfpbr.mongodb.net"
MONGO_DATABASE = "perfumesandmorebytuta"
MONGO_POOL_SIZE = 20

encoded_password = urllib.parse.quote_plus(MONGO_PASSWORD)
MONGO_URI = f"mongodb+srv://{MONGO_USERNAME}:{encoded_password}@{MONGO_CLUSTER}/?retryWrites=true&w=majority&maxPoolSize={MONGO_POOL_SIZE}"

async def update_expense_amount_paid():
    """
    Updates the 'amount_paid' field for all expenses based on their status.
    - 'paid': amount_paid = amount
    - 'not_paid', 'pending': amount_paid = 0
    - 'partially_paid': amount_paid is untouched if it exists, otherwise set to 0
    """
    client = MongoClient(MONGO_URI)
    db = client[MONGO_DATABASE]
    expenses_collection = db.expenses
    
    updated_count = 0
    
    for expense in expenses_collection.find():
        expense_id = expense["_id"]
        status = expense.get("status")
        amount = expense.get("amount", 0)
        
        update_data = {}
        
        if "amount_paid" not in expense:
            if status == "paid":
                update_data["amount_paid"] = amount
            elif status in ["not_paid", "pending"]:
                update_data["amount_paid"] = 0
            elif status == "partially_paid":
                # If it's partially paid but has no amount_paid, assume 0 for now.
                # This case might need manual review.
                update_data["amount_paid"] = 0
        
        if update_data:
            result = expenses_collection.update_one(
                {"_id": expense_id},
                {"$set": update_data}
            )
            if result.modified_count > 0:
                updated_count += 1
                print(f"Updated expense {expense_id}: status='{status}', amount={amount}, set amount_paid={update_data['amount_paid']}")

    print(f"\nFinished updating expenses. Total updated: {updated_count}")
    client.close()

if __name__ == "__main__":
    asyncio.run(update_expense_amount_paid())
