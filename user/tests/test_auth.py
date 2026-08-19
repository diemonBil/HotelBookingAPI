import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework.throttling import ScopedRateThrottle

pytestmark = pytest.mark.django_db

REGISTER_URL = reverse("user:register")
LOGIN_URL = reverse("user:token_obtain_pair")
REFRESH_URL = reverse("user:token_refresh")
ME_URL = reverse("user:me")

VALID_PAYLOAD = {
    "username": "newguest",
    "email": "newguest@example.com",
    "password": "Sup3rSecret!pass",
}


def test_registration_creates_a_user_with_a_hashed_password(api_client):
    response = api_client.post(REGISTER_URL, VALID_PAYLOAD)

    assert response.status_code == 201
    assert "password" not in response.data
    created = get_user_model().objects.get(username="newguest")
    assert created.password != VALID_PAYLOAD["password"]
    assert created.check_password(VALID_PAYLOAD["password"])


@pytest.mark.parametrize(
    "password",
    [
        pytest.param("abc12", id="too-short"),
        pytest.param("password", id="too-common"),
        pytest.param("83741926", id="numeric-only"),
    ],
)
def test_weak_passwords_are_rejected(api_client, password):
    """Regression: min_length=5 bypassed AUTH_PASSWORD_VALIDATORS entirely."""
    response = api_client.post(REGISTER_URL, {**VALID_PAYLOAD, "password": password})
    assert response.status_code == 400
    assert "password" in response.data


def test_email_is_required(api_client):
    payload = {k: v for k, v in VALID_PAYLOAD.items() if k != "email"}
    response = api_client.post(REGISTER_URL, payload)
    assert response.status_code == 400
    assert "email" in response.data


def test_email_must_be_unique(api_client, user):
    response = api_client.post(REGISTER_URL, {**VALID_PAYLOAD, "email": user.email})
    assert response.status_code == 400
    assert "email" in response.data


def test_new_user_is_not_staff(api_client):
    api_client.post(REGISTER_URL, {**VALID_PAYLOAD, "is_staff": True})
    assert get_user_model().objects.get(username="newguest").is_staff is False


def test_login_returns_a_token_pair(api_client, user):
    response = api_client.post(
        LOGIN_URL, {"username": user.username, "password": "Sup3rSecret!pass"}
    )
    assert response.status_code == 200
    assert {"access", "refresh"} <= set(response.data)


def test_login_with_a_wrong_password_fails(api_client, user):
    response = api_client.post(LOGIN_URL, {"username": user.username, "password": "nope"})
    assert response.status_code == 401


def test_refresh_returns_a_new_access_token(api_client, user):
    refresh = api_client.post(
        LOGIN_URL, {"username": user.username, "password": "Sup3rSecret!pass"}
    ).data["refresh"]

    response = api_client.post(REFRESH_URL, {"refresh": refresh})
    assert response.status_code == 200
    assert "access" in response.data


def test_access_token_authenticates_requests(api_client, user):
    access = api_client.post(
        LOGIN_URL, {"username": user.username, "password": "Sup3rSecret!pass"}
    ).data["access"]

    api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {access}")
    response = api_client.get(ME_URL)
    assert response.status_code == 200
    assert response.data["username"] == user.username


def test_me_requires_authentication(api_client):
    assert api_client.get(ME_URL).status_code == 401


def test_user_can_change_their_password(auth_client, user):
    response = auth_client.patch(ME_URL, {"password": "An0ther!Passphrase"})
    assert response.status_code == 200
    user.refresh_from_db()
    assert user.check_password("An0ther!Passphrase")


def test_user_cannot_promote_themselves(auth_client, user):
    auth_client.patch(ME_URL, {"is_staff": True})
    user.refresh_from_db()
    assert user.is_staff is False


def test_registration_is_rate_limited(api_client, monkeypatch):
    """Regression: /register and /login had no throttling at all."""
    # SimpleRateThrottle reads THROTTLE_RATES once, when the class is defined,
    # so override_settings would not reach it.
    monkeypatch.setattr(ScopedRateThrottle, "THROTTLE_RATES", {"auth": "2/min"})

    for index in range(2):
        response = api_client.post(
            REGISTER_URL,
            {**VALID_PAYLOAD, "username": f"user{index}", "email": f"user{index}@example.com"},
        )
        assert response.status_code == 201

    response = api_client.post(
        REGISTER_URL, {**VALID_PAYLOAD, "username": "user3", "email": "user3@example.com"}
    )
    assert response.status_code == 429
