import pytest

@pytest.mark.django_db
def test_menu_health(api_client):
    res = api_client.get("/health/")
    assert res.status_code == 200