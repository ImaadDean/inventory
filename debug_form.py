import requests
import time

# Test form registration with unique data
unique_id = str(int(time.time()))
form_data = {
    "full_name": "Debug User",
    "username": f"debug{unique_id}",
    "email": f"debug{unique_id}@example.com",
    "password": "debug123",
    "confirm_password": "debug123"
}

print(f"Testing form registration with username: debug{unique_id}")

try:
    response = requests.post("http://localhost:8000/auth/register", data=form_data)
    print(f"Status Code: {response.status_code}")
    print(f"Headers: {dict(response.headers)}")
    print(f"Response Length: {len(response.text)}")

    if response.status_code == 302:
        print("SUCCESS: Redirected (registration successful)")
        print(f"Redirect Location: {response.headers.get('location')}")
    elif "error" in response.text.lower():
        # Extract error message from HTML
        import re
        error_match = re.search(r'<p class="text-sm text-red-800">(.*?)</p>', response.text)
        if error_match:
            print(f"ERROR: {error_match.group(1)}")
        else:
            print("ERROR: Unknown error in response")
    else:
        print("Response preview:")
        print(response.text[:1000])

        # Look for any error messages in the HTML
        if "Registration failed" in response.text:
            print("\nFound 'Registration failed' in response")
        if "error" in response.text:
            print("\nFound 'error' in response")

        # Try to extract any visible error text
        import re
        error_patterns = [
            r'Registration failed[^<]*',
            r'error[^<]*',
            r'Error[^<]*',
            r'<div[^>]*error[^>]*>([^<]+)</div>',
        ]

        for pattern in error_patterns:
            matches = re.findall(pattern, response.text, re.IGNORECASE)
            if matches:
                print(f"Found error pattern '{pattern}': {matches}")

except Exception as e:
    print(f"Request failed: {e}")