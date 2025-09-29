from .counter import get_next_sequence_value
from pymongo.errors import DuplicateKeyError
import asyncio

async def generate_unique_sale_number(db, max_retries=10):
    """
    Generate a unique sale number by checking for conflicts and retrying if needed.
    
    Args:
        db: Database connection
        max_retries: Maximum number of retries to generate a unique number
        
    Returns:
        str: Unique sale number in format "SALE-XXXXXX"
        
    Raises:
        Exception: If unable to generate a unique sale number after max_retries
    """
    for attempt in range(max_retries):
        try:
            # Get next sequence value
            new_sale_number = await get_next_sequence_value("sale_number")
            sale_number = f"SALE-{new_sale_number:06d}"
            
            # Check if this sale number already exists
            existing_sale = await db.sales.find_one({"sale_number": sale_number})
            
            if existing_sale is None:
                # Number is unique, return it
                return sale_number
            # If number exists, continue to next attempt
            # Log warning for debugging
            print(f"Warning: Sale number {sale_number} already exists, retrying... (attempt {attempt + 1}/{max_retries})")
        except Exception as e:
            if attempt == max_retries - 1:
                # Last attempt, re-raise the exception
                raise e
            # Otherwise continue to next attempt
    
    # If we've exhausted all retries
    raise Exception(f"Unable to generate unique sale number after {max_retries} attempts")