from django.utils.timezone import make_aware
from rest_framework import viewsets, generics
from rest_framework.decorators import api_view
from rest_framework.permissions import IsAuthenticated, BasePermission
from rest_framework.response import Response
from datetime import datetime



class IsStaff(BasePermission):
    def has_permission(self, request, view):
        return request.user.is_authenticated and request.user.is_staff

from .models import Hotel, Room, Amenity, Booking, Payment, Review, RoomType
from .serializers import (
    HotelSerializer, RoomSerializer, AmenitySerializer,
    BookingSerializer, PaymentSerializer, ReviewSerializer, RoomTypeSerializer
)

class HotelViewSet(viewsets.ModelViewSet):
    queryset = Hotel.objects.all()
    serializer_class = HotelSerializer
    permission_classes = [IsStaff]

class RoomViewSet(viewsets.ModelViewSet):
    queryset = Room.objects.all()
    serializer_class = RoomSerializer
    permission_classes = [IsStaff]

class RoomTypeViewSet(viewsets.ModelViewSet):
    queryset = RoomType.objects.all()
    serializer_class = RoomTypeSerializer
    permission_classes = [IsStaff]

class AmenityViewSet(viewsets.ModelViewSet):
    queryset = Amenity.objects.all()
    serializer_class = AmenitySerializer
    permission_classes = [IsStaff]

class BookingViewSet(viewsets.ModelViewSet):
    queryset = Booking.objects.all()
    serializer_class = BookingSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        # Staff can see all bookings, regular users only their own
        if user.is_staff:
            return Booking.objects.all()
        return Booking.objects.filter(user=user)

    def perform_create(self, serializer):
        # Always assign the current user as the booking owner
        serializer.save(user=self.request.user)

class PaymentViewSet(viewsets.ModelViewSet):
    permission_classes = [IsStaff]
    queryset = Payment.objects.all()
    serializer_class = PaymentSerializer

class ReviewViewSet(viewsets.ModelViewSet):
    queryset = Review.objects.all()
    serializer_class = ReviewSerializer

@api_view(['GET'])
def available_room_types(request):
    # Get parameters from request
    check_in = request.GET.get('check_in')
    check_out = request.GET.get('check_out')
    hotel_id = request.GET.get('hotel')
    adults = int(request.GET.get('adults', 0))
    children = int(request.GET.get('children', 0))
    total_guests = adults + children

    # Validate input parameters
    if not check_in or not check_out or not hotel_id:
        return Response({'error': 'Missing hotel, check_in or check_out'}, status=400)

    check_in = make_aware(datetime.fromisoformat(check_in))
    check_out = make_aware(datetime.fromisoformat(check_out))

    # Check if the hotel exists
    try:
        hotel = Hotel.objects.get(id=hotel_id)
    except Hotel.DoesNotExist:
        return Response({'error': 'Hotel not found'}, status=404)

    available_types = []

    # Iterate through all room types
    for room_type in RoomType.objects.all():
        # Get rooms in the selected hotel of this type that can accommodate the guest count
        rooms = Room.objects.filter(
            hotel=hotel,
            room_type=room_type,
            max_guests__gte=total_guests,
            is_available=True
        )

        # Check if at least one room of this type is available for the selected dates
        for room in rooms:
            overlapping = Booking.objects.filter(
                rooms=room,
                check_in__lt=check_out,
                check_out__gt=check_in
            )
            if not overlapping.exists():
                available_types.append(room_type)
                break  # Found one available room of this type — no need to check more

    # Return available room types as JSON
    serializer = RoomTypeSerializer(available_types, many=True)
    return Response(serializer.data)