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


class BookingSerializer(serializers.ModelSerializer):
    class Meta:
        model = Booking
        fields = '__all__'


class PaymentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Payment
        fields = '__all__'


class ReviewSerializer(serializers.ModelSerializer):
    class Meta:
        model = Review
        fields = '__all__'
