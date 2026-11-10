from django.core.exceptions import ValidationError
from django.core.validators import validate_ipv46_address
from django.db import transaction

from .models import AuditLog


SENSITIVE_DETAIL_KEYS = {
    "authorization",
    "cookie",
    "csrf_token",
    "password",
    "raw_password",
    "secret",
    "session_key",
    "token",
}


def _validate_details(details):
    if not isinstance(details, dict):
        raise ValidationError("Audit details must be a dictionary.")
    for key, value in details.items():
        if str(key).lower() in SENSITIVE_DETAIL_KEYS:
            raise ValidationError(f"Sensitive audit detail is not allowed: {key}.")
        if isinstance(value, dict):
            _validate_details(value)


def log_activity(
    *,
    action,
    actor,
    target_employee=None,
    target=None,
    details=None,
    ip_address=None,
):
    if not transaction.get_connection().in_atomic_block:
        raise RuntimeError("Audit events must be written inside the action transaction.")
    details = details if details is not None else {}
    _validate_details(details)
    target_type = ""
    target_id = ""
    if target is not None:
        if target.pk is None:
            raise ValidationError("Audit targets must be saved before logging.")
        target_type = target._meta.label_lower
        target_id = str(target.pk)
    if ip_address:
        ip_address = str(ip_address)
        validate_ipv46_address(ip_address)
    return AuditLog.objects.create(
        action=action,
        actor=actor,
        target_employee=target_employee,
        target_type=target_type,
        target_id=target_id,
        details=details,
        ip_address=ip_address,
    )
