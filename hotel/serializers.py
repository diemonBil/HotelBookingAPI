from django.utils import timezone
from rest_framework import serializers
from django.utils.timezone import now
from .models import Hotel, Room, Amenity, Booking, Payment, Review, RoomType


class AmenitySerializer(serializers.ModelSerializer):
    class Meta:
        model = Amenity
        fields = '__all__'


class HotelSerializer(serializers.ModelSerializer):
    class Meta:
        model = Hotel
        fields = '__all__'

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

class RoomTypeSerializer(serializers.ModelSerializer):
    class Meta:
        model = RoomType
        fields = '__all__'

class BookingSerializer(serializers.ModelSerializer):
    hotel = serializers.PrimaryKeyRelatedField(
        queryset=Hotel.objects.all(),
        write_only=True
    )
    room_type = serializers.SlugRelatedField(
        slug_field='name',
        queryset=RoomType.objects.all(),
        write_only = True
    )
    rooms = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = Booking
        fields = [
            'hotel', 'room_type', 'check_in', 'check_out',
            'adults', 'children', 'rooms'
        ]

    def get_rooms(self, obj):
        return [
            {
                "id": room.id,
                "room_number": room.room_number,
                "hotel": room.hotel.name
            }
            for room in obj.rooms.all()
        ]

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

        # Check for each room if it is available in the selected date range
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

        # Pass the selected available room to use in the create() method
        self.available_room = available_room
        return data

    def create(self, validated_data):
        user = validated_data['user']
        check_in = validated_data['check_in']
        check_out = validated_data['check_out']
        adults = validated_data['adults']
        children = validated_data['children']

        # Create booking
        booking = Booking.objects.create(
            user=user,
            check_in=check_in,
            check_out=check_out,
            adults=adults,
            children=children
        )

        # Add room(s) from validation phase (self.available_room or similar)
        booking.rooms.add(self.available_room)

        # Calculate nights
        nights = (check_out - check_in).days

        # Total price = sum of all room prices * nights
        total_price = sum(room.price_per_night for room in booking.rooms.all()) * nights

        # Create related payment object
        Payment.objects.create(
            booking=booking,
            amount=total_price,
            status='pending',
            payment_date=timezone.now()
        )

        return booking



class PaymentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Payment
        fields = '__all__'


class ReviewSerializer(serializers.ModelSerializer):
    class Meta:
        model = Review
        fields = '__all__'
