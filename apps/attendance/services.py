from datetime import datetime

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import models, transaction
from django.shortcuts import get_object_or_404
from django.utils import timezone

from apps.audit.services import log_activity

from .models import (
    AttendanceCorrection,
    AttendanceRequest,
    AttendanceSession,
    GuardAssignment,
)
from .permissions import (
    require_admin,
    require_attendance_corrector,
    require_attendance_reviewer,
)
from .selectors import current_assignments, last_closed_assignment_end


def _lock_requester(actor):
    if not actor.is_authenticated:
        raise PermissionDenied("Authentication is required.")
    employee = get_object_or_404(
        get_user_model().objects.select_for_update(),
        pk=actor.pk,
    )
    if not employee.is_active or employee.role not in {"EMPLOYEE", "GUARD", "ADMIN"}:
        raise PermissionDenied("An active business role is required.")
    return employee


def _validate_attendance_at(attendance_at, submitted_at):
    if (
        not isinstance(attendance_at, datetime)
        or timezone.is_naive(attendance_at)
        or timezone.is_naive(submitted_at)
    ):
        raise ValidationError("Attendance time must include a timezone.")
    if attendance_at > submitted_at or attendance_at > timezone.now():
        raise ValidationError("Attendance time cannot be in the future.")
    if attendance_at < submitted_at - settings.ATTENDANCE_BACKDATE_LIMIT:
        raise ValidationError("Attendance time is outside the allowed backdating window.")


def _ensure_no_pending_request(employee, request_type):
    if AttendanceRequest.objects.filter(
        employee=employee,
        request_type=request_type,
        status=AttendanceRequest.Status.PENDING,
    ).exists():
        raise ValidationError(f"A pending {request_type.lower().replace('_', '-')} request already exists.")


def _active_session_for_update(employee):
    return AttendanceSession.objects.select_for_update().filter(
        employee=employee,
        check_out_at__isnull=True,
    ).first()


def _ensure_check_in_is_valid(employee, attendance_at):
    if _active_session_for_update(employee) is not None:
        raise ValidationError("The employee already has an active attendance session.")
    previous = AttendanceSession.objects.select_for_update().filter(
        employee=employee,
        check_out_at__isnull=False,
    ).order_by("-check_out_at").first()
    if previous and attendance_at < previous.check_out_at:
        raise ValidationError("Check-in cannot be before the previous session's check-out.")


def _log_request_submission(attendance_request, actor, ip_address=None):
    log_activity(
        action="ATTENDANCE_REQUEST_SUBMITTED",
        actor=actor,
        target_employee=attendance_request.employee,
        target=attendance_request,
        details={
            "request_id": attendance_request.pk,
            "request_type": attendance_request.request_type,
            "attendance_at": attendance_request.attendance_at.isoformat(),
            "requested_at": attendance_request.requested_at.isoformat(),
            "auto_approved": attendance_request.employee.role == "ADMIN",
        },
        ip_address=ip_address,
    )


def _apply_approved_attendance(
    attendance_request,
    employee,
    audit_actor,
    ip_address=None,
):
    if attendance_request.request_type == AttendanceRequest.RequestType.CHECK_IN:
        _ensure_check_in_is_valid(employee, attendance_request.attendance_at)
        session = AttendanceSession.objects.create(
            employee=employee,
            check_in_at=attendance_request.attendance_at,
        )
        attendance_request.session = session
        log_activity(
            action="ATTENDANCE_SESSION_CREATED",
            actor=audit_actor,
            target_employee=employee,
            target=session,
            details={
                "request_id": attendance_request.pk,
                "session_id": session.pk,
                "check_in_at": session.check_in_at.isoformat(),
            },
            ip_address=ip_address,
        )
        return session

    session = get_object_or_404(
        AttendanceSession.objects.select_for_update(),
        pk=attendance_request.session_id,
        employee=employee,
    )
    if session.check_out_at is not None:
        raise ValidationError("This attendance session is already complete.")
    if attendance_request.attendance_at <= session.check_in_at:
        raise ValidationError("Check-out must be later than check-in.")
    session.check_out_at = attendance_request.attendance_at
    session.save(update_fields=["check_out_at", "updated_at"])
    log_activity(
        action="ATTENDANCE_SESSION_COMPLETED",
        actor=audit_actor,
        target_employee=employee,
        target=session,
        details={
            "request_id": attendance_request.pk,
            "session_id": session.pk,
            "check_in_at": session.check_in_at.isoformat(),
            "check_out_at": session.check_out_at.isoformat(),
        },
        ip_address=ip_address,
    )
    return session


def _approve_locked_request(
    attendance_request,
    employee,
    *,
    reviewer,
    audit_actor,
    auto_approved,
    ip_address=None,
):
    if attendance_request.status != AttendanceRequest.Status.PENDING:
        raise ValidationError("This attendance request has already been reviewed.")
    if not employee.is_active:
        raise ValidationError("Attendance requests for inactive users cannot be approved.")
    _validate_attendance_at(
        attendance_request.attendance_at,
        attendance_request.requested_at,
    )
    session = _apply_approved_attendance(
        attendance_request,
        employee,
        audit_actor,
        ip_address,
    )
    attendance_request.status = AttendanceRequest.Status.APPROVED
    attendance_request.reviewed_by = reviewer
    attendance_request.reviewed_at = timezone.now()
    attendance_request.rejection_reason = ""
    attendance_request.auto_approved = auto_approved
    attendance_request.session = session
    attendance_request.save(
        update_fields=[
            "status",
            "reviewed_by",
            "reviewed_at",
            "rejection_reason",
            "auto_approved",
            "session",
            "updated_at",
        ]
    )
    log_activity(
        action="ATTENDANCE_REQUEST_APPROVED",
        actor=audit_actor,
        target_employee=employee,
        target=attendance_request,
        details={
            "request_id": attendance_request.pk,
            "request_type": attendance_request.request_type,
            "session_id": session.pk,
            "attendance_at": attendance_request.attendance_at.isoformat(),
            "auto_approved": auto_approved,
        },
        ip_address=ip_address,
    )
    return attendance_request


def _lock_request_for_review(request_id, reviewer):
    if not reviewer.is_authenticated:
        raise PermissionDenied("Authentication is required.")
    reference = get_object_or_404(
        AttendanceRequest.objects.only("employee_id"),
        pk=request_id,
    )
    employee = get_object_or_404(
        get_user_model().objects.select_for_update(),
        pk=reference.employee_id,
    )
    attendance_request = get_object_or_404(
        AttendanceRequest.objects.select_for_update(),
        pk=request_id,
        employee_id=employee.pk,
    )
    if attendance_request.status != AttendanceRequest.Status.PENDING:
        raise ValidationError("This attendance request has already been reviewed.")
    locked_reviewer = get_object_or_404(
        get_user_model().objects.select_for_update(),
        pk=reviewer.pk,
    )
    require_attendance_reviewer(locked_reviewer, employee)
    return attendance_request, employee, locked_reviewer


def _validate_correction_input(new_value, reason):
    if not isinstance(new_value, datetime) or timezone.is_naive(new_value):
        raise ValidationError("The corrected time must include a timezone.")
    if new_value > timezone.now():
        raise ValidationError("The corrected time cannot be in the future.")
    if not isinstance(reason, str) or len(reason.strip()) < 3:
        raise ValidationError("A meaningful correction reason is required.")
    return reason.strip()


def _lock_session_for_correction(session_id, actor):
    if not actor.is_authenticated:
        raise PermissionDenied("Authentication is required.")
    reference = get_object_or_404(
        AttendanceSession.objects.only("employee_id"),
        pk=session_id,
    )
    employee = get_object_or_404(
        get_user_model().objects.select_for_update(),
        pk=reference.employee_id,
    )
    session = get_object_or_404(
        AttendanceSession.objects.select_for_update(),
        pk=session_id,
        employee_id=employee.pk,
    )
    corrector = get_object_or_404(
        get_user_model().objects.select_for_update(),
        pk=actor.pk,
    )
    require_attendance_corrector(corrector, employee)
    if session.check_out_at is not None and session.check_out_at <= session.check_in_at:
        raise ValidationError("The attendance session has invalid timestamps.")
    if (
        corrector.role == "GUARD"
        and timezone.now() > session.check_in_at + settings.ATTENDANCE_GUARD_CORRECTION_LIMIT
    ):
        raise PermissionDenied("Guards can correct sessions up to 14 days after check-in.")
    return session, employee, corrector


def _ensure_no_session_overlap(session, check_in_at, check_out_at):
    overlapping = AttendanceSession.objects.select_for_update().filter(
        employee_id=session.employee_id,
    ).exclude(pk=session.pk).filter(
        models.Q(check_out_at__isnull=True) | models.Q(check_out_at__gt=check_in_at)
    )
    if check_out_at is not None:
        overlapping = overlapping.filter(check_in_at__lt=check_out_at)
    if overlapping.exists():
        raise ValidationError("The corrected attendance session would overlap another session.")


@transaction.atomic
def assign_guard(
    *,
    actor,
    employee_id,
    guard_id,
    expected_assignment_id,
    ip_address=None,
):
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
        target=assignment,
        details={
            "assignment_id": assignment.pk, "guard_id": guard.pk,
            "started_at": now.isoformat(),
            "previous_assignment_id": current.pk if current else None,
            "previous_guard_id": current.guard_id if current else None,
        },
        ip_address=ip_address,
    )
    return assignment


@transaction.atomic
def end_assignment(*, actor, employee_id, assignment_id, ip_address=None):
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
        target=assignment,
        details={"assignment_id": assignment.pk, "guard_id": assignment.guard_id, "ended_at": now.isoformat()},
        ip_address=ip_address,
    )
    return assignment


@transaction.atomic
def submit_check_in_request(*, actor, attendance_at, ip_address=None):
    employee = _lock_requester(actor)
    submitted_at = timezone.now()
    _validate_attendance_at(attendance_at, submitted_at)
    _ensure_no_pending_request(employee, AttendanceRequest.RequestType.CHECK_IN)
    _ensure_check_in_is_valid(employee, attendance_at)

    attendance_request = AttendanceRequest.objects.create(
        employee=employee,
        request_type=AttendanceRequest.RequestType.CHECK_IN,
        attendance_at=attendance_at,
        requested_at=submitted_at,
    )
    _log_request_submission(attendance_request, employee, ip_address)
    if employee.role == "ADMIN":
        _approve_locked_request(
            attendance_request,
            employee,
            reviewer=None,
            audit_actor=employee,
            auto_approved=True,
            ip_address=ip_address,
        )
    return attendance_request


@transaction.atomic
def submit_check_out_request(*, actor, attendance_at, ip_address=None):
    employee = _lock_requester(actor)
    submitted_at = timezone.now()
    _validate_attendance_at(attendance_at, submitted_at)
    _ensure_no_pending_request(employee, AttendanceRequest.RequestType.CHECK_OUT)
    if AttendanceRequest.objects.filter(
        employee=employee,
        request_type=AttendanceRequest.RequestType.CHECK_IN,
        status=AttendanceRequest.Status.PENDING,
    ).exists():
        raise ValidationError("Check-out cannot be requested while check-in is pending.")

    session = _active_session_for_update(employee)
    if session is None:
        raise ValidationError("An active attendance session is required for check-out.")
    if attendance_at <= session.check_in_at:
        raise ValidationError("Check-out must be later than check-in.")

    attendance_request = AttendanceRequest.objects.create(
        employee=employee,
        request_type=AttendanceRequest.RequestType.CHECK_OUT,
        attendance_at=attendance_at,
        requested_at=submitted_at,
        session=session,
    )
    _log_request_submission(attendance_request, employee, ip_address)
    if employee.role == "ADMIN":
        _approve_locked_request(
            attendance_request,
            employee,
            reviewer=None,
            audit_actor=employee,
            auto_approved=True,
            ip_address=ip_address,
        )
    return attendance_request


@transaction.atomic
def approve_attendance_request(*, reviewer, request_id, ip_address=None):
    attendance_request, employee, locked_reviewer = _lock_request_for_review(
        request_id,
        reviewer,
    )
    return _approve_locked_request(
        attendance_request,
        employee,
        reviewer=locked_reviewer,
        audit_actor=locked_reviewer,
        auto_approved=False,
        ip_address=ip_address,
    )


@transaction.atomic
def reject_attendance_request(*, reviewer, request_id, reason, ip_address=None):
    if not isinstance(reason, str) or not reason.strip():
        raise ValidationError("A rejection reason is required.")
    attendance_request, employee, locked_reviewer = _lock_request_for_review(
        request_id,
        reviewer,
    )
    attendance_request.status = AttendanceRequest.Status.REJECTED
    attendance_request.reviewed_by = locked_reviewer
    attendance_request.reviewed_at = timezone.now()
    attendance_request.rejection_reason = reason.strip()
    attendance_request.auto_approved = False
    attendance_request.save(
        update_fields=[
            "status",
            "reviewed_by",
            "reviewed_at",
            "rejection_reason",
            "auto_approved",
            "updated_at",
        ]
    )
    log_activity(
        action="ATTENDANCE_REQUEST_REJECTED",
        actor=locked_reviewer,
        target_employee=employee,
        target=attendance_request,
        details={
            "request_id": attendance_request.pk,
            "request_type": attendance_request.request_type,
            "attendance_at": attendance_request.attendance_at.isoformat(),
            "reason": attendance_request.rejection_reason,
        },
        ip_address=ip_address,
    )
    return attendance_request


@transaction.atomic
def cancel_attendance_request(*, actor, request_id, ip_address=None):
    employee = _lock_requester(actor)
    attendance_request = get_object_or_404(
        AttendanceRequest.objects.select_for_update(),
        pk=request_id,
        employee_id=employee.pk,
    )
    if attendance_request.status != AttendanceRequest.Status.PENDING:
        raise ValidationError("Only pending attendance requests can be cancelled.")
    attendance_request.status = AttendanceRequest.Status.CANCELLED
    attendance_request.save(update_fields=["status", "updated_at"])
    log_activity(
        action="ATTENDANCE_REQUEST_CANCELLED",
        actor=employee,
        target_employee=employee,
        target=attendance_request,
        details={
            "request_id": attendance_request.pk,
            "request_type": attendance_request.request_type,
            "attendance_at": attendance_request.attendance_at.isoformat(),
        },
        ip_address=ip_address,
    )
    return attendance_request


@transaction.atomic
def correct_attendance_session(
    *,
    actor,
    session_id,
    corrected_field,
    new_value,
    reason,
    ip_address=None,
):
    reason = _validate_correction_input(new_value, reason)
    session, employee, corrector = _lock_session_for_correction(session_id, actor)
    if corrected_field not in AttendanceCorrection.CorrectedField.values:
        raise ValidationError("Select a valid attendance field to correct.")

    if corrected_field == AttendanceCorrection.CorrectedField.CHECK_IN_AT:
        previous_value = session.check_in_at
        check_in_at = new_value
        check_out_at = session.check_out_at
        if check_out_at is not None and check_out_at <= check_in_at:
            raise ValidationError("Check-out must remain later than check-in.")
        session.check_in_at = new_value
        update_fields = ["check_in_at", "updated_at"]
    else:
        if session.check_out_at is None:
            raise ValidationError(
                "Use the explicit close-session operation for an active session."
            )
        previous_value = session.check_out_at
        check_in_at = session.check_in_at
        check_out_at = new_value
        if check_out_at <= check_in_at:
            raise ValidationError("Check-out must remain later than check-in.")
        session.check_out_at = new_value
        update_fields = ["check_out_at", "updated_at"]

    if previous_value == new_value:
        raise ValidationError("The corrected time must differ from the current value.")
    _ensure_no_session_overlap(session, check_in_at, check_out_at)
    correction = AttendanceCorrection.objects.create(
        session=session,
        corrected_by=corrector,
        corrected_field=corrected_field,
        previous_value=previous_value,
        new_value=new_value,
        reason=reason,
    )
    session.save(update_fields=update_fields)
    log_activity(
        action="ATTENDANCE_SESSION_CORRECTED",
        actor=corrector,
        target_employee=employee,
        target=correction,
        details={
            "session_id": session.pk,
            "correction_id": correction.pk,
            "corrected_field": corrected_field,
            "previous_value": previous_value.isoformat(),
            "new_value": new_value.isoformat(),
            "reason": reason,
        },
        ip_address=ip_address,
    )
    return correction


@transaction.atomic
def close_attendance_session(
    *,
    actor,
    session_id,
    check_out_at,
    reason,
    ip_address=None,
):
    reason = _validate_correction_input(check_out_at, reason)
    session, employee, corrector = _lock_session_for_correction(session_id, actor)
    if session.check_out_at is not None:
        raise ValidationError("This attendance session is already complete.")
    if AttendanceRequest.objects.select_for_update().filter(
        session=session,
        request_type=AttendanceRequest.RequestType.CHECK_OUT,
        status=AttendanceRequest.Status.PENDING,
    ).exists():
        raise ValidationError("Resolve the pending check-out request before closing the session.")
    if check_out_at <= session.check_in_at:
        raise ValidationError("Check-out must be later than check-in.")
    _ensure_no_session_overlap(session, session.check_in_at, check_out_at)

    correction = AttendanceCorrection.objects.create(
        session=session,
        corrected_by=corrector,
        corrected_field=AttendanceCorrection.CorrectedField.CHECK_OUT_AT,
        previous_value=None,
        new_value=check_out_at,
        reason=reason,
    )
    session.check_out_at = check_out_at
    session.save(update_fields=["check_out_at", "updated_at"])
    details = {
        "session_id": session.pk,
        "correction_id": correction.pk,
        "previous_value": None,
        "new_value": check_out_at.isoformat(),
        "reason": reason,
        "forgotten_check_out": True,
    }
    log_activity(
        action="ATTENDANCE_SESSION_CORRECTED",
        actor=corrector,
        target_employee=employee,
        target=correction,
        details={**details, "corrected_field": "CHECK_OUT_AT"},
        ip_address=ip_address,
    )
    log_activity(
        action="ATTENDANCE_SESSION_COMPLETED",
        actor=corrector,
        target_employee=employee,
        target=session,
        details=details,
        ip_address=ip_address,
    )
    return correction
