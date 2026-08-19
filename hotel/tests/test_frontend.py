"""The demo client is served by Django itself, so it is worth a smoke test."""

import pytest
from django.urls import reverse

pytestmark = pytest.mark.django_db


def test_home_serves_the_client(client):
    response = client.get(reverse("home"))
    assert response.status_code == 200
    body = response.content.decode()
    assert 'id="view"' in body
    # Both scripts must be referenced, through {% static %} rather than by hand.
    assert "js/api.js" in body
    assert "js/app.js" in body
    assert "css/app.css" in body


def test_home_needs_no_authentication(client):
    assert client.get("/").status_code == 200


def test_client_assets_are_discoverable_by_staticfiles():
    from django.contrib.staticfiles import finders

    for asset in ("css/app.css", "js/api.js", "js/app.js"):
        assert finders.find(asset), f"{asset} is not on the staticfiles path"
