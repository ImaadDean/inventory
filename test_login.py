import requests

# Test API login
api_data = {
    "username": "testuser",
    "password": "testpass123"
}

try:
    response = requests.post("http://localhost:8000/api/auth/login", json=api_data)
    print(f"API Login Status: {response.status_code}")
    if response.status_code == 200:
        result = response.json()
        print(f"API Login Success: {result['user']['username']} - Token: {result['access_token'][:20]}...")
    else:
        print(f"API Login Error: {response.json()}")
except Exception as e:
    print(f"API Login Error: {e}")

# Test form login
form_data = {
    "username": "testuser",
    "password": "testpass123"
}

try:
    response = requests.post("http://localhost:8000/auth/login", data=form_data, allow_redirects=False)
    print(f"Form Login Status: {response.status_code}")
    if response.status_code == 302:
        print(f"Form Login Success: Redirected to {response.headers.get('location')}")
        print(f"Cookie set: {response.cookies}")
    else:
        print(f"Form Login Response Length: {len(response.text)}")
except Exception as e:
    print(f"Form Login Error: {e}")