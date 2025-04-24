import uuid
from django.utils import timezone
from rest_framework import serializers
from django.utils.timezone import now
from .models import Hotel, Room, Amenity, Booking, Payment, Review, RoomType
from .services import create_monobank_invoice


"""Serializer for Amenity model"""
class AmenitySerializer(serializers.ModelSerializer):
    class Meta:
        model = Amenity
        fields = '__all__'


"""Serializer for Hotel model"""
class HotelSerializer(serializers.ModelSerializer):
    class Meta:
        model = Hotel
        fields = '__all__'


"""Serializer for Room model including nested relations to hotel, amenities, and room type"""
class RoomSerializer(serializers.ModelSerializer):
    hotel = serializers.SlugRelatedField(
        queryset=Hotel.objects.all(),
        slug_field='name'
    )
    amenities = serializers.PrimaryKeyRelatedField(
        many=True,
        queryset=Amenity.objects.all()
    )
    room_type = serializers.SlugRelatedField(
        queryset=RoomType.objects.all(),
        slug_field='name'
    )

    class Meta:
        model = Room
        fields = '__all__'


"""Serializer for RoomType model"""
class RoomTypeSerializer(serializers.ModelSerializer):
    class Meta:
        model = RoomType
        fields = '__all__'


"""Serializer for Booking model with room assignment logic"""
class BookingSerializer(serializers.ModelSerializer):
    hotel = serializers.PrimaryKeyRelatedField(
        queryset=Hotel.objects.all(),
        write_only=True
    )
    room_type = serializers.SlugRelatedField(
        slug_field='name',
        queryset=RoomType.objects.all(),
        write_only=True
    )
    rooms = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = Booking
        fields = [
            'hotel', 'room_type', 'check_in', 'check_out',
            'adults', 'children', 'rooms'
        ]

    # Return a list of rooms associated with the booking
    def get_rooms(self, obj):
        return [
            {
                "id": room.id,
                "room_number": room.room_number,
                "hotel": room.hotel.name
            }
            for room in obj.rooms.all()
        ]

    # Validate the booking input and assign a room
    def validate(self, data):
        check_in = data['check_in']
        check_out = data['check_out']
        hotel = data['hotel']
        room_type = data['room_type']
        adults = data['adults']
        children = data['children']
        total_guests = adults + children

        # Find all rooms of the selected type that can fit the guest count
        possible_rooms = Room.objects.filter(
            hotel=hotel,
            room_type=room_type,
            max_guests__gte=total_guests,
            is_available=True
        )

        # Disallow booking for past dates
        if check_in < now():
            raise serializers.ValidationError("Check-in date cannot be in the past.")

        # Ensure check-out is after check-in
        if check_out <= check_in:
            raise serializers.ValidationError("Check-out must be after check-in.")

        # Check availability of rooms by looking for overlapping bookings
        available_room = None
        for room in possible_rooms:
            overlapping = Booking.objects.filter(
                rooms=room,
                check_in__lt=check_out,
                check_out__gt=check_in
            )
            if not overlapping.exists():
                available_room = room
                break

        if not available_room:
            raise serializers.ValidationError(
                f"No available rooms of type '{room_type.name}' for the selected dates and guest count."
            )

        # Save the available room for later use in create()
        self.available_room = available_room
        return data

    # Create the booking, assign room, calculate total, and create payment
    def create(self, validated_data):
        user = validated_data['user']
        check_in = validated_data['check_in']
        check_out = validated_data['check_out']
        adults = validated_data['adults']
        children = validated_data['children']

        # Create booking record
        booking = Booking.objects.create(
            user=user,
            check_in=check_in,
            check_out=check_out,
            adults=adults,
            children=children
        )

        # Assign the available room
        booking.rooms.add(self.available_room)

        # Calculate the total amount for the booking
        nights = (check_out - check_in).days
        total_price = sum(room.price_per_night for room in booking.rooms.all()) * nights

        # Generate invoice ID
        invoice_id = f'inv_{uuid.uuid4().hex[:10]}'

        # Create a payment record
        payment = Payment.objects.create(
            booking=booking,
            amount=total_price,
            status='pending',
            payment_date=timezone.now(),
            invoice_id=invoice_id
        )

        # Create invoice through Monobank API
        invoice_data = create_monobank_invoice(payment)
        payment_url = invoice_data.get("pageUrl")
        print(f"[💳] Payment link: {payment_url}")

        # Optionally update invoice_id from Monobank response
        payment.invoice_id = invoice_data.get("invoiceId", invoice_id)
        payment.save()

        return booking


"""Serializer for full Payment object"""
class PaymentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Payment
        fields = '__all__'


"""Serializer for updating only the status field of Payment"""
class PaymentStatusUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Payment
        fields = ['status']


"""Serializer for Review model"""
class ReviewSerializer(serializers.ModelSerializer):
    class Meta:
        model = Review
        fields = '__all__'