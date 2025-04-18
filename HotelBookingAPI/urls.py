from django.urls import path, include
from rest_framework.routers import DefaultRouter
from hotel.views import (
    HotelViewSet, RoomViewSet, AmenityViewSet,
    BookingViewSet, PaymentViewSet, ReviewViewSet, RoomTypeViewSet, available_room_types
)
router = DefaultRouter()
router.register(r'hotels', HotelViewSet)
router.register(r'rooms', RoomViewSet)
router.register(r'room-types', RoomTypeViewSet)
router.register(r'amenities', AmenityViewSet)
router.register(r'bookings', BookingViewSet)
router.register(r'payments', PaymentViewSet)
router.register(r'reviews', ReviewViewSet)

urlpatterns = [
    path('api/v1/', include(router.urls)),
    path('api/available-room-types/', available_room_types),
    path('api/user/', include('user.urls')),
]
