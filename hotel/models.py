from django.conf import settings
from django.db import models
from django.core.validators import MaxValueValidator, MinValueValidator

class Amenity(models.Model):
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)

    def __str__(self):
        return self.name


class Hotel(models.Model):
    name = models.CharField(max_length=255)
    location = models.CharField(max_length=255)
    description = models.TextField()

    def __str__(self):
        return f"{self.name} ({self.location})"

class RoomType(models.Model):
    name = models.CharField(max_length=100, unique=True)
    description = models.TextField(blank=True)

    def __str__(self):
        return self.name

class Room(models.Model):
    hotel = models.ForeignKey(Hotel, on_delete=models.CASCADE, related_name='rooms')
    room_number = models.IntegerField()
    room_type = models.ForeignKey(RoomType, on_delete=models.CASCADE, related_name='rooms')
    price_per_night = models.DecimalField(max_digits=7, decimal_places=2)
    is_available = models.BooleanField(default=True)
    amenities = models.ManyToManyField(Amenity, related_name='rooms', blank=True)
    max_guests = models.IntegerField()

    def __str__(self):
        return f"Room {self.room_number} - {self.hotel.name}"

    class Meta:
        unique_together = ('hotel', 'room_number')


class Booking(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='bookings')
    room = models.ForeignKey(Room, on_delete=models.CASCADE, related_name='bookings')
    check_in = models.DateTimeField()
    check_out = models.DateTimeField()
    adults = models.IntegerField()
    children = models.IntegerField()

    def __str__(self):
        return f"Booking by {self.user.username} in {self.room}"


class Payment(models.Model):
    booking = models.OneToOneField(Booking, on_delete=models.CASCADE, related_name='payment')
    amount = models.DecimalField(max_digits=7, decimal_places=2)
    status = models.CharField(max_length=255)
    payment_date = models.DateTimeField()

    def __str__(self):
        return f"Payment for Booking #{self.booking.id} - {self.status}"


class Review(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='reviews')
    hotel = models.ForeignKey(Hotel, on_delete=models.CASCADE, related_name='reviews')
    rating = models.IntegerField(validators=[MinValueValidator(1), MaxValueValidator(5)])
    comment = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Review by {self.user.username} for {self.hotel.name} ({self.rating}/5)"