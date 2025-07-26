import requests

# First, login to get the authentication cookie
login_data = {
    "username": "imaad",
    "password": "Ertdfgx@0"
}

print("Testing login and dashboard access...")

try:
    # Create a session to maintain cookies
    session = requests.Session()

    # Login
    login_response = session.post("http://localhost:8000/auth/login", data=login_data, allow_redirects=False)
    print(f"Login Status: {login_response.status_code}")

    if login_response.status_code == 302:
        print("✅ Login successful (redirected)")
        print(f"Redirect Location: {login_response.headers.get('location')}")
        print(f"Cookies set: {session.cookies}")

        # Now try to access the dashboard
        dashboard_response = session.get("http://localhost:8000/dashboard/", allow_redirects=False)
        print(f"Dashboard Status: {dashboard_response.status_code}")

        if dashboard_response.status_code == 200:
            print("✅ Dashboard access successful!")
            print(f"Response length: {len(dashboard_response.text)}")
        elif dashboard_response.status_code == 302:
            print(f"Dashboard redirected to: {dashboard_response.headers.get('location')}")
        elif dashboard_response.status_code == 403:
            print("❌ Dashboard access forbidden (authentication issue)")
        else:
            print(f"❌ Unexpected dashboard status: {dashboard_response.status_code}")

    else:
        print(f"❌ Login failed with status: {login_response.status_code}")
        print(f"Response: {login_response.text[:200]}")

except Exception as e:
    print(f"Request failed: {e}")