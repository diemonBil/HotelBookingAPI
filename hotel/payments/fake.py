"""Offline payment provider used for local development and tests.

It mimics the real contract without any network access, so `git clone` →
`docker compose up` gives a fully working booking flow with no merchant token.
"""

from __future__ import annotations

import uuid
from collections.abc import Mapping

from .base import Invoice, InvoiceRequest, PaymentProvider, WebhookEvent

# Provider payload status -> Payment.Status, mirroring the Monobank mapping so
# tests exercise the same translation logic.
_STATUS_MAP = {
    "created": "pending",
    "processing": "pending",
    "success": "paid",
    "failure": "failed",
    "expired": "expired",
    "reversed": "reversed",
}


class FakePaymentProvider(PaymentProvider):
    name = "fake"

    def create_invoice(self, request: InvoiceRequest) -> Invoice:
        invoice_id = f"fake_{uuid.uuid4().hex[:16]}"
        return Invoice(
            provider_invoice_id=invoice_id,
            payment_url=f"{request.redirect_url}?invoice={invoice_id}",
        )

    def verify_webhook(self, body: bytes, headers: Mapping[str, str]) -> bool:
        # Nothing to authenticate: the fake provider is never reachable from
        # the internet, and production must not select it.
        return True

    def parse_webhook(self, payload: Mapping[str, object]) -> WebhookEvent:
        raw_status = str(payload.get("status", "")).lower()
        return WebhookEvent(
            provider_invoice_id=str(payload.get("invoiceId", "")),
            reference=str(payload.get("reference", "")),
            status=_STATUS_MAP.get(raw_status, "pending"),
        )
