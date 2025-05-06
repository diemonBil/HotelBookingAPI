from rest_framework.routers import DefaultRouter
from django.urls import path, include
from rest_framework import permissions
from drf_yasg.views import get_schema_view
from drf_yasg import openapi
from django.conf import settings
from django.conf.urls.static import static
from hotel.views import (
    HotelViewSet, RoomViewSet, AmenityViewSet,
    BookingViewSet, PaymentViewSet, ReviewViewSet, RoomTypeViewSet, available_room_types, update_payment_status,
    payment_success
)
router = DefaultRouter()
router.register(r'hotels', HotelViewSet)
router.register(r'rooms', RoomViewSet)
router.register(r'room-types', RoomTypeViewSet)
router.register(r'amenities', AmenityViewSet)
router.register(r'bookings', BookingViewSet)
router.register(r'payments', PaymentViewSet)
router.register(r'reviews', ReviewViewSet)


schema_view = get_schema_view(
   openapi.Info(
      title="Hotel Booking API",
      default_version='v1',
      description="Documentation for the hotel booking project",
      terms_of_service="https://www.example.com/terms/",
      contact=openapi.Contact(email="you@example.com"),
      license=openapi.License(name="MIT License"),
   ),
   public=True,
   permission_classes=[permissions.AllowAny],
)

urlpatterns = [
    path('api/v1/', include(router.urls)),
    path('api/v1/available-room-types/', available_room_types),
    path('api/v1/user/', include('user.urls')),
    path('api/v1/payment/update-status/', update_payment_status, name='update-payment-status'),
    path('api/v1/payment-success/', payment_success, name='payment-success'),
    # Swagger UI
    path('api/v1/swagger/', schema_view.with_ui('swagger', cache_timeout=0), name='schema-swagger-ui'),
    # ReDoc UI
    path('api/v1/redoc/', schema_view.with_ui('redoc', cache_timeout=0), name='schema-redoc'),
]

if settings.DEBUG:
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
