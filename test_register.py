import requests

# Test API registration
import time
unique_id = str(int(time.time()))
api_data = {
    "username": f"testuser{unique_id}",
    "email": f"test{unique_id}@example.com",
    "full_name": "Test User",
    "password": "testpass123",
    "role": "cashier"
}

try:
    response = requests.post("http://localhost:8000/api/auth/register", json=api_data)
    print(f"API Registration Status: {response.status_code}")
    print(f"API Response: {response.json()}")
except Exception as e:
    print(f"API Error: {e}")

# Test form registration
form_data = {
    "full_name": "Imaad Dean",
    "username": f"imaad{unique_id}",
    "email": f"imaad{unique_id}@example.com",
    "password": "Ertdfgx@0",
    "confirm_password": "Ertdfgx@0"
}

try:
    response = requests.post("http://localhost:8000/auth/register", data=form_data)
    print(f"Form Registration Status: {response.status_code}")
    print(f"Form Response Length: {len(response.text)}")
    if response.status_code != 200:
        print(f"Form Response: {response.text[:500]}")
except Exception as e:
    print(f"Form Error: {e}")