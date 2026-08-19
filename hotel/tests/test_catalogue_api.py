"""The public catalogue: hotels, rooms, room types and amenities.

Regression suite for the old permission model, where every one of these
endpoints was staff-only and a guest could not even list hotels.
"""

from decimal import Decimal

import pytest
from django.urls import reverse

from hotel.models import Hotel, Review, Room

pytestmark = pytest.mark.django_db

HOTELS_URL = reverse("hotel-list")
ROOMS_URL = reverse("room-list")
ROOM_TYPES_URL = reverse("roomtype-list")
AMENITIES_URL = reverse("amenity-list")


@pytest.mark.parametrize("url_name", ["hotel-list", "room-list", "roomtype-list", "amenity-list"])
def test_catalogue_is_readable_by_anyone(api_client, url_name, hotel, room, amenity):
    response = api_client.get(reverse(url_name))
    assert response.status_code == 200


def test_guests_cannot_create_hotels(auth_client):
    response = auth_client.post(
        HOTELS_URL, {"name": "Fake Inn", "location": "Nowhere", "description": ""}
    )
    assert response.status_code == 403
    assert not Hotel.objects.filter(name="Fake Inn").exists()


def test_anonymous_cannot_create_hotels(api_client):
    response = api_client.post(HOTELS_URL, {"name": "Fake Inn", "location": "Nowhere"})
    assert response.status_code == 401


def test_staff_can_create_hotels(staff_client):
    response = staff_client.post(
        HOTELS_URL, {"name": "New Hotel", "location": "Lviv", "description": "Central."}
    )
    assert response.status_code == 201


def test_guests_cannot_delete_rooms(auth_client, room):
    response = auth_client.delete(reverse("room-detail", args=[room.id]))
    assert response.status_code == 403
    assert Room.objects.filter(pk=room.pk).exists()


def test_hotel_list_reports_ratings(api_client, hotel, user, other_user):
    Review.objects.create(user=user, hotel=hotel, rating=5, comment="Excellent.")
    Review.objects.create(user=other_user, hotel=hotel, rating=3, comment="Fine.")

    response = api_client.get(HOTELS_URL)
    entry = response.data["results"][0]
    assert entry["average_rating"] == 4.0
    assert entry["review_count"] == 2


def test_hotels_can_be_searched(api_client, hotel):
    Hotel.objects.create(name="Mountain Lodge", location="Bukovel", description="")

    response = api_client.get(HOTELS_URL, {"search": "Bukovel"})
    assert [item["name"] for item in response.data["results"]] == ["Mountain Lodge"]


def test_rooms_can_be_filtered_by_hotel(api_client, hotel, room, room_type):
    other_hotel = Hotel.objects.create(name="Other", location="Kyiv", description="")
    Room.objects.create(
        hotel=other_hotel,
        room_number=1,
        room_type=room_type,
        price_per_night=Decimal("70.00"),
        max_guests=1,
    )

    response = api_client.get(ROOMS_URL, {"hotel": hotel.id})
    assert response.data["count"] == 1


def test_room_list_query_count_is_bounded(
    api_client, django_assert_max_num_queries, hotel, room_type, amenity
):
    """Regression: rooms used to trigger a query per hotel, type and amenity."""
    for number in range(1, 11):
        created = Room.objects.create(
            hotel=hotel,
            room_number=number,
            room_type=room_type,
            price_per_night=Decimal("90.00"),
            max_guests=2,
        )
        created.amenities.add(amenity)

    with django_assert_max_num_queries(5):
        response = api_client.get(ROOMS_URL)
    assert response.data["count"] == 10


def test_results_are_paginated(api_client, hotel):
    response = api_client.get(HOTELS_URL)
    assert {"count", "next", "previous", "results"} <= set(response.data)
