import pytest

@pytest.mark.django_db
def test_missing_gateway_headers_still_works(api_client):
    res = api_client.get("/api/menu/customer/categories/")
    assert res.status_code == 200