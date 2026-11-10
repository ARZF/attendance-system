from django.db import transaction

from .models import AuditLog


def log_activity(*, action, actor, target_employee=None, details=None):
    if not transaction.get_connection().in_atomic_block:
        raise RuntimeError("Audit events must be written inside the action transaction.")
    return AuditLog.objects.create(
        action=action, actor=actor, target_employee=target_employee,
        details=details if details is not None else {},
    )
