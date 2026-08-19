from decimal import Decimal

from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models


class Amenity(models.Model):
    """A feature a room can offer, e.g. "Free WiFi"."""

    name = models.CharField(max_length=255, unique=True)
    description = models.TextField(blank=True)

    class Meta:
        verbose_name_plural = "amenities"
        ordering = ["name"]

    def __str__(self):
        return self.name


class Hotel(models.Model):
    name = models.CharField(max_length=255)
    location = models.CharField(max_length=255)
    description = models.TextField(blank=True)

    class Meta:
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(
                fields=["name", "location"], name="unique_hotel_name_per_location"
            )
        ]

    def __str__(self):
        return f"{self.name} ({self.location})"


class RoomType(models.Model):
    """A bookable category of room. Guests pick a type, not a specific room."""

    name = models.CharField(max_length=100, unique=True)
    description = models.TextField(blank=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class Room(models.Model):
    hotel = models.ForeignKey(Hotel, on_delete=models.CASCADE, related_name="rooms")
    room_number = models.PositiveIntegerField()
    room_type = models.ForeignKey(RoomType, on_delete=models.PROTECT, related_name="rooms")
    price_per_night = models.DecimalField(
        max_digits=8,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.01"))],
    )
    # Cleared by staff to take a room out of service (renovation, damage, ...).
    is_available = models.BooleanField(default=True)
    amenities = models.ManyToManyField(Amenity, related_name="rooms", blank=True)
    max_guests = models.PositiveSmallIntegerField(validators=[MinValueValidator(1)])

    class Meta:
        ordering = ["hotel__name", "room_number"]
        constraints = [
            models.UniqueConstraint(
                fields=["hotel", "room_number"], name="unique_room_number_per_hotel"
            )
        ]
        indexes = [models.Index(fields=["hotel", "room_type"])]

    def __str__(self):
        return f"Room {self.room_number} - {self.hotel.name}"


class Booking(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending payment"
        CONFIRMED = "confirmed", "Confirmed"
        CANCELLED = "cancelled", "Cancelled"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="bookings"
    )
    # Denormalised from the assigned rooms: a booking never spans two hotels,
    # and storing it keeps listing and filtering queries to a single join.
    hotel = models.ForeignKey(Hotel, on_delete=models.PROTECT, related_name="bookings")
    rooms = models.ManyToManyField(Room, related_name="bookings")
    # Nights are calendar dates: a stay from the 1st to the 3rd is two nights,
    # regardless of the actual check-in and check-out clock times.
    check_in = models.DateField()
    check_out = models.DateField()
    adults = models.PositiveSmallIntegerField(validators=[MinValueValidator(1)])
    children = models.PositiveSmallIntegerField(default=0)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(check_out__gt=models.F("check_in")),
                name="booking_check_out_after_check_in",
            ),
            models.CheckConstraint(
                condition=models.Q(adults__gte=1), name="booking_at_least_one_adult"
            ),
        ]
        indexes = [
            models.Index(fields=["check_in", "check_out"]),
            models.Index(fields=["user", "status"]),
        ]

    def __str__(self):
        return f"Booking #{self.pk} by {self.user} ({self.check_in} - {self.check_out})"

    @property
    def nights(self) -> int:
        return (self.check_out - self.check_in).days

    @property
    def total_guests(self) -> int:
        return self.adults + self.children

    def calculate_total(self) -> Decimal:
        """Price of the stay: every assigned room, for every night booked."""
        nightly = sum((room.price_per_night for room in self.rooms.all()), start=Decimal("0"))
        return nightly * self.nights

    # Bookings in these states no longer hold their rooms.
    RELEASING_STATUSES = (Status.CANCELLED,)


class Payment(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        PAID = "paid", "Paid"
        FAILED = "failed", "Failed"
        EXPIRED = "expired", "Expired"
        REVERSED = "reversed", "Reversed"

    booking = models.OneToOneField(Booking, on_delete=models.CASCADE, related_name="payment")
    provider = models.CharField(max_length=50)
    # Our own idempotency key, sent to the provider and echoed back to us.
    reference = models.CharField(max_length=100, unique=True)
    # The provider's identifier for the invoice; unknown until the API replies.
    provider_invoice_id = models.CharField(max_length=100, null=True, blank=True, unique=True)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    currency_code = models.PositiveSmallIntegerField(default=980)  # ISO 4217: UAH
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    payment_url = models.URLField(max_length=500, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    paid_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"Payment for booking #{self.booking_id} - {self.status}"


class Review(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="reviews"
    )
    hotel = models.ForeignKey(Hotel, on_delete=models.CASCADE, related_name="reviews")
    rating = models.PositiveSmallIntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(5)]
    )
    comment = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(fields=["user", "hotel"], name="one_review_per_user_per_hotel")
        ]

    def __str__(self):
        return f"Review by {self.user} for {self.hotel.name} ({self.rating}/5)"


# drf-spectacular resolves ENUM_NAME_OVERRIDES with import_string, which cannot
# reach a nested class attribute. These module-level aliases give it a path it
# can import, so Booking.status and Payment.status get distinct enum names in
# the OpenAPI schema instead of a generated "Status593Enum".
BOOKING_STATUS_CHOICES = Booking.Status.choices
PAYMENT_STATUS_CHOICES = Payment.Status.choices
