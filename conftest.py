"""Shared pytest fixtures.

Test settings live in ``HotelBookingAPI.settings_test``; pytest-django loads
them before this module is imported.
"""

from datetime import timedelta
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.utils import timezone
from rest_framework.test import APIClient

from hotel.models import Amenity, Hotel, Room, RoomType


@pytest.fixture(autouse=True)
def _clear_throttle_cache():
    """DRF stores throttle counters in the cache; keep tests independent."""
    cache.clear()
    yield
    cache.clear()


@pytest.fixture
def api_client():
    return APIClient()


@pytest.fixture
def user(db):
    return get_user_model().objects.create_user(
        username="guest", email="guest@example.com", password="Sup3rSecret!pass"
    )


@pytest.fixture
def other_user(db):
    return get_user_model().objects.create_user(
        username="other", email="other@example.com", password="Sup3rSecret!pass"
    )


@pytest.fixture
def staff_user(db):
    return get_user_model().objects.create_user(
        username="staff", email="staff@example.com", password="Sup3rSecret!pass", is_staff=True
    )


@pytest.fixture
def auth_client(api_client, user):
    api_client.force_authenticate(user=user)
    return api_client


@pytest.fixture
def staff_client(staff_user):
    # A separate client: sharing api_client would re-authenticate the very
    # instance a test is using to assert a non-staff response.
    client = APIClient()
    client.force_authenticate(user=staff_user)
    return client


@pytest.fixture
def amenity(db):
    return Amenity.objects.create(name="Free WiFi", description="Fast and free.")


@pytest.fixture
def hotel(db):
    return Hotel.objects.create(name="Seaside Grand", location="Odesa", description="By the beach.")


@pytest.fixture
def room_type(db):
    return RoomType.objects.create(name="Double", description="Fits two guests.")


@pytest.fixture
def room(hotel, room_type):
    return Room.objects.create(
        hotel=hotel,
        room_number=101,
        room_type=room_type,
        price_per_night=Decimal("100.00"),
        max_guests=2,
    )


@pytest.fixture
def stay_dates():
    """A two-night stay starting a week from today."""
    check_in = timezone.localdate() + timedelta(days=7)
    return check_in, check_in + timedelta(days=2)


@pytest.fixture
def booking_payload(hotel, room_type, stay_dates):
    check_in, check_out = stay_dates
    return {
        "hotel": hotel.id,
        "room_type": room_type.id,
        "check_in": check_in.isoformat(),
        "check_out": check_out.isoformat(),
        "adults": 2,
        "children": 0,
    }
