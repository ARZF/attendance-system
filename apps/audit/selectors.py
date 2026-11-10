from .models import AuditLog


def audit_history(
    *,
    actor_id=None,
    target_employee_id=None,
    action=None,
    target_type=None,
    target_id=None,
    created_from=None,
    created_to=None,
):
    logs = AuditLog.objects.select_related("actor", "target_employee")
    if actor_id is not None:
        logs = logs.filter(actor_id=actor_id)
    if target_employee_id is not None:
        logs = logs.filter(target_employee_id=target_employee_id)
    if action:
        logs = logs.filter(action=action)
    if target_type:
        logs = logs.filter(target_type=target_type)
    if target_id:
        logs = logs.filter(target_id=str(target_id))
    if created_from is not None:
        logs = logs.filter(created_at__gte=created_from)
    if created_to is not None:
        logs = logs.filter(created_at__lt=created_to)
    return logs.order_by("-created_at", "-pk")
