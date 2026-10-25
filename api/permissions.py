from rest_framework.permissions import SAFE_METHODS, BasePermission


class IsStaffOrReadOnly(BasePermission):
    """Everyone who is logged in can read; only staff can create, edit or delete."""

    message = "Only staff can change this."

    def has_permission(self, request, view):
        return request.method in SAFE_METHODS or request.user.is_staff


class IsStaff(BasePermission):
    message = "Only staff can do this."

    def has_permission(self, request, view):
        return request.user.is_staff


def customer_of(user):
    """The Customer linked to a login, or None (for example a staff account)."""
    return getattr(user, "customer", None)
