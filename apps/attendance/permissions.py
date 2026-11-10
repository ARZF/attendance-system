from django.contrib.auth import get_user_model
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import PermissionDenied
from django.http import Http404
from django.utils import timezone

from .models import GuardAssignment


class RoleRequiredMixin(LoginRequiredMixin):
    allowed_roles = ("EMPLOYEE", "GUARD", "ADMIN")

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return self.handle_no_permission()
        if not request.user.is_active or request.user.role not in self.allowed_roles:
            raise PermissionDenied("Your business role cannot access this endpoint.")
        return super().dispatch(request, *args, **kwargs)


class AdminRequiredMixin(RoleRequiredMixin):
    allowed_roles = ("ADMIN",)


def require_admin(actor):
    if not actor.is_authenticated or not get_user_model().objects.filter(
        pk=actor.pk, role="ADMIN", is_active=True,
    ).exists():
        raise PermissionDenied("An active business administrator is required.")


def require_attendance_reviewer(reviewer, employee):
    if not reviewer.is_authenticated or not reviewer.is_active:
        raise PermissionDenied("An active reviewer is required.")
    if reviewer.pk == employee.pk:
        raise PermissionDenied("You cannot review your own attendance request.")
    if reviewer.role == "ADMIN":
        return
    if reviewer.role != "GUARD":
        raise PermissionDenied("Your business role cannot review attendance requests.")
    if employee.role != "EMPLOYEE":
        raise Http404("Attendance request not found.")
    if not GuardAssignment.objects.select_for_update().filter(
        employee_id=employee.pk,
        guard_id=reviewer.pk,
        started_at__lte=timezone.now(),
        ended_at__isnull=True,
    ).exists():
        raise Http404("Attendance request not found.")


def require_attendance_corrector(corrector, employee):
    if not corrector.is_authenticated or not corrector.is_active:
        raise PermissionDenied("An active corrector is required.")
    if corrector.pk == employee.pk:
        raise PermissionDenied("You cannot correct your own attendance session.")
    if corrector.role == "ADMIN":
        return
    if corrector.role != "GUARD":
        raise PermissionDenied("Your business role cannot correct attendance sessions.")
    if employee.role != "EMPLOYEE":
        raise Http404("Attendance session not found.")
    if not GuardAssignment.objects.select_for_update().filter(
        employee_id=employee.pk,
        guard_id=corrector.pk,
        started_at__lte=timezone.now(),
        ended_at__isnull=True,
    ).exists():
        raise Http404("Attendance session not found.")
