"""
Utility functions for handling perfume decant sales and inventory management
"""
from typing import Dict, Any, Optional, Tuple
from bson import ObjectId


async def process_decant_sale(db, product_id: ObjectId, quantity: int) -> Tuple[bool, str, Dict[str, Any]]:
    """
    Process a decant sale by reducing ml from opened bottles and opening new bottles when needed.
    
    Args:
        db: Database connection
        product_id: ObjectId of the product
        quantity: Number of decants to sell
        
    Returns:
        Tuple of (success: bool, message: str, updated_product: dict)
    """
    try:
        # Get the product
        product = await db.products.find_one({"_id": product_id})
        if not product:
            return False, "Product not found", {}
        
        # Check if product has decant capability
        decant_info = product.get("decant")
        if not decant_info or not decant_info.get("is_decantable"):
            return False, "This product is not decantable", {}
        
        decant_size_ml = decant_info.get("decant_size_ml")
        if not decant_size_ml:
            return False, "Decant size not configured for this product", {}
        
        # Calculate total ml needed
        total_ml_needed = quantity * decant_size_ml
        
        # Get current state
        current_stock = product.get("stock_quantity", 0)
        bottle_size_ml = product.get("bottle_size_ml")
        opened_bottle_ml_left = decant_info.get("opened_bottle_ml_left", 0)
        
        if not bottle_size_ml:
            return False, "Bottle size not configured for this product", {}
        
        # Calculate total available ml
        total_available_ml = (current_stock * bottle_size_ml) + opened_bottle_ml_left
        
        if total_available_ml < total_ml_needed:
            return False, f"Insufficient stock. Need {total_ml_needed}ml, have {total_available_ml}ml", {}
        
        # Process the sale
        remaining_ml_needed = total_ml_needed
        new_opened_bottle_ml_left = opened_bottle_ml_left
        new_stock_quantity = current_stock
        
        # First, use ml from opened bottle
        if new_opened_bottle_ml_left > 0:
            ml_from_opened = min(remaining_ml_needed, new_opened_bottle_ml_left)
            new_opened_bottle_ml_left -= ml_from_opened
            remaining_ml_needed -= ml_from_opened
        
        # If we still need more ml, open new bottles
        while remaining_ml_needed > 0 and new_stock_quantity > 0:
            # Open a new bottle
            new_stock_quantity -= 1
            new_opened_bottle_ml_left += bottle_size_ml
            
            # Use ml from the newly opened bottle
            ml_from_new_bottle = min(remaining_ml_needed, new_opened_bottle_ml_left)
            new_opened_bottle_ml_left -= ml_from_new_bottle
            remaining_ml_needed -= ml_from_new_bottle
        
        # Update the product in database
        update_data = {
            "stock_quantity": new_stock_quantity,
            "decant.opened_bottle_ml_left": new_opened_bottle_ml_left
        }
        
        result = await db.products.update_one(
            {"_id": product_id},
            {"$set": update_data}
        )
        
        if result.modified_count == 0:
            return False, "Failed to update product inventory", {}
        
        # Get updated product
        updated_product = await db.products.find_one({"_id": product_id})
        
        return True, f"Successfully sold {quantity} decants ({total_ml_needed}ml)", updated_product
        
    except Exception as e:
        return False, f"Error processing decant sale: {str(e)}", {}


async def open_new_bottle_for_decants(db, product_id: ObjectId) -> Tuple[bool, str, Dict[str, Any]]:
    """
    Open a new bottle to fulfill decant orders when no opened bottle is available.
    
    Args:
        db: Database connection
        product_id: ObjectId of the product
        
    Returns:
        Tuple of (success: bool, message: str, updated_product: dict)
    """
    try:
        # Get the product
        product = await db.products.find_one({"_id": product_id})
        if not product:
            return False, "Product not found", {}
        
        # Check if product has decant capability
        decant_info = product.get("decant")
        if not decant_info or not decant_info.get("is_decantable"):
            return False, "This product is not decantable", {}
        
        # Check if we have bottles in stock
        current_stock = product.get("stock_quantity", 0)
        if current_stock <= 0:
            return False, "No bottles in stock to open", {}
        
        # Check if there's already an opened bottle
        opened_bottle_ml_left = decant_info.get("opened_bottle_ml_left", 0)
        if opened_bottle_ml_left > 0:
            return False, f"There's already an opened bottle with {opened_bottle_ml_left}ml remaining", {}
        
        bottle_size_ml = product.get("bottle_size_ml")
        if not bottle_size_ml:
            return False, "Bottle size not configured for this product", {}
        
        # Open a new bottle
        new_stock_quantity = current_stock - 1
        new_opened_bottle_ml_left = bottle_size_ml
        
        # Update the product in database
        update_data = {
            "stock_quantity": new_stock_quantity,
            "decant.opened_bottle_ml_left": new_opened_bottle_ml_left
        }
        
        result = await db.products.update_one(
            {"_id": product_id},
            {"$set": update_data}
        )
        
        if result.modified_count == 0:
            return False, "Failed to update product inventory", {}
        
        # Get updated product
        updated_product = await db.products.find_one({"_id": product_id})
        
        return True, f"Successfully opened new bottle ({bottle_size_ml}ml available for decants)", updated_product
        
    except Exception as e:
        return False, f"Error opening new bottle: {str(e)}", {}


def calculate_decant_availability(product: Dict[str, Any]) -> Dict[str, Any]:
    """
    Calculate decant availability information for a product.

    Args:
        product: Product document from database

    Returns:
        Dictionary with decant availability information
    """
    decant_info = product.get("decant")

    if not decant_info or not decant_info.get("is_decantable"):
        return {
            "is_decantable": False,
            "available_decants": 0,
            "total_ml_available": 0,
            "opened_bottle_ml_left": 0
        }
    
    bottle_size_ml = product.get("bottle_size_ml", 0)
    stock_quantity = product.get("stock_quantity", 0)
    decant_size_ml = decant_info.get("decant_size_ml", 0)
    opened_bottle_ml_left = decant_info.get("opened_bottle_ml_left", 0)
    
    # Calculate total ml available
    total_ml_available = (stock_quantity * bottle_size_ml) + opened_bottle_ml_left
    
    # Calculate available decants
    available_decants = int(total_ml_available // decant_size_ml) if decant_size_ml > 0 else 0
    
    return {
        "is_decantable": True,
        "available_decants": available_decants,
        "total_ml_available": total_ml_available,
        "opened_bottle_ml_left": opened_bottle_ml_left,
        "decant_size_ml": decant_size_ml,
        "decant_price": decant_info.get("decant_price", 0)
    }
