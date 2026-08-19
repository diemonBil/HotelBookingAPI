"""Payment provider abstraction and the webhook that drives booking state."""

import base64
import json
from decimal import Decimal
from urllib.parse import parse_qs, urlparse

import pytest
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from django.core.cache import cache
from django.test import override_settings
from django.urls import reverse

from hotel.models import Booking, Payment
from hotel.payments import (
    FakePaymentProvider,
    MonobankPaymentProvider,
    PaymentError,
    get_payment_provider,
)
from hotel.payments.monobank import _PUBKEY_CACHE_KEY

WEBHOOK_URL = reverse("payment-webhook")
BOOKINGS_URL = reverse("booking-list")


# --------------------------------------------------------------------------
# Provider selection
# --------------------------------------------------------------------------


def test_configured_provider_is_returned():
    assert isinstance(get_payment_provider(), FakePaymentProvider)


def test_unknown_provider_fails_loudly():
    with pytest.raises(PaymentError, match="Unknown PAYMENT_PROVIDER"):
        get_payment_provider("stripe")


@override_settings(MONOBANK_TOKEN="")
def test_monobank_requires_a_token():
    with pytest.raises(PaymentError, match="MONOBANK_TOKEN"):
        MonobankPaymentProvider()


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("success", Payment.Status.PAID),
        ("failure", Payment.Status.FAILED),
        ("expired", Payment.Status.EXPIRED),
        ("reversed", Payment.Status.REVERSED),
        ("processing", Payment.Status.PENDING),
        ("something-new", Payment.Status.PENDING),
    ],
)
@override_settings(MONOBANK_TOKEN="test-token")
def test_monobank_status_mapping(raw, expected):
    event = MonobankPaymentProvider().parse_webhook({"invoiceId": "inv1", "status": raw})
    assert event.status == expected


# --------------------------------------------------------------------------
# Webhook signature verification
# --------------------------------------------------------------------------


@pytest.fixture
def signing_key():
    """An EC key pair standing in for Monobank's, cached as the public key."""
    private_key = ec.generate_private_key(ec.SECP256R1())
    pem = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    cache.set(_PUBKEY_CACHE_KEY, pem, 60)
    return private_key


def sign(private_key, body: bytes) -> str:
    return base64.b64encode(private_key.sign(body, ec.ECDSA(hashes.SHA256()))).decode()


@override_settings(MONOBANK_TOKEN="test-token")
def test_valid_signature_is_accepted(signing_key):
    body = b'{"invoiceId": "inv1", "status": "success"}'
    provider = MonobankPaymentProvider()
    assert provider.verify_webhook(body, {"X-Sign": sign(signing_key, body)}) is True


@override_settings(MONOBANK_TOKEN="test-token")
def test_tampered_body_is_rejected(signing_key):
    """Regression: the webhook used to accept any unauthenticated POST."""
    signature = sign(signing_key, b'{"invoiceId": "inv1", "status": "failure"}')
    forged = b'{"invoiceId": "inv1", "status": "success"}'

    provider = MonobankPaymentProvider()
    assert provider.verify_webhook(forged, {"X-Sign": signature}) is False


@override_settings(MONOBANK_TOKEN="test-token")
def test_missing_signature_header_is_rejected(signing_key):
    provider = MonobankPaymentProvider()
    assert provider.verify_webhook(b'{"status": "success"}', {}) is False


@override_settings(MONOBANK_TOKEN="test-token")
def test_garbage_signature_is_rejected(signing_key):
    provider = MonobankPaymentProvider()
    assert provider.verify_webhook(b"{}", {"X-Sign": "not-base64-!!"}) is False


@override_settings(MONOBANK_TOKEN="test-token", MONOBANK_VERIFY_WEBHOOK=False, DEBUG=False)
def test_verification_cannot_be_disabled_in_production():
    provider = MonobankPaymentProvider()
    with pytest.raises(PaymentError, match="Refusing to skip"):
        provider.verify_webhook(b"{}", {})


@override_settings(MONOBANK_TOKEN="test-token", MONOBANK_VERIFY_WEBHOOK=False, DEBUG=True)
def test_verification_can_be_skipped_while_debugging():
    assert MonobankPaymentProvider().verify_webhook(b"{}", {}) is True


# --------------------------------------------------------------------------
# Webhook endpoint
# --------------------------------------------------------------------------


@pytest.fixture
def pending_booking(auth_client, booking_payload, room):
    response = auth_client.post(BOOKINGS_URL, booking_payload)
    assert response.status_code == 201, response.data
    return Booking.objects.get(pk=response.data["id"])


def post_webhook(client, payload):
    return client.post(WEBHOOK_URL, data=json.dumps(payload), content_type="application/json")


@pytest.mark.django_db
def test_successful_payment_confirms_the_booking(api_client, pending_booking):
    payment = pending_booking.payment
    response = post_webhook(
        api_client, {"invoiceId": payment.provider_invoice_id, "status": "success"}
    )

    assert response.status_code == 200
    payment.refresh_from_db()
    pending_booking.refresh_from_db()
    assert payment.status == Payment.Status.PAID
    assert payment.paid_at is not None
    assert pending_booking.status == Booking.Status.CONFIRMED


@pytest.mark.django_db
def test_replayed_webhook_is_a_no_op(api_client, pending_booking):
    payment = pending_booking.payment
    payload = {"invoiceId": payment.provider_invoice_id, "status": "success"}

    assert post_webhook(api_client, payload).status_code == 200
    payment.refresh_from_db()
    first_paid_at = payment.paid_at

    assert post_webhook(api_client, payload).status_code == 200
    payment.refresh_from_db()
    assert payment.paid_at == first_paid_at


@pytest.mark.django_db
def test_failed_payment_cancels_the_booking_and_frees_the_room(
    api_client, pending_booking, auth_client, booking_payload
):
    post_webhook(
        api_client,
        {"invoiceId": pending_booking.payment.provider_invoice_id, "status": "failure"},
    )

    pending_booking.refresh_from_db()
    assert pending_booking.status == Booking.Status.CANCELLED
    # The room is bookable again.
    assert auth_client.post(BOOKINGS_URL, booking_payload).status_code == 201


@pytest.mark.django_db
def test_webhook_for_an_unknown_invoice_is_a_404(api_client):
    response = post_webhook(api_client, {"invoiceId": "nope", "status": "success"})
    assert response.status_code == 404


@pytest.mark.django_db
def test_webhook_without_an_identifier_is_a_400(api_client):
    response = post_webhook(api_client, {"status": "success"})
    assert response.status_code == 400


@pytest.mark.django_db
def test_malformed_webhook_body_is_a_400(api_client):
    response = api_client.post(WEBHOOK_URL, data="{not json", content_type="application/json")
    assert response.status_code == 400


@pytest.mark.django_db
def test_payment_records_are_staff_only(auth_client, staff_client, pending_booking):
    assert auth_client.get(reverse("payment-list")).status_code == 403
    assert staff_client.get(reverse("payment-list")).data["count"] == 1


@pytest.mark.django_db
def test_invoice_amount_matches_the_stay(pending_booking):
    assert pending_booking.payment.amount == Decimal("200.00")


# --------------------------------------------------------------------------
# Provider failures must not leave a room held
# --------------------------------------------------------------------------


class BrokenProvider(FakePaymentProvider):
    """Stands in for an acquirer that is down when we try to invoice."""

    def create_invoice(self, request):
        raise PaymentError("provider unreachable")


@pytest.mark.django_db
def test_failed_invoice_cancels_the_booking_and_frees_the_room(
    auth_client, booking_payload, room, monkeypatch
):
    monkeypatch.setattr("hotel.services.get_payment_provider", lambda *a, **kw: BrokenProvider())

    response = auth_client.post(BOOKINGS_URL, booking_payload)
    assert response.status_code == 400

    booking = Booking.objects.get()
    assert booking.status == Booking.Status.CANCELLED
    assert booking.payment.status == Payment.Status.FAILED

    # With the provider healthy again the same room can be booked.
    monkeypatch.undo()
    assert auth_client.post(BOOKINGS_URL, booking_payload).status_code == 201


@pytest.mark.django_db
def test_fake_payment_url_carries_the_invoice_id(pending_booking):
    """The demo client reads the invoice id straight out of the payment link."""
    payment = pending_booking.payment
    query = parse_qs(urlparse(payment.payment_url).query)
    assert query["invoice"] == [payment.provider_invoice_id]
