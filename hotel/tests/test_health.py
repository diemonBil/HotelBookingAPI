import pytest
from django.urls import reverse

HEALTH_URL = reverse("health")


@pytest.mark.django_db
def test_health_reports_ok(api_client):
    response = api_client.get(HEALTH_URL)
    assert response.status_code == 200
    assert response.data == {"status": "ok", "database": "ok"}


@pytest.mark.django_db
def test_health_is_public(api_client):
    assert api_client.get(HEALTH_URL).status_code == 200
