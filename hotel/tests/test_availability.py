from datetime import timedelta
from decimal import Decimal

import pytest
from django.urls import reverse

from hotel.models import Booking, Room, RoomType
from hotel.services import available_room_types, find_available_rooms

pytestmark = pytest.mark.django_db


def _book(user, hotel, room, check_in, check_out, status=Booking.Status.PENDING):
    booking = Booking.objects.create(
        user=user,
        hotel=hotel,
        check_in=check_in,
        check_out=check_out,
        adults=1,
        status=status,
    )
    booking.rooms.add(room)
    return booking


def test_free_room_is_available(hotel, room_type, room, stay_dates):
    check_in, check_out = stay_dates
    found = find_available_rooms(
        hotel=hotel, room_type=room_type, check_in=check_in, check_out=check_out, guests=2
    )
    assert list(found) == [room]


def test_overlapping_booking_hides_the_room(user, hotel, room_type, room, stay_dates):
    check_in, check_out = stay_dates
    _book(user, hotel, room, check_in, check_out)

    found = find_available_rooms(
        hotel=hotel, room_type=room_type, check_in=check_in, check_out=check_out, guests=2
    )
    assert not found.exists()


def test_back_to_back_stays_do_not_conflict(user, hotel, room_type, room, stay_dates):
    """Checking out on the day the next guest checks in is not an overlap."""
    check_in, check_out = stay_dates
    _book(user, hotel, room, check_in, check_out)

    found = find_available_rooms(
        hotel=hotel,
        room_type=room_type,
        check_in=check_out,
        check_out=check_out + timedelta(days=1),
        guests=2,
    )
    assert list(found) == [room]


def test_cancelled_booking_releases_the_room(user, hotel, room_type, room, stay_dates):
    check_in, check_out = stay_dates
    _book(user, hotel, room, check_in, check_out, status=Booking.Status.CANCELLED)

    found = find_available_rooms(
        hotel=hotel, room_type=room_type, check_in=check_in, check_out=check_out, guests=2
    )
    assert list(found) == [room]


def test_room_too_small_is_excluded(hotel, room_type, room, stay_dates):
    check_in, check_out = stay_dates
    found = find_available_rooms(
        hotel=hotel, room_type=room_type, check_in=check_in, check_out=check_out, guests=5
    )
    assert not found.exists()


def test_out_of_service_room_is_excluded(hotel, room_type, room, stay_dates):
    room.is_available = False
    room.save(update_fields=["is_available"])

    check_in, check_out = stay_dates
    found = find_available_rooms(
        hotel=hotel, room_type=room_type, check_in=check_in, check_out=check_out, guests=1
    )
    assert not found.exists()


def test_available_room_types_lists_only_bookable_types(user, hotel, room, stay_dates):
    suite = RoomType.objects.create(name="Suite")
    suite_room = Room.objects.create(
        hotel=hotel,
        room_number=202,
        room_type=suite,
        price_per_night=Decimal("300.00"),
        max_guests=2,
    )
    check_in, check_out = stay_dates
    _book(user, hotel, suite_room, check_in, check_out)

    types = available_room_types(hotel=hotel, check_in=check_in, check_out=check_out, guests=2)
    assert [t.name for t in types] == ["Double"]


class TestAvailabilityEndpoint:
    url = reverse("available-room-types")

    def test_is_public(self, api_client, hotel, room, stay_dates):
        check_in, check_out = stay_dates
        response = api_client.get(
            self.url,
            {"hotel": hotel.id, "check_in": check_in, "check_out": check_out, "adults": 2},
        )
        assert response.status_code == 200
        assert [item["name"] for item in response.data] == ["Double"]

    @pytest.mark.parametrize(
        "params",
        [
            pytest.param({}, id="no-params"),
            pytest.param({"hotel": "abc"}, id="non-numeric-hotel"),
            pytest.param({"hotel": 999999}, id="unknown-hotel"),
        ],
    )
    def test_bad_input_is_a_400_not_a_500(self, api_client, params):
        """Regression: these inputs used to raise and return a 500."""
        response = api_client.get(self.url, params)
        assert response.status_code == 400

    def test_malformed_dates_are_rejected(self, api_client, hotel):
        response = api_client.get(
            self.url, {"hotel": hotel.id, "check_in": "not-a-date", "check_out": "2030-01-02"}
        )
        assert response.status_code == 400
        assert "check_in" in response.data

    def test_non_integer_guest_count_is_rejected(self, api_client, hotel, stay_dates):
        check_in, check_out = stay_dates
        response = api_client.get(
            self.url,
            {
                "hotel": hotel.id,
                "check_in": check_in,
                "check_out": check_out,
                "adults": "many",
            },
        )
        assert response.status_code == 400
