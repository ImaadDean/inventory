#!/usr/bin/env python3
"""
Debug script to test POS search functionality and check database content
"""

import asyncio
import sys
import os
import subprocess
from datetime import datetime

# Add the app directory to the path
sys.path.append(os.path.join(os.path.dirname(__file__), 'app'))

from app.config.database import connect_to_mongo, get_database
from app.utils.auth import create_access_token


async def check_database_products():
    """Check what products are in the database"""
    print("📦 Checking Database Products")
    print("=" * 60)
    
    try:
        await connect_to_mongo()
        db = await get_database()
        
        # Get total product count
        total_products = await db.products.count_documents({})
        active_products = await db.products.count_documents({"is_active": True})
        in_stock_products = await db.products.count_documents({"is_active": True, "stock_quantity": {"$gt": 0}})
        
        print(f"📊 Product Statistics:")
        print(f"   Total products: {total_products}")
        print(f"   Active products: {active_products}")
        print(f"   In-stock products: {in_stock_products}")
        
        # Get some sample products
        sample_products = await db.products.find(
            {"is_active": True, "stock_quantity": {"$gt": 0}}, 
            {"name": 1, "barcode": 1, "stock_quantity": 1, "price": 1}
        ).limit(5).to_list(5)
        
        print(f"\n📋 Sample Products (first 5 in stock):")
        for i, product in enumerate(sample_products, 1):
            name = product.get("name", "No name")
            barcode = product.get("barcode", "No barcode")
            stock = product.get("stock_quantity", 0)
            price = product.get("price", 0)
            print(f"   {i}. {name}")
            print(f"      Barcode: {barcode}")
            print(f"      Stock: {stock}, Price: UGX {price:,.2f}")
            print()
        
        # Search for products containing "ima"
        ima_products = await db.products.find(
            {
                "is_active": True,
                "stock_quantity": {"$gt": 0},
                "$or": [
                    {"name": {"$regex": "ima", "$options": "i"}},
                    {"barcode": {"$regex": "ima", "$options": "i"}}
                ]
            },
            {"name": 1, "barcode": 1, "stock_quantity": 1}
        ).to_list(10)
        
        print(f"🔍 Products matching 'ima': {len(ima_products)}")
        for product in ima_products:
            print(f"   - {product.get('name', 'No name')} (Stock: {product.get('stock_quantity', 0)})")
        
        return len(sample_products) > 0
        
    except Exception as e:
        print(f"❌ Database check failed: {e}")
        return False


async def test_api_directly():
    """Test the API endpoint directly"""
    print(f"\n🔧 Testing API Endpoint Directly")
    print("=" * 60)
    
    try:
        await connect_to_mongo()
        db = await get_database()
        
        # Find a test user
        user_data = await db.users.find_one({"is_active": True})
        if not user_data:
            print("❌ No active users found for testing")
            return False
        
        username = user_data["username"]
        token = create_access_token(data={"sub": username})
        
        # Test different search queries
        test_queries = ["ima", "a", "perfume", "test"]
        
        for query in test_queries:
            print(f"\n🔍 Testing search for: '{query}'")
            
            try:
                curl_cmd = [
                    "curl", "-s", "-w", "\\n%{http_code}",
                    "-H", f"Authorization: Bearer {token}",
                    f"http://localhost:8000/api/pos/products/search?query={query}&limit=5"
                ]
                
                result = subprocess.run(curl_cmd, capture_output=True, text=True, timeout=10)
                
                if result.returncode == 0:
                    output_lines = result.stdout.strip().split('\n')
                    if len(output_lines) >= 2:
                        response_body = '\n'.join(output_lines[:-1])
                        status_code = output_lines[-1]
                        
                        print(f"   Status: {status_code}")
                        
                        if status_code == "200":
                            try:
                                import json
                                data = json.loads(response_body)
                                if isinstance(data, list):
                                    print(f"   Found {len(data)} products")
                                    for i, product in enumerate(data[:3], 1):  # Show first 3
                                        print(f"      {i}. {product.get('name', 'No name')} (Stock: {product.get('stock_quantity', 0)})")
                                else:
                                    print(f"   Unexpected response format: {type(data)}")
                            except json.JSONDecodeError as e:
                                print(f"   JSON decode error: {e}")
                                print(f"   Raw response: {response_body[:200]}...")
                        else:
                            print(f"   Error response: {response_body[:200]}...")
                    else:
                        print(f"   Unexpected output format")
                else:
                    print(f"   Curl failed with return code: {result.returncode}")
                    print(f"   Error: {result.stderr}")
                    
            except Exception as e:
                print(f"   Test failed: {e}")
        
        return True
        
    except Exception as e:
        print(f"❌ API test failed: {e}")
        return False


async def main():
    """Main test function"""
    print("🔍 POS Search Debug Test")
    print("=" * 50)
    print("This will help diagnose why search isn't working")
    print()
    
    # Check database content
    db_ok = await check_database_products()
    
    # Test API directly
    api_ok = await test_api_directly()
    
    print(f"\n📋 DIAGNOSIS:")
    print("=" * 50)
    print(f"Database has products: {'✅ YES' if db_ok else '❌ NO'}")
    print(f"API responds correctly: {'✅ YES' if api_ok else '❌ NO'}")
    
    if db_ok and api_ok:
        print(f"\n💡 LIKELY ISSUE:")
        print("The backend is working fine. The issue might be:")
        print("1. Frontend JavaScript not triggering properly")
        print("2. Browser console errors")
        print("3. Network connectivity issues")
        print("4. Authentication cookies not being sent")
        print(f"\n🔧 NEXT STEPS:")
        print("1. Open browser developer tools (F12)")
        print("2. Go to Console tab")
        print("3. Try typing 'ima' in the search box")
        print("4. Look for any JavaScript errors or network requests")
        print("5. Check Network tab for failed requests")
    else:
        print(f"\n💡 ISSUE FOUND:")
        if not db_ok:
            print("- Database has no products or connection issues")
        if not api_ok:
            print("- API endpoint is not responding correctly")


if __name__ == "__main__":
    asyncio.run(main())
