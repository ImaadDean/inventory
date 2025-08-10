#!/usr/bin/env python3
"""
Integration test script for the forgot password API
This script tests the actual API endpoints with real HTTP requests
"""

import requests
import json
import time
from typing import Dict, Any


class ForgotPasswordIntegrationTest:
    """Integration test class for forgot password functionality"""
    
    def __init__(self, base_url: str = "http://localhost:8000"):
        self.base_url = base_url.rstrip('/')
        self.api_url = f"{self.base_url}/api/auth"
        
    def test_forgot_password_endpoint(self, email: str) -> Dict[str, Any]:
        """Test the forgot password endpoint with a given email"""
        
        url = f"{self.api_url}/forgot-password"
        payload = {"email": email}
        
        print(f"\n🔄 Testing forgot password for: {email}")
        print(f"   URL: {url}")
        print(f"   Payload: {json.dumps(payload, indent=2)}")
        
        try:
            response = requests.post(
                url,
                json=payload,
                headers={"Content-Type": "application/json"},
                timeout=10
            )
            
            print(f"   Status Code: {response.status_code}")
            
            try:
                response_data = response.json()
                print(f"   Response: {json.dumps(response_data, indent=2)}")
            except json.JSONDecodeError:
                print(f"   Response (raw): {response.text}")
                response_data = {"error": "Invalid JSON response"}
            
            return {
                "status_code": response.status_code,
                "data": response_data,
                "success": response.status_code == 200  # All responses are now 200 with different status fields
            }
            
        except requests.exceptions.RequestException as e:
            print(f"   ❌ Request failed: {e}")
            return {
                "status_code": None,
                "data": {"error": str(e)},
                "success": False
            }
    
    def test_api_health(self) -> bool:
        """Test if the API is running and accessible"""
        
        try:
            url = f"{self.api_url}/ping"
            response = requests.get(url, timeout=5)
            
            if response.status_code == 200:
                print(f"✅ API is accessible at {self.base_url}")
                return True
            else:
                print(f"❌ API returned status {response.status_code}")
                return False
                
        except requests.exceptions.RequestException as e:
            print(f"❌ Cannot connect to API at {self.base_url}: {e}")
            return False
    
    def run_comprehensive_test(self):
        """Run comprehensive tests with different scenarios"""
        
        print("🚀 Forgot Password Integration Test")
        print("=" * 60)
        
        # Check API health first
        if not self.test_api_health():
            print("\n❌ API is not accessible. Please ensure the server is running.")
            return
        
        # Test scenarios
        test_scenarios = [
            {
                "name": "Valid email (if exists in DB)",
                "email": "admin@example.com",
                "expected_codes": [200],  # Always 200, check status field
                "expected_status": ["email_sent", "email_not_found"]
            },
            {
                "name": "Another valid email format",
                "email": "user@test.com",
                "expected_codes": [200],
                "expected_status": ["email_sent", "email_not_found"]
            },
            {
                "name": "Non-existent email",
                "email": "definitely-not-exists@nowhere.com",
                "expected_codes": [200],
                "expected_status": ["email_not_found"]
            },
            {
                "name": "Invalid email format",
                "email": "invalid-email",
                "expected_codes": [422],  # Validation error
                "expected_status": []
            },
            {
                "name": "Empty email",
                "email": "",
                "expected_codes": [422],  # Validation error
                "expected_status": []
            }
        ]
        
        results = []
        
        print(f"\n📋 Running {len(test_scenarios)} test scenarios...")
        
        for i, scenario in enumerate(test_scenarios, 1):
            print(f"\n--- Test {i}: {scenario['name']} ---")
            
            result = self.test_forgot_password_endpoint(scenario['email'])
            
            # Check if result matches expected codes
            expected_codes = scenario['expected_codes']
            expected_status = scenario.get('expected_status', [])
            actual_code = result['status_code']
            actual_status = result['data'].get('status', '') if isinstance(result['data'], dict) else ''

            code_match = actual_code in expected_codes
            status_match = not expected_status or actual_status in expected_status

            if code_match and status_match:
                print(f"   ✅ PASS: Status code {actual_code}, status '{actual_status}'")
                result['test_passed'] = True
            else:
                print(f"   ❌ FAIL: Status code {actual_code} (expected {expected_codes}), status '{actual_status}' (expected {expected_status})")
                result['test_passed'] = False
            
            result['scenario'] = scenario['name']
            results.append(result)
            
            # Small delay between requests
            time.sleep(0.5)
        
        # Summary
        print(f"\n" + "=" * 60)
        print("📊 TEST SUMMARY")
        print("=" * 60)
        
        passed = sum(1 for r in results if r.get('test_passed', False))
        total = len(results)
        
        print(f"Total tests: {total}")
        print(f"Passed: {passed}")
        print(f"Failed: {total - passed}")
        print(f"Success rate: {(passed/total)*100:.1f}%")
        
        # Detailed results
        print(f"\n📋 DETAILED RESULTS:")
        for i, result in enumerate(results, 1):
            status = "✅ PASS" if result.get('test_passed', False) else "❌ FAIL"
            print(f"{i}. {result['scenario']}: {status} (HTTP {result['status_code']})")
        
        return results


def main():
    """Main function to run the integration tests"""
    
    import argparse
    
    parser = argparse.ArgumentParser(description="Forgot Password Integration Test")
    parser.add_argument(
        "--url", 
        default="http://localhost:8000",
        help="Base URL of the API (default: http://localhost:8000)"
    )
    parser.add_argument(
        "--email",
        help="Test a specific email address"
    )
    
    args = parser.parse_args()
    
    tester = ForgotPasswordIntegrationTest(args.url)
    
    if args.email:
        # Test specific email
        print(f"🎯 Testing specific email: {args.email}")
        result = tester.test_forgot_password_endpoint(args.email)
        
        if result['success']:
            print("✅ Test completed successfully")
        else:
            print("❌ Test failed")
    else:
        # Run comprehensive tests
        tester.run_comprehensive_test()


if __name__ == "__main__":
    main()
