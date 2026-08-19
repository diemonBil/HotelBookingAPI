"""Monobank Acquiring integration.

API reference: https://api.monobank.ua/docs/acquiring.html
"""

from __future__ import annotations

import base64
import logging
from collections.abc import Mapping

import requests
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from django.conf import settings
from django.core.cache import cache

from .base import Invoice, InvoiceRequest, PaymentError, PaymentProvider, WebhookEvent

logger = logging.getLogger(__name__)

# Monobank invoice status -> Payment.Status
_STATUS_MAP = {
    "created": "pending",
    "processing": "pending",
    "hold": "pending",
    "success": "paid",
    "failure": "failed",
    "expired": "expired",
    "reversed": "reversed",
}

_PUBKEY_CACHE_KEY = "monobank:pubkey"
_PUBKEY_CACHE_TTL = 60 * 60  # The key rotates rarely; an hour is plenty.
_REQUEST_TIMEOUT = 15


class MonobankPaymentProvider(PaymentProvider):
    name = "monobank"

    def __init__(self, token: str | None = None, api_url: str | None = None):
        self.token = token if token is not None else settings.MONOBANK_TOKEN
        self.api_url = (api_url or settings.MONOBANK_API_URL).rstrip("/")
        if not self.token:
            raise PaymentError(
                "MONOBANK_TOKEN is not configured. Set it, or use PAYMENT_PROVIDER=fake."
            )

    @property
    def _headers(self) -> dict[str, str]:
        return {"X-Token": self.token, "Content-Type": "application/json"}

    def create_invoice(self, request: InvoiceRequest) -> Invoice:
        payload = {
            # Monobank expects the minor currency unit (kopecks).
            "amount": int(request.amount * 100),
            "ccy": request.currency_code,
            "merchantPaymInfo": {
                "reference": request.reference,
                "destination": request.description,
            },
            "redirectUrl": request.redirect_url,
            "webHookUrl": request.webhook_url,
        }

        try:
            response = requests.post(
                f"{self.api_url}/api/merchant/invoice/create",
                json=payload,
                headers=self._headers,
                timeout=_REQUEST_TIMEOUT,
            )
            response.raise_for_status()
            data = response.json()
        except requests.RequestException as exc:
            raise PaymentError(f"Monobank invoice request failed: {exc}") from exc
        except ValueError as exc:
            raise PaymentError("Monobank returned a non-JSON response") from exc

        invoice_id = data.get("invoiceId")
        page_url = data.get("pageUrl")
        if not invoice_id or not page_url:
            raise PaymentError(f"Unexpected Monobank response: {data!r}")

        return Invoice(provider_invoice_id=invoice_id, payment_url=page_url)

    def verify_webhook(self, body: bytes, headers: Mapping[str, str]) -> bool:
        """Check the X-Sign header: ECDSA/SHA-256 over the raw request body."""
        if not settings.MONOBANK_VERIFY_WEBHOOK:
            if not settings.DEBUG:
                raise PaymentError("Refusing to skip webhook signature verification outside DEBUG.")
            logger.warning("Monobank webhook signature verification is disabled (DEBUG).")
            return True

        signature = headers.get("X-Sign") or headers.get("x-sign")
        if not signature:
            logger.warning("Monobank webhook rejected: missing X-Sign header")
            return False

        try:
            public_key = self._public_key()
            public_key.verify(base64.b64decode(signature), body, ec.ECDSA(hashes.SHA256()))
        except (InvalidSignature, ValueError, TypeError) as exc:
            logger.warning("Monobank webhook rejected: %s", exc)
            return False
        return True

    def _public_key(self) -> ec.EllipticCurvePublicKey:
        """Fetch (and cache) the merchant public key used to sign webhooks."""
        pem = cache.get(_PUBKEY_CACHE_KEY)
        if pem is None:
            try:
                response = requests.get(
                    f"{self.api_url}/api/merchant/pubkey",
                    headers=self._headers,
                    timeout=_REQUEST_TIMEOUT,
                )
                response.raise_for_status()
                key_b64 = response.json()["key"]
            except (requests.RequestException, ValueError, KeyError) as exc:
                raise PaymentError(f"Could not fetch Monobank public key: {exc}") from exc
            pem = base64.b64decode(key_b64)
            cache.set(_PUBKEY_CACHE_KEY, pem, _PUBKEY_CACHE_TTL)

        key = serialization.load_pem_public_key(pem)
        if not isinstance(key, ec.EllipticCurvePublicKey):
            raise PaymentError("Monobank public key is not an EC key")
        return key

    def parse_webhook(self, payload: Mapping[str, object]) -> WebhookEvent:
        raw_status = str(payload.get("status", "")).lower()
        if raw_status not in _STATUS_MAP:
            logger.warning("Unknown Monobank status %r, treating as pending", raw_status)
        return WebhookEvent(
            provider_invoice_id=str(payload.get("invoiceId", "")),
            reference=str(payload.get("reference", "")),
            status=_STATUS_MAP.get(raw_status, "pending"),
        )
