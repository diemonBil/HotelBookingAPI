from rest_framework import permissions


class IsAdminOrReadOnly(permissions.BasePermission):
    """Anyone may browse the catalogue; only staff may change it.

    Hotels, rooms, room types and amenities are public data — a booking API
    that hides them from guests is not much use.
    """

    def has_permission(self, request, view):
        if request.method in permissions.SAFE_METHODS:
            return True
        return bool(request.user and request.user.is_staff)


class IsOwnerOrReadOnly(permissions.BasePermission):
    """Object-level guard so users can only edit what they created."""

    def has_object_permission(self, request, view, obj):
        if request.method in permissions.SAFE_METHODS:
            return True
        if request.user and request.user.is_staff:
            return True
        return obj.user_id == request.user.id


class IsStaff(permissions.BasePermission):
    """Full access restricted to staff members."""

    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated and request.user.is_staff)
