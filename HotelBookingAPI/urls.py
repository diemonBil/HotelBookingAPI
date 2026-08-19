from django.contrib import admin
from django.urls import include, path
from django.views.generic import TemplateView
from drf_spectacular.views import (
    SpectacularAPIView,
    SpectacularRedocView,
    SpectacularSwaggerView,
)
from rest_framework.routers import DefaultRouter

from hotel.views import (
    AmenityViewSet,
    BookingViewSet,
    HotelViewSet,
    PaymentViewSet,
    ReviewViewSet,
    RoomTypeViewSet,
    RoomViewSet,
    available_room_types,
    health,
    payment_success,
    payment_webhook,
)

router = DefaultRouter()
router.register("hotels", HotelViewSet, basename="hotel")
router.register("rooms", RoomViewSet, basename="room")
router.register("room-types", RoomTypeViewSet)
router.register("amenities", AmenityViewSet)
router.register("bookings", BookingViewSet, basename="booking")
router.register("payments", PaymentViewSet)
router.register("reviews", ReviewViewSet, basename="review")

# These sit before the router include: "webhook" and "success" would otherwise
# be captured by the router's /payments/<pk>/ detail route.
payment_urls = [
    path("payments/webhook/", payment_webhook, name="payment-webhook"),
    path("payments/success/", payment_success, name="payment-success"),
]

api_v1 = [
    path("health/", health, name="health"),
    *payment_urls,
    path("availability/room-types/", available_room_types, name="available-room-types"),
    path("user/", include("user.urls")),
    path("", include(router.urls)),
    # OpenAPI schema and the two documentation UIs rendered from it.
    path("schema/", SpectacularAPIView.as_view(), name="schema"),
    path(
        "docs/",
        SpectacularSwaggerView.as_view(url_name="schema"),
        name="swagger-ui",
    ),
    path("redoc/", SpectacularRedocView.as_view(url_name="schema"), name="redoc"),
]

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/v1/", include(api_v1)),
    # The demo client. Its own routing is hash-based, so no catch-all is
    # needed and a refresh on any screen still resolves here.
    path("", TemplateView.as_view(template_name="index.html"), name="home"),
]
