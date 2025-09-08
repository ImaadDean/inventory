import logging
from .timezone import now_kampala, kampala_to_utc, format_kampala_date

logger = logging.getLogger(__name__)

async def initialize_default_expense_categories(db):
    """Initialize default expense categories"""
    try:
        categories_collection = db.expense_categories

        # Remove old default categories including the ones we're replacing
        unwanted_defaults = [
            "Inventory", "Utilities", "Rent", "Supplies",
            "Marketing", "Transport", "Other", "Restocking", "Stocking"
        ]

        for category_name in unwanted_defaults:
            await categories_collection.delete_many({
                "name": category_name,
                "is_default": True
            })

        # Define default categories to create
        default_categories = [
            {
                "name": "Stock Purchase",
                "icon": "🛒",
                "description": "Expenses for purchasing stock and inventory (restocking and new stock)"
            },
            {
                "name": "External Labor",
                "icon": "👷",
                "description": "Payments for external workers and contractors"
            }
        ]

        # Check and create each default category
        for category_info in default_categories:
            category_exists = await categories_collection.find_one({
                "name": category_info["name"],
                "is_default": True
            })

            if not category_exists:
                category_doc = {
                    "name": category_info["name"],
                    "icon": category_info["icon"],
                    "is_default": True,
                    "is_active": True,
                    "created_at": kampala_to_utc(now_kampala()),
                    "updated_at": kampala_to_utc(now_kampala()),
                    "created_by": "system"
                }

                # Insert category
                result = await categories_collection.insert_one(category_doc)

                if result.inserted_id:
                    logger.info(f"Successfully initialized {category_info['name']} expense category")
                else:
                    logger.error(f"Failed to initialize {category_info['name']} expense category")
            else:
                logger.info(f"{category_info['name']} category already exists")

    except Exception as e:
        logger.error(f"Error initializing default expense categories: {e}")

async def create_restocking_expense(db, product_name, quantity, unit_cost, total_cost, supplier_name=None, user_username=None, payment_method=None):
    """Create an automatic expense entry when restocking products"""
    try:
        expenses_collection = db.expenses

        # Determine status based on payment method
        final_payment_method = payment_method or "pending payment"
        status = "not_paid"
        if final_payment_method.strip().lower() in ["cash", "mobile_money"]:
            status = "paid"

        # Create expense document for restocking
        expense_doc = {
            "description": f"Restocking: {product_name} (Qty: {quantity})",
            "category": "Stock Purchase",
            "amount": float(total_cost),
            "expense_date": format_kampala_date(now_kampala()),  # Convert to string in EAT
            "payment_method": final_payment_method,
            "vendor": supplier_name or "Unknown Supplier",
            "notes": f"Automatic expense created for restocking {quantity} units of {product_name} at UGX {unit_cost:,.2f} per unit",
            "status": status,
            "created_at": kampala_to_utc(now_kampala()),
            "updated_at": kampala_to_utc(now_kampala()),
            "created_by": user_username or "system",
            "is_auto_generated": True  # Flag to identify auto-generated expenses
        }

        result = await expenses_collection.insert_one(expense_doc)
        
        if result.inserted_id:
            logger.info(f"Created automatic restocking expense: {expense_doc['description']} - UGX {total_cost}")
            return str(result.inserted_id)
        else:
            logger.error("Failed to create automatic restocking expense")
            return None
            
    except Exception as e:
        logger.error(f"Error creating restocking expense: {e}")
        return None


async def create_stocking_expense(db, product_name, quantity, unit_cost, total_cost, supplier_name=None, user_username=None, payment_method=None):
    """Create an automatic expense entry when adding new products (initial stocking)"""
    try:
        expenses_collection = db.expenses

        # Determine status based on payment method
        final_payment_method = payment_method or "pending payment"
        status = "not_paid"
        if final_payment_method.strip().lower() in ["cash", "mobile_money"]:
            status = "paid"

        # Create expense document for initial stocking
        expense_doc = {
            "description": f"Initial Stocking: {product_name} (Qty: {quantity})",
            "category": "Stock Purchase",
            "amount": float(total_cost),
            "expense_date": format_kampala_date(now_kampala()),  # Convert to string in EAT
            "payment_method": final_payment_method,
            "vendor": supplier_name or "Unknown Supplier",
            "notes": f"Automatic expense created for initial stocking of {quantity} units of {product_name} at UGX {unit_cost:,.2f} per unit",
            "status": status,
            "created_at": kampala_to_utc(now_kampala()),
            "updated_at": kampala_to_utc(now_kampala()),
            "created_by": user_username or "system",
            "is_auto_generated": True  # Flag to identify auto-generated expenses
        }

        result = await expenses_collection.insert_one(expense_doc)

        if result.inserted_id:
            logger.info(f"Created automatic stocking expense: {expense_doc['description']} - UGX {total_cost}")
            return str(result.inserted_id)
        else:
            logger.error("Failed to create automatic stocking expense")
            return None

    except Exception as e:
        logger.error(f"Error creating stocking expense: {e}")
        return None
