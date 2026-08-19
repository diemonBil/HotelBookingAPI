from __future__ import annotations

from django.utils import timezone
from rest_framework import serializers

from .models import Amenity, Booking, Hotel, Payment, Review, Room, RoomType
from .payments import PaymentError
from .services import NoRoomAvailable, create_booking, find_available_rooms

# Guard against typos like a 2027 check-out on a 2025 check-in.
MAX_STAY_NIGHTS = 30


class AmenitySerializer(serializers.ModelSerializer):
    class Meta:
        model = Amenity
        fields = ("id", "name", "description")


class HotelSerializer(serializers.ModelSerializer):
    average_rating = serializers.FloatField(read_only=True)
    review_count = serializers.IntegerField(read_only=True)

    class Meta:
        model = Hotel
        fields = ("id", "name", "location", "description", "average_rating", "review_count")


class RoomTypeSerializer(serializers.ModelSerializer):
    class Meta:
        model = RoomType
        fields = ("id", "name", "description")


class RoomSerializer(serializers.ModelSerializer):
    """Readable nested output, but plain ids on write."""

    hotel_name = serializers.CharField(source="hotel.name", read_only=True)
    room_type_name = serializers.CharField(source="room_type.name", read_only=True)
    amenities_detail = AmenitySerializer(source="amenities", many=True, read_only=True)

    class Meta:
        model = Room
        fields = (
            "id",
            "hotel",
            "hotel_name",
            "room_number",
            "room_type",
            "room_type_name",
            "price_per_night",
            "is_available",
            "max_guests",
            "amenities",
            "amenities_detail",
        )


class RoomSummarySerializer(serializers.ModelSerializer):
    """Compact room representation embedded in a booking."""

    hotel_name = serializers.CharField(source="hotel.name", read_only=True)
    room_type_name = serializers.CharField(source="room_type.name", read_only=True)

    class Meta:
        model = Room
        fields = ("id", "room_number", "hotel_name", "room_type_name", "price_per_night")


class PaymentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Payment
        fields = (
            "id",
            "booking",
            "provider",
            "reference",
            "provider_invoice_id",
            "amount",
            "currency_code",
            "status",
            "payment_url",
            "created_at",
            "paid_at",
        )
        read_only_fields = fields


class BookingPaymentSerializer(serializers.ModelSerializer):
    """The payment details a guest needs: how much, and where to pay."""

    class Meta:
        model = Payment
        fields = ("provider", "status", "amount", "currency_code", "payment_url", "paid_at")
        read_only_fields = fields


class BookingSerializer(serializers.ModelSerializer):
    hotel = serializers.PrimaryKeyRelatedField(queryset=Hotel.objects.all())
    room_type = serializers.PrimaryKeyRelatedField(queryset=RoomType.objects.all(), write_only=True)
    hotel_name = serializers.CharField(source="hotel.name", read_only=True)
    rooms = RoomSummarySerializer(many=True, read_only=True)
    payment = BookingPaymentSerializer(read_only=True)
    nights = serializers.IntegerField(read_only=True)

    class Meta:
        model = Booking
        fields = (
            "id",
            "hotel",
            "hotel_name",
            "room_type",
            "check_in",
            "check_out",
            "nights",
            "adults",
            "children",
            "status",
            "rooms",
            "payment",
            "created_at",
        )
        read_only_fields = ("id", "status", "rooms", "payment", "created_at")

    def validate(self, attrs):
        check_in = attrs["check_in"]
        check_out = attrs["check_out"]
        guests = attrs["adults"] + attrs.get("children", 0)

        if check_in < timezone.localdate():
            raise serializers.ValidationError({"check_in": "Check-in date cannot be in the past."})
        if check_out <= check_in:
            raise serializers.ValidationError({"check_out": "Check-out must be after check-in."})
        if (check_out - check_in).days > MAX_STAY_NIGHTS:
            raise serializers.ValidationError(
                {"check_out": f"A stay cannot exceed {MAX_STAY_NIGHTS} nights."}
            )

        # Advisory check so the client gets a clear 400 instead of a surprise
        # later; the binding check happens under a row lock in the service.
        available = find_available_rooms(
            hotel=attrs["hotel"],
            room_type=attrs["room_type"],
            check_in=check_in,
            check_out=check_out,
            guests=guests,
        )
        if not available.exists():
            raise serializers.ValidationError(
                "No available rooms of the requested type for these dates and party size."
            )
        return attrs

    def create(self, validated_data):
        try:
            return create_booking(
                user=validated_data["user"],
                hotel=validated_data["hotel"],
                room_type=validated_data["room_type"],
                check_in=validated_data["check_in"],
                check_out=validated_data["check_out"],
                adults=validated_data["adults"],
                children=validated_data.get("children", 0),
            )
        except NoRoomAvailable as exc:
            # Lost the race against a concurrent booking.
            raise serializers.ValidationError(str(exc)) from exc
        except PaymentError as exc:
            raise serializers.ValidationError(f"Could not initiate payment: {exc}") from exc


class ReviewSerializer(serializers.ModelSerializer):
    user = serializers.PrimaryKeyRelatedField(read_only=True)
    username = serializers.CharField(source="user.username", read_only=True)

    class Meta:
        model = Review
        fields = (
            "id",
            "user",
            "username",
            "hotel",
            "rating",
            "comment",
            "created_at",
            "updated_at",
        )
        read_only_fields = ("id", "user", "created_at", "updated_at")

    def validate(self, attrs):
        request = self.context.get("request")
        hotel = attrs.get("hotel", getattr(self.instance, "hotel", None))
        if request and self.instance is None:
            already_reviewed = Review.objects.filter(user=request.user, hotel=hotel).exists()
            if already_reviewed:
                raise serializers.ValidationError(
                    "You have already reviewed this hotel; edit your existing review."
                )
        return attrs


class AvailabilityQuerySerializer(serializers.Serializer):
    """Validates the query string of the availability endpoint.

    Previously these parameters were parsed inline, so any malformed value
    produced a 500 instead of a 400.
    """

    hotel = serializers.PrimaryKeyRelatedField(queryset=Hotel.objects.all())
    check_in = serializers.DateField()
    check_out = serializers.DateField()
    adults = serializers.IntegerField(min_value=1, default=1)
    children = serializers.IntegerField(min_value=0, default=0)

    def validate(self, attrs):
        if attrs["check_out"] <= attrs["check_in"]:
            raise serializers.ValidationError({"check_out": "Check-out must be after check-in."})
        return attrs
