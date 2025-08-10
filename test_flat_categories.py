#!/usr/bin/env python3
"""
Test script to verify that categories are now flat (no parent/child relationships).
This test ensures that only name and description are saved for categories.
"""

import asyncio
import sys
import os
from datetime import datetime

# Add the app directory to the Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'app'))

from app.config.database import get_database
from app.models.category import Category


async def test_flat_categories():
    """Test that categories are flat with only name and description"""
    
    print("🧪 Testing Flat Category Structure...")
    
    try:
        # Get database connection
        db = await get_database()
        
        # Clean up any existing test data
        await db.categories.delete_many({"name": {"$regex": "^Test.*Category$"}})
        
        # 1. Test Category model structure
        print("\n1️⃣ Testing Category model structure...")
        
        # Create a category instance
        category = Category(
            name="Test Electronics Category",
            description="A test category for electronics",
            is_active=True
        )
        
        # Verify the model only has expected fields
        category_dict = category.model_dump(by_alias=True, exclude={"id"})
        expected_fields = {"name", "description", "is_active", "created_at", "updated_at"}
        actual_fields = set(category_dict.keys())
        
        print(f"📋 Expected fields: {expected_fields}")
        print(f"📋 Actual fields: {actual_fields}")
        
        if actual_fields == expected_fields:
            print("✅ SUCCESS: Category model has correct flat structure")
        else:
            print("❌ FAILURE: Category model has unexpected fields")
            print(f"   Extra fields: {actual_fields - expected_fields}")
            print(f"   Missing fields: {expected_fields - actual_fields}")
            return False
        
        # 2. Test database insertion
        print("\n2️⃣ Testing database insertion...")
        
        result = await db.categories.insert_one(category_dict)
        category_id = result.inserted_id
        print(f"✅ Category inserted with ID: {category_id}")
        
        # 3. Verify stored document structure
        print("\n3️⃣ Verifying stored document structure...")
        
        stored_category = await db.categories.find_one({"_id": category_id})
        stored_fields = set(stored_category.keys())
        
        # Expected fields in database (including _id)
        expected_db_fields = {"_id", "name", "description", "is_active", "created_at", "updated_at"}
        
        print(f"📋 Expected DB fields: {expected_db_fields}")
        print(f"📋 Actual DB fields: {stored_fields}")
        
        if stored_fields == expected_db_fields:
            print("✅ SUCCESS: Stored category has correct flat structure")
        else:
            print("❌ FAILURE: Stored category has unexpected fields")
            print(f"   Extra fields: {stored_fields - expected_db_fields}")
            print(f"   Missing fields: {expected_db_fields - stored_fields}")
            return False
        
        # 4. Verify no parent_id field exists
        print("\n4️⃣ Verifying no parent_id field...")
        
        if "parent_id" not in stored_category:
            print("✅ SUCCESS: No parent_id field found in stored category")
        else:
            print("❌ FAILURE: parent_id field found in stored category")
            print(f"   parent_id value: {stored_category.get('parent_id')}")
            return False
        
        # 5. Test category update
        print("\n5️⃣ Testing category update...")
        
        update_result = await db.categories.update_one(
            {"_id": category_id},
            {"$set": {
                "description": "Updated test category description",
                "updated_at": datetime.utcnow()
            }}
        )
        
        if update_result.modified_count == 1:
            print("✅ SUCCESS: Category updated successfully")
        else:
            print("❌ FAILURE: Category update failed")
            return False
        
        # 6. Verify updated document structure
        print("\n6️⃣ Verifying updated document structure...")
        
        updated_category = await db.categories.find_one({"_id": category_id})
        updated_fields = set(updated_category.keys())
        
        if updated_fields == expected_db_fields:
            print("✅ SUCCESS: Updated category maintains flat structure")
        else:
            print("❌ FAILURE: Updated category has unexpected fields")
            return False
        
        # 7. Clean up test data
        print("\n7️⃣ Cleaning up test data...")
        await db.categories.delete_one({"_id": category_id})
        print("✅ Test data cleaned up")
        
        print("\n🎉 ALL TESTS PASSED: Categories are now flat with only name and description!")
        return True
        
    except Exception as e:
        print(f"\n❌ TEST FAILED with error: {e}")
        return False


async def main():
    """Main test function"""
    success = await test_flat_categories()
    if not success:
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
