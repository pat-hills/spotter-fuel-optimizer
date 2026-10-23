import pytest
from rest_framework.test import APIClient

@pytest.mark.django_db
def test_missing_locations_are_rejected():
    response = APIClient().post("/api/v1/fuel-plans/optimize/", {}, format="json")
    assert response.status_code == 400
    assert "error" in response.data
