import pytest
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient
from django.contrib.auth import get_user_model

User = get_user_model()


@pytest.mark.django_db
def test_user_login_success():
    client = APIClient()

    # Create user
    User.objects.create_user(
        email="loginuser@example.com",
        password="StrongPass@123",
        mobile_number="+919999999998",
        first_name="Login"
    )

    url = reverse("login_user")

    payload = {
        "mobile_number": "+919999999998",
        "password": "StrongPass@123",
    }

    response = client.post(url, payload, format="json")

    # ✅ Correct assertions (match API)
    assert response.status_code == status.HTTP_200_OK
    assert "access_token" in response.data
    assert response.data["message"] == "User logged in successfully"