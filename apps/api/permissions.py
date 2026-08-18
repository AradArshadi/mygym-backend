from rest_framework.permissions import BasePermission


class IsStaffOrPlatformAdmin(BasePermission):
    """Allow only Django staff/superusers or users with the custom ADMIN role."""

    message = 'This API endpoint is restricted to platform admins.'

    def has_permission(self, request, view):
        user = request.user
        return bool(
            user
            and user.is_authenticated
            and (
                user.is_staff
                or user.is_superuser
                or getattr(user, 'role', '') == 'ADMIN'
            )
        )


class IsOwnerOrStaffAdmin(BasePermission):
    """Allow gym owners plus staff/platform admins."""

    message = 'This API endpoint is restricted to gym owners and platform admins.'

    def has_permission(self, request, view):
        user = request.user
        return bool(
            user
            and user.is_authenticated
            and (
                user.is_staff
                or user.is_superuser
                or getattr(user, 'role', '') in {'OWNER', 'ADMIN'}
            )
        )
