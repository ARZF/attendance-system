from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied
from django.db import models
from django.db.models import Q
from django.db.models.functions import Coalesce, Greatest, Least
from django.shortcuts import get_object_or_404
from django.utils import timezone

from .models import AttendanceRequest, AttendanceSession, GuardAssignment
from .permissions import require_admin


def current_assignments():
    return GuardAssignment.objects.filter(ended_at__isnull=True)


def has_open_assignments(user_id):
    return current_assignments().filter(Q(employee_id=user_id) | Q(guard_id=user_id)).exists()


def has_pending_requests(user_id):
    pending = AttendanceRequest.objects.filter(status=AttendanceRequest.Status.PENDING)
    if pending.filter(employee_id=user_id).exists():
        return True
    return pending.filter(
        employee__role="EMPLOYEE",
        employee__guard_assignments__guard_id=user_id,
        employee__guard_assignments__started_at__lte=timezone.now(),
        employee__guard_assignments__ended_at__isnull=True,
    ).exists()


def attendance_history_for(employee_id):
    return AttendanceSession.objects.filter(employee_id=employee_id).select_related(
        "employee"
    )


def active_session_for(employee_id):
    return AttendanceSession.objects.filter(
        employee_id=employee_id,
        check_out_at__isnull=True,
    ).select_related("employee").first()


def pending_requests_for_employee(employee_id):
    return AttendanceRequest.objects.filter(
        employee_id=employee_id,
        status=AttendanceRequest.Status.PENDING,
    ).select_related("employee", "session")


def pending_requests_for_guard(guard):
    if not guard.is_authenticated or not guard.is_active or guard.role != "GUARD":
        raise PermissionDenied("An active guard is required.")
    return AttendanceRequest.objects.filter(
        status=AttendanceRequest.Status.PENDING,
        employee__role="EMPLOYEE",
        employee__guard_assignments__guard_id=guard.pk,
        employee__guard_assignments__started_at__lte=timezone.now(),
        employee__guard_assignments__ended_at__isnull=True,
    ).select_related("employee", "session")


def pending_requests_for_admin(admin):
    require_admin(admin)
    return AttendanceRequest.objects.filter(
        status=AttendanceRequest.Status.PENDING,
    ).select_related("employee", "session")


def attendance_sessions_in_range(
    *,
    start_at,
    end_at,
    employee_id=None,
    employee_ids=None,
    sort="-check_in_at",
):
    allowed_sort = {
        "check_in_at",
        "-check_in_at",
        "check_out_at",
        "-check_out_at",
        "employee__username",
        "-employee__username",
    }
    sessions = AttendanceSession.objects.filter(
        check_in_at__lt=end_at,
    ).filter(
        Q(check_out_at__isnull=True) | Q(check_out_at__gt=start_at)
    ).select_related("employee")
    if employee_id is not None:
        sessions = sessions.filter(employee_id=employee_id)
    if employee_ids is not None:
        sessions = sessions.filter(employee_id__in=employee_ids)
    return sessions.order_by(sort if sort in allowed_sort else "-check_in_at", "-pk")


def completed_working_time(*, start_at, end_at, employee_id=None, employee_ids=None):
    sessions = AttendanceSession.objects.filter(
        check_out_at__isnull=False,
        check_in_at__lt=end_at,
        check_out_at__gt=start_at,
    )
    if employee_id is not None:
        sessions = sessions.filter(employee_id=employee_id)
    if employee_ids is not None:
        sessions = sessions.filter(employee_id__in=employee_ids)
    duration = models.ExpressionWrapper(
        Least("check_out_at", models.Value(end_at))
        - Greatest("check_in_at", models.Value(start_at)),
        output_field=models.DurationField(),
    )
    return sessions.aggregate(
        total=Coalesce(
            models.Sum(duration),
            models.Value(timedelta(0), output_field=models.DurationField()),
        )
    )["total"]


def attendance_overview(*, start_at, end_at, employee_ids=None):
    sessions = AttendanceSession.objects.filter(
        check_out_at__isnull=False,
        check_in_at__lt=end_at,
        check_out_at__gt=start_at,
    )
    if employee_ids is not None:
        sessions = sessions.filter(employee_id__in=employee_ids)
    duration = models.ExpressionWrapper(
        Least("check_out_at", models.Value(end_at))
        - Greatest("check_in_at", models.Value(start_at)),
        output_field=models.DurationField(),
    )
    return sessions.values("employee_id", "employee__username").annotate(
        session_count=models.Count("pk"),
        total_working_time=Coalesce(
            models.Sum(duration),
            models.Value(timedelta(0), output_field=models.DurationField()),
        ),
    ).order_by("employee__username")


def rejected_requests_for_employee(employee_id):
    return AttendanceRequest.objects.filter(
        employee_id=employee_id,
        status=AttendanceRequest.Status.REJECTED,
    ).select_related("employee", "reviewed_by", "session").order_by(
        "-reviewed_at",
        "-pk",
    )


def request_history_for_employee(employee_id):
    return AttendanceRequest.objects.filter(employee_id=employee_id).select_related(
        "reviewed_by",
        "session",
    ).order_by("-requested_at", "-pk")


def global_request_history(*, status=None, request_type=None, employee_id=None):
    requests = AttendanceRequest.objects.select_related(
        "employee",
        "reviewed_by",
        "session",
    )
    if status:
        requests = requests.filter(status=status)
    if request_type:
        requests = requests.filter(request_type=request_type)
    if employee_id is not None:
        requests = requests.filter(employee_id=employee_id)
    return requests.order_by("-requested_at", "-pk")


def recent_attendance_activity(limit=20):
    return AttendanceRequest.objects.exclude(
        status=AttendanceRequest.Status.PENDING,
    ).select_related("employee", "reviewed_by", "session").order_by(
        "-updated_at",
        "-pk",
    )[:limit]


def admin_dashboard_counts():
    users = get_user_model().objects
    return {
        "active_employees": users.filter(role="EMPLOYEE", is_active=True).count(),
        "active_guards": users.filter(role="GUARD", is_active=True).count(),
        "active_sessions": AttendanceSession.objects.filter(
            check_out_at__isnull=True,
        ).count(),
        "pending_requests": AttendanceRequest.objects.filter(
            status=AttendanceRequest.Status.PENDING,
        ).count(),
    }


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


def current_guard_assignments(guard_id=None):
    assignments = current_assignments().select_related("employee", "guard")
    if guard_id is not None:
        assignments = assignments.filter(guard_id=guard_id)
    return assignments.order_by("employee__username")


def guard_assignment_history(*, employee_id=None, guard_id=None):
    assignments = GuardAssignment.objects.select_related("employee", "guard")
    if employee_id is not None:
        assignments = assignments.filter(employee_id=employee_id)
    if guard_id is not None:
        assignments = assignments.filter(guard_id=guard_id)
    return assignments.order_by("-started_at", "-pk")


def last_closed_assignment_end(employee_id):
    return GuardAssignment.objects.filter(employee_id=employee_id, ended_at__isnull=False).order_by("-ended_at").values_list("ended_at", flat=True).first()


def assignment_management_data():
    users = get_user_model().objects
    assignments = {assignment.employee_id: assignment for assignment in current_assignments().select_related("guard")}
    return {
        "rows": [
            {"employee": employee, "assignment": assignments.get(employee.pk)}
            for employee in users.filter(role="EMPLOYEE").order_by("username")
        ],
        "guards": users.filter(role="GUARD", is_active=True).order_by("username"),
    }
