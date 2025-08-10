#!/usr/bin/env python3
"""
Unit tests for the forgot password API functionality
"""

import pytest
import asyncio
from fastapi.testclient import TestClient
from unittest.mock import AsyncMock, patch
import sys
import os

# Add the app directory to the Python path
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'app'))

from app.main import app
from app.utils.auth import check_email_exists, get_user_by_email
from app.models import User, UserRole
from datetime import datetime


class TestForgotPasswordAPI:
    """Test class for forgot password API functionality"""
    
    def setup_method(self):
        """Setup test client"""
        self.client = TestClient(app)
        self.test_email_exists = "test@example.com"
        self.test_email_not_exists = "notfound@example.com"
        self.test_inactive_email = "inactive@example.com"
    
    @patch('app.routes.auth.api.check_email_exists')
    @patch('app.routes.auth.api.get_user_by_email')
    @patch('app.routes.auth.api.generate_reset_token')
    @patch('app.routes.auth.api.store_reset_token')
    @patch('app.routes.auth.api.send_password_reset_email')
    def test_forgot_password_success(self, mock_send_email, mock_store_token, 
                                   mock_generate_token, mock_get_user, mock_check_email):
        """Test successful forgot password flow"""
        
        # Mock return values
        mock_check_email.return_value = True
        mock_user = User(
            username="testuser",
            email=self.test_email_exists,
            full_name="Test User",
            hashed_password="hashed_password",
            role=UserRole.CASHIER,
            is_active=True,
            created_at=datetime.utcnow()
        )
        mock_get_user.return_value = mock_user
        mock_generate_token.return_value = "test_token_123"
        mock_store_token.return_value = True
        mock_send_email.return_value = True
        
        # Make request
        response = self.client.post(
            "/api/auth/forgot-password",
            json={"email": self.test_email_exists}
        )
        
        # Assertions
        assert response.status_code == 200
        data = response.json()
        assert "Email exists in our system" in data["message"]
        assert "Password reset link has been sent successfully" in data["message"]
        assert data["email"] == self.test_email_exists
        assert data["status"] == "email_sent"
        
        # Verify mocks were called
        mock_check_email.assert_called_once_with(self.test_email_exists)
        mock_get_user.assert_called_once_with(self.test_email_exists)
        mock_generate_token.assert_called_once()
        mock_store_token.assert_called_once()
        mock_send_email.assert_called_once()
    
    @patch('app.routes.auth.api.check_email_exists')
    def test_forgot_password_email_not_found(self, mock_check_email):
        """Test forgot password with non-existent email"""
        
        # Mock return values
        mock_check_email.return_value = False
        
        # Make request
        response = self.client.post(
            "/api/auth/forgot-password",
            json={"email": self.test_email_not_exists}
        )
        
        # Assertions
        assert response.status_code == 200
        data = response.json()
        assert "Email does not exist in our system" in data["message"]
        assert data["email"] == self.test_email_not_exists
        assert data["status"] == "email_not_found"
        
        # Verify mock was called
        mock_check_email.assert_called_once_with(self.test_email_not_exists)
    
    @patch('app.routes.auth.api.check_email_exists')
    @patch('app.routes.auth.api.get_user_by_email')
    def test_forgot_password_inactive_user(self, mock_get_user, mock_check_email):
        """Test forgot password with inactive user"""
        
        # Mock return values
        mock_check_email.return_value = True
        mock_user = User(
            username="inactiveuser",
            email=self.test_inactive_email,
            full_name="Inactive User",
            hashed_password="hashed_password",
            role=UserRole.CASHIER,
            is_active=False,  # Inactive user
            created_at=datetime.utcnow()
        )
        mock_get_user.return_value = mock_user
        
        # Make request
        response = self.client.post(
            "/api/auth/forgot-password",
            json={"email": self.test_inactive_email}
        )
        
        # Assertions
        assert response.status_code == 200
        data = response.json()
        assert "Email exists but account is inactive" in data["message"]
        assert data["email"] == self.test_inactive_email
        assert data["status"] == "account_inactive"
        
        # Verify mocks were called
        mock_check_email.assert_called_once_with(self.test_inactive_email)
        mock_get_user.assert_called_once_with(self.test_inactive_email)
    
    def test_forgot_password_invalid_email_format(self):
        """Test forgot password with invalid email format"""
        
        # Make request with invalid email
        response = self.client.post(
            "/api/auth/forgot-password",
            json={"email": "invalid-email"}
        )
        
        # Assertions
        assert response.status_code == 422  # Validation error
        data = response.json()
        assert "detail" in data
    
    def test_forgot_password_missing_email(self):
        """Test forgot password with missing email field"""
        
        # Make request without email
        response = self.client.post(
            "/api/auth/forgot-password",
            json={}
        )
        
        # Assertions
        assert response.status_code == 422  # Validation error
        data = response.json()
        assert "detail" in data
    
    @patch('app.routes.auth.api.check_email_exists')
    @patch('app.routes.auth.api.get_user_by_email')
    @patch('app.routes.auth.api.generate_reset_token')
    @patch('app.routes.auth.api.store_reset_token')
    def test_forgot_password_token_storage_failure(self, mock_store_token, mock_generate_token, 
                                                  mock_get_user, mock_check_email):
        """Test forgot password when token storage fails"""
        
        # Mock return values
        mock_check_email.return_value = True
        mock_user = User(
            username="testuser",
            email=self.test_email_exists,
            full_name="Test User",
            hashed_password="hashed_password",
            role=UserRole.CASHIER,
            is_active=True,
            created_at=datetime.utcnow()
        )
        mock_get_user.return_value = mock_user
        mock_generate_token.return_value = "test_token_123"
        mock_store_token.return_value = False  # Storage failure
        
        # Make request
        response = self.client.post(
            "/api/auth/forgot-password",
            json={"email": self.test_email_exists}
        )
        
        # Assertions
        assert response.status_code == 500
        data = response.json()
        assert "Failed to generate reset token" in data["detail"]
    
    @patch('app.routes.auth.api.check_email_exists')
    @patch('app.routes.auth.api.get_user_by_email')
    @patch('app.routes.auth.api.generate_reset_token')
    @patch('app.routes.auth.api.store_reset_token')
    @patch('app.routes.auth.api.send_password_reset_email')
    def test_forgot_password_email_sending_failure(self, mock_send_email, mock_store_token, 
                                                  mock_generate_token, mock_get_user, mock_check_email):
        """Test forgot password when email sending fails"""
        
        # Mock return values
        mock_check_email.return_value = True
        mock_user = User(
            username="testuser",
            email=self.test_email_exists,
            full_name="Test User",
            hashed_password="hashed_password",
            role=UserRole.CASHIER,
            is_active=True,
            created_at=datetime.utcnow()
        )
        mock_get_user.return_value = mock_user
        mock_generate_token.return_value = "test_token_123"
        mock_store_token.return_value = True
        mock_send_email.return_value = False  # Email sending failure
        
        # Make request
        response = self.client.post(
            "/api/auth/forgot-password",
            json={"email": self.test_email_exists}
        )
        
        # Assertions
        assert response.status_code == 500
        data = response.json()
        assert "Failed to send reset email" in data["detail"]


if __name__ == "__main__":
    # Run tests with pytest
    pytest.main([__file__, "-v"])
