import requests

# Test category system
session = requests.Session()

# Login first
login_data = {
    "username": "imaad",
    "password": "Ertdfgx@0"
}

print("Testing category system...")

try:
    # Login
    login_response = session.post("http://localhost:8000/auth/login", data=login_data, allow_redirects=False)
    print(f"Login Status: {login_response.status_code}")

    if login_response.status_code == 302:
        print("✅ Login successful")

        # Test category page
        categories_response = session.get("http://localhost:8000/categories/", allow_redirects=False)
        if categories_response.status_code == 200:
            print("✅ Categories page: Working (Status 200)")
        else:
            print(f"❌ Categories page: Error (Status {categories_response.status_code})")

        # Test category API
        api_response = session.get("http://localhost:8000/api/categories/", allow_redirects=False)
        if api_response.status_code == 200:
            print("✅ Categories API: Working (Status 200)")
            categories = api_response.json()
            print(f"   Found {len(categories)} categories")
        else:
            print(f"❌ Categories API: Error (Status {api_response.status_code})")

        # Test creating a category
        new_category = {
            "name": "Electronics",
            "description": "Electronic devices and accessories",
            "is_active": True
        }

        create_response = session.post("http://localhost:8000/api/categories/", json=new_category)
        if create_response.status_code == 201:
            print("✅ Create category: Working (Status 201)")
            created_category = create_response.json()
            print(f"   Created category: {created_category['name']}")
        elif create_response.status_code == 400:
            print("⚠️  Create category: Category already exists (Status 400)")
        else:
            print(f"❌ Create category: Error (Status {create_response.status_code})")
            print(f"   Response: {create_response.text}")

    else:
        print(f"❌ Login failed: {login_response.status_code}")

except Exception as e:
    print(f"Error: {e}")