import pytest
from dishes.models import Category

@pytest.mark.django_db
def test_list_categories(api_client, gateway_headers):
    Category.objects.create(name="Starters")
    Category.objects.create(name="Main Course")

    res = api_client.get(
        "/api/menu/customer/categories/",
        **gateway_headers
    )

    assert res.status_code == 200
    assert len(res.data) == 4