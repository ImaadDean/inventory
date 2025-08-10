#!/usr/bin/env python3
"""
Demo script showing the exact behavior of the forgot password functionality
"""

import requests
import json


def demo_forgot_password(base_url="http://localhost:8000"):
    """Demo the forgot password functionality"""
    
    print("🔐 FORGOT PASSWORD DEMO")
    print("=" * 60)
    print("This demo shows exactly what happens when users try to reset their password")
    print()
    
    # Test scenarios
    scenarios = [
        {
            "email": "existing@example.com",
            "description": "Email that EXISTS in database"
        },
        {
            "email": "notfound@example.com", 
            "description": "Email that DOES NOT EXIST in database"
        },
        {
            "email": "inactive@example.com",
            "description": "Email that exists but account is INACTIVE"
        }
    ]
    
    for i, scenario in enumerate(scenarios, 1):
        print(f"📧 SCENARIO {i}: {scenario['description']}")
        print(f"   Email: {scenario['email']}")
        print("-" * 50)
        
        # Make API call
        try:
            response = requests.post(
                f"{base_url}/api/auth/forgot-password",
                json={"email": scenario['email']},
                headers={"Content-Type": "application/json"}
            )
            
            print(f"   HTTP Status: {response.status_code}")
            
            if response.status_code == 200:
                data = response.json()
                status = data.get('status', 'unknown')
                message = data.get('message', 'No message')
                email = data.get('email', 'No email')
                
                print(f"   Status: {status}")
                print(f"   Message: {message}")
                print(f"   Email: {email}")
                
                if status == 'email_sent':
                    print("   🟢 RESULT: EMAIL EXISTS → RESET LINK SENT")
                elif status == 'email_not_found':
                    print("   🔴 RESULT: EMAIL DOES NOT EXIST → NO EMAIL SENT")
                elif status == 'account_inactive':
                    print("   🟡 RESULT: EMAIL EXISTS BUT INACTIVE → NO EMAIL SENT")
                else:
                    print(f"   ⚪ RESULT: UNKNOWN STATUS → {status}")
                    
            else:
                print(f"   Error: {response.text}")
                
        except Exception as e:
            print(f"   ❌ Connection Error: {e}")
        
        print()
    
    print("=" * 60)
    print("📋 SUMMARY:")
    print("✅ If email EXISTS and account is ACTIVE → Send reset email")
    print("❌ If email DOES NOT EXIST → Show 'email does not exist' message")
    print("⚠️  If email EXISTS but account INACTIVE → Show 'account inactive' message")
    print()
    print("🔑 KEY POINT: Email is ONLY sent when email exists AND account is active")


def show_api_responses():
    """Show what the API responses look like"""
    
    print("\n🔍 API RESPONSE EXAMPLES")
    print("=" * 60)
    
    print("1️⃣  EMAIL EXISTS AND ACTIVE (Email sent):")
    print(json.dumps({
        "message": "Email exists in our system. Password reset link has been sent successfully. Please check your email inbox.",
        "email": "user@example.com",
        "status": "email_sent"
    }, indent=2))
    
    print("\n2️⃣  EMAIL DOES NOT EXIST (No email sent):")
    print(json.dumps({
        "message": "Email does not exist in our system. Please check your email address and try again.",
        "email": "notfound@example.com", 
        "status": "email_not_found"
    }, indent=2))
    
    print("\n3️⃣  EMAIL EXISTS BUT INACTIVE (No email sent):")
    print(json.dumps({
        "message": "Email exists but account is inactive. Please contact your administrator.",
        "email": "inactive@example.com",
        "status": "account_inactive"
    }, indent=2))


def main():
    """Main function"""
    
    import argparse
    
    parser = argparse.ArgumentParser(description="Forgot Password Demo")
    parser.add_argument(
        "--url",
        default="http://localhost:8000", 
        help="API base URL"
    )
    parser.add_argument(
        "--responses-only",
        action="store_true",
        help="Only show response examples, don't make API calls"
    )
    
    args = parser.parse_args()
    
    if args.responses_only:
        show_api_responses()
    else:
        print("🚀 Starting forgot password demo...")
        print(f"📡 API URL: {args.url}")
        print()
        
        # Show what responses look like
        show_api_responses()
        
        # Demo the actual functionality
        demo_forgot_password(args.url)


if __name__ == "__main__":
    main()
