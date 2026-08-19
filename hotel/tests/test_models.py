from datetime import timedelta
from decimal import Decimal

import pytest
from django.db import IntegrityError
from django.utils import timezone

from hotel.models import Booking, Review, Room

pytestmark = pytest.mark.django_db


def test_nights_counts_calendar_nights(user, hotel, room, stay_dates):
    check_in, check_out = stay_dates
    booking = Booking.objects.create(
        user=user, hotel=hotel, check_in=check_in, check_out=check_out, adults=2
    )
    assert booking.nights == 2


def test_total_is_price_times_nights(user, hotel, room, stay_dates):
    """Regression: DateTimeField + ``.days`` used to bill a one-night stay as 0."""
    check_in, check_out = stay_dates
    booking = Booking.objects.create(
        user=user, hotel=hotel, check_in=check_in, check_out=check_in + timedelta(days=1), adults=2
    )
    booking.rooms.add(room)
    assert booking.calculate_total() == Decimal("100.00")


def test_check_out_must_be_after_check_in(user, hotel):
    today = timezone.localdate()
    with pytest.raises(IntegrityError):
        Booking.objects.create(user=user, hotel=hotel, check_in=today, check_out=today, adults=1)


def test_room_number_is_unique_within_a_hotel(hotel, room_type, room):
    with pytest.raises(IntegrityError):
        Room.objects.create(
            hotel=hotel,
            room_number=room.room_number,
            room_type=room_type,
            price_per_night=Decimal("50.00"),
            max_guests=1,
        )


def test_one_review_per_user_per_hotel(user, hotel):
    Review.objects.create(user=user, hotel=hotel, rating=5, comment="Great.")
    with pytest.raises(IntegrityError):
        Review.objects.create(user=user, hotel=hotel, rating=1, comment="Changed my mind.")
