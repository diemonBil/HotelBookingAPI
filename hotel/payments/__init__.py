"""Payment provider registry.

``settings.PAYMENT_PROVIDER`` picks the implementation; everything else in the
project depends only on the :class:`PaymentProvider` interface.
"""

from __future__ import annotations

from django.conf import settings

from .base import (
    Invoice,
    InvoiceRequest,
    PaymentError,
    PaymentProvider,
    WebhookEvent,
)
from .fake import FakePaymentProvider
from .monobank import MonobankPaymentProvider

_PROVIDERS: dict[str, type[PaymentProvider]] = {
    FakePaymentProvider.name: FakePaymentProvider,
    MonobankPaymentProvider.name: MonobankPaymentProvider,
}


def get_payment_provider(name: str | None = None) -> PaymentProvider:
    """Instantiate the configured provider.

    Raises :class:`PaymentError` for an unknown name so a typo in the
    environment fails loudly instead of silently skipping payments.
    """
    provider_name = (name or settings.PAYMENT_PROVIDER).lower()
    try:
        provider_class = _PROVIDERS[provider_name]
    except KeyError:
        known = ", ".join(sorted(_PROVIDERS))
        raise PaymentError(
            f"Unknown PAYMENT_PROVIDER {provider_name!r}. Available: {known}."
        ) from None
    return provider_class()


__all__ = [
    "FakePaymentProvider",
    "Invoice",
    "InvoiceRequest",
    "MonobankPaymentProvider",
    "PaymentError",
    "PaymentProvider",
    "WebhookEvent",
    "get_payment_provider",
]
