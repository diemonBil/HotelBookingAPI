"""Provider-agnostic payment interface.

The booking flow only ever talks to :class:`PaymentProvider`, so swapping
Monobank for another acquirer (or for the offline fake) is a settings change.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal


class PaymentError(Exception):
    """Raised when a provider cannot create or interpret an invoice."""


@dataclass(frozen=True)
class Invoice:
    """What a provider hands back after an invoice is created."""

    provider_invoice_id: str
    payment_url: str


@dataclass(frozen=True)
class InvoiceRequest:
    reference: str
    amount: Decimal
    currency_code: int
    description: str
    redirect_url: str
    webhook_url: str


@dataclass(frozen=True)
class WebhookEvent:
    """A normalised payment status update coming from a provider."""

    provider_invoice_id: str
    reference: str
    # One of hotel.models.Payment.Status values.
    status: str


class PaymentProvider(ABC):
    """Contract every payment integration must satisfy."""

    name: str

    @abstractmethod
    def create_invoice(self, request: InvoiceRequest) -> Invoice:
        """Register an invoice with the provider and return its payment link."""

    @abstractmethod
    def verify_webhook(self, body: bytes, headers: Mapping[str, str]) -> bool:
        """Return whether the callback genuinely came from the provider."""

    @abstractmethod
    def parse_webhook(self, payload: Mapping[str, object]) -> WebhookEvent:
        """Translate a provider payload into a :class:`WebhookEvent`."""
