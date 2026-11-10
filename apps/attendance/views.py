from datetime import datetime, time, timedelta

from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.views import View

from apps.audit.selectors import audit_history
from config.security import get_client_ip

from .forms import (
    AttendanceTimestampForm,
    AuditFilterForm,
    CloseSessionForm,
    CorrectionForm,
    DateRangeForm,
    PaginationForm,
    RejectionForm,
    RequestFilterForm,
)
from .permissions import AdminRequiredMixin, RoleRequiredMixin
from .selectors import (
    active_session_for,
    admin_dashboard_counts,
    attendance_overview,
    attendance_sessions_in_range,
    completed_working_time,
    current_guard_assignments,
    employee_for_user,
    employees_visible_to,
    global_request_history,
    guard_assignment_history,
    pending_requests_for_admin,
    pending_requests_for_employee,
    pending_requests_for_guard,
    recent_attendance_activity,
    rejected_requests_for_employee,
    request_history_for_employee,
)
from .services import (
    approve_attendance_request,
    cancel_attendance_request,
    close_attendance_session,
    correct_attendance_session,
    reject_attendance_request,
    submit_check_in_request,
    submit_check_out_request,
)


def form_error_response(form):
    return JsonResponse(
        {"errors": {field: [str(error) for error in errors] for field, errors in form.errors.items()}},
        status=400,
    )


def validation_error_response(error):
    return JsonResponse({"errors": error.messages}, status=400)


def date_bounds(cleaned_data):
    zone = timezone.get_current_timezone()
    start_at = timezone.make_aware(
        datetime.combine(cleaned_data["start_date"], time.min),
        zone,
    )
    end_at = timezone.make_aware(
        datetime.combine(cleaned_data["end_date"] + timedelta(days=1), time.min),
        zone,
    )
    return start_at, end_at


def session_data(session):
    return {
        "id": session.pk,
        "employee_id": session.employee_id,
        "employee_username": session.employee.username,
        "check_in_at": session.check_in_at.isoformat(),
        "check_out_at": session.check_out_at.isoformat() if session.check_out_at else None,
    }


def request_data(attendance_request):
    return {
        "id": attendance_request.pk,
        "employee_id": attendance_request.employee_id,
        "employee_username": attendance_request.employee.username,
        "request_type": attendance_request.request_type,
        "attendance_at": attendance_request.attendance_at.isoformat(),
        "requested_at": attendance_request.requested_at.isoformat(),
        "status": attendance_request.status,
        "reviewed_by_id": attendance_request.reviewed_by_id,
        "reviewed_at": (
            attendance_request.reviewed_at.isoformat()
            if attendance_request.reviewed_at
            else None
        ),
        "rejection_reason": attendance_request.rejection_reason,
        "session_id": attendance_request.session_id,
        "auto_approved": attendance_request.auto_approved,
    }


def paginated_data(page):
    return {
        "page": page.number,
        "pages": page.paginator.num_pages,
        "page_size": page.paginator.per_page,
        "total": page.paginator.count,
    }


def overview_data(row):
    return {
        "employee_id": row["employee_id"],
        "employee_username": row["employee__username"],
        "session_count": row["session_count"],
        "total_working_seconds": row["total_working_time"].total_seconds(),
    }


def assignment_data(assignment):
    return {
        "id": assignment.pk,
        "employee_id": assignment.employee_id,
        "employee_username": assignment.employee.username,
        "guard_id": assignment.guard_id,
        "guard_username": assignment.guard.username,
        "started_at": assignment.started_at.isoformat(),
        "ended_at": assignment.ended_at.isoformat() if assignment.ended_at else None,
    }


def correction_data(correction):
    return {
        "id": correction.pk,
        "session_id": correction.session_id,
        "corrected_by_id": correction.corrected_by_id,
        "corrected_field": correction.corrected_field,
        "previous_value": (
            correction.previous_value.isoformat() if correction.previous_value else None
        ),
        "new_value": correction.new_value.isoformat(),
        "reason": correction.reason,
        "created_at": correction.created_at.isoformat(),
    }


def audit_data(log):
    return {
        "id": log.pk,
        "created_at": log.created_at.isoformat(),
        "actor_id": log.actor_id,
        "target_employee_id": log.target_employee_id,
        "target_type": log.target_type,
        "target_id": log.target_id,
        "action": log.action,
        "details": log.details,
        "ip_address": log.ip_address,
    }


class EmployeeDashboardView(RoleRequiredMixin, View):
    def get(self, request):
        form = DateRangeForm(request.GET)
        if not form.is_valid():
            return form_error_response(form)
        start_at, end_at = date_bounds(form.cleaned_data)
        today_data = dict(form.cleaned_data)
        today_data["start_date"] = timezone.localdate()
        today_data["end_date"] = timezone.localdate()
        today_start, today_end = date_bounds(today_data)
        history = attendance_sessions_in_range(
            start_at=start_at,
            end_at=end_at,
            employee_id=request.user.pk,
            sort=form.cleaned_data["sort"],
        )
        page = Paginator(history, form.cleaned_data["page_size"]).get_page(
            form.cleaned_data["page"]
        )
        active = active_session_for(request.user.pk)
        return JsonResponse(
            {
                "active_session": session_data(active) if active else None,
                "today": [
                    session_data(session)
                    for session in attendance_sessions_in_range(
                        start_at=today_start,
                        end_at=today_end,
                        employee_id=request.user.pk,
                    )
                ],
                "history": [session_data(session) for session in page.object_list],
                "pagination": paginated_data(page),
                "pending_requests": [
                    request_data(item)
                    for item in pending_requests_for_employee(request.user.pk)
                ],
                "rejected_requests": [
                    request_data(item)
                    for item in rejected_requests_for_employee(request.user.pk)[:25]
                ],
                "total_working_seconds": completed_working_time(
                    start_at=start_at,
                    end_at=end_at,
                    employee_id=request.user.pk,
                ).total_seconds(),
            }
        )


class GuardDashboardView(RoleRequiredMixin, View):
    allowed_roles = ("GUARD",)

    def get(self, request):
        form = DateRangeForm(request.GET)
        if not form.is_valid():
            return form_error_response(form)
        start_at, end_at = date_bounds(form.cleaned_data)
        assignments = list(current_guard_assignments(request.user.pk))
        employee_ids = [assignment.employee_id for assignment in assignments]
        return JsonResponse(
            {
                "assigned_employees": [
                    {
                        "id": assignment.employee_id,
                        "username": assignment.employee.username,
                        "assignment_id": assignment.pk,
                        "started_at": assignment.started_at.isoformat(),
                    }
                    for assignment in assignments
                ],
                "pending_requests": [
                    request_data(item) for item in pending_requests_for_guard(request.user)
                ],
                "attendance_overview": [
                    overview_data(row)
                    for row in attendance_overview(
                        start_at=start_at,
                        end_at=end_at,
                        employee_ids=employee_ids,
                    )
                ],
            }
        )


class AdminDashboardView(AdminRequiredMixin, View):
    def get(self, request):
        form = DateRangeForm(request.GET)
        if not form.is_valid():
            return form_error_response(form)
        start_at, end_at = date_bounds(form.cleaned_data)
        overview = Paginator(
            attendance_overview(start_at=start_at, end_at=end_at),
            form.cleaned_data["page_size"],
        ).get_page(form.cleaned_data["page"])
        return JsonResponse(
            {
                "counts": admin_dashboard_counts(),
                "pending_requests": [
                    request_data(item) for item in pending_requests_for_admin(request.user)[:25]
                ],
                "recent_activity": [
                    request_data(item) for item in recent_attendance_activity()
                ],
                "attendance_overview": [
                    overview_data(row) for row in overview.object_list
                ],
                "pagination": paginated_data(overview),
            }
        )


class AttendanceReportView(RoleRequiredMixin, View):
    def get(self, request):
        form = DateRangeForm(request.GET)
        if not form.is_valid():
            return form_error_response(form)
        start_at, end_at = date_bounds(form.cleaned_data)
        requested_employee_id = form.cleaned_data.get("employee_id")
        employee_id = None
        employee_ids = None
        if requested_employee_id is not None:
            employee_id = employee_for_user(request.user, requested_employee_id).pk
        elif request.user.role == "EMPLOYEE":
            employee_id = request.user.pk
        elif request.user.role == "GUARD":
            employee_ids = employees_visible_to(request.user).values_list("pk", flat=True)
        sessions = attendance_sessions_in_range(
            start_at=start_at,
            end_at=end_at,
            employee_id=employee_id,
            employee_ids=employee_ids,
            sort=form.cleaned_data["sort"],
        )
        page = Paginator(sessions, form.cleaned_data["page_size"]).get_page(
            form.cleaned_data["page"]
        )
        return JsonResponse(
            {
                "sessions": [session_data(session) for session in page.object_list],
                "pagination": paginated_data(page),
                "total_working_seconds": completed_working_time(
                    start_at=start_at,
                    end_at=end_at,
                    employee_id=employee_id,
                    employee_ids=employee_ids,
                ).total_seconds(),
            }
        )


class OwnAttendanceHistoryView(RoleRequiredMixin, View):
    def get(self, request):
        form = DateRangeForm(request.GET)
        if not form.is_valid():
            return form_error_response(form)
        start_at, end_at = date_bounds(form.cleaned_data)
        sessions = attendance_sessions_in_range(
            start_at=start_at,
            end_at=end_at,
            employee_id=request.user.pk,
            sort=form.cleaned_data["sort"],
        )
        page = Paginator(sessions, form.cleaned_data["page_size"]).get_page(
            form.cleaned_data["page"]
        )
        return JsonResponse(
            {
                "sessions": [session_data(session) for session in page.object_list],
                "pagination": paginated_data(page),
                "total_working_seconds": completed_working_time(
                    start_at=start_at,
                    end_at=end_at,
                    employee_id=request.user.pk,
                ).total_seconds(),
            }
        )


class CheckInRequestView(RoleRequiredMixin, View):
    def post(self, request):
        form = AttendanceTimestampForm(request.POST)
        if not form.is_valid():
            return form_error_response(form)
        try:
            attendance_request = submit_check_in_request(
                actor=request.user,
                ip_address=get_client_ip(request),
                **form.cleaned_data,
            )
        except ValidationError as error:
            return validation_error_response(error)
        return JsonResponse({"request": request_data(attendance_request)}, status=201)


class CheckOutRequestView(RoleRequiredMixin, View):
    def post(self, request):
        form = AttendanceTimestampForm(request.POST)
        if not form.is_valid():
            return form_error_response(form)
        try:
            attendance_request = submit_check_out_request(
                actor=request.user,
                ip_address=get_client_ip(request),
                **form.cleaned_data,
            )
        except ValidationError as error:
            return validation_error_response(error)
        return JsonResponse({"request": request_data(attendance_request)}, status=201)


class CancelRequestView(RoleRequiredMixin, View):
    def post(self, request, request_id):
        try:
            attendance_request = cancel_attendance_request(
                actor=request.user,
                request_id=request_id,
                ip_address=get_client_ip(request),
            )
        except ValidationError as error:
            return validation_error_response(error)
        return JsonResponse({"request": request_data(attendance_request)})


class OwnRequestHistoryView(RoleRequiredMixin, View):
    def get(self, request):
        form = PaginationForm(request.GET)
        if not form.is_valid():
            return form_error_response(form)
        page = Paginator(
            request_history_for_employee(request.user.pk),
            form.cleaned_data["page_size"],
        ).get_page(form.cleaned_data["page"])
        return JsonResponse(
            {
                "requests": [request_data(item) for item in page.object_list],
                "pagination": paginated_data(page),
            }
        )


class OwnRequestDetailView(RoleRequiredMixin, View):
    def get(self, request, request_id):
        attendance_request = get_object_or_404(
            request_history_for_employee(request.user.pk),
            pk=request_id,
        )
        return JsonResponse({"request": request_data(attendance_request)})


class GuardAssignedEmployeesView(RoleRequiredMixin, View):
    allowed_roles = ("GUARD",)

    def get(self, request):
        return JsonResponse(
            {
                "assignments": [
                    assignment_data(item)
                    for item in current_guard_assignments(request.user.pk)
                ]
            }
        )


class GuardPendingRequestsView(RoleRequiredMixin, View):
    allowed_roles = ("GUARD",)

    def get(self, request):
        return JsonResponse(
            {
                "requests": [
                    request_data(item) for item in pending_requests_for_guard(request.user)
                ]
            }
        )


class ReviewRequestView(RoleRequiredMixin, View):
    allowed_roles = ("GUARD", "ADMIN")

    def post(self, request, request_id):
        try:
            attendance_request = approve_attendance_request(
                reviewer=request.user,
                request_id=request_id,
                ip_address=get_client_ip(request),
            )
        except ValidationError as error:
            return validation_error_response(error)
        return JsonResponse({"request": request_data(attendance_request)})


class RejectRequestView(RoleRequiredMixin, View):
    allowed_roles = ("GUARD", "ADMIN")

    def post(self, request, request_id):
        form = RejectionForm(request.POST)
        if not form.is_valid():
            return form_error_response(form)
        try:
            attendance_request = reject_attendance_request(
                reviewer=request.user,
                request_id=request_id,
                ip_address=get_client_ip(request),
                **form.cleaned_data,
            )
        except ValidationError as error:
            return validation_error_response(error)
        return JsonResponse({"request": request_data(attendance_request)})


class ScopedEmployeeHistoryView(RoleRequiredMixin, View):
    allowed_roles = ("GUARD", "ADMIN")

    def get(self, request, employee_id):
        employee = employee_for_user(request.user, employee_id)
        form = DateRangeForm(request.GET)
        if not form.is_valid():
            return form_error_response(form)
        start_at, end_at = date_bounds(form.cleaned_data)
        sessions = attendance_sessions_in_range(
            start_at=start_at,
            end_at=end_at,
            employee_id=employee.pk,
            sort=form.cleaned_data["sort"],
        )
        page = Paginator(sessions, form.cleaned_data["page_size"]).get_page(
            form.cleaned_data["page"]
        )
        return JsonResponse(
            {
                "employee": {"id": employee.pk, "username": employee.username},
                "sessions": [session_data(item) for item in page.object_list],
                "pagination": paginated_data(page),
                "total_working_seconds": completed_working_time(
                    start_at=start_at,
                    end_at=end_at,
                    employee_id=employee.pk,
                ).total_seconds(),
            }
        )


class CorrectSessionView(RoleRequiredMixin, View):
    allowed_roles = ("GUARD", "ADMIN")

    def post(self, request, session_id):
        form = CorrectionForm(request.POST)
        if not form.is_valid():
            return form_error_response(form)
        try:
            correction = correct_attendance_session(
                actor=request.user,
                session_id=session_id,
                ip_address=get_client_ip(request),
                **form.cleaned_data,
            )
        except ValidationError as error:
            return validation_error_response(error)
        return JsonResponse({"correction": correction_data(correction)})


class CloseSessionView(RoleRequiredMixin, View):
    allowed_roles = ("GUARD", "ADMIN")

    def post(self, request, session_id):
        form = CloseSessionForm(request.POST)
        if not form.is_valid():
            return form_error_response(form)
        try:
            correction = close_attendance_session(
                actor=request.user,
                session_id=session_id,
                ip_address=get_client_ip(request),
                **form.cleaned_data,
            )
        except ValidationError as error:
            return validation_error_response(error)
        return JsonResponse({"correction": correction_data(correction)})


class AdminRequestHistoryView(AdminRequiredMixin, View):
    def get(self, request):
        form = RequestFilterForm(request.GET)
        if not form.is_valid():
            return form_error_response(form)
        requests = global_request_history(
            status=form.cleaned_data.get("status"),
            request_type=form.cleaned_data.get("request_type"),
            employee_id=form.cleaned_data.get("employee_id"),
        )
        page = Paginator(requests, form.cleaned_data["page_size"]).get_page(
            form.cleaned_data["page"]
        )
        return JsonResponse(
            {
                "requests": [request_data(item) for item in page.object_list],
                "pagination": paginated_data(page),
            }
        )


class AdminAssignmentHistoryView(AdminRequiredMixin, View):
    def get(self, request):
        form = RequestFilterForm(request.GET)
        if not form.is_valid():
            return form_error_response(form)
        assignments = guard_assignment_history(
            employee_id=form.cleaned_data.get("employee_id"),
        )
        page = Paginator(assignments, form.cleaned_data["page_size"]).get_page(
            form.cleaned_data["page"]
        )
        return JsonResponse(
            {
                "assignments": [assignment_data(item) for item in page.object_list],
                "pagination": paginated_data(page),
            }
        )


class AdminAuditHistoryView(AdminRequiredMixin, View):
    def get(self, request):
        form = AuditFilterForm(request.GET)
        if not form.is_valid():
            return form_error_response(form)
        cleaned = form.cleaned_data
        zone = timezone.get_current_timezone()
        created_from = (
            timezone.make_aware(datetime.combine(cleaned["start_date"], time.min), zone)
            if cleaned.get("start_date")
            else None
        )
        created_to = (
            timezone.make_aware(
                datetime.combine(cleaned["end_date"] + timedelta(days=1), time.min),
                zone,
            )
            if cleaned.get("end_date")
            else None
        )
        logs = audit_history(
            actor_id=cleaned.get("actor_id"),
            target_employee_id=cleaned.get("target_employee_id"),
            action=cleaned.get("action"),
            target_type=cleaned.get("target_type"),
            target_id=cleaned.get("target_id"),
            created_from=created_from,
            created_to=created_to,
        )
        page = Paginator(logs, cleaned["page_size"]).get_page(cleaned["page"])
        return JsonResponse(
            {
                "audit_logs": [audit_data(item) for item in page.object_list],
                "pagination": paginated_data(page),
            }
        )
