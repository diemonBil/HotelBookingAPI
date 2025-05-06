import json
from django.shortcuts import render
from django.utils.timezone import make_aware
from rest_framework import viewsets
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from datetime import datetime
from rest_framework.permissions import IsAuthenticated, BasePermission
from rest_framework import permissions
from .models import Hotel, Room, Amenity, Booking, Payment, Review, RoomType
from .serializers import (
    HotelSerializer, RoomSerializer, AmenitySerializer,
    BookingSerializer, PaymentSerializer, ReviewSerializer, RoomTypeSerializer, PaymentStatusUpdateSerializer
)

""" Custom permission class that allows access only to staff users """
class IsStaff(BasePermission):
    def has_permission(self, request, view):
        return request.user.is_authenticated and request.user.is_staff


""" ViewSet for managing Hotel objects (accessible only by staff) """
class HotelViewSet(viewsets.ModelViewSet):
    queryset = Hotel.objects.all()
    serializer_class = HotelSerializer
    permission_classes = [IsStaff]


""" ViewSet for managing Room objects (accessible only by staff) """
class RoomViewSet(viewsets.ModelViewSet):
    queryset = Room.objects.all()
    serializer_class = RoomSerializer
    permission_classes = [IsStaff]


""" ViewSet for managing RoomType objects (accessible only by staff) """
class RoomTypeViewSet(viewsets.ModelViewSet):
    queryset = RoomType.objects.all()
    serializer_class = RoomTypeSerializer
    permission_classes = [IsStaff]


""" ViewSet for managing Amenity objects (accessible only by staff) """
class AmenityViewSet(viewsets.ModelViewSet):
    queryset = Amenity.objects.all()
    serializer_class = AmenitySerializer
    permission_classes = [IsStaff]


"""
    ViewSet for handling booking creation and viewing
    Staff can view all bookings; regular users can only view their own
"""
class BookingViewSet(viewsets.ModelViewSet):
    queryset = Booking.objects.all()
    serializer_class = BookingSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        # Skip real DB query during schema generation
        if getattr(self, 'swagger_fake_view', False):
            return Booking.objects.none()
        user = self.request.user
        # Staff can see all bookings, regular users only their own
        if user.is_staff:
            return Booking.objects.all()
        return Booking.objects.filter(user=user)

    def perform_create(self, serializer):
        # Automatically assign the booking to the current authenticated user
        serializer.save(user=self.request.user)


"""ViewSet for managing Payment objects (accessible only by staff)"""
class PaymentViewSet(viewsets.ModelViewSet):
    permission_classes = [IsStaff]
    queryset = Payment.objects.all()
    serializer_class = PaymentSerializer


"""ViewSet for managing user reviews (no explicit permission set — open by default)"""
class ReviewViewSet(viewsets.ModelViewSet):
    queryset = Review.objects.all()
    serializer_class = ReviewSerializer

"""
    Returns a list of available room types for a given hotel and date range.

    This endpoint is used to check which room types are available for booking in a specific hotel
    for the selected date range and number of guests. It validates the input parameters, 
    checks each room type against existing bookings and capacity, and returns the types that 
    have at least one available room.

    Query Parameters:
        - hotel: ID of the hotel to check
        - check_in: Start date of the booking (ISO format: YYYY-MM-DDTHH:MM)
        - check_out: End date of the booking (ISO format: YYYY-MM-DDTHH:MM)
        - adults: Number of adult guests
        - children: Number of child guests

    Returns:
        - 200 OK with a list of available room types (as serialized data)
        - 400 Bad Request if required parameters are missing
        - 404 Not Found if the specified hotel does not exist
"""
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

"""
    Updates the status of a payment based on invoice_id.

    This endpoint is typically called by Monobank via webhook after a payment is processed.
    It receives the invoice_id and the new status (e.g., 'paid') and updates the corresponding
    Payment record in the database.

    Expected JSON payload:
        {
            "invoice_id": "inv_abc123",
            "status": "paid"
        }

    Returns:
        - 200 OK with success message if update is successful
        - 400 Bad Request if required data is missing or validation fails
        - 404 Not Found if payment with given invoice_id does not exist
"""
@api_view(['POST'])
@permission_classes([permissions.AllowAny])
def update_payment_status(request):
    # Extract invoice_id and new status from the request payload
    invoice_id = request.data.get('invoiceId')
    new_status = request.data.get('status')

    # Validate input: both fields are required
    if not invoice_id or not new_status:
        return Response({'error': 'invoice_id and status are required'}, status=400)

    try:
        # Attempt to retrieve the payment object by invoice ID
        payment = Payment.objects.get(invoice_id=invoice_id)
    except Payment.DoesNotExist:
        # Return an error if payment was not found
        return Response({'error': 'Payment not found'}, status=404)

    # Create a serializer with partial update to update only the status field
    serializer = PaymentStatusUpdateSerializer(payment, data={'status': new_status}, partial=True)
    if serializer.is_valid():
        # Save the updated payment status
        serializer.save()
        return Response({'message': 'Payment status updated successfully'})

    # Return validation errors if any
    return Response(serializer.errors, status=400)

""" Render a success page after payment is completed """
def payment_success(request):
    return render(request, 'payment-success.html')