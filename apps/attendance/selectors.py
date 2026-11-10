from django.contrib.auth import get_user_model
from django.db.models import Q
from django.shortcuts import get_object_or_404
from django.utils import timezone

from .models import GuardAssignment


def current_assignments():
    return GuardAssignment.objects.filter(ended_at__isnull=True)


def has_open_assignments(user_id):
    return current_assignments().filter(Q(employee_id=user_id) | Q(guard_id=user_id)).exists()


def has_pending_requests(user_id):
    # shortcut: request models do not exist yet; replace this stub in Phase 3.
    return False


def employees_visible_to(user):
    employees = get_user_model().objects.filter(role="EMPLOYEE")
    if user.role == "ADMIN":
        return employees
    if user.role == "GUARD":
        assigned_ids = current_assignments().filter(
            guard_id=user.pk, started_at__lte=timezone.now(),
        ).values("employee_id")
        return employees.filter(pk__in=assigned_ids)
    return employees.filter(pk=user.pk)


def employee_for_user(user, employee_id):
    return get_object_or_404(employees_visible_to(user), pk=employee_id)


def assignment_history_for(employee_id):
    return GuardAssignment.objects.filter(employee_id=employee_id).select_related("guard").order_by("-started_at", "-pk")


def last_closed_assignment_end(employee_id):
    return GuardAssignment.objects.filter(employee_id=employee_id, ended_at__isnull=False).order_by("-ended_at").values_list("ended_at", flat=True).first()


def assignment_management_data():
    users = get_user_model().objects
    assignments = {assignment.employee_id: assignment for assignment in current_assignments().select_related("guard")}
    return {
        "rows": [
            {"employee": employee, "assignment": assignments.get(employee.pk)}
            for employee in users.filter(role="EMPLOYEE", is_active=True).order_by("username")
        ],
        "guards": users.filter(role="GUARD", is_active=True).order_by("username"),
    }
