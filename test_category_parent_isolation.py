#!/usr/bin/env python3
"""
Test script to verify that saving a Category does not modify the parent Category.
This test ensures that parent categories remain unchanged when child categories are created or updated.
"""

import asyncio
import sys
import os
from datetime import datetime
from bson import ObjectId

# Add the app directory to the Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'app'))

from app.config.database import get_database
from app.models.category import Category


async def test_category_parent_isolation():
    """Test that saving a child category doesn't modify the parent category"""
    
    print("🧪 Testing Category Parent Isolation...")
    
    try:
        # Get database connection
        db = await get_database()
        
        # Clean up any existing test data
        await db.categories.delete_many({"name": {"$in": ["Test Parent Category", "Test Child Category"]}})
        
        # 1. Create a parent category
        print("\n1️⃣ Creating parent category...")
        parent_category_data = {
            "name": "Test Parent Category",
            "description": "A test parent category",
            "parent_id": None,
            "is_active": True,
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow()
        }
        
        parent_result = await db.categories.insert_one(parent_category_data)
        parent_id = parent_result.inserted_id
        print(f"✅ Parent category created with ID: {parent_id}")
        
        # Get the initial parent category state
        initial_parent = await db.categories.find_one({"_id": parent_id})
        initial_parent_updated_at = initial_parent["updated_at"]
        print(f"📅 Initial parent updated_at: {initial_parent_updated_at}")
        
        # Wait a moment to ensure timestamp difference
        await asyncio.sleep(1)
        
        # 2. Create a child category
        print("\n2️⃣ Creating child category...")
        child_category_data = {
            "name": "Test Child Category",
            "description": "A test child category",
            "parent_id": parent_id,
            "is_active": True,
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow()
        }
        
        child_result = await db.categories.insert_one(child_category_data)
        child_id = child_result.inserted_id
        print(f"✅ Child category created with ID: {child_id}")
        
        # 3. Verify parent category was not modified
        print("\n3️⃣ Checking if parent category was modified...")
        final_parent = await db.categories.find_one({"_id": parent_id})
        final_parent_updated_at = final_parent["updated_at"]
        print(f"📅 Final parent updated_at: {final_parent_updated_at}")
        
        if initial_parent_updated_at == final_parent_updated_at:
            print("✅ SUCCESS: Parent category was NOT modified when child was created")
        else:
            print("❌ FAILURE: Parent category was modified when child was created")
            return False
        
        # Wait a moment to ensure timestamp difference
        await asyncio.sleep(1)
        
        # 4. Update the child category
        print("\n4️⃣ Updating child category...")
        update_result = await db.categories.update_one(
            {"_id": child_id},
            {"$set": {
                "description": "Updated child category description",
                "updated_at": datetime.utcnow()
            }}
        )
        print(f"✅ Child category updated (modified {update_result.modified_count} document)")
        
        # 5. Verify parent category was still not modified
        print("\n5️⃣ Checking if parent category was modified after child update...")
        updated_parent = await db.categories.find_one({"_id": parent_id})
        updated_parent_updated_at = updated_parent["updated_at"]
        print(f"📅 Parent updated_at after child update: {updated_parent_updated_at}")
        
        if initial_parent_updated_at == updated_parent_updated_at:
            print("✅ SUCCESS: Parent category was NOT modified when child was updated")
        else:
            print("❌ FAILURE: Parent category was modified when child was updated")
            return False
        
        # 6. Clean up test data
        print("\n6️⃣ Cleaning up test data...")
        await db.categories.delete_many({"_id": {"$in": [parent_id, child_id]}})
        print("✅ Test data cleaned up")
        
        print("\n🎉 ALL TESTS PASSED: Category parent isolation is working correctly!")
        return True
        
    except Exception as e:
        print(f"\n❌ TEST FAILED with error: {e}")
        return False


async def main():
    """Main test function"""
    success = await test_category_parent_isolation()
    if not success:
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
