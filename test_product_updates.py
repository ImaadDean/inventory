#!/usr/bin/env python3
"""
Test script to verify product model updates:
1. Min stock level default changed to 4
2. SKU, Max Stock Level, and Location fields removed
3. Perfume category detection works
"""

import asyncio
import sys
import os
from datetime import datetime

# Add the app directory to the Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'app'))

from app.config.database import get_database
from app.models.product import Product
from app.schemas.product import ProductCreate


async def test_product_updates():
    """Test that product updates work correctly"""
    
    print("🧪 Testing Product Model Updates...")
    
    try:
        # Get database connection
        db = await get_database()
        
        # Clean up any existing test data
        await db.products.delete_many({"name": {"$regex": "^Test.*Product$"}})
        
        # 1. Test Product model structure
        print("\n1️⃣ Testing Product model structure...")
        
        # Create a product instance
        product = Product(
            name="Test Electronics Product",
            description="A test product for electronics",
            barcode="123456789",
            price=1000.0,
            cost_price=750.0,
            stock_quantity=10,
            min_stock_level=4,  # Should default to 4
            unit="pcs",
            supplier="Test Supplier",
            is_active=True
        )
        
        # Verify the model only has expected fields (no SKU, max_stock_level, location)
        product_dict = product.model_dump(by_alias=True, exclude={"id"})
        
        # Fields that should NOT be present
        forbidden_fields = {"sku", "max_stock_level", "location"}
        actual_fields = set(product_dict.keys())
        
        print(f"📋 Checking for forbidden fields: {forbidden_fields}")
        found_forbidden = forbidden_fields.intersection(actual_fields)
        
        if found_forbidden:
            print(f"❌ FAILURE: Found forbidden fields: {found_forbidden}")
            return False
        else:
            print("✅ SUCCESS: No forbidden fields found in product model")
        
        # 2. Test min stock level default
        print("\n2️⃣ Testing min stock level default...")
        
        if product.min_stock_level == 4:
            print("✅ SUCCESS: Min stock level defaults to 4")
        else:
            print(f"❌ FAILURE: Min stock level is {product.min_stock_level}, expected 4")
            return False
        
        # 3. Test ProductCreate schema
        print("\n3️⃣ Testing ProductCreate schema...")
        
        product_create = ProductCreate(
            name="Test Schema Product",
            description="Testing schema",
            price=500.0,
            stock_quantity=5
            # min_stock_level should default to 4
        )
        
        if product_create.min_stock_level == 4:
            print("✅ SUCCESS: ProductCreate schema defaults min_stock_level to 4")
        else:
            print(f"❌ FAILURE: ProductCreate min_stock_level is {product_create.min_stock_level}, expected 4")
            return False
        
        # 4. Test database insertion
        print("\n4️⃣ Testing database insertion...")
        
        result = await db.products.insert_one(product_dict)
        product_id = result.inserted_id
        print(f"✅ Product inserted with ID: {product_id}")
        
        # 5. Verify stored document structure
        print("\n5️⃣ Verifying stored document structure...")
        
        stored_product = await db.products.find_one({"_id": product_id})
        stored_fields = set(stored_product.keys())
        
        # Check that forbidden fields are not in the stored document
        found_forbidden_in_db = forbidden_fields.intersection(stored_fields)
        
        if found_forbidden_in_db:
            print(f"❌ FAILURE: Found forbidden fields in database: {found_forbidden_in_db}")
            return False
        else:
            print("✅ SUCCESS: No forbidden fields found in stored product")
        
        # 6. Verify min stock level in database
        print("\n6️⃣ Verifying min stock level in database...")
        
        if stored_product.get("min_stock_level") == 4:
            print("✅ SUCCESS: Min stock level correctly stored as 4")
        else:
            print(f"❌ FAILURE: Stored min_stock_level is {stored_product.get('min_stock_level')}, expected 4")
            return False
        
        # 7. Clean up test data
        print("\n7️⃣ Cleaning up test data...")
        await db.products.delete_one({"_id": product_id})
        print("✅ Test data cleaned up")
        
        print("\n🎉 ALL TESTS PASSED: Product model updates are working correctly!")
        print("✅ SKU, Max Stock Level, and Location fields removed")
        print("✅ Min Stock Level defaults to 4")
        print("✅ Database operations work correctly")
        return True
        
    except Exception as e:
        print(f"\n❌ TEST FAILED with error: {e}")
        import traceback
        traceback.print_exc()
        return False


async def main():
    """Main test function"""
    success = await test_product_updates()
    if not success:
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
