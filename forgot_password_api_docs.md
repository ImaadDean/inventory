# Forgot Password API Documentation

## Overview
The forgot password functionality has been updated to provide clear feedback about email existence in the database. This allows users to know immediately if they've entered the correct email address.

## API Endpoint

### POST `/api/auth/forgot-password`

**Description:** Initiates password reset process by checking if email exists and sending reset link.

**Request Body:**
```json
{
    "email": "user@example.com"
}
```

**Response Scenarios:**

#### 1. Email Found & Reset Email Sent (Success)
**Status Code:** `200 OK`
```json
{
    "message": "Email exists in our system. Password reset link has been sent successfully. Please check your email inbox.",
    "email": "user@example.com",
    "status": "email_sent"
}
```

#### 2. Email Not Found (No Email Sent)
**Status Code:** `200 OK`
```json
{
    "message": "Email does not exist in our system. Please check your email address and try again.",
    "email": "user@example.com",
    "status": "email_not_found"
}
```

#### 3. Account Inactive (No Email Sent)
**Status Code:** `200 OK`
```json
{
    "message": "Email exists but account is inactive. Please contact your administrator.",
    "email": "user@example.com",
    "status": "account_inactive"
}
```

#### 4. Server Error
**Status Code:** `500 Internal Server Error`
```json
{
    "detail": "Internal server error"
}
```

## Implementation Details

### Database Functions Added

1. **`check_email_exists(email: str) -> bool`**
   - Fast check if email exists in database
   - Uses `count_documents()` with limit=1 for efficiency
   - Returns boolean without loading user data

2. **`get_user_by_email(email: str) -> Optional[User]`**
   - Retrieves complete user object by email
   - Returns None if user not found
   - Used after confirming email exists

### Security Considerations

**Previous Behavior:**
- Always returned the same message regardless of email existence
- Followed security best practice of not revealing user information

**New Behavior:**
- Explicitly tells users if email doesn't exist
- Provides better user experience
- Trade-off: Slightly less secure as it reveals email existence

### Usage Examples

#### Frontend JavaScript Example
```javascript
async function forgotPassword(email) {
    try {
        const response = await fetch('/api/auth/forgot-password', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({ email: email })
        });

        const data = await response.json();

        if (response.ok) {
            // Check the status field to determine what happened
            if (data.status === 'email_sent') {
                showSuccess('Email exists! Reset link sent to your inbox.');
            } else if (data.status === 'email_not_found') {
                showError('Email does not exist. Please check your email address.');
            } else if (data.status === 'account_inactive') {
                showError('Account is inactive. Contact administrator.');
            }
        } else {
            // Validation or other errors
            showError('Please check your email format and try again.');
        }
    } catch (error) {
        showError('Network error. Please try again.');
    }
}
```

#### Python Client Example
```python
import requests

def forgot_password(email):
    url = "http://your-api-url/api/auth/forgot-password"
    payload = {"email": email}

    response = requests.post(url, json=payload)

    if response.status_code == 200:
        data = response.json()
        status = data.get('status', '')

        if status == 'email_sent':
            print("✅ Email exists! Reset link sent successfully!")
            return True
        elif status == 'email_not_found':
            print("❌ Email does not exist in system")
            return False
        elif status == 'account_inactive':
            print("❌ Account is inactive")
            return False
        else:
            print(f"❌ Unknown status: {status}")
            return False
    else:
        print(f"❌ Error: {response.json().get('detail', 'Unknown error')}")
        return False
```

## Testing

Use the provided `test_forgot_password.py` script to test the functionality:

```bash
python test_forgot_password.py
```

This script will:
1. Test email existence checking
2. Simulate forgot password flows
3. Show different response scenarios

## Benefits

1. **Better User Experience:** Users know immediately if they've entered the wrong email
2. **Faster Processing:** Quick email existence check before processing
3. **Clear Error Messages:** Specific feedback for different scenarios
4. **Efficient Database Queries:** Uses optimized queries for email checking

## Migration Notes

- No database schema changes required
- Backward compatible with existing reset tokens
- Email templates remain unchanged
- Only API response behavior has changed
