"""Populate the database with a small, realistic demo dataset.

Replaces the old ``dump.json`` fixture, which carried real user accounts and
password hashes. Everything here is generated, idempotent and safe to commit.

    python manage.py seed_demo_data
"""

from __future__ import annotations

import random
from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from hotel.models import Amenity, Booking, Hotel, Payment, Review, Room, RoomType

AMENITIES = [
    ("Free WiFi", "High-speed wireless internet throughout the building."),
    ("Free parking", "On-site parking at no extra charge."),
    ("Non-smoking rooms", "Rooms kept in a 100% smoke-free environment."),
    ("Spa", "Wellness treatments and massage services."),
    ("EV charging", "Type 2 charging points in the garage."),
    ("Air conditioning", "Individually controlled climate in every room."),
    ("Breakfast included", "Buffet breakfast served from 07:00 to 10:30."),
]

ROOM_TYPES = [
    ("Standard", "A comfortable room with the essentials.", 1, Decimal("55.00")),
    ("Double", "Twin or king bed, suitable for two guests.", 2, Decimal("85.00")),
    ("Family", "Extra space and bedding for children.", 4, Decimal("130.00")),
    ("Deluxe", "Larger room with a seating area and a better view.", 2, Decimal("165.00")),
    ("Suite", "Separate living room and bedroom.", 4, Decimal("240.00")),
]

HOTELS = [
    ("Seaside Grand", "Odesa", "A restored 19th-century building a short walk from the beach."),
    (
        "Carpathian Lodge",
        "Bukovel",
        "Timber-built mountain lodge with direct access to the slopes.",
    ),
    (
        "Riverside Boutique",
        "Kyiv",
        "Quiet boutique hotel on the left bank, ten minutes from the centre.",
    ),
    ("Old Town Inn", "Lviv", "Family-run inn on a cobbled street inside the historic centre."),
]

REVIEW_COMMENTS = [
    "Spotless room and genuinely helpful staff. Would stay again.",
    "Great location, though the street noise carries at night.",
    "Breakfast was the highlight. Room was smaller than the photos suggest.",
    "Excellent value for the price. Check-in took a while.",
    "Comfortable bed, strong WiFi, everything worked as advertised.",
]

DEMO_PASSWORD = "DemoPassw0rd!42"


class Command(BaseCommand):
    help = "Create demo hotels, rooms, users, bookings and reviews."

    def add_arguments(self, parser):
        parser.add_argument(
            "--flush",
            action="store_true",
            help="Delete existing hotel data before seeding.",
        )
        parser.add_argument(
            "--password",
            default=DEMO_PASSWORD,
            help="Password for the generated demo accounts.",
        )
        parser.add_argument(
            "--seed", type=int, default=20240501, help="Random seed, for reproducible data."
        )

    @transaction.atomic
    def handle(self, *args, **options):
        random.seed(options["seed"])
        password = options["password"]
        verbose = options["verbosity"] > 0

        if options["flush"]:
            if verbose:
                self.stdout.write("Removing existing hotel data...")
            Payment.objects.all().delete()
            Booking.objects.all().delete()
            Review.objects.all().delete()
            Room.objects.all().delete()
            Hotel.objects.all().delete()
            RoomType.objects.all().delete()
            Amenity.objects.all().delete()

        amenities = self._create_amenities()
        room_types = self._create_room_types()
        hotels = self._create_hotels(room_types, amenities)
        users = self._create_users(password)
        self._create_bookings(hotels, users)
        self._create_reviews(hotels, users)

        if verbose:
            self.stdout.write(
                self.style.SUCCESS(
                    f"Seeded {Hotel.objects.count()} hotels, {Room.objects.count()} rooms, "
                    f"{Booking.objects.count()} bookings, {Review.objects.count()} reviews."
                )
            )
            self.stdout.write(f"Demo accounts: admin / guest1 / guest2  (password: {password})")

    def _create_amenities(self) -> list[Amenity]:
        return [
            Amenity.objects.get_or_create(name=name, defaults={"description": description})[0]
            for name, description in AMENITIES
        ]

    def _create_room_types(self) -> dict[str, RoomType]:
        types = {}
        for name, description, _capacity, _price in ROOM_TYPES:
            types[name] = RoomType.objects.get_or_create(
                name=name, defaults={"description": description}
            )[0]
        return types

    def _create_hotels(self, room_types, amenities) -> list[Hotel]:
        hotels = []
        for name, location, description in HOTELS:
            hotel, _ = Hotel.objects.get_or_create(
                name=name, location=location, defaults={"description": description}
            )
            hotels.append(hotel)

            room_number = 101
            for type_name, _desc, capacity, base_price in ROOM_TYPES:
                # Two rooms of every type, so availability tests have room to move.
                for _ in range(2):
                    room, created = Room.objects.get_or_create(
                        hotel=hotel,
                        room_number=room_number,
                        defaults={
                            "room_type": room_types[type_name],
                            # A little spread so ordering by price is meaningful.
                            "price_per_night": base_price + Decimal(random.randrange(0, 25)),
                            "max_guests": capacity,
                        },
                    )
                    if created:
                        room.amenities.set(random.sample(amenities, k=random.randint(2, 5)))
                    room_number += 1
        return hotels

    def _create_users(self, password: str):
        user_model = get_user_model()
        if len(password) < 8:
            raise CommandError("Demo password must be at least 8 characters.")

        users = []
        admin, created = user_model.objects.get_or_create(
            username="admin",
            defaults={"email": "admin@example.com", "is_staff": True, "is_superuser": True},
        )
        if created:
            admin.set_password(password)
            admin.save(update_fields=["password"])

        for index in (1, 2):
            guest, created = user_model.objects.get_or_create(
                username=f"guest{index}",
                defaults={
                    "email": f"guest{index}@example.com",
                    "first_name": f"Guest{index}",
                },
            )
            if created:
                guest.set_password(password)
                guest.save(update_fields=["password"])
            users.append(guest)
        return users

    def _create_bookings(self, hotels, users):
        if Booking.objects.exists():
            return

        today = timezone.localdate()
        for index, user in enumerate(users):
            for offset in (7, 45):
                hotel = hotels[(index + offset) % len(hotels)]
                room = hotel.rooms.order_by("room_number").first()
                if room is None:
                    continue

                check_in = today + timedelta(days=offset)
                check_out = check_in + timedelta(days=random.randint(2, 5))
                booking = Booking.objects.create(
                    user=user,
                    hotel=hotel,
                    check_in=check_in,
                    check_out=check_out,
                    adults=min(2, room.max_guests),
                    children=0,
                    status=Booking.Status.CONFIRMED,
                )
                booking.rooms.add(room)
                Payment.objects.create(
                    booking=booking,
                    provider="fake",
                    reference=f"seed-{booking.pk}",
                    provider_invoice_id=f"seed_inv_{booking.pk}",
                    amount=booking.calculate_total(),
                    status=Payment.Status.PAID,
                    paid_at=timezone.now(),
                )

    def _create_reviews(self, hotels, users):
        # Chosen by index rather than sampled: re-running the command must not
        # produce a different pairing and therefore extra reviews.
        for user_index, user in enumerate(users):
            for step in range(2):
                hotel = hotels[(user_index + step) % len(hotels)]
                position = user_index * 2 + step
                Review.objects.get_or_create(
                    user=user,
                    hotel=hotel,
                    defaults={
                        "rating": 3 + (position % 3),
                        "comment": REVIEW_COMMENTS[position % len(REVIEW_COMMENTS)],
                    },
                )
