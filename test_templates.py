import requests

# Test template access with authentication
session = requests.Session()

# Login first
login_data = {
    "username": "imaad",
    "password": "Ertdfgx@0"
}

print("Testing template access...")

try:
    # Login
    login_response = session.post("http://localhost:8000/auth/login", data=login_data, allow_redirects=False)
    print(f"Login Status: {login_response.status_code}")

    if login_response.status_code == 302:
        print("✅ Login successful")

        # Test each template
        templates_to_test = [
            ("/dashboard/", "Dashboard"),
            ("/products/", "Products"),
            ("/customers/", "Customers"),
            ("/users/", "Users"),
            ("/pos/", "POS")
        ]

        for url, name in templates_to_test:
            response = session.get(f"http://localhost:8000{url}", allow_redirects=False)
            if response.status_code == 200:
                print(f"✅ {name}: Working (Status 200)")
            elif response.status_code == 302:
                print(f"⚠️  {name}: Redirected (Status 302) to {response.headers.get('location')}")
            else:
                print(f"❌ {name}: Error (Status {response.status_code})")

    else:
        print(f"❌ Login failed: {login_response.status_code}")

except Exception as e:
    print(f"Error: {e}")