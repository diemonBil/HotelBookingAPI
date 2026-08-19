from datetime import timedelta
from decimal import Decimal

import pytest
from django.urls import reverse
from django.utils import timezone

from hotel.models import Booking, Payment, Room

pytestmark = pytest.mark.django_db

LIST_URL = reverse("booking-list")


def detail_url(pk):
    return reverse("booking-detail", args=[pk])


def cancel_url(pk):
    return reverse("booking-cancel", args=[pk])


def test_anonymous_cannot_book(api_client, booking_payload, room):
    response = api_client.post(LIST_URL, booking_payload)
    assert response.status_code == 401


def test_booking_returns_a_payment_link(auth_client, booking_payload, room):
    """Regression: the payment URL used to be printed to stdout and lost."""
    response = auth_client.post(LIST_URL, booking_payload)

    assert response.status_code == 201, response.data
    assert response.data["status"] == Booking.Status.PENDING
    payment = response.data["payment"]
    assert payment["payment_url"]
    assert payment["status"] == Payment.Status.PENDING
    # Two nights in a 100.00 room.
    assert Decimal(payment["amount"]) == Decimal("200.00")


def test_booking_assigns_a_room(auth_client, booking_payload, room):
    response = auth_client.post(LIST_URL, booking_payload)
    assert [item["id"] for item in response.data["rooms"]] == [room.id]


def test_check_in_cannot_be_in_the_past(auth_client, booking_payload, room):
    today = timezone.localdate()
    booking_payload["check_in"] = (today - timedelta(days=1)).isoformat()
    booking_payload["check_out"] = (today + timedelta(days=1)).isoformat()

    response = auth_client.post(LIST_URL, booking_payload)
    assert response.status_code == 400
    assert "check_in" in response.data


def test_check_out_must_be_after_check_in(auth_client, booking_payload, room):
    booking_payload["check_out"] = booking_payload["check_in"]
    response = auth_client.post(LIST_URL, booking_payload)
    assert response.status_code == 400
    assert "check_out" in response.data


def test_stay_length_is_capped(auth_client, booking_payload, room):
    check_in = timezone.localdate() + timedelta(days=7)
    booking_payload["check_out"] = (check_in + timedelta(days=90)).isoformat()
    response = auth_client.post(LIST_URL, booking_payload)
    assert response.status_code == 400


def test_party_larger_than_the_room_is_rejected(auth_client, booking_payload, room):
    booking_payload["adults"] = 4
    response = auth_client.post(LIST_URL, booking_payload)
    assert response.status_code == 400


def test_last_room_cannot_be_booked_twice(
    auth_client, api_client, other_user, booking_payload, room
):
    assert auth_client.post(LIST_URL, booking_payload).status_code == 201

    api_client.force_authenticate(user=other_user)
    response = api_client.post(LIST_URL, booking_payload)

    assert response.status_code == 400
    assert Booking.objects.count() == 1


def test_second_room_of_the_same_type_is_still_bookable(
    auth_client, api_client, other_user, booking_payload, hotel, room_type, room
):
    Room.objects.create(
        hotel=hotel,
        room_number=102,
        room_type=room_type,
        price_per_night=Decimal("100.00"),
        max_guests=2,
    )
    assert auth_client.post(LIST_URL, booking_payload).status_code == 201

    api_client.force_authenticate(user=other_user)
    assert api_client.post(LIST_URL, booking_payload).status_code == 201
    assert Booking.objects.count() == 2


def test_users_see_only_their_own_bookings(
    auth_client, api_client, user, other_user, booking_payload, room
):
    auth_client.post(LIST_URL, booking_payload)

    api_client.force_authenticate(user=other_user)
    response = api_client.get(LIST_URL)
    assert response.data["count"] == 0


def test_staff_see_every_booking(auth_client, staff_client, booking_payload, room):
    auth_client.post(LIST_URL, booking_payload)
    response = staff_client.get(LIST_URL)
    assert response.data["count"] == 1


def test_other_users_booking_is_not_reachable(
    auth_client, api_client, other_user, booking_payload, room
):
    booking_id = auth_client.post(LIST_URL, booking_payload).data["id"]

    api_client.force_authenticate(user=other_user)
    assert api_client.get(detail_url(booking_id)).status_code == 404
    assert api_client.post(cancel_url(booking_id)).status_code == 404


def test_owner_can_cancel_and_the_room_is_released(
    auth_client, api_client, other_user, booking_payload, room
):
    booking_id = auth_client.post(LIST_URL, booking_payload).data["id"]

    response = auth_client.post(cancel_url(booking_id))
    assert response.status_code == 200
    assert response.data["status"] == Booking.Status.CANCELLED

    # The freed room can be booked by somebody else.
    api_client.force_authenticate(user=other_user)
    assert api_client.post(LIST_URL, booking_payload).status_code == 201


def test_cancelling_twice_is_rejected(auth_client, booking_payload, room):
    booking_id = auth_client.post(LIST_URL, booking_payload).data["id"]
    auth_client.post(cancel_url(booking_id))

    assert auth_client.post(cancel_url(booking_id)).status_code == 400


def test_booking_list_does_not_scale_queries_with_rows(
    auth_client, django_assert_max_num_queries, booking_payload, hotel, room_type, room
):
    """Regression: the list endpoint used to issue a query per booking."""
    for number in range(102, 106):
        Room.objects.create(
            hotel=hotel,
            room_number=number,
            room_type=room_type,
            price_per_night=Decimal("100.00"),
            max_guests=2,
        )
    for _ in range(5):
        auth_client.post(LIST_URL, booking_payload)

    with django_assert_max_num_queries(8):
        response = auth_client.get(LIST_URL)
    assert response.data["count"] == 5
