from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import transaction
from django.shortcuts import get_object_or_404
from django.utils import timezone

from apps.audit.services import log_activity

from .models import GuardAssignment
from .permissions import require_admin
from .selectors import current_assignments, last_closed_assignment_end


@transaction.atomic
def assign_guard(*, actor, employee_id, guard_id, expected_assignment_id):
    require_admin(actor)
    users = get_user_model().objects
    employee = get_object_or_404(users.select_for_update(), pk=employee_id)
    require_admin(actor)
    if employee.role != "EMPLOYEE" or not employee.is_active:
        raise ValidationError("The employee must be an active EMPLOYEE.")
    guard = get_object_or_404(users.select_for_update(), pk=guard_id)
    if guard.role != "GUARD" or not guard.is_active:
        raise ValidationError("The reviewer must be an active GUARD.")

    current = current_assignments().select_for_update().filter(employee_id=employee.pk).first()
    if expected_assignment_id != (current.pk if current else None):
        raise ValidationError("The assignment changed. Refresh the page before submitting again.")
    if current and current.guard_id == guard.pk:
        return current

    now = timezone.now()
    if current is None:
        previous_end = last_closed_assignment_end(employee.pk)
        if previous_end is not None and previous_end > now:
            raise ValidationError("This assignment would overlap the employee's assignment history.")
    if current:
        if now <= current.started_at:
            raise ValidationError("An assignment must end after it starts.")
        current.ended_at = now
        current.save(update_fields=["ended_at"])
    assignment = GuardAssignment.objects.create(employee=employee, guard=guard, started_at=now)
    log_activity(
        action="ASSIGNMENT_REPLACED" if current else "ASSIGNMENT_CREATED",
        actor=actor, target_employee=employee,
        details={
            "assignment_id": assignment.pk, "guard_id": guard.pk,
            "started_at": now.isoformat(),
            "previous_assignment_id": current.pk if current else None,
            "previous_guard_id": current.guard_id if current else None,
        },
    )
    return assignment


@transaction.atomic
def end_assignment(*, actor, employee_id, assignment_id):
    require_admin(actor)
    employee = get_object_or_404(get_user_model().objects.select_for_update(), pk=employee_id)
    assignment = get_object_or_404(
        GuardAssignment.objects.select_for_update(), pk=assignment_id, employee_id=employee.pk,
    )
    require_admin(actor)
    if assignment.ended_at is not None:
        raise ValidationError("This assignment has already ended. Refresh the page.")
    now = timezone.now()
    if now <= assignment.started_at:
        raise ValidationError("An assignment must end after it starts.")
    assignment.ended_at = now
    assignment.save(update_fields=["ended_at"])
    log_activity(
        action="ASSIGNMENT_ENDED", actor=actor, target_employee=employee,
        details={"assignment_id": assignment.pk, "guard_id": assignment.guard_id, "ended_at": now.isoformat()},
    )
    return assignment
