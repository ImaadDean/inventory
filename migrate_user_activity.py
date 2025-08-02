#!/usr/bin/env python3
"""
Migration script to add last_activity field to existing users
"""

import asyncio
import sys
import os
from datetime import datetime

# Add the app directory to the path
sys.path.append(os.path.join(os.path.dirname(__file__), 'app'))

from app.config.database import get_database
from app.utils.timezone import now_kampala, kampala_to_utc


async def migrate_user_activity():
    """Add last_activity field to all existing users"""
    print("🔄 Migrating user activity fields...")
    
    try:
        db = await get_database()
        users_collection = db.users
        
        # Get all users
        users = await users_collection.find({}).to_list(length=None)
        print(f"📊 Found {len(users)} users to migrate")
        
        updated_count = 0
        
        for user in users:
            user_id = user["_id"]
            username = user.get("username", "Unknown")
            
            # Check if user already has last_activity field
            if "last_activity" not in user:
                # Set last_activity to last_login if it exists, otherwise None
                last_activity = user.get("last_login")
                
                update_data = {"last_activity": last_activity}
                
                result = await users_collection.update_one(
                    {"_id": user_id},
                    {"$set": update_data}
                )
                
                if result.modified_count > 0:
                    updated_count += 1
                    status = "✅"
                    if last_activity:
                        activity_str = last_activity.strftime("%Y-%m-%d %H:%M:%S")
                    else:
                        activity_str = "None"
                else:
                    status = "❌"
                    activity_str = "Failed"
                
                print(f"   {status} {username}: last_activity = {activity_str}")
            else:
                print(f"   ⏭️  {username}: already has last_activity field")
        
        print(f"\n🎉 Migration completed!")
        print(f"   Updated {updated_count} users")
        print(f"   Total users: {len(users)}")
        
        # Verify the migration
        print(f"\n🔍 Verifying migration...")
        users_after = await users_collection.find({}).to_list(length=None)
        
        for user in users_after:
            username = user.get("username", "Unknown")
            last_login = user.get("last_login")
            last_activity = user.get("last_activity")
            
            print(f"   👤 {username}:")
            print(f"      last_login: {last_login.strftime('%Y-%m-%d %H:%M:%S') if last_login else 'None'}")
            print(f"      last_activity: {last_activity.strftime('%Y-%m-%d %H:%M:%S') if last_activity else 'None'}")
        
        return True
        
    except Exception as e:
        print(f"❌ Migration failed: {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_activity_status():
    """Test the activity status function with current user data"""
    print(f"\n🧪 Testing activity status calculation...")
    
    try:
        from app.utils.user_activity import get_detailed_user_status
        
        db = await get_database()
        users_collection = db.users
        
        users = await users_collection.find({}).to_list(length=None)
        
        for user in users:
            username = user.get("username", "Unknown")
            last_login = user.get("last_login")
            last_activity = user.get("last_activity")
            
            status_info = get_detailed_user_status(last_login, last_activity)
            
            print(f"   👤 {username}:")
            print(f"      Status: {status_info['status']}")
            print(f"      Display: {status_info['display_text']}")
            print(f"      Online: {status_info['is_online']}")
            print(f"      Tooltip: {status_info['tooltip']}")
            print()
        
    except Exception as e:
        print(f"❌ Test failed: {e}")
        import traceback
        traceback.print_exc()


async def main():
    """Main migration function"""
    print("🚀 User Activity Migration Script")
    print("=" * 50)
    
    # Run migration
    success = await migrate_user_activity()
    
    if success:
        # Test the activity status calculation
        await test_activity_status()
        print("✅ All operations completed successfully!")
    else:
        print("❌ Migration failed!")


if __name__ == "__main__":
    asyncio.run(main())
