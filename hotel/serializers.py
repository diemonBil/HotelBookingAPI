from rest_framework import serializers
from django.conf import settings
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
    rooms = serializers.PrimaryKeyRelatedField(
        queryset=Room.objects.all(),
        many=True
    )
    class Meta:
        model = Booking
        fields = '__all__'

    def validate(self, data):
        adults = data.get('adults', 0)
        children = data.get('children', 0)
        rooms = data.get('rooms', [])
        total_guests = adults + children

        total_capacity = sum(room.max_guests for room in rooms)

        if total_guests > total_capacity:
            raise serializers.ValidationError(
                f"Total guests ({total_guests}) exceed room capacity ({total_capacity})."
            )

        return data


class PaymentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Payment
        fields = '__all__'


class ReviewSerializer(serializers.ModelSerializer):
    class Meta:
        model = Review
        fields = '__all__'
