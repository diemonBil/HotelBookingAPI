import pytest
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import CommandError

from hotel.models import Amenity, Booking, Hotel, Payment, Review, Room, RoomType

pytestmark = pytest.mark.django_db


def test_seed_creates_a_usable_dataset():
    call_command("seed_demo_data", verbosity=0)

    assert Hotel.objects.exists()
    assert Room.objects.exists()
    assert RoomType.objects.exists()
    assert Amenity.objects.exists()
    assert Booking.objects.exists()
    assert Review.objects.exists()
    # Every seeded booking is paid for.
    assert Payment.objects.filter(status=Payment.Status.PAID).count() == Booking.objects.count()


def test_seeded_accounts_can_log_in():
    call_command("seed_demo_data", verbosity=0, password="Seeded!Passw0rd")

    admin = get_user_model().objects.get(username="admin")
    assert admin.is_staff and admin.is_superuser
    assert admin.check_password("Seeded!Passw0rd")


def test_seeding_twice_does_not_duplicate_data():
    call_command("seed_demo_data", verbosity=0)
    hotels, rooms, reviews = Hotel.objects.count(), Room.objects.count(), Review.objects.count()

    call_command("seed_demo_data", verbosity=0)

    assert Hotel.objects.count() == hotels
    assert Room.objects.count() == rooms
    assert Review.objects.count() == reviews


def test_flush_resets_the_dataset():
    call_command("seed_demo_data", verbosity=0)
    call_command("seed_demo_data", "--flush", verbosity=0)

    assert Hotel.objects.count() == 4


def test_short_password_is_rejected():
    with pytest.raises(CommandError):
        call_command("seed_demo_data", verbosity=0, password="short")
