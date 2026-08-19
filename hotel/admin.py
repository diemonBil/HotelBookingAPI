from django.contrib import admin

from .models import Amenity, Booking, Hotel, Payment, Review, Room, RoomType


class RoomInline(admin.TabularInline):
    model = Room
    extra = 0
    fields = ("room_number", "room_type", "price_per_night", "max_guests", "is_available")
    show_change_link = True


@admin.register(Hotel)
class HotelAdmin(admin.ModelAdmin):
    list_display = ("name", "location", "room_count")
    search_fields = ("name", "location")
    list_filter = ("location",)
    inlines = (RoomInline,)

    def get_queryset(self, request):
        return super().get_queryset(request).prefetch_related("rooms")

    @admin.display(description="rooms")
    def room_count(self, obj):
        return obj.rooms.count()


@admin.register(Room)
class RoomAdmin(admin.ModelAdmin):
    list_display = (
        "room_number",
        "hotel",
        "room_type",
        "price_per_night",
        "max_guests",
        "is_available",
    )
    list_filter = ("hotel", "room_type", "is_available")
    search_fields = ("room_number", "hotel__name")
    list_select_related = ("hotel", "room_type")
    filter_horizontal = ("amenities",)


@admin.register(RoomType)
class RoomTypeAdmin(admin.ModelAdmin):
    list_display = ("name",)
    search_fields = ("name",)


@admin.register(Amenity)
class AmenityAdmin(admin.ModelAdmin):
    list_display = ("name",)
    search_fields = ("name",)


class PaymentInline(admin.StackedInline):
    model = Payment
    extra = 0
    readonly_fields = ("provider", "reference", "provider_invoice_id", "amount", "payment_url")


@admin.register(Booking)
class BookingAdmin(admin.ModelAdmin):
    list_display = ("id", "user", "hotel", "check_in", "check_out", "status", "created_at")
    list_filter = ("status", "hotel", "check_in")
    search_fields = ("user__username", "user__email", "hotel__name")
    list_select_related = ("user", "hotel")
    date_hierarchy = "check_in"
    filter_horizontal = ("rooms",)
    inlines = (PaymentInline,)


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = ("id", "booking", "provider", "amount", "status", "created_at", "paid_at")
    list_filter = ("status", "provider")
    search_fields = ("reference", "provider_invoice_id")
    list_select_related = ("booking",)
    # Payments mirror an external ledger; edit them there, not here.
    readonly_fields = (
        "provider",
        "reference",
        "provider_invoice_id",
        "amount",
        "payment_url",
        "paid_at",
    )


@admin.register(Review)
class ReviewAdmin(admin.ModelAdmin):
    list_display = ("hotel", "user", "rating", "created_at")
    list_filter = ("rating", "hotel")
    search_fields = ("user__username", "hotel__name", "comment")
    list_select_related = ("user", "hotel")
