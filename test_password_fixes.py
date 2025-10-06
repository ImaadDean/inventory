#!/usr/bin/env python3
"""
Test script to verify password length fixes and bcrypt compatibility.
"""

import sys
import os

# Add the app directory to the Python path
sys.path.append(os.path.join(os.path.dirname(__file__), 'app'))

from app.utils.auth import get_password_hash, verify_password


def test_password_length_handling():
    """Test that passwords longer than 72 bytes are properly handled"""
    print("Testing password length handling...")
    
    # Test with a short password
    short_password = "short123"
    hashed_short = get_password_hash(short_password)
    assert verify_password(short_password, hashed_short), "Short password verification failed"
    print("✓ Short password test passed")
    
    # Test with a password exactly 72 bytes
    password_72_bytes = "a" * 72
    hashed_72 = get_password_hash(password_72_bytes)
    assert verify_password(password_72_bytes, hashed_72), "72-byte password verification failed"
    print("✓ 72-byte password test passed")
    
    # Test with a password longer than 72 bytes
    long_password = "a" * 100
    hashed_long = get_password_hash(long_password)
    
    # The verification should work with the full long password (as it gets truncated)
    assert verify_password(long_password, hashed_long), "Long password verification failed"
    
    # But it should also work with just the first 72 characters
    assert verify_password("a" * 72, hashed_long), "Truncated password verification failed"
    print("✓ Long password truncation test passed")
    
    print("All password length tests passed!")


def test_unicode_passwords():
    """Test password handling with unicode characters"""
    print("\nTesting unicode password handling...")
    
    # Test with unicode characters
    unicode_password = "pässwörd123"
    hashed_unicode = get_password_hash(unicode_password)
    assert verify_password(unicode_password, hashed_unicode), "Unicode password verification failed"
    print("✓ Unicode password test passed")
    
    # Test with unicode characters that make the byte representation longer
    unicode_long = "🚀" * 50  # Each rocket emoji is multiple bytes
    hashed_unicode_long = get_password_hash(unicode_long)
    assert verify_password(unicode_long, hashed_unicode_long), "Long unicode password verification failed"
    print("✓ Long unicode password test passed")
    
    print("All unicode password tests passed!")


def main():
    """Main test function"""
    print("Password Fix Verification Tests")
    print("=" * 35)
    
    try:
        test_password_length_handling()
        test_unicode_passwords()
        print("\n🎉 All tests passed! Password fixes are working correctly.")
        return True
    except Exception as e:
        print(f"\n❌ Test failed with error: {e}")
        return False


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)