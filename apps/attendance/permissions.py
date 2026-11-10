from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied


def require_admin(actor):
    if not actor.is_authenticated or not get_user_model().objects.filter(
        pk=actor.pk, role="ADMIN", is_active=True,
    ).exists():
        raise PermissionDenied("An active business administrator is required.")
