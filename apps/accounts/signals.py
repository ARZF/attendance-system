from django.contrib.auth.signals import user_login_failed
from django.db import transaction
from django.dispatch import receiver

from apps.audit.services import log_activity

from .security import get_client_ip


@receiver(user_login_failed)
def audit_failed_login(sender, credentials, request, **kwargs):
    username = credentials.get("username")
    details = {"username": str(username)[:150]} if username else {}
    with transaction.atomic():
        log_activity(
            action="LOGIN_FAILED",
            actor=None,
            details=details,
            ip_address=get_client_ip(request) if request is not None else None,
        )
