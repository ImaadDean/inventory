import requests
import time

# Test form registration with redirect handling
unique_id = str(int(time.time()))
form_data = {
    "full_name": "Final Test User",
    "username": f"final{unique_id}",
    "email": f"final{unique_id}@example.com",
    "password": "final123",
    "confirm_password": "final123"
}

print(f"Testing form registration with username: final{unique_id}")

try:
    # Test without following redirects
    response = requests.post("http://localhost:8000/auth/register", data=form_data, allow_redirects=False)
    print(f"Status Code (no redirect): {response.status_code}")

    if response.status_code == 302:
        print("✅ SUCCESS: Registration successful (redirected)")
        print(f"Redirect Location: {response.headers.get('location')}")
    else:
        print(f"❌ Unexpected status: {response.status_code}")

    # Test with following redirects
    response_with_redirect = requests.post("http://localhost:8000/auth/register", data=form_data)
    print(f"Status Code (with redirect): {response_with_redirect.status_code}")
    print(f"Final URL: {response_with_redirect.url}")

    if "registered=true" in response_with_redirect.url:
        print("✅ SUCCESS: Redirected to login page with success message")

except Exception as e:
    print(f"Request failed: {e}")