#!/usr/bin/env python3
"""
Test script for the forgot password functionality
This script demonstrates how the email checking works
"""

import asyncio
import sys
import os

# Add the app directory to the Python path
sys.path.append(os.path.join(os.path.dirname(__file__), 'app'))

from app.utils.auth import check_email_exists, get_user_by_email
from app.config.database import connect_to_mongo, get_database


async def test_email_checking():
    """Test the email checking functionality"""
    
    # Connect to database
    await connect_to_mongo()
    
    # Test emails
    test_emails = [
        "existing@example.com",  # Replace with an actual email from your database
        "nonexistent@example.com",  # This should not exist
        "admin@example.com",  # Replace with another actual email
        "fake@test.com"  # This should not exist
    ]
    
    print("🔍 Testing Email Existence Check")
    print("=" * 50)
    
    for email in test_emails:
        print(f"\n📧 Testing email: {email}")
        
        # Fast check if email exists
        exists = await check_email_exists(email)
        print(f"   ✅ Email exists: {exists}")
        
        if exists:
            # Get user details if email exists
            user = await get_user_by_email(email)
            if user:
                print(f"   👤 User found: {user.full_name} ({user.username})")
                print(f"   🔒 Account active: {user.is_active}")
            else:
                print("   ❌ Error: Email exists but user not found")
        else:
            print("   ❌ Email not found in database")


async def simulate_forgot_password_flow(email: str):
    """Simulate the forgot password flow for a given email"""
    
    print(f"\n🔄 Simulating forgot password flow for: {email}")
    print("-" * 60)
    
    # Step 1: Check if email exists
    email_exists = await check_email_exists(email)
    
    if not email_exists:
        print("❌ RESULT: Email does not exist in our system.")
        print("   MESSAGE: Please check your email address and try again.")
        print("   STATUS: email_not_found")
        print("   📧 NO EMAIL SENT")
        return False
    
    # Step 2: Get user details
    user = await get_user_by_email(email)
    
    if not user:
        print("❌ RESULT: Email does not exist in our system.")
        print("   MESSAGE: Please check your email address and try again.")
        print("   STATUS: email_not_found")
        print("   📧 NO EMAIL SENT")
        return False
    
    # Step 3: Check if user is active
    if not user.is_active:
        print("❌ RESULT: Email exists but account is inactive.")
        print("   MESSAGE: Please contact your administrator.")
        print("   STATUS: account_inactive")
        print("   📧 NO EMAIL SENT")
        return False
    
    # Step 4: Success - would send email in real implementation
    print("✅ RESULT: Email exists in our system and user is active.")
    print(f"   MESSAGE: Password reset link would be sent to {email}")
    print(f"   USER: {user.full_name} ({user.username})")
    print("   STATUS: email_sent")
    print("   📧 EMAIL SENT SUCCESSFULLY")

    return True


async def main():
    """Main test function"""
    
    print("🚀 Forgot Password Email Checking Test")
    print("=" * 60)
    
    try:
        # Connect to database
        await connect_to_mongo()
        
        # Test basic email checking
        await test_email_checking()
        
        print("\n" + "=" * 60)
        print("🧪 FORGOT PASSWORD FLOW SIMULATION")
        print("=" * 60)
        
        # Test forgot password flow with different scenarios
        test_scenarios = [
            "existing@example.com",  # Replace with actual email
            "nonexistent@example.com",  # Non-existent email
            "admin@example.com"  # Replace with another actual email
        ]
        
        for email in test_scenarios:
            await simulate_forgot_password_flow(email)
        
        print("\n" + "=" * 60)
        print("✅ Test completed successfully!")
        
    except Exception as e:
        print(f"❌ Error during testing: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    # Run the test
    asyncio.run(main())
