from __future__ import annotations

import json
import logging

from django.db import OperationalError, connection
from django.db.models import Avg, Count
from django.shortcuts import render
from drf_spectacular.utils import OpenApiParameter, extend_schema, extend_schema_view
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action, api_view, permission_classes, throttle_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response

from . import services
from .models import Amenity, Booking, Hotel, Payment, Review, Room, RoomType
from .payments import PaymentError, get_payment_provider
from .permissions import IsAdminOrReadOnly, IsOwnerOrReadOnly, IsStaff
from .serializers import (
    AmenitySerializer,
    AvailabilityQuerySerializer,
    BookingSerializer,
    HotelSerializer,
    PaymentSerializer,
    ReviewSerializer,
    RoomSerializer,
    RoomTypeSerializer,
)

logger = logging.getLogger(__name__)


class HotelViewSet(viewsets.ModelViewSet):
    """Public hotel catalogue. Staff may create, update and delete."""

    serializer_class = HotelSerializer
    permission_classes = [IsAdminOrReadOnly]
    filterset_fields = ["location"]
    search_fields = ["name", "location", "description"]
    ordering_fields = ["name", "average_rating"]
    ordering = ["name"]

    def get_queryset(self):
        # Django drops Meta.ordering from aggregate queries, so it is restored
        # here to keep pagination stable.
        return Hotel.objects.annotate(
            average_rating=Avg("reviews__rating"),
            review_count=Count("reviews", distinct=True),
        ).order_by("name")


class RoomViewSet(viewsets.ModelViewSet):
    """Public room catalogue. Staff may create, update and delete."""

    serializer_class = RoomSerializer
    permission_classes = [IsAdminOrReadOnly]
    filterset_fields = ["hotel", "room_type", "is_available", "max_guests"]
    ordering_fields = ["price_per_night", "room_number"]

    def get_queryset(self):
        # select_related/prefetch_related keep the list endpoint at a constant
        # number of queries instead of one per row.
        return Room.objects.select_related("hotel", "room_type").prefetch_related("amenities")


class RoomTypeViewSet(viewsets.ModelViewSet):
    queryset = RoomType.objects.all()
    serializer_class = RoomTypeSerializer
    permission_classes = [IsAdminOrReadOnly]
    search_fields = ["name"]


class AmenityViewSet(viewsets.ModelViewSet):
    queryset = Amenity.objects.all()
    serializer_class = AmenitySerializer
    permission_classes = [IsAdminOrReadOnly]
    search_fields = ["name"]


@extend_schema_view(
    list=extend_schema(description="Bookings of the current user; staff see all bookings."),
    create=extend_schema(
        description=(
            "Reserve a room of the requested type and open a payment invoice. "
            "The response includes `payment.payment_url` to send the guest to."
        )
    ),
)
class BookingViewSet(
    mixins.CreateModelMixin,
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    viewsets.GenericViewSet,
):
    """Bookings are created and cancelled, never edited in place."""

    serializer_class = BookingSerializer
    permission_classes = [IsAuthenticated, IsOwnerOrReadOnly]
    filterset_fields = ["status", "hotel"]
    ordering_fields = ["created_at", "check_in"]

    def get_queryset(self):
        # drf-spectacular introspects the view without a real request.
        if getattr(self, "swagger_fake_view", False):
            return Booking.objects.none()
        queryset = Booking.objects.select_related("hotel", "payment", "user").prefetch_related(
            "rooms__hotel", "rooms__room_type"
        )
        user = self.request.user
        if user.is_staff:
            return queryset
        return queryset.filter(user=user)

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)

    @extend_schema(
        request=None,
        responses={200: BookingSerializer},
        description="Cancel a booking and release its room.",
    )
    @action(detail=True, methods=["post"])
    def cancel(self, request, pk=None):
        booking = self.get_object()
        self.check_object_permissions(request, booking)

        if booking.status == Booking.Status.CANCELLED:
            return Response(
                {"detail": "Booking is already cancelled."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        booking.status = Booking.Status.CANCELLED
        booking.save(update_fields=["status"])
        logger.info("Booking %s cancelled by user %s", booking.pk, request.user.pk)
        return Response(self.get_serializer(booking).data)


class PaymentViewSet(viewsets.ReadOnlyModelViewSet):
    """Payment records. Staff only: these are financial records."""

    queryset = Payment.objects.select_related("booking").all()
    serializer_class = PaymentSerializer
    permission_classes = [IsStaff]
    filterset_fields = ["status", "provider"]
    ordering_fields = ["created_at", "amount"]


class ReviewViewSet(viewsets.ModelViewSet):
    """Anyone may read reviews; authors may edit only their own."""

    serializer_class = ReviewSerializer
    filterset_fields = ["hotel", "rating"]
    ordering_fields = ["created_at", "rating"]

    def get_queryset(self):
        return Review.objects.select_related("user", "hotel")

    def get_permissions(self):
        # Reading is public, writing requires a login, and editing requires
        # ownership (enforced object-level by IsOwnerOrReadOnly).
        if self.request.method in ("GET", "HEAD", "OPTIONS"):
            return [AllowAny()]
        return [IsAuthenticated(), IsOwnerOrReadOnly()]

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)


@extend_schema(
    parameters=[
        OpenApiParameter("hotel", int, required=True, description="Hotel id."),
        OpenApiParameter("check_in", str, required=True, description="YYYY-MM-DD."),
        OpenApiParameter("check_out", str, required=True, description="YYYY-MM-DD."),
        OpenApiParameter("adults", int, description="Defaults to 1."),
        OpenApiParameter("children", int, description="Defaults to 0."),
    ],
    responses={200: RoomTypeSerializer(many=True)},
    description="Room types with at least one free room for the requested stay.",
)
@api_view(["GET"])
@permission_classes([AllowAny])
def available_room_types(request):
    query = AvailabilityQuerySerializer(data=request.query_params)
    query.is_valid(raise_exception=True)
    data = query.validated_data

    room_types = services.available_room_types(
        hotel=data["hotel"],
        check_in=data["check_in"],
        check_out=data["check_out"],
        guests=data["adults"] + data["children"],
    )
    return Response(RoomTypeSerializer(room_types, many=True).data)


@extend_schema(
    request=None,
    responses={200: None, 400: None, 403: None, 404: None},
    description=(
        "Payment provider callback. The request is authenticated by the "
        "provider's signature over the raw body, not by a user session."
    ),
)
@api_view(["POST"])
@permission_classes([AllowAny])
def payment_webhook(request):
    provider = get_payment_provider()

    try:
        if not provider.verify_webhook(request.body, request.headers):
            # Do not reveal why: an attacker probing the endpoint learns nothing.
            return Response({"detail": "Invalid signature."}, status=status.HTTP_403_FORBIDDEN)
    except PaymentError:
        logger.exception("Webhook verification could not be completed")
        return Response(
            {"detail": "Verification unavailable."},
            status=status.HTTP_503_SERVICE_UNAVAILABLE,
        )

    try:
        payload = json.loads(request.body or b"{}")
    except json.JSONDecodeError:
        return Response({"detail": "Malformed JSON."}, status=status.HTTP_400_BAD_REQUEST)
    if not isinstance(payload, dict):
        return Response({"detail": "Malformed payload."}, status=status.HTTP_400_BAD_REQUEST)

    event = provider.parse_webhook(payload)
    if not event.provider_invoice_id and not event.reference:
        return Response(
            {"detail": "Payload identifies no invoice."}, status=status.HTTP_400_BAD_REQUEST
        )

    try:
        services.apply_payment_event(event)
    except Payment.DoesNotExist:
        logger.warning("Webhook for unknown invoice %s", event.provider_invoice_id)
        return Response({"detail": "Payment not found."}, status=status.HTTP_404_NOT_FOUND)

    return Response({"detail": "Payment status updated."})


def payment_success(request):
    """Landing page the provider redirects the guest to after paying."""
    return render(request, "payment-success.html")


@extend_schema(
    responses={200: None, 503: None},
    description="Liveness and database connectivity probe, used by Docker and load balancers.",
)
@api_view(["GET"])
@permission_classes([AllowAny])
@throttle_classes([])
def health(request):
    try:
        connection.ensure_connection()
    except OperationalError:
        logger.exception("Health check failed: database unreachable")
        return Response(
            {"status": "error", "database": "unreachable"},
            status=status.HTTP_503_SERVICE_UNAVAILABLE,
        )
    return Response({"status": "ok", "database": "ok"})
