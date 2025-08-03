#!/usr/bin/env python3
"""
Debug script to check supplier and product data
"""
import asyncio
import sys
import os

# Add the app directory to the path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.config.database import get_database

async def debug_supplier_products():
    """Debug supplier and product data"""
    try:
        db = await get_database()
        
        # Get all suppliers
        print("=== SUPPLIERS ===")
        suppliers = await db.suppliers.find({}).to_list(length=None)
        for supplier in suppliers:
            print(f"ID: {supplier['_id']}")
            print(f"Name: '{supplier['name']}'")
            print(f"Active: {supplier.get('is_active', True)}")
            print("---")
        
        # Get all products and their suppliers
        print("\n=== PRODUCTS AND THEIR SUPPLIERS ===")
        products = await db.products.find({}).to_list(length=None)
        supplier_counts = {}
        
        for product in products:
            supplier_name = product.get('supplier', 'No Supplier')
            if supplier_name in supplier_counts:
                supplier_counts[supplier_name] += 1
            else:
                supplier_counts[supplier_name] = 1
            
            print(f"Product: {product['name']}")
            print(f"Supplier: '{supplier_name}'")
            print(f"Active: {product.get('is_active', True)}")
            print("---")
        
        print("\n=== SUPPLIER COUNTS ===")
        for supplier, count in supplier_counts.items():
            print(f"'{supplier}': {count} products")
            
        # Test the specific supplier "male"
        print("\n=== TESTING SUPPLIER 'male' ===")
        male_products = await db.products.find({"supplier": {"$regex": "^male$", "$options": "i"}}).to_list(length=None)
        print(f"Found {len(male_products)} products for supplier 'male'")
        for product in male_products:
            print(f"- {product['name']} (supplier: '{product.get('supplier', 'None')}')")
            
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(debug_supplier_products())
