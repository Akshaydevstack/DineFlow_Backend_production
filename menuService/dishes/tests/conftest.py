import pytest
from rest_framework.test import APIClient

@pytest.fixture
def api_client():
    return APIClient()

@pytest.fixture
def gateway_headers():
    return {
        "HTTP_X_USER_ID": "user_123",
        "HTTP_X_USER_ROLE": "customer",
        "HTTP_X_USER_EMAIL": "test@example.com",
    }

@pytest.fixture
def admin_headers():
    return {
        "HTTP_X_USER_ID": "admin_1",
        "HTTP_X_USER_ROLE": "admin",
        "HTTP_X_USER_EMAIL": "admin@example.com",
    }