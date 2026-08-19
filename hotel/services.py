"""Booking and payment use cases.

Views and serializers stay thin: they validate input and delegate the actual
transactional work to the functions below.
"""

from __future__ import annotations

import logging
import uuid
from datetime import date

from django.conf import settings
from django.db import connection, transaction
from django.db.models import QuerySet
from django.utils import timezone

from .models import Booking, Hotel, Payment, Room, RoomType
from .payments import InvoiceRequest, PaymentError, WebhookEvent, get_payment_provider

logger = logging.getLogger(__name__)


class NoRoomAvailable(Exception):
    """No room of the requested type is free for the requested dates."""


def _for_update(queryset: QuerySet) -> QuerySet:
    """Lock the selected rows, where the backend can.

    SQLite has no SELECT ... FOR UPDATE and raises if asked for one, but it
    serialises write transactions anyway, so skipping the lock is safe there.
    """
    if connection.features.has_select_for_update:
        return queryset.select_for_update()
    return queryset


def rooms_matching(*, hotel: Hotel, room_type: RoomType | None, guests: int) -> QuerySet[Room]:
    """Rooms in a hotel that are in service and large enough for the party."""
    queryset = Room.objects.filter(hotel=hotel, is_available=True, max_guests__gte=guests)
    if room_type is not None:
        queryset = queryset.filter(room_type=room_type)
    return queryset


def _occupied_room_ids(check_in: date, check_out: date) -> QuerySet:
    """Ids of rooms held by a booking overlapping the requested nights.

    Two stays overlap when each starts before the other ends. Cancelled
    bookings release their rooms and are therefore ignored.
    """
    return (
        Booking.objects.exclude(status__in=Booking.RELEASING_STATUSES)
        .filter(check_in__lt=check_out, check_out__gt=check_in)
        .values_list("rooms__id", flat=True)
    )


def find_available_rooms(
    *,
    hotel: Hotel,
    room_type: RoomType | None,
    check_in: date,
    check_out: date,
    guests: int,
) -> QuerySet[Room]:
    """Bookable rooms for the given hotel, type, dates and party size.

    A single query replaces the previous per-room Python loop. This is the
    read-only view used by the availability endpoint and by serializer
    validation; committing to a room goes through :func:`_reserve`, which locks
    first.
    """
    return rooms_matching(hotel=hotel, room_type=room_type, guests=guests).exclude(
        id__in=_occupied_room_ids(check_in, check_out)
    )


def available_room_types(
    *, hotel: Hotel, check_in: date, check_out: date, guests: int
) -> QuerySet[RoomType]:
    """Room types with at least one bookable room for the requested stay."""
    available = find_available_rooms(
        hotel=hotel,
        room_type=None,
        check_in=check_in,
        check_out=check_out,
        guests=guests,
    )
    return RoomType.objects.filter(
        id__in=available.values_list("room_type_id", flat=True)
    ).distinct()


@transaction.atomic
def _reserve(
    *,
    user,
    hotel: Hotel,
    room_type: RoomType,
    check_in: date,
    check_out: date,
    adults: int,
    children: int,
) -> Booking:
    """Claim a room and record the booking together with a pending payment.

    Availability is re-checked here, inside the transaction and under a row
    lock: the check performed during serializer validation is only advisory,
    because another request may take the last room in between.

    Order matters. Every candidate room is locked *before* occupancy is read,
    not as part of the same statement. A competing transaction can only commit
    its booking while holding these same rows, so by the time the lock is ours
    its work is committed and the following query — a new statement, and so a
    new snapshot under READ COMMITTED — sees it. Filtering and locking in one
    statement would not be enough: the ``NOT IN`` subquery is evaluated when the
    statement starts, which is before the lock is granted.
    """
    candidates = list(
        _for_update(
            rooms_matching(hotel=hotel, room_type=room_type, guests=adults + children)
        ).order_by("room_number")
    )
    occupied = set(_occupied_room_ids(check_in, check_out))
    room = next((candidate for candidate in candidates if candidate.id not in occupied), None)

    if room is None:
        raise NoRoomAvailable(
            f"No available rooms of type {room_type.name!r} for the selected dates."
        )

    booking = Booking.objects.create(
        user=user,
        hotel=hotel,
        check_in=check_in,
        check_out=check_out,
        adults=adults,
        children=children,
        status=Booking.Status.PENDING,
    )
    booking.rooms.add(room)

    provider = get_payment_provider()
    Payment.objects.create(
        booking=booking,
        provider=provider.name,
        reference=f"booking-{booking.pk}-{uuid.uuid4().hex[:8]}",
        amount=booking.calculate_total(),
        currency_code=settings.PAYMENT_CURRENCY_CODE,
        status=Payment.Status.PENDING,
    )
    return booking


def create_booking(
    *,
    user,
    hotel: Hotel,
    room_type: RoomType,
    check_in: date,
    check_out: date,
    adults: int,
    children: int,
) -> Booking:
    """Create a booking and attach a payment link to it.

    The invoice is requested *after* the database transaction commits, so a
    slow provider never holds row locks. If the provider cannot be reached the
    booking is rolled forward to CANCELLED, which releases the room again.
    """
    booking = _reserve(
        user=user,
        hotel=hotel,
        room_type=room_type,
        check_in=check_in,
        check_out=check_out,
        adults=adults,
        children=children,
    )
    payment = booking.payment
    provider = get_payment_provider()

    try:
        invoice = provider.create_invoice(
            InvoiceRequest(
                reference=payment.reference,
                amount=payment.amount,
                currency_code=payment.currency_code,
                description=(
                    f"Booking #{booking.pk} at {hotel.name}: "
                    f"{booking.nights} night(s) from {check_in}"
                ),
                redirect_url=f"{settings.PUBLIC_BASE_URL}/api/v1/payments/success/",
                webhook_url=f"{settings.PUBLIC_BASE_URL}/api/v1/payments/webhook/",
            )
        )
    except PaymentError:
        logger.exception("Invoice creation failed for booking %s", booking.pk)
        with transaction.atomic():
            payment.status = Payment.Status.FAILED
            payment.save(update_fields=["status", "updated_at"])
            booking.status = Booking.Status.CANCELLED
            booking.save(update_fields=["status"])
        raise

    payment.provider_invoice_id = invoice.provider_invoice_id
    payment.payment_url = invoice.payment_url
    payment.save(update_fields=["provider_invoice_id", "payment_url", "updated_at"])
    return booking


@transaction.atomic
def apply_payment_event(event: WebhookEvent) -> Payment:
    """Apply a provider status update to the matching payment.

    Idempotent: providers retry webhooks, and a replayed event for a payment
    that is already in the reported state is a no-op.
    """
    lookup = (
        {"provider_invoice_id": event.provider_invoice_id}
        if event.provider_invoice_id
        else {"reference": event.reference}
    )
    payment = _for_update(Payment.objects.select_related("booking")).get(**lookup)

    if payment.status == event.status:
        return payment

    payment.status = event.status
    updated_fields = ["status", "updated_at"]
    if event.status == Payment.Status.PAID and payment.paid_at is None:
        payment.paid_at = timezone.now()
        updated_fields.append("paid_at")
    payment.save(update_fields=updated_fields)

    booking = payment.booking
    if event.status == Payment.Status.PAID:
        booking.status = Booking.Status.CONFIRMED
    elif event.status in {
        Payment.Status.FAILED,
        Payment.Status.EXPIRED,
        Payment.Status.REVERSED,
    }:
        # Releases the room for other guests.
        booking.status = Booking.Status.CANCELLED
    else:
        return payment

    booking.save(update_fields=["status"])
    logger.info("Booking %s moved to %s via payment webhook", booking.pk, booking.status)
    return payment
