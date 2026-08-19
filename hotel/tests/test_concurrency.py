"""The race that row locking exists to prevent.

These tests need real committed transactions and a backend with
``SELECT ... FOR UPDATE``, so they are skipped on SQLite. Run them with:

    TEST_DATABASE_URL=postgres://... pytest hotel/tests/test_concurrency.py
"""

import os
import threading
from decimal import Decimal

import pytest
from django.db import connection, connections

from hotel.models import Booking, Payment, Room
from hotel.services import NoRoomAvailable, create_booking

# CI sets REQUIRE_LOCKING_TESTS=1 on the PostgreSQL run. With it set the skip is
# lifted, so a misconfigured job runs these tests against a backend that cannot
# lock and fails loudly: a concurrency test that quietly disappears is worse
# than not having one.
_required = os.getenv("REQUIRE_LOCKING_TESTS") == "1"

pytestmark = pytest.mark.skipif(
    not _required and not connection.features.has_select_for_update,
    reason="requires a backend with SELECT ... FOR UPDATE (PostgreSQL)",
)


def _book(results, index, **kwargs):
    """Run one booking attempt in its own thread and record the outcome."""
    try:
        booking = create_booking(**kwargs)
        results[index] = ("booked", booking.pk)
    except NoRoomAvailable:
        results[index] = ("rejected", None)
    except Exception as exc:  # noqa: BLE001 - surfaced by the assertions below
        results[index] = ("error", repr(exc))
    finally:
        # Each thread opens its own connection; leaving it open would keep the
        # test database busy and stall teardown.
        connections.close_all()


def _run_concurrently(attempts):
    results = [None] * len(attempts)
    threads = [
        threading.Thread(target=_book, args=(results, index), kwargs=kwargs)
        for index, kwargs in enumerate(attempts)
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=30)
    return results


@pytest.mark.django_db(transaction=True)
def test_two_requests_cannot_take_the_last_room(
    user, other_user, hotel, room_type, room, stay_dates
):
    check_in, check_out = stay_dates
    common = {
        "hotel": hotel,
        "room_type": room_type,
        "check_in": check_in,
        "check_out": check_out,
        "adults": 2,
        "children": 0,
    }

    results = _run_concurrently([{"user": user, **common}, {"user": other_user, **common}])

    assert [outcome for outcome, _ in results].count("booked") == 1, results
    assert [outcome for outcome, _ in results].count("rejected") == 1, results
    assert Booking.objects.count() == 1
    assert Booking.objects.get().rooms.get() == room


@pytest.mark.django_db(transaction=True)
def test_two_rooms_serve_two_concurrent_requests(
    user, other_user, hotel, room_type, room, stay_dates
):
    """The lock must serialise competing requests, not block legitimate ones."""
    Room.objects.create(
        hotel=hotel,
        room_number=102,
        room_type=room_type,
        price_per_night=Decimal("100.00"),
        max_guests=2,
    )
    check_in, check_out = stay_dates
    common = {
        "hotel": hotel,
        "room_type": room_type,
        "check_in": check_in,
        "check_out": check_out,
        "adults": 2,
        "children": 0,
    }

    results = _run_concurrently([{"user": user, **common}, {"user": other_user, **common}])

    assert [outcome for outcome, _ in results] == ["booked", "booked"], results
    assert Booking.objects.count() == 2
    # Two bookings, two distinct rooms, two distinct invoices.
    assigned = {booking.rooms.get().id for booking in Booking.objects.all()}
    assert len(assigned) == 2
    assert Payment.objects.values("reference").distinct().count() == 2
