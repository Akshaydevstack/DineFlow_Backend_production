import pytest
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient
from django.contrib.auth import get_user_model

User = get_user_model()


@pytest.mark.django_db
def test_user_registration_success(mocker):
    client = APIClient()

    # ✅ Mock Firebase verification
    mocker.patch(
        "firebase_admin.auth.verify_id_token",
        return_value={
            "uid": "firebase-uid-123",
            "phone_number": "+919999999999",
            "email": "testuser@example.com",
        }
    )

    url = reverse("register_user")

    payload = {
        "email": "testuser@example.com",
        "password": "StrongPass@123",
        "mobile_number": "+919999999999",
        "first_name": "Akshay",
        "firebase_token": "fake-firebase-token",
    }

    response = client.post(url, payload, format="json")

    assert response.status_code == status.HTTP_201_CREATED
    assert User.objects.filter(email="testuser@example.com").exists()