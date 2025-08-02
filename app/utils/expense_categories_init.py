from datetime import datetime
import logging

logger = logging.getLogger(__name__)

async def initialize_default_expense_categories(db):
    """Initialize default expense categories - only Restocking"""
    try:
        categories_collection = db.expense_categories

        # Remove old default categories except Restocking
        unwanted_defaults = [
            "Inventory", "Utilities", "Rent", "Supplies",
            "Marketing", "Transport", "Other"
        ]

        for category_name in unwanted_defaults:
            await categories_collection.delete_many({
                "name": category_name,
                "is_default": True
            })

        # Check if Restocking category already exists
        restocking_exists = await categories_collection.find_one({
            "name": "Restocking",
            "is_default": True
        })

        # Check if Stocking category already exists
        stocking_exists = await categories_collection.find_one({
            "name": "Stocking",
            "is_default": True
        })

        if restocking_exists and stocking_exists:
            logger.info("Restocking and Stocking categories already exist")
            return
        
        # Create Restocking category if it doesn't exist
        if not restocking_exists:
            restocking_category = {
                "name": "Restocking",
                "icon": "📦",
                "is_default": True,
                "is_active": True,
                "created_at": datetime.utcnow(),
                "updated_at": datetime.utcnow(),
                "created_by": "system"
            }

            # Insert Restocking category
            result = await categories_collection.insert_one(restocking_category)

            if result.inserted_id:
                logger.info("Successfully initialized Restocking expense category")
            else:
                logger.error("Failed to initialize Restocking expense category")

        # Create Stocking category if it doesn't exist
        if not stocking_exists:
            stocking_category = {
                "name": "Stocking",
                "icon": "📋",
                "is_default": True,
                "is_active": True,
                "created_at": datetime.utcnow(),
                "updated_at": datetime.utcnow(),
                "created_by": "system"
            }

            # Insert Stocking category
            result = await categories_collection.insert_one(stocking_category)

            if result.inserted_id:
                logger.info("Successfully initialized Stocking expense category")
            else:
                logger.error("Failed to initialize Stocking expense category")
            
    except Exception as e:
        logger.error(f"Error initializing default expense categories: {e}")

async def create_restocking_expense(db, product_name, quantity, unit_cost, total_cost, supplier_name=None, user_username=None, payment_method=None):
    """Create an automatic expense entry when restocking products"""
    try:
        expenses_collection = db.expenses

        # Create expense document for restocking
        expense_doc = {
            "description": f"Restocking: {product_name} (Qty: {quantity})",
            "category": "Restocking",
            "amount": float(total_cost),
            "expense_date": datetime.utcnow().strftime("%Y-%m-%d"),  # Convert to string
            "payment_method": payment_method or "pending",
            "vendor": supplier_name or "Unknown Supplier",
            "notes": f"Automatic expense created for restocking {quantity} units of {product_name} at UGX {unit_cost:,.2f} per unit",
            "status": "pending" if not payment_method else "paid",
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow(),
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

        # Create expense document for initial stocking
        expense_doc = {
            "description": f"Initial Stocking: {product_name} (Qty: {quantity})",
            "category": "Stocking",
            "amount": float(total_cost),
            "expense_date": datetime.utcnow().strftime("%Y-%m-%d"),  # Convert to string
            "payment_method": payment_method or "pending",
            "vendor": supplier_name or "Unknown Supplier",
            "notes": f"Automatic expense created for initial stocking of {quantity} units of {product_name} at UGX {unit_cost:,.2f} per unit",
            "status": "pending" if not payment_method else "paid",
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow(),
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
